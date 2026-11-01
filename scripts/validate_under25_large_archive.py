#!/usr/bin/env python3
"""Additional retrospective check of the same Under 2.5 metric, no subgroup search."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

try:
    from . import binary_metric_math as bm
except ImportError:
    import binary_metric_math as bm

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/club_football_match_data/Matches.csv"
OUT = ROOT / "data/analysis/under25_large_archive_check.json"
REPORT = ROOT / "NUMEROS_MENOS_25_BASE_GRANDE.md"


def numeric(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def summary(rows):
    n = len(rows)
    returned = sum((Decimal(r["under_source"]) for r in rows if r["win"]), Decimal(0))
    profit = returned - n
    check = math.fsum(r["win"] * r["under_odds"] - 1 for r in rows)
    if abs(float(profit) - check) > 1e-8:
        raise ArithmeticError("Decimal and compensated floating-point totals disagree")
    return {"bets": n, "wins": sum(r["win"] for r in rows),
            "hit_rate": sum(r["win"] for r in rows)/n if n else None,
            "staked_units": n, "returned_units": float(returned), "profit_units": float(profit),
            "roi": float(profit/n) if n else None,
            "source_date_min": min((r["start_time_source"] for r in rows), default=None),
            "source_date_max": max((r["start_time_source"] for r in rows), default=None)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-10-30", help="Client-local analysis date, YYYY-MM-DD")
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of)
    excluded = Counter()
    rows, identities, divisions = [], Counter(), Counter()
    with SOURCE.open(newline="", encoding="utf-8-sig") as stream:
        for line, raw in enumerate(csv.DictReader(stream), 2):
            try:
                day = date.fromisoformat(raw["MatchDate"])
            except (ValueError, TypeError):
                excluded["invalid_date"] += 1
                continue
            if day > as_of:
                excluded["future_date"] += 1
                continue
            under, over = numeric(raw["Under25"]), numeric(raw["Over25"])
            if under is None or over is None or min(under, over) <= 1:
                excluded["missing_or_invalid_paired_bet365_odds"] += 1
                continue
            home, away = numeric(raw["FTHome"]), numeric(raw["FTAway"])
            if home is None or away is None or min(home, away) < 0 or not home.is_integer() or not away.is_integer():
                excluded["missing_or_invalid_final_score"] += 1
                continue
            expected = "H" if home > away else "A" if away > home else "D"
            if raw["FTResult"] != expected:
                excluded["inconsistent_or_missing_result_label"] += 1
                continue
            key = (raw["Division"], raw["MatchDate"], raw["HomeTeam"], raw["AwayTeam"])
            identities[key] += 1
            divisions[raw["Division"]] += 1
            rows.append({"match_row_id": line, "start_time_source": raw["MatchDate"],
                         "division": raw["Division"], "home": raw["HomeTeam"], "away": raw["AwayTeam"],
                         "home_score": int(home), "away_score": int(away),
                         "under_odds": under, "over_odds": over, "under_source": raw["Under25"],
                         "win": int(home + away <= 2)})
    duplicate_rows = sum(c-1 for c in identities.values())
    if duplicate_rows:
        raise ValueError("Duplicate included identities require explicit review")
    rows.sort(key=lambda r: (r["start_time_source"], r["match_row_id"]))
    selected_sha = hashlib.sha256()
    for row in rows:
        selected_sha.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode())
        selected_sha.update(b"\n")
    cutoff, train, later = bm.split_by_date(rows)
    alpha = bm.fit_intercept(train, "under_odds", "over_odds")
    selected, evs = [], []
    for row in later:
        p = bm.logistic(math.log(row["over_odds"]/row["under_odds"]) + alpha)
        ev = p*row["under_odds"]-1
        evs.append(ev)
        if ev > 0:
            selected.append(dict(row, calibrated_p=p, estimated_ev=ev))
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "as_of_client_date": args.as_of,
        "metric": "Full-time Under 2.5 goals, fixed flat one-unit stake, paired Bet365 prices",
        "source": {"path": str(SOURCE.relative_to(ROOT)),
                   "url": "https://github.com/xgabora/Club-Football-Match-Data",
                   "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                   "provenance": "Club Football Match Data consolidates Football-Data.co.uk; not independent observations from other archives."},
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "shared_math_sha256": hashlib.sha256((ROOT/"scripts/binary_metric_math.py").read_bytes()).hexdigest(),
        "selection_sha256": selected_sha.hexdigest(), "excluded_rows": dict(excluded),
        "unique_match_identities": len(identities), "duplicate_identity_rows": duplicate_rows,
        "division_counts": dict(divisions), "date_cutoff_source": cutoff,
        "full_sample_flat_stakes": summary(rows), "training_flat_stakes": summary(train),
        "later_period_flat_stakes": summary(later),
        "calibration": {"alpha": alpha, "formula": "logistic(log(over_odds/under_odds)+alpha), alpha fitted only before cutoff",
                        "rule": "p*under_odds-1>0", "later_ev_range": [min(evs), max(evs)],
                        "later_period_selected": summary(selected)},
        "selected_observations": selected,
        "uncertainty": {"bootstrap_performed": False,
                        "reason": "Corroborating descriptive check; no confidence interval or future profitability claim asserted."},
        "limitations": ["Additional retrospective check of the same metric, not an independent prospective validation.",
                        "No league, team, odds band or threshold selected to improve ROI.",
                        "Some matches overlap other collected sources: do not sum these counts as independent observations.",
                        "Exact odds capture times, executable prices, limits, void rules and outcome scope are not independently verified.",
                        "No player predictions, wagers or bot model changes."]}
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n")
    full, last = audit["full_sample_flat_stakes"], audit["later_period_flat_stakes"]
    REPORT.write_text(f"""# Menos de 2,5 goles: comprobación en la base grande

Misma métrica que la prueba SGodds, usando cuotas Bet365 reales registradas en Club Football / Football-Data.

| Muestra | Partidos | Aciertos | ROI simulado |
|---|---:|---:|---:|
| Completa | {full['bets']} | {full['wins']} ({100*full['hit_rate']:.2f}%) | {100*full['roi']:.2f}% |
| Posterior a partir de {cutoff} | {last['bets']} | {last['wins']} ({100*last['hit_rate']:.2f}%) | {100*last['roi']:.2f}% |

Una unidad por partido; beneficio exacto = suma(acierto × cuota individual − 1).
Se apostaron {full['staked_units']} unidades simuladas, se devolvieron {full['returned_units']:.2f}; resultado {full['profit_units']:.2f}.
El calibrador entrenado con fechas anteriores seleccionó {len(selected)} apuestas posteriores con EV estimado positivo.

No se buscaron ligas, equipos ni rangos de cuota ganadores. Esta comprobación es retrospectiva, sin intervalo de confianza calculado aquí.
El archivo se superpone con otras fuentes; sus partidos no deben sumarse como observaciones independientes.
Los precios no están verificados como ofertas ejecutables.

Código reproducible: `python3 scripts/validate_under25_large_archive.py --as-of 2026-10-30`.
Auditoría: `data/analysis/under25_large_archive_check.json` (SHA, filtros, duplicados, fechas y resultados).
""")
    print(json.dumps({"full": full, "later": last, "cutoff": cutoff,
                      "selected": audit["calibration"]["later_period_selected"], "alpha": alpha,
                      "rows_excluded": dict(excluded), "json": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
