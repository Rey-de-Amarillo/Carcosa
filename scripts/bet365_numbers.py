#!/usr/bin/env python3
"""Offline fixed-rule football returns at archived, named Bet365 prices.

No downloads, ROI optimization, live quotes or bets. Uses pre-closing prices,
never substitutes closing/average/maximum quotes, and never invents HT prices.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.markets import market_distribution, net_return, settle_score
from engine.models_v2 import score_grid
from engine.report import read_matches
from scripts.research_v2 import predictions

PERIODS = {"selection_2022_2023": ("2022-01-01", "2023-12-31"),
           "previously_seen_audit_2024_plus": ("2024-01-01", "2026-10-30")}
BASELINES = (("home_1x2", "Local 1X2", "h2h", "1x2", "home", 0),
             ("draw_1x2", "Empate 1X2", "h2h", "1x2", "draw", 1),
             ("away_1x2", "Visitante 1X2", "h2h", "1x2", "away", 2),
             ("over25", "Más de 2,5 goles", "totals25", "totals", "over", 0),
             ("under25", "Menos de 2,5 goles", "totals25", "totals", "under", 1),
             ("home_asian", "Local al hándicap asiático B365 de cada partido", "asian_handicap", "asian_handicap", "home", 0))
PROBABILITY_OUTCOMES = ("win", "half_win", "push", "half_loss", "loss")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory():
    headers = collections.Counter()
    files = []
    for path in sorted((ROOT / "data/raw/football").glob("*.csv")):
        if path.name == "fixtures.csv":
            continue
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            columns = next(csv.reader(stream), [])
        headers.update(columns)
        files.append({"file": str(path.relative_to(ROOT)), "sha256": sha(path),
                      "bet365_columns": [name for name in columns if "B365" in name.upper()],
                      "half_time_result_columns": [name for name in columns if name in ("HTHG", "HTAG", "HTR")]})
    b365 = {name: count for name, count in sorted(headers.items()) if "B365" in name.upper()}
    first_half_prices = [name for name in b365 if any(token in name.upper() for token in ("HT", "1H", "FH", "HALF"))]
    return {"historical_csv_files": len(files), "bet365_columns_and_file_counts": b365,
            "first_half_bet365_price_columns": first_half_prices,
            "first_half_bet365_price_count": len(first_half_prices), "files": files,
            "note": "HTHG/HTAG/HTR son resultados del descanso, no cuotas. No hay cuotas de jugador ni primer goleador en estas columnas."}


def binary_distribution(probability):
    return {"win": probability, "half_win": 0., "push": 0., "half_loss": 0., "loss": 1-probability}


def expected_return(probabilities, odds):
    return ((probabilities["win"]+.5*probabilities["half_win"])*(odds-1)
            - probabilities["loss"]-.5*probabilities["half_loss"])


def _logit(probability):
    probability = float(probability)
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("Invalid calibration probability")
    probability = min(1-1e-12, max(1e-12, probability))
    return math.log(probability)-math.log1p(-probability)


def _sigmoid(value):
    if value >= 0:
        return 1/(1+math.exp(-value))
    exp = math.exp(value)
    return exp/(1+exp)


def platt_probability(probability, calibration):
    """Apply an already fitted two-parameter logistic recalibration."""
    return _sigmoid(float(calibration["intercept"])+float(calibration["slope"])*_logit(probability))


def fit_platt(probabilities, outcomes):
    """Minimize binary log loss, with no prices or ROI in the optimization.

    The caller owns the temporal split. Returns a frozen coefficient mapping
    that can be passed directly to platt_probability. No labels are smoothed,
    no hyperparameters selected and no regularization penalty is fitted.
    """
    probabilities, outcomes = list(probabilities), list(outcomes)
    if len(probabilities) != len(outcomes) or len(probabilities) < 3:
        raise ValueError("Invalid calibration sample")
    if any(value not in (0, 1, False, True) for value in outcomes) or len(set(outcomes)) < 2:
        raise ValueError("Calibration needs both binary outcomes")
    xs, ys = [_logit(p) for p in probabilities], [int(y) for y in outcomes]
    n = len(xs)
    if max(xs)-min(xs) < 1e-12:
        # Constant input identifies an intercept, but not two parameters.
        raise ValueError("Calibration inputs have no variation")
    def objective(a, b):
        total = 0.
        for x, y in zip(xs, ys):
            z = a+b*x
            total += max(z, 0)-z*y+math.log1p(math.exp(-abs(z)))
        return total/n
    a, b = 0., 1.
    initial = objective(a, b)
    converged = False
    iterations = 0
    for iterations in range(1, 101):
        g0 = g1 = h00 = h01 = h11 = 0.
        for x, y in zip(xs, ys):
            p = _sigmoid(a+b*x)
            residual, weight = p-y, p*(1-p)
            g0 += residual
            g1 += residual*x
            h00 += weight
            h01 += weight*x
            h11 += weight*x*x
        g0 /= n; g1 /= n; h00 /= n; h01 /= n; h11 /= n
        gradient_max = max(abs(g0), abs(g1))
        if gradient_max < 1e-10:
            converged = True
            break
        determinant = h00*h11-h01*h01
        if determinant <= 1e-18:
            break
        d0, d1 = (h11*g0-h01*g1)/determinant, (h00*g1-h01*g0)/determinant
        before = objective(a, b)
        step = 1.
        while step >= 2**-30:
            proposed = objective(a-step*d0, b-step*d1)
            if proposed <= before-1e-4*step*(g0*d0+g1*d1):
                break
            step *= .5
        if step < 2**-30:
            break
        a, b = a-step*d0, b-step*d1
    final_gradient = [0., 0.]
    for x, y in zip(xs, ys):
        residual = _sigmoid(a+b*x)-y
        final_gradient[0] += residual/n
        final_gradient[1] += residual*x/n
    result = {"intercept": a, "slope": b, "n": n, "converged": converged,
              "iterations": iterations, "gradient_max_abs": max(map(abs, final_gradient)),
              "training_log_loss_before": initial, "training_log_loss_after": objective(a, b),
              "formula": "sigmoid(intercept + slope * logit(raw_probability))",
              "objective": "unregularized_binary_log_loss", "optimizer": "Newton 2x2 with Armijo backtracking",
              "probability_clip_for_logit": 1e-12, "odds_or_roi_used_for_fit": False}
    if result["training_log_loss_after"] > initial+1e-12:
        raise AssertionError("Calibration optimizer increased training loss")
    return result


def wilson(successes, n):
    if not n:
        return {"low": None, "high": None, "method": "Wilson 95%"}
    z = 1.959963984540054
    p = successes/n
    center = (p+z*z/(2*n))/(1+z*z/n)
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return {"low": center-radius, "high": center+radius, "method": "Wilson 95%; no ajusta dependencia temporal"}


def roi_interval(positions, replicates=2000):
    daily = collections.defaultdict(lambda: [0., 0])
    for position in positions:
        daily[position["date"]][0] += position["net_return"]
        daily[position["date"]][1] += 1
    blocks = list(daily.values())
    if len(blocks) < 2:
        return {"low": None, "high": None, "dates": len(blocks), "replicates": 0}
    rng = random.Random(36520261030)
    samples = []
    for _ in range(replicates):
        profit = stake = 0.
        for _ in blocks:
            day_profit, day_n = blocks[rng.randrange(len(blocks))]
            profit += day_profit
            stake += day_n
        samples.append(profit/stake)
    samples.sort()
    def quantile(probability):
        index = probability*(len(samples)-1)
        lo = int(index)
        hi = min(len(samples)-1, lo+1)
        return samples[lo]+(index-lo)*(samples[hi]-samples[lo])
    return {"low": quantile(.025), "high": quantile(.975), "dates": len(blocks),
            "replicates": replicates, "seed": 36520261030,
            "method": "Percentil bootstrap 95% por fecha: remuestreo conjunto de beneficio e importe; 1 unidad por posición",
            "limitation": "Intervalos marginales descriptivos, sin corrección por múltiples filas ni toda dependencia serial; auditoría ya inspeccionada."}


def summarize(positions, identifier, name, period, replicates):
    n = len(positions)
    counts = collections.Counter(p["outcome"] for p in positions)
    profit = sum(p["net_return"] for p in positions)
    distribution = {label: sum(p["probabilities"][label] for p in positions)/n if n else None
                    for label in PROBABILITY_OUTCOMES}
    result = {"id": identifier, "name": name, "period": period,
              "from": min((p["date"] for p in positions), default=None),
              "to": max((p["date"] for p in positions), default=None),
              "n": n, "unique_matches": len({p["id"] for p in positions}),
              "full_wins": counts["win"], "half_wins": counts["half_win"], "pushes": counts["push"],
              "half_losses": counts["half_loss"], "full_losses": counts["loss"],
              "positive_returns": counts["win"]+counts["half_win"],
              "negative_returns": counts["loss"]+counts["half_loss"],
              "observed_hit_rate": (counts["win"]+counts["half_win"])/n if n else None,
              "hit_rate_definition": "Frecuencia de retorno positivo, incluidos medios aciertos; denominador incluye reembolsos.",
              "observed_hit_rate_ci95": wilson(counts["win"]+counts["half_win"], n),
              "mean_decimal_odds": sum(p["odds"] for p in positions)/n if n else None,
              "min_decimal_odds": min((p["odds"] for p in positions), default=None),
              "max_decimal_odds": max((p["odds"] for p in positions), default=None),
              "mean_model_settlement_probabilities": distribution,
              "mean_model_probability_positive_return": (distribution["win"]+distribution["half_win"]) if n else None,
              "mean_model_ev_per_stake": sum(p["model_ev"] for p in positions)/n if n else None,
              "flat_stake_units": n, "historical_net_profit_units": profit,
              "historical_flat_stake_roi": profit/n if n else None,
              "historical_roi_ci95": roi_interval(positions, replicates),
              "historical_roi_after_1pct_decimal_price_haircut": sum(p["net_after_haircut"] for p in positions)/n if n else None,
              "bet365_price_snapshot": "pre", "closing_price_substitutions": 0,
              "source_files": sorted({p["source_file"] for p in positions}),
              "leagues": dict(sorted(collections.Counter(p["league"] for p in positions).items())),
              "line_counts": dict(sorted(collections.Counter(str(p["line"]) for p in positions).items())) if identifier == "home_asian" else None,
              "executed_bets": 0, "executable": False,
              "positions_sha256": hashlib.sha256(json.dumps(positions,sort_keys=True,separators=(",", ":")).encode()).hexdigest()}
    assert sum(counts.values()) == n and result["unique_matches"] == n
    return result


def binary_metrics(cohort, probabilities):
    if len(cohort) != len(probabilities) or not cohort:
        raise ValueError("Invalid paired evaluation cohort")
    losses = []
    squared = []
    correct = 0
    for row, probability in zip(cohort, probabilities):
        probability = min(1-1e-12, max(1e-12, probability))
        y = row["actual_over"]
        losses.append(-math.log(probability if y else 1-probability))
        squared.append((probability-y)**2)
        correct += (probability >= .5) == bool(y)
    return {"n": len(cohort), "log_loss": sum(losses)/len(cohort),
            "binary_brier": sum(squared)/len(cohort), "binary_brier_definition": "mean((p_over-y_over)^2), escala 0–1",
            "classification_accuracy_at_0_5": correct/len(cohort),
            "mean_probability_over": sum(probabilities)/len(probabilities),
            "observed_over_frequency": sum(r["actual_over"] for r in cohort)/len(cohort),
            "cohort_ids_sha256": hashlib.sha256("\n".join(r["id"] for r in cohort).encode()).hexdigest()}


def ou_calibration_experiment(groups, replicates):
    cohorts = {}
    for period in PERIODS:
        overs = groups[(period, "over25")]
        unders = {p["id"]: p for p in groups[(period, "under25")]}
        if set(unders) != {p["id"] for p in overs}:
            raise AssertionError("OU calibration must use the exact paired Bet365 cohort")
        cohorts[period] = [{"id": over["id"], "date": over["date"],
                            "raw_p_over": over["probabilities"]["win"],
                            "actual_over": int(over["outcome"] == "win"),
                            "over": over, "under": unders[over["id"]]} for over in overs]
    train = cohorts["selection_2022_2023"]
    test = cohorts["previously_seen_audit_2024_plus"]
    fit = fit_platt([r["raw_p_over"] for r in train], [r["actual_over"] for r in train])
    if not fit["converged"]:
        raise ValueError("OU calibrator did not converge")
    fit.update({"training_period": "selection_2022_2023", "training_start": min(r["date"] for r in train),
                "training_max_date": max(r["date"] for r in train),
                "coefficients_usable_from": "2024-01-01",
                "training_cohort_sha256": hashlib.sha256(json.dumps([(r["id"], r["raw_p_over"], r["actual_over"]) for r in train],
                                                                        separators=(",", ":")).encode()).hexdigest(),
                "fitted_on_2024_or_later_labels": False})
    assert fit["training_max_date"] < min(r["date"] for r in test)
    frozen = {key: fit[key] for key in ("intercept", "slope", "training_max_date", "training_cohort_sha256")}
    fit["frozen_coefficients_sha256"] = hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    training_metrics = {"raw": binary_metrics(train, [r["raw_p_over"] for r in train]),
                        "platt": binary_metrics(train, [platt_probability(r["raw_p_over"], fit) for r in train]),
                        "in_sample_calibration_fit": True,
                        "roi": None,
                        "note": "Métricas del conjunto usado para ajustar Platt; no son pronósticos calibrados disponibles en cada fecha de 2022–23 ni una simulación financiera causal."}
    probabilities = {"raw": [r["raw_p_over"] for r in test],
                     "platt": [platt_probability(r["raw_p_over"], fit) for r in test],
                     "bet365_proportional_devig_reference": [(1/r["over"]["odds"])/(1/r["over"]["odds"]+1/r["under"]["odds"]) for r in test]}
    evaluation = {key: {"forecast_metrics": binary_metrics(test, values)} for key, values in probabilities.items()}
    selected = {}
    for method in ("raw", "platt"):
        positions = []
        for row, p_over in zip(test, probabilities[method]):
            sides = []
            for side, p_side in (("over", p_over), ("under", 1-p_over)):
                position = dict(row[side])
                position["probabilities"] = binary_distribution(p_side)
                position["model_ev"] = p_side*position["odds"]-1
                if method == "platt":
                    position["calibration_training_max_date"] = fit["training_max_date"]
                    assert fit["training_max_date"] < position["date"]
                sides.append(position)
            chosen = max(sides, key=lambda position: position["model_ev"])
            if chosen["model_ev"] >= .03:
                positions.append(chosen)
        selected[method] = positions
        evaluation[method]["ev3_policy"] = summarize(positions, "ou25_"+method+"_ev3", "OU2,5 · "+method+" · mayor EV si ≥3%",
                                                      "previously_seen_audit_2024_plus", replicates)
        evaluation[method]["ev3_policy"]["selection_side_counts"] = dict(collections.Counter(p["selection"] for p in positions))
        evaluation[method]["profit_units_per_available_match"] = sum(p["net_return"] for p in positions)/len(test)
    evaluation["bet365_proportional_devig_reference"].update({"independent_probability_source": False,
                                                               "note": "Referencia de calibración obtenida de la misma pareja de precios que se evalúa; no constituye ventaja independiente."})
    ids = {method: {(p["id"], p["selection"]) for p in positions} for method, positions in selected.items()}
    common = ids["raw"] & ids["platt"]
    raw_events = {p["id"]: p for p in selected["raw"]}
    calibrated_events = {p["id"]: p for p in selected["platt"]}
    overlap = {"common_selected_contracts": len(common),
               "raw_only_contracts": len(ids["raw"]-ids["platt"]),
               "platt_only_contracts": len(ids["platt"]-ids["raw"]),
               "opposite_sides_same_match": sum(raw_events[rid]["selection"] != calibrated_events[rid]["selection"] for rid in set(raw_events)&set(calibrated_events)),
               "common_contract_roi": sum(p["net_return"] for p in selected["raw"] if (p["id"], p["selection"]) in common)/len(common) if common else None,
               "note": "Las métricas predictivas usan exactamente los mismos partidos. El corte EV fijo produce subconjuntos de apuestas distintos; en contratos comunes precio, importe y ROI coinciden."}
    # Paired comparison on ALL available matches: absent bets are zero P/L.
    # Its denominator is fixtures, not staked units, so it is not labelled ROI.
    difference = [{"date": row["date"], "net_return": calibrated_events.get(row["id"], {}).get("net_return", 0.)-raw_events.get(row["id"], {}).get("net_return", 0.)} for row in test]
    delta_ci = roi_interval(difference, replicates)
    delta_ci["method"] = "Bootstrap por fecha de la diferencia pareada de P/L por partido disponible, con abstención=0; no ROI por importe apostado"
    delta = sum(p["net_return"] for p in difference)/len(test)
    paired_forecast = {}
    for metric in ("log_loss", "binary_brier"):
        improvements = []
        for row, raw, calibrated in zip(test, probabilities["raw"], probabilities["platt"]):
            y = row["actual_over"]
            if metric == "log_loss":
                improvement = -math.log(raw if y else 1-raw)+math.log(calibrated if y else 1-calibrated)
            else:
                improvement = (raw-y)**2-(calibrated-y)**2
            improvements.append({"date": row["date"], "net_return": improvement})
        interval = roi_interval(improvements, replicates)
        interval["method"] = "Bootstrap por fecha de la mejora pareada de pérdida (raw menos calibrado); valor positivo favorece calibrado"
        paired_forecast[metric] = {"mean_improvement": sum(p["net_return"] for p in improvements)/len(test), "ci95": interval}
    result = {"calibrator": fit, "training_fit_metrics": training_metrics,
              "evaluation_period": "previously_seen_audit_2024_plus", "evaluation_start": min(r["date"] for r in test),
              "evaluation_end": max(r["date"] for r in test), "evaluation_available_matches": len(test),
              "evaluation": evaluation, "policy_overlap": overlap,
              "paired_forecast_improvement": paired_forecast,
              "paired_profit_change_units_per_available_match": delta,
              "paired_profit_change_ci95": delta_ci,
              "protocol": ["Ajuste de dos coeficientes Platt con logloss, exclusivamente 2022–23; luego congelados.",
                           "Sin búsqueda de umbrales, ligas o cuotas por ROI. Mismo corte EV≥3%, máximo un lado y 1u por partido en ambos métodos.",
                           "Métricas 2024+ sobre exactamente el mismo universo de partidos elegibles con ambas cuotas B365 pre; no se usa cierre.",
                           "El tramo 2024+ ya había sido inspeccionado y esta hipótesis se propuso después: evaluación cronológica retrospectiva, no confirmación prospectiva independiente.",
                           "El calibrador no cambia el modelo elegido en selected_model_v2.json ni crea una distribución conjunta de marcadores para otros mercados.",
                           "Mejor logloss o Brier no garantiza mejora de ROI. ROI de la política cambia de subconjunto; se informa su solapamiento y P/L pareado por partido disponible."],
              "executed_bets": 0, "executable": False}
    return result


def build(output, replicates=2000):
    raw_inventory = inventory()
    raw_hashes = {entry["file"]: entry["sha256"] for entry in raw_inventory["files"]}
    rows, data_meta = read_matches(ROOT / "data/processed")
    rows = [row for row in rows if row["sport"] == "football"]
    forecast = predictions(rows)
    quotes = {}
    with (ROOT / "data/analysis/quote_history.jsonl").open() as stream:
        for line in stream:
            q = json.loads(line)
            if q["id"] in quotes:
                raise ValueError("Duplicate quote identity")
            if raw_hashes.get(q["source"]["file"]) != q["source"]["sha256"]:
                raise ValueError("Raw quote input changed: rebuild scripts/build_quote_history.py first")
            quotes[q["id"]] = q
    groups = collections.defaultdict(list)
    signals = collections.defaultdict(list)
    coverage = collections.Counter()
    dropped = collections.Counter()
    training_checked = 0
    for row in rows:
        period = next((key for key, (start, end) in PERIODS.items() if start <= row["date"] <= end), None)
        if period is None:
            continue
        q = quotes.get(row["id"])
        if q is None:
            dropped[period+":missing_quote_record"] += 1
            continue
        assert (row["date"], row["home_team"], row["away_team"]) == (q["date"], q["home_team"], q["away_team"])
        for family in ("h2h", "totals25", "asian_handicap"):
            for snapshot in ("pre", "closing"):
                coverage[period+":"+family+":"+snapshot] += "B365" in q[family][snapshot]
        p = forecast.get(row["id"])
        if not p or not p["eligible"]:
            dropped[period+":model_ineligible"] += 1
            continue
        if not p.get("training_max_date") or p["training_max_date"] >= row["date"]:
            raise ValueError("Leaking parameter fit")
        if not p.get("observed_results_max_date") or p["observed_results_max_date"] >= row["date"]:
            raise ValueError("Leaking observed-result history")
        training_checked += 1
        grid = None
        ou_positions = []
        for identifier, name, family, market, selection, side_index in BASELINES:
            price = q[family]["pre"].get("B365")
            if price is None:
                dropped[period+":"+identifier+":missing_bet365_pre"] += 1
                continue
            line = 2.5 if market == "totals" else price["line"] if market == "asian_handicap" else None
            odds = float(price["odds"][side_index] if market == "asian_handicap" else price[side_index])
            if market == "1x2":
                probabilities = binary_distribution(p[selection])
            elif market == "totals":
                probabilities = binary_distribution(p["over25"] if selection == "over" else p["under25"])
            else:
                if grid is None:
                    grid = score_grid(p["home_rate"], p["away_rate"], p["rho_applied"])["grid"]
                probabilities = market_distribution(grid, market, selection, line=line)["probabilities"]
            settled = settle_score(row["home_score"], row["away_score"], market, selection, line=line)
            position = {"id": row["id"], "date": row["date"], "league": row["league"],
                        "market": market, "selection": selection, "line": line, "odds": odds,
                        "outcome": settled["outcome"], "net_return": net_return(settled, odds),
                        "net_after_haircut": net_return(settled, odds*.99),
                        "probabilities": probabilities, "model_ev": expected_return(probabilities, odds),
                        "training_max_date": p["training_max_date"], "source_file": q["source"]["file"]}
            groups[(period, identifier)].append(position)
            if family == "totals25":
                ou_positions.append(position)
        # Fixed before outcomes are inspected: at most one OU2.5 bet per match,
        # choose largest prior-only structural EV, require EV >= 3%; no tuning.
        if ou_positions:
            candidate = max(ou_positions, key=lambda value: value["model_ev"])
            if candidate["model_ev"] >= .03:
                signals[period].append(candidate)
    baseline = [summarize(groups[(period, identifier)], identifier, name, period, replicates)
                for period in PERIODS for identifier, name, *_ in BASELINES]
    signal_rows = [summarize(signals[period], "ou25_structural_v2_ev3", "OU 2,5: mayor EV estructural v2, si EV ≥ 3%", period, replicates)
                   for period in PERIODS]
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "source": "Football-Data.co.uk, columnas explícitas Bet365; uso privado de investigación",
              "periods": PERIODS, "raw_inventory": raw_inventory,
              "coverage_before_model_eligibility": dict(coverage), "dropped": dict(dropped),
              "baseline_rows": baseline, "model_signal_rows": signal_rows,
              "ou25_platt_experiment": ou_calibration_experiment(groups, replicates),
              "methodology": [
                  "Seis filas fijas: local/empate/visitante 1X2, Over/Under2.5 y local al AH publicado. No se buscaron ligas, cuotas ni cortes de probabilidad para mejorar ROI.",
                  "Cada fila apuesta 1 unidad por partido elegible y con cuota Bet365 pre válida. Las filas se superponen: no sumar sus n como partidos independientes ni tratarlas como una cartera conjunta.",
                  "Probabilidades del modelo estructural opponent_adjusted_poisson_dc_v2 previamente existente, entrenado sólo con fechas anteriores. Es auxiliar: el modelo seleccionado en el experimento v2 fue consenso de mercado, no este modelo estructural.",
                  "EV es promedio de retornos esperados por posición con su cuota y distribución; no se multiplica la probabilidad media por la cuota media.",
                  "La fila de señales OU usa EV estructural ≥3% y elige como máximo un lado por partido; umbral fijo, sin retunear. Es exploratoria y no sustituye la política de consenso registrada.",
                  "ROI histórico liquidado con resultados y cuotas B365 archivadas, no beneficio de apuestas realmente aceptadas. Cero apuestas ejecutadas; no incluye impuestos, restricciones, límites ni deslizamiento.",
                  "Snapshot pre y cierre permanecen separados. Las columnas sin C son anteriores al cierre, no necesariamente cuotas de apertura; faltan timestamps exactos por precio y no se demuestra disponibilidad antes del cálculo.",
                  "2022–2023 y 2024+ se informan separados. El tramo 2024+ ya fue inspeccionado previamente: no es holdout independiente ni validación prospectiva.",
                  "Los retornos AH incluyen media ganancia, reembolso y media pérdida. Acierto significa retorno positivo; no es comparable directamente con una cuota binaria sin push.",
                  "No hay cuotas históricas B365 de primer tiempo ni de jugadores en los CSV inventariados: no se calcula ROI/EV para esos mercados con cuotas inventadas."],
              "leakage_checks": {"prior_date_forecasts_checked": training_checked, "same_day_result_updates_allowed": False,
                                 "closing_price_substitutions": 0, "price_timestamp_verified": False,
                                 "historical_execution_proven": False},
              "inputs": {name: {"path": name, "sha256": sha(ROOT/name)} for name in (
                  "data/processed/matches.csv", "data/analysis/quote_history.jsonl", "data/analysis/v2_prediction_cache.jsonl",
                  "engine/models_v2.py", "engine/markets.py", "scripts/bet365_numbers.py")},
              "executed_bets": 0, "executable": False}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT/"data/analysis/bet365_numbers.json"))
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    args = parser.parse_args()
    if args.bootstrap_replicates < 100:
        parser.error("bootstrap-replicates must be >= 100")
    result = build(args.output, args.bootstrap_replicates)
    for row in result["baseline_rows"]+result["model_signal_rows"]:
        print(json.dumps({key: row[key] for key in ("period", "name", "n", "full_wins", "half_wins", "pushes", "half_losses", "full_losses", "observed_hit_rate", "mean_decimal_odds", "mean_model_probability_positive_return", "mean_model_ev_per_stake", "historical_flat_stake_roi", "historical_roi_ci95")}, ensure_ascii=False), flush=True)
    experiment = result["ou25_platt_experiment"]
    print(json.dumps({"ou25_platt_calibrator": experiment["calibrator"],
                      "audit_prediction_metrics": {key: value["forecast_metrics"] for key, value in experiment["evaluation"].items()},
                      "audit_policy_returns": {key: {field: value["ev3_policy"][field] for field in ("n", "mean_decimal_odds", "historical_flat_stake_roi", "historical_roi_ci95")}
                                               for key, value in experiment["evaluation"].items() if "ev3_policy" in value}}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
