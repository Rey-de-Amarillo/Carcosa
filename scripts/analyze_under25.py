#!/usr/bin/env python3
"""One fixed football metric: total full-time goals UNDER 2.5 at recorded prices."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

try:
    from . import binary_metric_math as bm
    from .analyze_btts_yes import write_index
except ImportError:
    import binary_metric_math as bm
    from analyze_btts_yes import write_index

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/metric_experiments.json"
OUT = ROOT / "data/analysis/under25_backtest.json"
REPORT = ROOT / "NUMEROS_MENOS_25_GOLES.md"


def settle_under25(home, away):
    if not isinstance(home, int) or not isinstance(away, int) or min(home, away) < 0:
        raise ValueError("Completed match needs nonnegative integer scores")
    return int(home + away <= 2)


def main():
    registry = json.loads(REGISTRY.read_text())
    spec = next(x for x in registry["experiments"] if x["id"] == "under25_v1")
    if (spec["market"], spec["selection"], spec["line"]) != ("ft_goal_total", "under", 2.5):
        raise ValueError("This script only evaluates full-time UNDER 2.5 goals")
    conn = sqlite3.connect(f"file:{ROOT / 'data/processed/free_football_history.sqlite'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    pairs = [dict(r) for r in conn.execute("""
      SELECT m.match_row_id,m.match_name,m.league,m.start_time_source,m.ft_home,m.ft_away,
             m.has_ht_ft_result,m.source_file_id,u.decimal_odds AS under_odds,o.decimal_odds AS over_odds
      FROM sgodds_prices u JOIN sgodds_matches m USING(match_row_id)
      JOIN sgodds_prices o ON o.match_row_id=u.match_row_id AND o.market=u.market
             AND o.selection='over' AND CAST(o.line_source AS REAL)=?
      WHERE u.market=? AND u.selection=? AND CAST(u.line_source AS REAL)=?
      ORDER BY m.start_time_source,m.match_row_id
    """, (spec["line"], spec["market"], spec["selection"], spec["line"]))]
    conn.close()
    if len({r["match_row_id"] for r in pairs}) != len(pairs):
        raise ValueError("Duplicate match observations")
    rows = [dict(r, win=settle_under25(r["ft_home"], r["ft_away"])) for r in pairs if r["has_ht_ft_result"]]
    result = bm.analyze_rows(rows, "under_odds", "over_odds")
    best = min(pairs, key=lambda r: 1/r["under_odds"] + 1/r["over_odds"])
    best_sum = 1/best["under_odds"] + 1/best["over_odds"]
    result.update({
        "generated_at": datetime.now(timezone.utc).isoformat(), "experiment_id": spec["id"],
        "market": spec["label"], "source": "SGodds / Singapore Pools recorded opening prices",
        "experiment_spec": spec, "shared_protocol": registry["shared_protocol"], "registry_snapshot": registry,
        "registry_sha256": hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
        "selection_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "math_code_sha256": hashlib.sha256((ROOT / "scripts/binary_metric_math.py").read_bytes()).hexdigest(),
        "source_audit_sha256": hashlib.sha256((ROOT / "data/analysis/sgodds_archive_audit.json").read_bytes()).hexdigest(),
        "direct_price_cover": {"paired_rows_including_pending": len(pairs),
                               "inverse_sum_below_one": sum(1/r["under_odds"] + 1/r["over_odds"] < 1-1e-12 for r in pairs),
                               "best_pair": best, "best_inverse_sum": best_sum,
                               "best_locked_return": 1/best_sum-1, "simultaneity_and_execution_verified": False},
        "limitations": ["Only games with the recorded principal FT total-goals line of 2.5; not all matches.",
                        "Retrospective temporal evaluation; no team, league or odds-band optimization.",
                        "Each new market is another exploratory hypothesis, not independent prospective validation.",
                        "Recorded opening price timing, executability, limits and void rules are not verified.",
                        "Date bootstrap uncertainty is conditional on the archive and does not remove regime changes.",
                        "The result does not rule out different selection rules or individual opportunities."],
    })
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    full, later = result["full_sample_flat_stakes"], result["later_period_flat_stakes"]
    chosen = result["calibration"]["later_period_selected"]
    verdict = "No se encontró ventaja rentable en esta prueba." if later["roi"] <= 0 and not chosen["bets"] else "Resultado exploratorio: evaluar la muestra posterior y su incertidumbre antes de afirmar una ventaja."
    REPORT.write_text(f"""# Una apuesta: menos de 2,5 goles en el partido

**{verdict}**

| Simulación de una unidad por partido | Partidos | Aciertos | Resultado por cada 100 apostados |
|---|---:|---:|---:|
| Muestra completa | {full['bets']} | {full['wins']} ({100*full['hit_rate']:.2f}%) | {100*full['roi']:.2f} |
| Posteriores desde {result['date_cutoff_source']} | {later['bets']} | {later['wins']} ({100*later['hit_rate']:.2f}%) | {100*later['roi']:.2f} |

Apostado: {full['staked_units']} unidades. Devuelto: {full['returned_units']:.2f}. Resultado neto: {full['profit_units']:.2f}.
Se gana con 0, 1 o 2 goles totales; con 3 o más se pierde. No hay devolución por total entero en la línea 2,5.
Fórmula: `suma(acierto × cuota individual − 1)`.

La calibración ajustada sólo con partidos anteriores seleccionó {chosen['bets']} apuestas posteriores con `p × cuota − 1 > 0`.
Se encontraron {result['direct_price_cover']['inverse_sum_below_one']} coberturas directas con suma inversa menor que 1 entre {len(pairs)} pares Under/Over, incluidos pendientes.

Datos de [SGodds](https://sgodds.com/football/data), sólo cuando la línea principal registrada era 2,5. Son simulaciones a precios históricos, no apuestas ejecutadas.
La comparación cronológica es retrospectiva y no descarta otras estrategias. Se conserva esta prueba junto con las anteriores en [METRICAS_PROBADAS.md](METRICAS_PROBADAS.md).
La misma apuesta se contrasta también con la [base grande de Football-Data](NUMEROS_MENOS_25_BASE_GRANDE.md), por separado y sin sumar partidos como si fueran independientes.

Código: `scripts/analyze_under25.py`. Datos, predicciones, incertidumbre por fecha y hashes: `data/analysis/under25_backtest.json`.
Reproducir: `python3 scripts/analyze_under25.py`.
""")
    write_index()
    print(json.dumps({"full": full, "later": later, "calibrated_positive_ev_selections": chosen["bets"],
                      "direct_arbitrage_rows": result["direct_price_cover"]["inverse_sum_below_one"],
                      "report": str(REPORT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
