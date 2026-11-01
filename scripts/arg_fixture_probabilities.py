#!/usr/bin/env python3
"""Argentina-only fixed-window goal models and a dated fixture forecast.

Offline research. No EPL calibrator, betting-price optimization or execution.
The FT grid is the joint state used for dependent combinations.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
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

from engine.models_v2 import OnlineGoalsV2
from scripts.first_half_numbers import wilson

LEAGUE = "Argentina Liga Profesional"
HOME, AWAY = "Estudiantes Rio Cuarto", "Gimnasia L.P."
AS_OF = "2026-10-30"
AUDIT_START = "2024-01-01"
CONFIG = {"prior_strength": 12., "half_life_days": 365., "refit_days": 14,
          "rho_mode": "fitted", "fit_iterations": 12}


def market_probabilities(grid):
    """Every event is summed from the same joint FT distribution."""
    cells = [(h, a, p) for h, row in enumerate(grid) for a, p in enumerate(row)]
    def probability(predicate):
        return sum(p for h, a, p in cells if predicate(h, a))
    output = {
        "home_win": probability(lambda h, a: h > a), "draw": probability(lambda h, a: h == a),
        "away_win": probability(lambda h, a: h < a),
        "home_or_draw": probability(lambda h, a: h >= a), "away_or_draw": probability(lambda h, a: h <= a),
        "no_draw": probability(lambda h, a: h != a),
        "btts_yes": probability(lambda h, a: h > 0 and a > 0),
        "btts_no": probability(lambda h, a: h == 0 or a == 0),
    }
    for line in (.5, 1.5, 2.5, 3.5, 4.5, 5.5):
        key = str(line).replace(".", "_")
        output["over_" + key] = probability(lambda h, a, line=line: h + a > line)
        output["under_" + key] = 1 - output["over_" + key]
    for team in ("home", "away"):
        for line in (.5, 1.5, 2.5):
            key = str(line).replace(".", "_")
            output[team + "_over_" + key] = probability(lambda h, a, line=line, team=team: (h if team == "home" else a) > line)
            output[team + "_under_" + key] = 1 - output[team + "_over_" + key]
    combos = {
        "home_win_and_under_3_5": lambda h, a: h > a and h + a < 3.5,
        "away_win_and_under_3_5": lambda h, a: a > h and h + a < 3.5,
        "home_or_draw_and_under_3_5": lambda h, a: h >= a and h + a < 3.5,
        "away_or_draw_and_under_3_5": lambda h, a: h <= a and h + a < 3.5,
        "home_or_draw_and_under_2_5": lambda h, a: h >= a and h + a < 2.5,
        "away_or_draw_and_under_2_5": lambda h, a: h <= a and h + a < 2.5,
        "btts_yes_and_over_2_5": lambda h, a: h > 0 and a > 0 and h + a > 2.5,
        "btts_no_and_under_2_5": lambda h, a: (h == 0 or a == 0) and h + a < 2.5,
        "home_win_and_btts_yes": lambda h, a: h > a and a > 0,
        "away_win_and_btts_yes": lambda h, a: a > h and h > 0,
        "draw_and_btts_no": lambda h, a: h == 0 and a == 0,
    }
    output.update({key: probability(predicate) for key, predicate in combos.items()})
    output.update({"goals_0_to_1": probability(lambda h, a: h + a <= 1),
                   "goals_2_to_3": probability(lambda h, a: 2 <= h + a <= 3),
                   "goals_4_to_6": probability(lambda h, a: 4 <= h + a <= 6),
                   "goals_7_plus": probability(lambda h, a: h + a >= 7)})
    return output


def train_forecast(rows, day, window_days, home=HOME, away=AWAY):
    model = OnlineGoalsV2(window_days=window_days, **CONFIG)
    cutoff = date.fromisoformat(day) - timedelta(days=window_days)
    past = [r for r in rows if cutoff.isoformat() <= r["date"] < day]
    for _, entries in groupby(past, lambda r: r["date"]):
        model.update_batch(list(entries))
    prediction = model.predict(home, away, day)
    probabilities = market_probabilities(prediction["grid"])
    return {**prediction, "window_days": window_days, "parameters": {**CONFIG, "window_days": window_days},
            "fitting_mode": "fresh_refit_of_fixed_window_for_current_fixture",
            "markets": probabilities,
            "break_even_decimal_odds": {key: 1 / p if p > 0 else None for key, p in probabilities.items()},
            "total_goal_counts": [{"goals": k, "probability": sum(p for h, row in enumerate(prediction["grid"]) for a, p in enumerate(row) if h + a == k)} for k in range(7)] +
                                  [{"goals": "7+", "probability": sum(p for h, row in enumerate(prediction["grid"]) for a, p in enumerate(row) if h + a >= 7)}],
            "exact_scores": sorted([{"home": h, "away": a, "probability": p} for h, row in enumerate(prediction["grid"]) for a, p in enumerate(row)], key=lambda x: -x["probability"])[:15],
            "counts_by_team": {team: sum(team in (r["home_team"], r["away_team"]) for r in past) for team in (home, away)}}


def _baseline(history, day, window_days):
    today = date.fromisoformat(day)
    totals, over, btts, outcome = 0., 0., 0., [0., 0., 0.]
    for result_day, h, a, hg, ag in history:
        age = (today - result_day).days
        if age > window_days:
            continue
        w = 2 ** (-age / 365.)
        totals += w
        over += w * (hg + ag > 2.5)
        btts += w * (hg > 0 and ag > 0)
        outcome[0 if hg > ag else 1 if hg == ag else 2] += w
    return {"1x2": [(n + 1) / (totals + 3) for n in outcome], "over25": (over + 1) / (totals + 2),
            "btts": (btts + 1) / (totals + 2)}


def _metrics(records, target):
    if not records:
        return {"n": 0}
    multiclass = target == "1x2"
    losses, briers, base_losses, base_briers, bins = [], [], [], [], defaultdict(list)
    correct = base_correct = 0
    for r in records:
        p, y, baseline = r[target], r["y_" + target], r["base_" + target]
        if multiclass:
            selected = max(range(3), key=p.__getitem__)
            correct += selected == y
            base_correct += max(range(3), key=baseline.__getitem__) == y
            losses.append(-math.log(max(1e-15, p[y])))
            base_losses.append(-math.log(max(1e-15, baseline[y])))
            briers.append(sum((v - (i == y)) ** 2 for i, v in enumerate(p)))
            base_briers.append(sum((v - (i == y)) ** 2 for i, v in enumerate(baseline)))
            bins[min(9, int(p[selected] * 10))].append((p[selected], int(selected == y)))
        else:
            correct += (p >= .5) == bool(y)
            base_correct += (baseline >= .5) == bool(y)
            losses.append(-math.log(max(1e-15, p if y else 1 - p)))
            base_losses.append(-math.log(max(1e-15, baseline if y else 1 - baseline)))
            briers.append((p - y) ** 2)
            base_briers.append((baseline - y) ** 2)
            bins[min(9, int(p * 10))].append((p, y))
    n = len(records)
    daily = defaultdict(lambda: [0, 0., 0.])
    for record, loss, brier, base_loss, base_brier in zip(records, losses, briers, base_losses, base_briers):
        block = daily[record["date"]]
        block[0] += 1
        block[1] += base_loss - loss
        block[2] += base_brier - brier
    blocks = list(daily.values())
    rng = random.Random(30102026)
    ll_improvements, brier_improvements = [], []
    for _ in range(2000):
        sample = [rng.choice(blocks) for _ in blocks]
        size = sum(v[0] for v in sample)
        ll_improvements.append(sum(v[1] for v in sample) / size)
        brier_improvements.append(sum(v[2] for v in sample) / size)
    return {"n": n, "date_count": len({r["date"] for r in records}),
            "log_loss": sum(losses) / n, "brier": sum(briers) / n, "accuracy": correct / n,
            "accuracy_ci95_wilson": wilson(correct, n), "baseline_log_loss": sum(base_losses) / n,
            "baseline_brier": sum(base_briers) / n, "baseline_accuracy": base_correct / n,
            "calibration": [{"bin": k, "n": len(v), "mean_predicted": sum(p for p, _ in v) / len(v),
                             "observed": sum(y for _, y in v) / len(v),
                             "observed_ci95_wilson": wilson(sum(y for _, y in v), len(v))} for k, v in sorted(bins.items())],
            "calibration_target": "most_likely_class_accuracy" if multiclass else "event_probability",
            "brier_definition": "multiclass_sum_0_to_2" if multiclass else "binary_0_to_1",
            "improvement_ci95_date_bootstrap": {"replicates": 2000,
                                                "log_loss": [_q(ll_improvements, .025), _q(ll_improvements, .975)],
                                                "brier": [_q(brier_improvements, .025), _q(brier_improvements, .975)],
                                                "positive_means": "Lower error than the prior-frequency baseline"},
            "historical_financial_roi": None}


def evaluate(rows, window_days):
    model = OnlineGoalsV2(window_days=window_days, **CONFIG)
    records = []
    for day, entries in groupby(rows, lambda r: r["date"]):
        batch = list(entries)
        if day >= AUDIT_START:
            baseline = None
            for row in batch:
                prediction = model.predict(row["home_team"], row["away_team"], day)
                if not prediction["eligible"]:
                    continue
                if baseline is None:
                    baseline = _baseline(model.history, day, window_days)
                hg, ag = int(float(row["home_score"])), int(float(row["away_score"]))
                records.append({"id": row["id"], "date": day,
                                "1x2": [prediction["home"], prediction["draw"], prediction["away"]],
                                "over25": prediction["over25"], "btts": prediction["btts_yes"],
                                "y_1x2": 0 if hg > ag else 1 if hg == ag else 2,
                                "y_over25": int(hg + ag > 2.5), "y_btts": int(hg > 0 and ag > 0),
                                "base_1x2": baseline["1x2"], "base_over25": baseline["over25"], "base_btts": baseline["btts"]})
        model.update_batch(batch)
    return {"window_days": window_days, "from": AUDIT_START, "through": max((r["date"] for r in records), default=None),
            "prediction_updates": "Same-date batch predicted before its outcomes; refit interval14d, fixed parameters.",
            "baseline": "Argentina-only prior frequency, Beta/Dirichlet(1), same window and365d half-life.",
            "targets": {target: _metrics(records, target) for target in ("1x2", "over25", "btts")}}, records


def _q(values, p):
    values = sorted(values)
    index = (len(values) - 1) * p
    low = int(index)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)


def bootstrap_forecast(rows, repetitions=200):
    cutoff = (date.fromisoformat(AS_OF) - timedelta(days=730)).isoformat()
    daily = defaultdict(list)
    for row in rows:
        if cutoff <= row["date"] < AS_OF:
            daily[row["date"]].append(row)
    days = sorted(daily)
    rng = random.Random(20261030365)
    samples = defaultdict(list)
    draws = []
    for _ in range(repetitions):
        weights = Counter(rng.choice(days) for _ in days)
        bootstrap_rows = [row for day in days for _ in range(weights[day]) for row in daily[day]]
        forecast = train_forecast(bootstrap_rows, AS_OF, 730)
        draws.append({"home_rate": forecast["home_rate"], "away_rate": forecast["away_rate"],
                      "rho_applied": forecast["rho_applied"]})
        for key, p in forecast["markets"].items():
            samples[key].append(p)
    return {"repetitions": repetitions, "seed": 20261030365, "unit": "whole_result_dates_with_replacement",
            "interval_label": "Percentiles of fixed-model parameter resampling; NOT calibrated confidence intervals for true probabilities.",
            "limitations": "Conditional on the Poisson/DC model and observed schedule; does not cover all structural/serial/lineup uncertainty.",
            "draws": draws,
            "markets": {key: {"p025": _q(v, .025), "p50": _q(v, .5), "p975": _q(v, .975)} for key, v in samples.items()}}


def timing_fractions(games, home, away, *, prior_goals=20.):
    """Estimate HT timing from observed HT/FT goals, not a fixed50% split."""
    components = [(g["event_id"], side, g[side + "_team"], g[("away" if side == "home" else "home") + "_team"],
                   float(g[side + "_ht_score"]), float(g[side + "_score"])) for g in games for side in ("home", "away")]
    total_ht, total_ft = sum(x[4] for x in components), sum(x[5] for x in components)
    pooled = (total_ht + 1) / (total_ft + 2)
    output = {"pooled_ht_goals": total_ht, "pooled_ft_goals": total_ft,
              "pooled_ht_fraction": pooled, "prior_goal_exposure": prior_goals}
    for side, scorer, conceder in (("home", home, away), ("away", away, home)):
        selected = [x for x in components if x[2] == scorer or x[3] == conceder]
        ht, ft = sum(x[4] for x in selected), sum(x[5] for x in selected)
        output["q_" + side] = (ht + prior_goals * pooled) / (ft + prior_goals)
        output[side + "_goal_exposure"] = ft
        output[side + "_ht_goals"] = ht
        output[side + "_event_count"] = len({x[0] for x in selected})
    return output


def ht_ft_joint(ft_grid, q_home, q_away, *, include_states=True):
    """Binomial thinning conditional on each FT state; FT marginal preserved."""
    if not 0 < q_home < 1 or not 0 < q_away < 1:
        raise ValueError("Invalid HT goal-timing fractions")
    size = len(ft_grid)
    ht_grid = [[0. for _ in range(size)] for _ in range(size)]
    states, retained = [], 0.
    combinations = defaultdict(float)
    for fh, row in enumerate(ft_grid):
        for fa, ft_p in enumerate(row):
            if ft_p <= 0:
                continue
            for hh in range(fh + 1):
                ph = math.comb(fh, hh) * q_home ** hh * (1 - q_home) ** (fh - hh)
                for ha in range(fa + 1):
                    pa = math.comb(fa, ha) * q_away ** ha * (1 - q_away) ** (fa - ha)
                    p = ft_p * ph * pa
                    ht_grid[hh][ha] += p
                    if include_states and p >= 1e-14:
                        states.append([hh, ha, fh, fa, p]); retained += p
                    labels = {
                        "ht_draw_and_away_or_draw": hh == ha and fh <= fa,
                        "ht_under_1_5_and_ft_under_3_5": hh + ha < 1.5 and fh + fa < 3.5,
                        "ht_under_0_5_and_ft_under_2_5": hh + ha < .5 and fh + fa < 2.5,
                        "ht_draw_ft_draw": hh == ha and fh == fa,
                        "ht_draw_ft_away_win": hh == ha and fh < fa,
                        "ht_home_win_ft_home_win": hh > ha and fh > fa,
                        "ht_away_win_ft_away_win": hh < ha and fh < fa,
                    }
                    for key, won in labels.items():
                        if won:
                            combinations[key] += p
    return {"ht_grid": ht_grid, "states": states,
            "states_columns": ["ht_home", "ht_away", "ft_home", "ft_away", "probability"],
            "retained_state_probability_mass": retained if include_states else None,
            "omitted_state_probability_mass": max(0., 1 - retained) if include_states else None,
            "state_export_probability_floor": 1e-14,
            "combinations": dict(combinations)}


def build_first_half(output, rows, audit_path):
    if not audit_path.exists():
        return
    audit = json.loads(audit_path.read_text())
    games = sorted([g for g in audit["espn"]["games"] if g.get("two_half_sum_matches_final")
                    and g["date_utc"][:10] < AS_OF], key=lambda g: g["date_utc"])
    if not games:
        return
    fractions = timing_fractions(games, HOME, AWAY)
    joint = ht_ft_joint(output["forecast"]["grid"], fractions["q_home"], fractions["q_away"])
    output["joint_ht_ft"] = {**joint, "model": "Conditional binomial goal timing given the ARG FT score grid",
                             "assumptions": ["HT home/away goal allocations independent conditional on the FT score and fitted timing fractions.",
                                             "Timing fractions based only on actual2026 HT/FT goals of these teams; no EPL transfer or FT/2.",
                                             "Exploratory model with a small, selected-team validation sample; not a validated pricing edge."]}
    ht_probabilities = market_probabilities(joint["ht_grid"])
    sensitivity = {}
    for prior in (10., 20., 40.):
        q = timing_fractions(games, HOME, AWAY, prior_goals=prior)
        g = ht_ft_joint(output["forecast"]["grid"], q["q_home"], q["q_away"], include_states=False)["ht_grid"]
        sensitivity[str(int(prior))] = {"timing_fractions": q, "markets": market_probabilities(g)}
    records = []
    matched = 0
    for i, game in enumerate(games):
        past = games[:i]
        if len(past) < 20:
            continue
        # Exact identities and FT scores; allow the two documented UTC/CSV
        # date offsets, taking the EARLIER date to avoid temporal leakage.
        candidates = [r for r in rows if r["home_team"] == game["home_team"] and r["away_team"] == game["away_team"]
                      and abs((date.fromisoformat(r["date"]) - date.fromisoformat(game["date_utc"][:10])).days) <= 1
                      and int(float(r["home_score"])) == int(game["home_score"]) and int(float(r["away_score"])) == int(game["away_score"])]
        if len(candidates) != 1:
            continue
        matched += 1
        day = min(candidates[0]["date"], game["date_utc"][:10])
        past = [p for p in past if p["date_utc"][:10] < day]
        if len(past) < 20:
            continue
        f = train_forecast(rows, day, 730, game["home_team"], game["away_team"])
        if not f["eligible"]:
            continue
        q = timing_fractions(past, game["home_team"], game["away_team"])
        g = ht_ft_joint(f["grid"], q["q_home"], q["q_away"], include_states=False)["ht_grid"]
        probs = market_probabilities(g)
        hh, ha = game["home_ht_score"], game["away_ht_score"]
        bs = {"1x2": [1., 1., 1.], "over05": 1., "over15": 1., "btts": 1.}
        for previous in past:
            ph, pa = previous["home_ht_score"], previous["away_ht_score"]
            bs["1x2"][0 if ph > pa else 1 if ph == pa else 2] += 1
            bs["over05"] += ph + pa > .5; bs["over15"] += ph + pa > 1.5
            bs["btts"] += ph > 0 and pa > 0
        records.append({"id": game["event_id"], "date": day,
                        "1x2": [probs["home_win"], probs["draw"], probs["away_win"]],
                        "over05": probs["over_0_5"], "over15": probs["over_1_5"], "btts": probs["btts_yes"],
                        "y_1x2": 0 if hh > ha else 1 if hh == ha else 2,
                        "y_over05": int(hh + ha > .5), "y_over15": int(hh + ha > 1.5), "y_btts": int(hh > 0 and ha > 0),
                        "base_1x2": [v / sum(bs["1x2"]) for v in bs["1x2"]],
                        "base_over05": bs["over05"] / (len(past) + 2), "base_over15": bs["over15"] / (len(past) + 2),
                        "base_btts": bs["btts"] / (len(past) + 2)})
    output["first_half"] = {"available": True, "status": "exploratory_small_sample_argentina_2026",
                            "model": "ARG_FT_grid_with_observed_ESPN_goal_timing",
                            "source_unique_events": len(games), "timing_fractions": fractions,
                            "grid": joint["ht_grid"], "markets": ht_probabilities,
                            "break_even_decimal_odds": {k: 1 / p if p > 0 else None for k, p in ht_probabilities.items()},
                            "prior_sensitivity": sensitivity,
                            "validation": {"warmup_events": 20, "matched_games_after_warmup": matched,
                                           "eligible_test_events": len(records),
                                           "targets": {target: _metrics(records, target) for target in ("1x2", "over05", "over15", "btts")}},
                            "warning": "Selected histories of two teams, not a full ARG HT archive. No demonstrated superiority or financial ROI."}
    output["conditions"].append("HT and HT/FT joint use actual ESPN half scores; conditional binomial timing is an explicit exploratory assumption, separately tested on the small2026 sample.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=ROOT / "data/processed/matches.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/analysis/arg_fixture_probabilities.json")
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument("--data-audit", type=Path, default=ROOT / "data/analysis/arg_fixture_data_audit.json")
    args = parser.parse_args(argv)
    if args.bootstrap < 0:
        raise ValueError("Bootstrap repetitions must be nonnegative")
    def write_report(report):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        temporary.replace(args.output)
    all_rows = list(csv.DictReader(args.history.open(newline="")))
    rows = sorted((r for r in all_rows if r.get("league") == LEAGUE and r["date"] < AS_OF), key=lambda r: (r["date"], r["id"]))
    variants = {"window_" + str(window): train_forecast(rows, AS_OF, window) for window in (365, 730)}
    output = {"schema_version": 1, "as_of_date": AS_OF,
              "fixture": {"league": LEAGUE, "home_team": HOME, "away_team": AWAY,
                          "commence_time": "2026-10-30T19:00:00-03:00", "bet365_event_id": "202426204"},
              "history": {"matches": len(rows), "min_date": rows[0]["date"], "max_date": rows[-1]["date"],
                          "ht_observed_count": sum(bool(r.get("home_ht_score")) and bool(r.get("away_ht_score")) for r in rows),
                          "team_samples": {team: sum(team in (r["home_team"], r["away_team"]) for r in rows) for team in (HOME, AWAY)}},
              "forecast": variants["window_730"], "variants": variants,
              "window_sensitivity": {key: {"min_probability": min(v["markets"][key] for v in variants.values()),
                                            "max_probability": max(v["markets"][key] for v in variants.values()),
                                            "interpretation": "Two fixed windows; sensitivity envelope, not a confidence interval."} for key in variants["window_730"]["markets"]},
              "first_half": {"available": False, "reason": "No half-time scores in the ingested ARG CSV; pending separately sourced summaries. No FT/2 or EPL transfer."},
              "validation_status": "running", "execution_enabled": False,
              "conditions": ["Window730 is the declared primary specification, not selected by audit performance/ROI.",
                             "Opponent-adjusted attack/defence with fixed Gamma shrinkage12 and Dixon-Coles low-score correction.",
                             "All FT combinations come from the joint score grid; no multiplication of marginal events.",
                             "No first-goal, timing, player, corner or card probability follows from an FT goal grid.",
                             "Prospective performance and true event probabilities are unknown; financial ROI not identified here."]}
    if not args.output.exists():
        write_report(output)
    print("FT grids saved before validation", flush=True)
    validation = {}
    # For2024+ forecasts, anything before2022 is outside the longest window.
    replay_rows = [r for r in rows if r["date"] >= "2022-01-01"]
    for window in (365, 730):
        validation["window_" + str(window)], _ = evaluate(replay_rows, window)
    output["validation"] = validation
    output["validation_status"] = "chronological_retrospective_argentina_only"
    if args.bootstrap > 0:
        output["parameter_sensitivity_bootstrap"] = bootstrap_forecast(rows, args.bootstrap)
    build_first_half(output, rows, args.data_audit)
    output["sources"] = [{"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for path in (args.history, ROOT / "engine/models_v2.py", Path(__file__))]
    if args.data_audit.exists():
        output["sources"].append({"path": str(args.data_audit.relative_to(ROOT)), "sha256": hashlib.sha256(args.data_audit.read_bytes()).hexdigest()})
    write_report(output)
    print(json.dumps({"output": str(args.output), "p": output["forecast"]["markets"],
                      "validation_n": {key: value["targets"]["1x2"]["n"] for key, value in validation.items()}}, ensure_ascii=False), flush=True)
    return output


if __name__ == "__main__":
    main()
