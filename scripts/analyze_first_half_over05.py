#!/usr/bin/env python3
"""One fixed market: recorded first-half over 0.5 goals prices and HT scores.

Retrospective chronological evaluation, not a prospectively registered strategy.
No other market/league/team is searched to select a profitable subgroup.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3

try:
    from . import binary_metric_math as binary_math
except ImportError:
    import binary_metric_math as binary_math

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/analysis/first_half_over05_backtest.json"
REPORT = ROOT / "NUMEROS_PRIMER_TIEMPO.md"


def logistic(x):
    return binary_math.logistic(x)


def fit_intercept(rows):
    return binary_math.fit_intercept(rows, "over_odds", "under_odds")


def summarize(rows):
    return binary_math.summarize(rows, "over_odds")


def main():
    conn = sqlite3.connect(f"file:{ROOT / 'data/processed/free_football_history.sqlite'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("""
      SELECT m.match_row_id,m.match_name,m.league,m.start_time_source,m.ht_home,m.ht_away,
             p.decimal_odds AS over_odds,u.decimal_odds AS under_odds
      FROM sgodds_prices p JOIN sgodds_matches m USING(match_row_id)
      JOIN sgodds_prices u ON u.match_row_id=p.match_row_id AND u.market='ht_goal_total'
             AND u.selection='under' AND CAST(u.line_source AS REAL)=0.5
      WHERE p.market='ht_goal_total' AND p.selection='over' AND CAST(p.line_source AS REAL)=0.5
             AND m.has_ht_ft_result=1
      ORDER BY m.start_time_source,m.match_row_id
    """)]
    conn.close()
    assert len({r["match_row_id"] for r in rows}) == len(rows)
    for r in rows:
        r["win"] = int(r["ht_home"] + r["ht_away"] >= 1)
    selection_sha = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    cutoff, train, test = binary_math.split_by_date(rows)
    assert train[-1]["start_time_source"][:10] < test[0]["start_time_source"][:10]
    alpha = fit_intercept(train)
    # Offset logistic calibration: normalized two-sided prices, fitted only on train.
    # Rule is fixed EV>0; no thresholds, teams, leagues or other markets are optimized.
    for r in rows:
        r["calibrated_p"] = logistic(math.log(r["under_odds"] / r["over_odds"]) + alpha)
        r["estimated_ev"] = r["calibrated_p"] * r["over_odds"] - 1
    selected = [r for r in test if r["estimated_ev"] > 0]
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": "First half over 0.5 goals, SGodds/Singapore Pools recorded opening odds",
        "selection_sha256": selection_sha,
        "sgodds_source_audit_sha256": hashlib.sha256((ROOT / "data/analysis/sgodds_archive_audit.json").read_bytes()).hexdigest(),
        "full_sample_flat_stakes": summarize(rows), "training_flat_stakes": summarize(train),
        "later_period_flat_stakes": summarize(test), "date_cutoff_source": cutoff,
        "calibration": {"formula": "p=logistic(log(under_odds/over_odds)+alpha); alpha fits prior training scores only",
                        "alpha": alpha, "selection_rule": "p*over_odds-1>0",
                        "later_period_selected": summarize(selected),
                        "later_period_ev_range": [min(r["estimated_ev"] for r in test), max(r["estimated_ev"] for r in test)]},
        "limitations": [
            "Only matches whose quoted main HT goals line is 0.5; not all football matches.",
            "Retrospective temporal split; no prospective registration or claim that this is the only possible model.",
            "Exact historical quote timestamps, executability, limits and all void rules are not independently verified.",
            "Date-cluster bootstrap is descriptive conditional on this archive; it does not remove drift or prove future returns.",
            "Negative aggregate performance does not rule out profitable individual selections or other strategies.",
        ], "observations": rows,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    full, later = result["full_sample_flat_stakes"], result["later_period_flat_stakes"]
    REPORT.write_text(f"""# Una apuesta: un gol o más en el primer tiempo

**No se encontró una ventaja rentable en esta prueba.**

| Simulación, una unidad por partido | Partidos | Aciertos | Resultado por cada 100 apostados |
|---|---:|---:|---:|
| Toda la muestra | {full['bets']} | {full['wins']} ({100*full['hit_rate']:.2f}%) | {100*full['roi']:.2f} |
| Período posterior, desde {cutoff} | {later['bets']} | {later['wins']} ({100*later['hit_rate']:.2f}%) | {100*later['roi']:.2f} |

Se usó la cuota registrada de cada partido: `beneficio = suma(acierto × cuota − 1)`.
Son cuotas y marcadores históricos de [SGodds](https://sgodds.com/football/data), sólo cuando su línea principal de primer tiempo era 0,5.
El importe simulado total es {full['staked_units']} unidades y la pérdida es {abs(full['profit_units']):.2f} unidades.

El ajuste de probabilidades con los {len(train)} partidos anteriores no seleccionó ninguna apuesta posterior con valor esperado positivo: {len(selected)} de {len(test)}.
Este modelo sencillo no descarta otras estrategias. La división es retrospectiva y no constituye una validación prospectiva.

Los precios históricos no se verificaron como ofertas ejecutables. No se realizaron apuestas.
Los resultados detallados, incertidumbre por fecha y procedencia están en `data/analysis/first_half_over05_backtest.json`.

Reproducir: `python3 scripts/analyze_first_half_over05.py`.
""")
    print(json.dumps({"full": full, "later": later, "calibrated_positive_ev_selections": len(selected),
                      "report": str(REPORT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
