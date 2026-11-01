#!/usr/bin/env python3
"""Build a region-controlled descriptive h2h panel from an existing snapshot.

No provider/network requests. Region filtering deliberately precedes cost-board
construction and alias deduplication, so a newer UK/US quote cannot replace the
EU quote of the same exposure in a comparison labelled EU.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.quote_costs import summarize_costs


def _date(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def _quantile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (position - lower)


def build_comparison(sample, *, region="eu", horizon_days=7, source_path="", source_sha256=""):
    """Return the balanced descriptive panel, with all margins in decimals."""
    snapshot_at = _date(sample.get("meta", {}).get("generated_at"))
    if snapshot_at is None:
        raise ValueError("El snapshot requiere generated_at con zona horaria.")
    if isinstance(horizon_days, bool) or not isinstance(horizon_days, int) or horizon_days <= 0:
        raise ValueError("El horizonte debe ser un entero positivo de días.")
    region = str(region).strip().lower()
    if not region:
        raise ValueError("La región de comparación debe ser explícita.")
    fresh_quotes = sample.get("fresh_quotes", [])
    # Must occur before summarize_costs: its alias deduplication intentionally
    # selects the freshest complete board and is allowed to compare regions.
    regional_quotes = [q for q in fresh_quotes if isinstance(q, dict) and q.get("region") == region]
    cutoff = snapshot_at + timedelta(days=horizon_days)
    costs = summarize_costs(regional_quotes)
    all_h2h = [b for b in costs["boards"] if b["market_family"] == "h2h" and b["period"] == "full_game"]
    boards = [b for b in all_h2h if (kickoff := _date(b["commence_time"])) is not None and snapshot_at < kickoff <= cutoff]
    by_sport = defaultdict(list)
    for board in boards:
        by_sport[board["sport"]].append(board)
    common_books = set.intersection(*[{b["bookmaker"] for b in sample_boards} for sample_boards in by_sport.values()]) if by_sport else set()
    rows, by_bookmaker = [], defaultdict(list)
    for sport, sample_boards in sorted(by_sport.items()):
        common_events = set.intersection(*[{b["event_id"] for b in sample_boards if b["bookmaker"] == book} for book in common_books]) if common_books else set()
        panel = [b for b in sample_boards if b["bookmaker"] in common_books and b["event_id"] in common_events]
        if not panel:
            continue
        if len(panel) != len(common_events) * len(common_books):
            raise ValueError("Un evento contiene más de un contrato h2h por marca; no se construye un panel ambiguo.")
        if {b["region"] for b in panel} != {region}:
            raise ValueError("El panel no conserva una región única.")
        margins = [b["overround"] for b in panel]
        per_book = []
        for book in sorted(common_books):
            book_margins = [b["overround"] for b in panel if b["bookmaker"] == book]
            metric = {"bookmaker": book, "sport": sport, "event_count": len(book_margins),
                      "median_overround": median(book_margins),
                      "min_overround": min(book_margins), "max_overround": max(book_margins)}
            per_book.append(metric)
            by_bookmaker[book].append(metric)
        ages = [b["quote_age_seconds"] for b in panel if b["quote_age_seconds"] is not None]
        rows.append({"sport": sport, "sport_keys": sorted({b["sport_key"] for b in panel}),
                     "comparison_region": region,
                     "event_count": len(common_events), "board_count": len(panel), "bookmaker_count": len(common_books),
                     "median_overround": median(margins), "p25_overround": _quantile(margins, .25),
                     "p75_overround": _quantile(margins, .75),
                     "min_overround": min(margins), "max_overround": max(margins), "range": [min(margins), max(margins)],
                     "median_loss_proxy": median(b["proportional_loss_proxy"] for b in panel),
                     "median_across_book_medians": median(b["median_overround"] for b in per_book),
                     "restriction_horizon_days": horizon_days,
                     "observed_kickoff_start": min(b["commence_time"] for b in panel),
                     "observed_kickoff_end": max(b["commence_time"] for b in panel),
                     "observed_quote_age_max_seconds": max(ages) if ages else None,
                     "regions_observed": sorted({b["region"] for b in panel}),
                     "verified_rules_all": all(b["verified_rules"] for b in panel), "per_book": per_book})
    return {
        "schema_version": 2, "snapshot_generated_at": snapshot_at.isoformat(),
        "source_path": source_path, "source_sha256": source_sha256,
        "comparison_region": region, "region_filter_applied_before_costs_and_dedup": True,
        "input_fresh_quote_count": len(fresh_quotes), "region_filtered_quote_count": len(regional_quotes),
        "excluded_noncomparison_region_quote_count": len(fresh_quotes) - len(regional_quotes),
        "all_h2h_full_game_board_count": len(all_h2h), "horizon_h2h_full_game_board_count": len(boards),
        "restriction_horizon_days": horizon_days,
        "restriction_horizon": {"start_exclusive": snapshot_at.isoformat(), "end_inclusive": cutoff.isoformat()},
        "bookmakers": sorted(common_books), "bookmaker_count": len(common_books), "rows": rows,
        "by_bookmaker": [{"bookmaker": book, "rows": metrics} for book, metrics in sorted(by_bookmaker.items())],
        "methodology": [
            "Utiliza fresh_quotes del snapshot, sin consultas adicionales.",
            f"Filtra las filas RAW por region == '{region}' ANTES de summarize_costs y de deduplicar aliases/capturas. Una cuota más reciente de otra región no puede sustituir la región comparada.",
            "Incluye únicamente h2h de partido completo, boards completos, sin exchange/DFS. Fútbol requiere home/draw/away; otros contratos de dos o tres resultados preservan su identidad.",
            f"Limita kickoff a los próximos {horizon_days} días desde generated_at; excluye eventos ya iniciados y fechas desconocidas.",
            "Elige la intersección de marcas disponibles en todos los deportes retenidos dentro del horizonte y de la región comparada.",
            "Dentro de cada deporte conserva únicamente eventos con las mismas marcas. Cada evento aporta exactamente un board por marca; no se rellenan cuotas faltantes.",
            "No busca eventos comunes entre deportes: sus eventos son distintos. Compara una muestra de la misma familia comercial bajo controles de composición.",
            "Mediana, P25/P75 y rango se calculan sobre los boards del panel. Se proporcionan también medianas por marca y mediana de esas medianas.",
            "Overround = suma de inversas de cuotas menos uno. Valores decimales: 0.05 representa 5%. Loss proxy presupone margen proporcional; no es ROI real.",
        ],
        "limitations": [
            "Comparación descriptiva, no causal; no permite ordenar deportes por rentabilidad ni por EV positivo.",
            "Ganador 90 minutos con empate en fútbol no es el mismo contrato que ganador con OT/shootout en otros deportes; reglas de ticket sin verificar individualmente.",
            "Muestras distintas de eventos, ligas, cercanía al inicio y cantidad de partidos; NHL y tenis tienen pocos eventos.",
            "Las marcas no implican formadores de precios independientes. Existen precios repetidos; los boards no son observaciones independientes de resultados.",
            "Snapshots observados no acreditan disponibilidad, aceptación, simultaneidad de ejecución ni límites.",
            "No incluye historiales financieros NBA/MLB ni ROI comparativo entre deportes.",
        ],
        "executable": False, "research_only": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/analysis/football_audit_sample.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/analysis/football_sport_comparison.json")
    parser.add_argument("--region", default="eu")
    parser.add_argument("--horizon-days", type=int, default=7)
    args = parser.parse_args(argv)
    source_bytes = args.input.read_bytes()
    try:
        source_label = str(args.input.resolve().relative_to(ROOT))
    except ValueError:
        source_label = str(args.input)
    report = build_comparison(json.loads(source_bytes), region=args.region, horizon_days=args.horizon_days,
                              source_path=source_label, source_sha256=hashlib.sha256(source_bytes).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "comparison_region": report["comparison_region"],
                      "bookmaker_count": report["bookmaker_count"],
                      "rows": [{k: row[k] for k in ("sport", "event_count", "board_count", "median_overround", "range", "regions_observed")}
                               for row in report["rows"]]}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
