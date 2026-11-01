#!/usr/bin/env python3
"""Reproducible fixed experiment: full-time both-teams-to-score YES.

No team, league, odds interval or cutoff is selected to maximize historical ROI.
Results are simulations at recorded prices, not executed betting returns.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

try:
    from . import binary_metric_math as binary_math
except ImportError:
    import binary_metric_math as binary_math

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/metric_experiments.json"
OUT = ROOT / "data/analysis/btts_yes_backtest.json"
REPORT = ROOT / "NUMEROS_AMBOS_MARCAN.md"
INDEX = ROOT / "METRICAS_PROBADAS.md"


def settle_btts(home, away):
    if not isinstance(home, int) or not isinstance(away, int) or min(home, away) < 0:
        raise ValueError("Completed match needs nonnegative integer scores")
    return int(home > 0 and away > 0)


def analyze_rows(rows, *, bootstrap_iterations=10000):
    return binary_math.analyze_rows(rows, "yes_odds", "no_odds", bootstrap_iterations=bootstrap_iterations)


def write_index():
    lines = ["# Métricas probadas", "", "Se conservan todas las pruebas, incluidos los resultados negativos. Cada fila usa una unidad por partido a su cuota histórica registrada.",
             "", "| Métrica | Partidos | ROI total | Partidos posteriores | ROI posterior | Código |",
             "|---|---:|---:|---:|---:|---|"]
    registry = json.loads(REGISTRY.read_text())
    for spec in registry["experiments"]:
        path = ROOT / spec["result"]
        if not path.exists():
            continue
        result = json.loads(path.read_text())
        full, later = result["full_sample_flat_stakes"], result["later_period_flat_stakes"]
        lines.append(f"| [{spec['label']}]({spec['report']}) | {full['bets']} | {100*full['roi']:.2f}% | {later['bets']} | {100*later['roi']:.2f}% | [{spec['script']}]({spec['script']}) |")
    for spec in registry["experiments"]:
        for check in spec.get("additional_checks", []):
            path = ROOT / check["result"]
            if not path.exists():
                continue
            extra = json.loads(path.read_text())
            full, later = extra["full_sample_flat_stakes"], extra["later_period_flat_stakes"]
            lines.extend(["", f"Comprobación adicional de **{spec['label']}**, {check['source']}: {full['bets']} partidos, ROI total {100*full['roi']:.2f}%; tramo posterior {later['bets']} partidos, ROI {100*later['roi']:.2f}%. [Datos y código]({check['report']}). No se suman las fuentes como partidos independientes."])
    lines.extend(["", "Protocolo: primeros dos tercios cronológicos para ajustar y fechas posteriores para comparar; la fecha de corte nunca se reparte entre ambos grupos. No se optimizan equipos o ligas.",
                  "", "La calibración usa ambas cuotas del mercado y resultados anteriores; sólo selecciona si `p × cuota − 1 > 0`. Una muestra retrospectiva y los precios no verificados como ejecutables no demuestran ganancias futuras.",
                  "", "Cada métrica nueva cuenta como otra hipótesis exploratoria: no se descartan pérdidas ni se declara una estrategia validada por encontrar un resultado positivo entre muchas pruebas.",
                  "", "Registro de protocolos y rutas: `config/metric_experiments.json`. Resultados detallados: `data/analysis/*_backtest.json`."])
    INDEX.write_text("\n".join(lines) + "\n")


def main():
    registry = json.loads(REGISTRY.read_text())
    spec = next(x for x in registry["experiments"] if x["id"] == "btts_yes_v1")
    if spec["market"] != "ft_btts" or spec["selection"] != "yes":
        raise ValueError("This script only evaluates full-time BTTS YES")
    conn = sqlite3.connect(f"file:{ROOT / 'data/processed/free_football_history.sqlite'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("""
      SELECT m.match_row_id,m.match_name,m.league,m.start_time_source,m.ft_home,m.ft_away,
             y.decimal_odds AS yes_odds,n.decimal_odds AS no_odds,m.source_file_id
      FROM sgodds_prices y JOIN sgodds_matches m USING(match_row_id)
      JOIN sgodds_prices n ON n.match_row_id=y.match_row_id AND n.market=y.market AND n.selection='no'
      WHERE y.market=? AND y.selection=? AND m.has_ht_ft_result=1
      ORDER BY m.start_time_source,m.match_row_id
    """, (spec["market"], spec["selection"]))]
    if len({r["match_row_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate match observations")
    paired_quotes = [dict(r) for r in conn.execute("""
      SELECT m.match_row_id,m.match_name,m.start_time_source,y.decimal_odds AS yes_odds,n.decimal_odds AS no_odds
      FROM sgodds_prices y JOIN sgodds_matches m USING(match_row_id)
      JOIN sgodds_prices n ON n.match_row_id=y.match_row_id AND n.market=y.market AND n.selection='no'
      WHERE y.market=? AND y.selection=?
    """, (spec["market"], spec["selection"]))]
    conn.close()
    for r in rows:
        r["win"] = settle_btts(r["ft_home"], r["ft_away"])
    result = analyze_rows(rows)
    best = min(paired_quotes, key=lambda r: 1/r["yes_odds"] + 1/r["no_odds"])
    best_sum = 1/best["yes_odds"] + 1/best["no_odds"]
    result.update({
        "generated_at": datetime.now(timezone.utc).isoformat(), "experiment_id": spec["id"],
        "market": spec["label"], "source": "SGodds / Singapore Pools recorded opening prices",
        "experiment_spec": spec, "shared_protocol": registry["shared_protocol"],
        "registry_sha256": hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
        "selection_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "math_code_sha256": hashlib.sha256((ROOT / "scripts/binary_metric_math.py").read_bytes()).hexdigest(),
        "source_audit_sha256": hashlib.sha256((ROOT / "data/analysis/sgodds_archive_audit.json").read_bytes()).hexdigest(),
        "direct_price_cover": {"paired_rows_including_pending": len(paired_quotes),
                               "inverse_sum_below_one": sum(1/r["yes_odds"] + 1/r["no_odds"] < 1-1e-12 for r in paired_quotes),
                               "best_pair": best, "best_inverse_sum": best_sum,
                               "best_locked_return": 1/best_sum-1,
                               "simultaneity_and_execution_verified": False},
        "limitations": ["Retrospective temporal evaluation, not prospective validation.",
                        "No team, league or odds-band optimization; further experiments increase multiple-testing exposure.",
                        "Quotes labelled opening by source; exact quote timestamps, execution, limits and void-rule equivalence are not verified.",
                        "Date bootstrap uncertainty is conditional on this archive and does not remove regime changes.",
                        "Negative aggregate results do not rule out other selection rules or individual opportunities."],
    })
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    full, later = result["full_sample_flat_stakes"], result["later_period_flat_stakes"]
    selected = result["calibration"]["later_period_selected"]["bets"]
    REPORT.write_text(f"""# Una apuesta: ambos equipos marcan, Sí

**La prueba no mostró una ventaja rentable.**

| Simulación de una unidad por partido | Partidos | Aciertos | Resultado por cada 100 apostados |
|---|---:|---:|---:|
| Muestra completa | {full['bets']} | {full['wins']} ({100*full['hit_rate']:.2f}%) | {100*full['roi']:.2f} |
| Fechas posteriores desde {result['date_cutoff_source']} | {later['bets']} | {later['wins']} ({100*later['hit_rate']:.2f}%) | {100*later['roi']:.2f} |

Importe simulado: {full['staked_units']} unidades. Devuelto: {full['returned_units']:.2f}. Pérdida: {abs(full['profit_units']):.2f}.
Fórmula exacta: `suma(acierto × cuota individual − 1)`; acierto exige que ambos marcadores finales sean mayores que cero.

La calibración ajustada sólo con los partidos anteriores seleccionó **{selected}** apuestas posteriores con `p × cuota − 1 > 0`.
Cobertura de Sí y No: {result['direct_price_cover']['inverse_sum_below_one']} sumas inversas menores que 1 entre {len(paired_quotes)} pares registrados, incluidos pendientes.

Son precios históricos de [SGodds](https://sgodds.com/football/data), no operaciones ejecutadas. No se optimizaron equipos, ligas o rangos de cuota.
La comparación cronológica es retrospectiva; no descarta otras reglas. Se conserva esta prueba negativa junto con la anterior en [METRICAS_PROBADAS.md](METRICAS_PROBADAS.md).

Código: `scripts/analyze_btts_yes.py`; protocolo: `config/metric_experiments.json`.
Datos, predicciones, intervalos por fecha y hashes: `data/analysis/btts_yes_backtest.json`.
Reproducir: `python3 scripts/analyze_btts_yes.py`.
""")
    write_index()
    print(json.dumps({"full": full, "later": later, "calibrated_positive_ev_selections": selected,
                      "direct_arbitrage_rows": result["direct_price_cover"]["inverse_sum_below_one"],
                      "report": str(REPORT), "registry": str(REGISTRY)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
