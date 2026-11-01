#!/usr/bin/env python3
"""Actual EPL first-half probabilities and chronological checks, without APIs.

Uses HTHG/HTAG-derived columns and the existing StatCountModel. Does not infer
half-time goals from full-time scores, fit to future outcomes or invent odds.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
from itertools import groupby
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.stat_markets import StatCountModel, observed_counts
from engine.models_v2 import score_grid
from scripts.bet365_numbers import fit_platt, platt_probability

LEAGUE = "England Premier League"
TARGETS = (("first_half_over_0_5", .5, "prob_over_0_5"),
           ("first_half_over_1_5", 1.5, "prob_over_1_5"))


def wilson(successes, n):
    """95% binomial Wilson interval; not a per-match probability interval."""
    if not n:
        return None
    z = 1.959963984540054
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0., center - radius), min(1., center + radius)]


def _quantile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)


def _date_bootstrap(observations, *, repetitions=2000):
    dates = defaultdict(lambda: [0, 0., 0., 0.])
    for item in observations:
        block = dates[item["date"]]
        block[0] += 1
        block[1] += int((item["p"] >= .5) == bool(item["y"]))
        block[2] += int((item["baseline_p"] >= .5) == bool(item["y"]))
        block[3] += (item["baseline_p"] - item["y"]) ** 2 - (item["p"] - item["y"]) ** 2
    blocks = list(dates.values())
    if not blocks:
        return {"model_accuracy": None, "baseline_accuracy": None, "brier_improvement": None}
    rng = random.Random(29010)
    accuracies, baseline_accuracies, improvements = [], [], []
    for _ in range(repetitions):
        selected = [blocks[rng.randrange(len(blocks))] for _ in blocks]
        n = sum(b[0] for b in selected)
        accuracies.append(sum(b[1] for b in selected) / n)
        baseline_accuracies.append(sum(b[2] for b in selected) / n)
        improvements.append(sum(b[3] for b in selected) / n)
    return {"model_accuracy": [_quantile(accuracies, .025), _quantile(accuracies, .975)],
            "baseline_accuracy": [_quantile(baseline_accuracies, .025), _quantile(baseline_accuracies, .975)],
            "brier_improvement": [_quantile(improvements, .025), _quantile(improvements, .975)]}


def summarize_test(identifier, line, observations):
    n = len(observations)
    if not n:
        return {"market": identifier, "line": line, "n": 0, "roi": None}
    wins = sum((item["p"] >= .5) == bool(item["y"]) for item in observations)
    baseline_wins = sum((item["baseline_p"] >= .5) == bool(item["y"]) for item in observations)
    actual_over = sum(item["y"] for item in observations)
    brier = sum((x["p"] - x["y"]) ** 2 for x in observations) / n
    baseline_brier = sum((x["baseline_p"] - x["y"]) ** 2 for x in observations) / n
    bins = []
    for i in range(10):
        members = [x for x in observations if min(9, int(x["p"] * 10)) == i]
        if not members:
            continue
        successes = sum(x["y"] for x in members)
        bins.append({"lower_inclusive": i / 10, "upper_exclusive": (i + 1) / 10,
                     "n": len(members), "mean_model_probability": sum(x["p"] for x in members) / len(members),
                     "observed_over_rate": successes / len(members), "observed_rate_ci95_wilson": wilson(successes, len(members))})
    return {"market": identifier, "line": line, "n": n,
            "distinct_dates": len({x["date"] for x in observations}),
            "actual_over_count": actual_over, "actual_over_rate": actual_over / n,
            "actual_over_rate_ci95_wilson": wilson(actual_over, n),
            "mean_model_probability": sum(x["p"] for x in observations) / n,
            "mean_baseline_probability": sum(x["baseline_p"] for x in observations) / n,
            "accuracy": wins / n, "correct_classifications": wins,
            "predicted_over_count": sum(x["p"] >= .5 for x in observations),
            "predicted_under_count": sum(x["p"] < .5 for x in observations),
            "accuracy_ci95_wilson": wilson(wins, n),
            "baseline_accuracy": baseline_wins / n,
            "baseline_accuracy_ci95_wilson": wilson(baseline_wins, n),
            "accuracy_rule": "Predice over si p >= 0.5; si no, under. No selecciona apuestas ni cuotas.",
            "brier": brier, "baseline_brier": baseline_brier,
            "brier_improvement_over_frequency": baseline_brier - brier,
            "log_loss": -sum(math.log(max(1e-15, x["p"] if x["y"] else 1 - x["p"])) for x in observations) / n,
            "baseline_log_loss": -sum(math.log(max(1e-15, x["baseline_p"] if x["y"] else 1 - x["baseline_p"])) for x in observations) / n,
            "date_cluster_bootstrap_ci95": _date_bootstrap(observations),
            "reliability_bins": bins, "historical_odds_events": 0, "roi": None}


def _binary_scores(observations, probability_key="p"):
    n = len(observations)
    return {"n": n,
            "mean_probability": sum(x[probability_key] for x in observations) / n,
            "observed_over_rate": sum(x["y"] for x in observations) / n,
            "brier": sum((x[probability_key] - x["y"]) ** 2 for x in observations) / n,
            "log_loss": -sum(math.log(max(1e-15, x[probability_key] if x["y"] else 1 - x[probability_key])) for x in observations) / n}


def _fit_half_time_calibration(training, test):
    if any(not "2022-01-01" <= x["date"] <= "2023-12-31" for x in training):
        raise ValueError("El entrenamiento Platt HT sólo admite2022–2023.")
    if any(x["date"] < "2024-01-01" for x in test):
        raise ValueError("El test Platt HT sólo admite2024 en adelante.")
    result = {"target": "first_half_over_0_5", "complement": "first_half_correct_score_0_0",
              "training_period": {"from": "2022-01-01", "through": "2023-12-31"},
              "test_period": {"from": "2024-01-01", "kind": "chronological_previously_inspected"},
              "method": "Platt: sigmoid(intercept + slope * logit(raw_p_over_0_5))",
              "selection_criterion": "binary_log_loss_only", "odds_or_roi_used_for_fit": False,
              "base_model_parameters_changed": False, "training_n": len(training)}
    if len(training) < 3 or len({x["y"] for x in training}) < 2:
        return {**result, "status": "insufficient_calibration_training", "fit": None}
    fit = fit_platt([x["p"] for x in training], [x["y"] for x in training])
    if not fit["converged"]:
        return {**result, "status": "calibrator_did_not_converge", "fit": fit}
    calibrated_test = [{**x, "calibrated_p": platt_probability(x["p"], fit)} for x in test]
    raw_scores = _binary_scores(test) if test else None
    calibrated_scores = _binary_scores(calibrated_test, "calibrated_p") if test else None
    # Paired blocks: calibrated forecast against the raw forecast for exactly
    # the same events/dates. Positive improvement means lower calibrated Brier.
    paired = [{**x, "p": x["calibrated_p"], "baseline_p": x["p"]} for x in calibrated_test]
    return {**result, "status": "fitted_frozen_after_2023", "fit": fit,
            "training_actual_dates": [min(x["date"] for x in training), max(x["date"] for x in training)],
            "test_actual_dates": [min(x["date"] for x in test), max(x["date"] for x in test)] if test else None,
            "test_raw": raw_scores, "test_calibrated": calibrated_scores,
            "test_brier_improvement": raw_scores["brier"] - calibrated_scores["brier"] if test else None,
            "test_log_loss_improvement": raw_scores["log_loss"] - calibrated_scores["log_loss"] if test else None,
            "test_brier_improvement_ci95_date_bootstrap": _date_bootstrap(paired)["brier_improvement"],
            "limitations": ["Auditoría ya inspeccionada; no es validación prospectiva independiente.",
                            "Recalibra sólo el evento over0.5 y su complemento0–0. No crea una scoregrid ni probabilidades1x2/BTTS recalibradas.",
                            "No hay selección o ajuste por ROI. Las cuotas observadas se aplican después de congelar coeficientes."]}


def build_numbers(history, fixtures, *, as_of_date, audit_start="2024-01-01", fixture_limit=10):
    as_of_date = date.fromisoformat(str(as_of_date)[:10])
    # Date-only outcomes from the current day are excluded; no completion-time
    # assumption is needed. Predict all matches of a date before updating it.
    history = sorted((r for r in history if r.get("sport") in ("football", "soccer") and r.get("league") == LEAGUE
                      and str(r["date"])[:10] < as_of_date.isoformat()), key=lambda r: (r["date"], r.get("id", "")))
    model = StatCountModel("period_half")
    observations = {identifier: [] for identifier, _, _ in TARGETS}
    calibration_training = []
    baseline_counts = {identifier: [0., 0.] for identifier, _, _ in TARGETS}
    baseline_date = None

    def baseline_probs(day):
        nonlocal baseline_date
        day = date.fromisoformat(str(day)[:10])
        if baseline_date is not None:
            decay = 2 ** (-(day - baseline_date).days / 365.)
            for values in baseline_counts.values():
                values[:] = [v * decay for v in values]
        baseline_date = day
        return {identifier: (values[1] + 1) / (sum(values) + 2) for identifier, values in baseline_counts.items()}

    missing_ht = 0
    for day, iterator in groupby(history, lambda row: row["date"][:10]):
        batch = list(iterator)
        base = baseline_probs(day)
        for row in batch:
            counts = observed_counts(row, "period_half")
            if counts is None:
                missing_ht += 1
                continue
            prediction = model.predict(row["home_team"], row["away_team"], day, row.get("neutral_venue", False))
            if "2022-01-01" <= day <= "2023-12-31" and prediction["eligible"]:
                calibration_training.append({"date": day, "id": row.get("id"),
                                             "p": prediction["prob_over_0_5"], "y": int(sum(counts) > .5)})
            if day >= audit_start and prediction["eligible"]:
                if prediction["training_max_date"] >= day:
                    raise ValueError("Predicción con fuga temporal")
                for identifier, line, key in TARGETS:
                    observations[identifier].append({"date": day, "id": row.get("id"), "p": prediction[key],
                                                      "baseline_p": base[identifier], "y": int(sum(counts) > line)})
        model.update_batch(batch)
        for row in batch:
            counts = observed_counts(row, "period_half")
            if counts is None or str(row.get("neutral_venue", "false")).lower() in ("true", "1", "yes"):
                continue
            for identifier, line, _ in TARGETS:
                baseline_counts[identifier][int(sum(counts) > line)] += 1
    tests = [summarize_test(identifier, line, observations[identifier]) for identifier, line, _ in TARGETS]
    calibration_test = [x for x in observations["first_half_over_0_5"] if x["date"] >= "2024-01-01"]
    calibration = (_fit_half_time_calibration(calibration_training, calibration_test)
                   if as_of_date >= date(2024, 1, 1)
                   else {"status": "training_period_not_completed", "fit": None, "training_n": len(calibration_training)})
    tests_by_key = {item["market"]: item for item in tests}
    selected_fixtures = sorted((r for r in fixtures if r.get("league") == LEAGUE and r["date"] >= as_of_date.isoformat()),
                               key=lambda r: (r["date"], r.get("time", ""), r.get("id", "")))[:fixture_limit]
    predictions = []
    for fixture in selected_fixtures:
        prediction = model.predict(fixture["home_team"], fixture["away_team"], fixture["date"], fixture.get("neutral_venue", False))
        base = baseline_probs(fixture["date"])
        markets = []
        for identifier, line, key in TARGETS:
            p = prediction[key]
            reference_bin = next((b for b in tests_by_key[identifier].get("reliability_bins", [])
                                  if b["lower_inclusive"] <= p < b["upper_exclusive"]), None)
            markets.append({"market": identifier, "period": "first_half", "line": line,
                            "probability_over": p, "probability_under": 1 - p,
                            "break_even_decimal_odds_over": 1 / p,
                            "break_even_decimal_odds_under": 1 / (1 - p),
                            "prior_only_league_over_frequency": base[identifier],
                            "bet365_decimal_odds": None,
                            "bet365_price_status": "Sin cuota Bet365 de primer tiempo observada en las entradas locales.",
                            "historical_calibration_bin": reference_bin,
                            "historical_bin_precision": "insufficient_n" if reference_bin is None or reference_bin["n"] < 30 else "descriptive_only",
                            "model_ev_at_observed_bet365_price": None})
            if identifier == "first_half_over_0_5" and calibration["status"] == "fitted_frozen_after_2023":
                calibrated_p = platt_probability(p, calibration["fit"])
                markets[-1].update({"calibrated_probability_over": calibrated_p,
                                    "calibrated_probability_under": 1 - calibrated_p,
                                    "calibrated_break_even_decimal_odds_over": 1 / calibrated_p,
                                    "calibrated_break_even_decimal_odds_under": 1 / (1 - calibrated_p),
                                    "calibration_training_period": "2022–2023 only"})
        predictions.append({"fixture_id": fixture.get("id"), "date": fixture["date"], "time": fixture.get("time"),
                            "home_team": fixture["home_team"], "away_team": fixture["away_team"], "league": LEAGUE,
                            "kickoff_timezone": fixture.get("kickoff_timezone", "unknown"),
                            "kickoff_reliable": str(fixture.get("kickoff_reliable", "false")).lower() == "true",
                            "model_eligible": prediction["eligible"], "model_reasons": prediction["reasons"],
                            "training_max_date": prediction["training_max_date"],
                            "team_sample_min": prediction["sample_size"], "team_effective_sample_min": prediction["effective_sample_size"],
                            "expected_first_half_home_goals": prediction["home_rate"],
                            "expected_first_half_away_goals": prediction["away_rate"], "markets": markets})
    return {"schema_version": 1, "as_of_date": as_of_date.isoformat(), "league": LEAGUE,
            "model": "half_time_empirical_bayes_poisson_v2", "model_parameters": {"half_life_days": 365, "prior_games": 20},
            "history_matches": len(history), "history_with_half_time_counts": len(history) - missing_ht,
            "history_missing_half_time_counts": missing_ht,
            "history_last_date": max((r["date"] for r in history), default=None),
            "audit": {"from": audit_start, "through_exclusive": as_of_date.isoformat(),
                      "kind": "chronological_retrospective_previously_inspected", "independent_holdout": False,
                      "baseline": "Frecuencia de over de EPL con decaimiento365d y prior Beta(1,1), sólo resultados anteriores a cada fecha.",
                      "same_day_results_used_before_prediction": False,
                      "confidence_intervals": "Wilson binomial y bootstrap por fecha2000 réplicas. Son intervalos de tasas/estadísticas históricas, no IC de la probabilidad de un fixture."},
            "test": tests, "fixtures": predictions, "calibration_over_0_5": calibration,
            "conditions": ["HTHG/HTAG observados de Football-Data; no se divide el marcador final por dos.",
                           "Cuota de equilibrio=1/p del modelo, sin margen. Para EV positivo bajo ese modelo la cuota debe ser estrictamente mayor; error de estimación puede eliminar ese supuesto valor.",
                           "Los bins muestran frecuencia observada en la auditoría ya vista; no recalibran ni ajustan la probabilidad del fixture sobre ese período.",
                           "Acierto mide clasificación over/under con umbral0.5; no equivale a acertar todas las selecciones ni ganar dinero.",
                           "No hay cuotas históricas equivalentes de primer tiempo en el histórico ingerido. ROI no identificado.",
                           "Cuotas Bet365 de primer tiempo no observadas localmente: no se presentan como precios ofertados.",
                           "Marcadores incluyen el descuento de primer tiempo según la definición de la fuente; reglas del contrato deben coincidir."],
            "execution_enabled": False}


def attach_bet365_snapshot(report, snapshot):
    """Attach theoretical EV for explicitly transcribed, timestamped prices.

    The input is evidence of a viewed price, never evidence of acceptance or a
    statistically validated probability. Only one exactly identified fixture
    may receive this snapshot; prices are never propagated to other events.
    """
    if snapshot.get("period") != "first_half":
        raise ValueError("La captura debe identificar explícitamente primer tiempo.")
    observed = datetime.fromisoformat(str(snapshot["observed_at"]).replace("Z", "+00:00"))
    kickoff = datetime.fromisoformat(str(snapshot["commence_time"]).replace("Z", "+00:00"))
    if observed.tzinfo is None or kickoff.tzinfo is None or observed >= kickoff:
        raise ValueError("La captura Bet365 requiere horas válidas anteriores al evento.")
    candidates = [f for f in report["fixtures"] if f["home_team"] == snapshot["home_team"]
                  and f["away_team"] == snapshot["away_team"] and f["date"] == kickoff.date().isoformat()]
    if len(candidates) != 1:
        raise ValueError("La captura Bet365 no corresponde a un fixture único.")
    fixture = candidates[0]
    grid = score_grid(fixture["expected_first_half_home_goals"], fixture["expected_first_half_away_goals"])
    team_yes = {"home": sum(p for h, row in enumerate(grid["grid"]) for p in row if h > 0),
                "away": sum(p for row in grid["grid"] for a, p in enumerate(row) if a > 0)}
    rows = []
    for source in snapshot["prices"]:
        market, selection = source["market"], source["selection"]
        odds = source["decimal_odds"]
        if isinstance(odds, bool) or not math.isfinite(float(odds)) or float(odds) <= 1:
            raise ValueError("Cuota Bet365 inválida.")
        odds = float(odds)
        if market == "first_half_1x2" and selection in ("home", "draw", "away"):
            p = grid[selection]
        elif market == "first_half_btts" and selection in ("yes", "no"):
            p = grid["btts_" + selection]
        elif market == "first_half_team_to_score" and source.get("team") in ("home", "away") and selection in ("yes", "no"):
            yes = team_yes[source["team"]]
            p = yes if selection == "yes" else 1 - yes
        elif market == "first_half_totals" and selection in ("over", "under"):
            line = float(source["line"])
            # This p*odds-1 calculation is only valid for half-goal lines,
            # not integer pushes or quarter-line partial settlements.
            if line < 0 or not math.isclose(line % 1, .5, abs_tol=1e-10):
                raise ValueError("EV binario de totales requiere línea de medio gol.")
            p_over = sum(p for h, row in enumerate(grid["grid"]) for a, p in enumerate(row) if h + a > line)
            p = p_over if selection == "over" else 1 - p_over
        elif market == "first_half_correct_score":
            parts = selection.replace("–", "-").split("-")
            if len(parts) != 2 or any(not part.isdigit() for part in parts):
                raise ValueError("Marcador correcto HT inválido.")
            home_goals, away_goals = map(int, parts)
            if home_goals >= len(grid["grid"]) or away_goals >= len(grid["grid"][0]):
                raise ValueError("Marcador fuera de la cuadrícula HT.")
            p = grid["grid"][home_goals][away_goals]
        else:
            raise ValueError("Mercado Bet365 fuera del modelo de primer tiempo: " + market)
        mapping_verified = source.get("period_mapping_verified", True) is True
        model_ev = p * odds - 1 if mapping_verified else None
        rows.append({**source, "decimal_odds": odds,
                     "model_probability": p, "price_break_even_probability": 1 / odds if mapping_verified else None,
                     "probability_edge": p - 1 / odds if mapping_verified else None,
                     "model_break_even_decimal_odds": 1 / p,
                     "model_expected_net_return_per_unit": model_ev,
                     "positive_model_ev": model_ev > 0 if model_ev is not None else None,
                     "period_mapping_verified": mapping_verified,
                     "model_eligible": fixture["model_eligible"],
                     "probability_validated_above_baseline": False,
                     "interpretation": "EV teórico de modelo HT, no ROI observado ni ventaja demostrada." if mapping_verified else "Asignación de columna a período sin confirmar; EV bloqueado hasta verificación visual.",
                     "execution_enabled": False})
        if market == "first_half_correct_score" and selection in ("0-0", "0–0"):
            over05 = next(item for item in fixture["markets"] if item["line"] == .5)
            if "calibrated_probability_under" in over05:
                p_calibrated = over05["calibrated_probability_under"]
                rows[-1].update({"calibrated_model_probability": p_calibrated,
                                 "calibrated_model_break_even_decimal_odds": 1 / p_calibrated,
                                 "calibrated_model_expected_net_return_per_unit": p_calibrated * odds - 1 if mapping_verified else None,
                                 "calibrated_positive_model_ev": p_calibrated * odds > 1 if mapping_verified else None,
                                 "calibration_training_period": "2022–2023 only"})
        if market == "first_half_totals" and selection == "over" and mapping_verified:
            for item in fixture["markets"]:
                if item["line"] == float(source["line"]):
                    item["bet365_decimal_odds"] = odds
                    item["bet365_price_status"] = "Precio observado directamente en Bet365 Argentina en observed_at; no aceptado."
                    item["model_ev_at_observed_bet365_price"] = model_ev
        if market == "first_half_correct_score" and selection in ("0-0", "0–0") and mapping_verified:
            for item in fixture["markets"]:
                if item["line"] == .5:
                    item["bet365_under_decimal_odds"] = odds
                    item["bet365_under_source_market"] = "first_half_correct_score_0_0"
                    item["bet365_under_model_ev"] = model_ev
    fixture["bet365_observed_markets"] = rows
    fixture["bet365_snapshot"] = {key: snapshot[key] for key in ("bookmaker", "source_url", "observed_at", "commence_time", "capture_method")}
    report["bet365_snapshot_attached"] = True
    report["conditions"] = [c for c in report["conditions"] if not c.startswith("Cuotas Bet365 de primer tiempo no observadas")]
    report["conditions"].append("Cuotas Bet365 directas sólo para el fixture identificado y la hora indicada; se calcula EV teórico, sin ejecución ni acreditación de beneficio futuro.")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=ROOT / "data/processed/matches.csv")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "data/processed/fixtures.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/analysis/first_half_numbers.json")
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--bet365-snapshot", type=Path, default=ROOT / "data/analysis/bet365_first_half_snapshot.json")
    args = parser.parse_args(argv)
    with args.history.open(newline="") as handle:
        history = list(csv.DictReader(handle))
    with args.fixtures.open(newline="") as handle:
        fixtures = list(csv.DictReader(handle))
    as_of_date = args.as_of_date or max((r.get("retrieved_at", "")[:10] for r in fixtures if r.get("retrieved_at")),
                                      default=datetime.now(timezone.utc).date().isoformat())
    output = build_numbers(history, fixtures, as_of_date=as_of_date)
    def path_label(path):
        try:
            return str(path.resolve().relative_to(ROOT))
        except ValueError:
            return str(path)
    output["sources"] = [{"path": path_label(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for path in (args.history, args.fixtures, ROOT / "engine/stat_markets.py", ROOT / "engine/models_v2.py", ROOT / "scripts/bet365_numbers.py", Path(__file__))]
    if args.bet365_snapshot.exists():
        snapshot_bytes = args.bet365_snapshot.read_bytes()
        attach_bet365_snapshot(output, json.loads(snapshot_bytes))
        output["sources"].append({"path": path_label(args.bet365_snapshot), "sha256": hashlib.sha256(snapshot_bytes).hexdigest()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "history_matches": output["history_matches"],
                      "test": [{k: item[k] for k in ("market", "n", "accuracy", "accuracy_ci95_wilson", "brier", "baseline_brier")} for item in output["test"]],
                      "fixture_count": len(output["fixtures"])}, ensure_ascii=False))
    return output


if __name__ == "__main__":
    main()
