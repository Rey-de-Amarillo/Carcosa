#!/usr/bin/env python3
"""Offline settlement and joint-score analysis of observed Bet365 ARG quotes.

Only reads captured offers and prior-only probability grids. Never retrieves a
result, multiplies same-match marginals, places a bet or synthesizes book odds.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.market_audit import _pair_solution, _triple_solution
from engine.markets import MARKET_ALIASES, SELECTION_ALIASES, settle_score
from engine.models_v2 import score_grid

EPS = 1e-9
SCORE_MARKETS = {"1x2", "double_chance", "dnb", "btts", "correct_score", "totals",
                 "team_totals", "asian_handicap", "european_handicap", "odd_even", "winning_margin"}
ALIASES = {"both_teams_score": "btts", "both_teams_to_score": "btts", "result": "1x2",
           "result_btts": "combo", "result_totals": "combo", "combination": "combo",
           "goals_range": "goal_range", "total_goals_range": "goal_range",
           "exact_total_goals": "exact_goals", "half_time_full_time": "htft"}
FT_PERIODS = {"ft", "full_time", "90m", "regulation", "regulation_90m", "full_match"}


class UnsupportedContract(ValueError):
    pass


def finite(value):
    if isinstance(value, bool):
        raise ValueError("boolean_numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite_numeric")
    return result


def canonical(raw, *, inherited_period=None):
    q = dict(raw)
    market = str(q.get("market", "")).strip().lower()
    q["market"] = ALIASES.get(market, MARKET_ALIASES.get(market, market))
    selection = str(q.get("selection", "")).strip().lower()
    q["selection"] = SELECTION_ALIASES.get(selection, selection)
    q["statistic"] = str(q.get("statistic", "goals")).strip().lower()
    period = str(q.get("period", inherited_period or "")).strip().lower()
    q["period"] = "ft" if period in FT_PERIODS else period
    q["period"] = {"first_half": "ht", "half_time": "ht", "1h": "ht", "second_half": "sh", "2h": "sh"}.get(q["period"], q["period"])
    if q["market"] == "team_to_score":
        if q["selection"] not in ("yes", "no") or q.get("team") not in ("home", "away"):
            raise UnsupportedContract("invalid_team_to_score_contract")
        q.update({"market": "team_totals", "selection": "over" if q["selection"] == "yes" else "under", "line": .5})
    if q.get("line") is not None:
        q["line"] = finite(q["line"])
    if q["market"] == "combo":
        if not isinstance(q.get("legs"), list) or not q["legs"]:
            raise UnsupportedContract("missing_explicit_combination_legs")
        q["legs"] = [canonical(leg, inherited_period=q["period"]) for leg in q["legs"]]
    return q


def requires_timing(q):
    return q["period"] != "ft" or q["market"] in ("htft", "win_either_half") or any(requires_timing(leg) for leg in q.get("legs", []))


def _range(value, q, lower_key, upper_key):
    if lower_key not in q and upper_key not in q:
        raise UnsupportedContract("missing_range_bounds")
    lower, upper = q.get(lower_key, 0), q.get(upper_key)
    lower = finite(lower)
    upper = finite(upper) if upper is not None else math.inf
    if lower < 0 or lower != int(lower) or upper != math.inf and (upper != int(upper) or upper < lower):
        raise UnsupportedContract("invalid_integer_range")
    return lower <= value <= upper


def fractions(q, home, away, *, ht=None):
    if q["statistic"] != "goals":
        raise UnsupportedContract("no_ARG_model_for_"+q["statistic"])
    market, selection = q["market"], q["selection"]
    if market == "combo":
        legs = [fractions(leg, home, away, ht=ht) for leg in q["legs"]]
        if any(loss == 1 for win, loss, void in legs):
            return 0., 1., 0.
        if any(win != 1 for win, loss, void in legs):
            raise UnsupportedContract("combination_with_void_or_partial_settlement_requires_Bet365_rule")
        return 1., 0., 0.
    if market == "htft":
        if ht is None:
            raise UnsupportedContract("missing_joint_HT_FT_distribution")
        half, full = q.get("half_selection"), q.get("full_selection")
        if half is None or full is None:
            parts = selection.split("/")
            if len(parts) != 2:
                raise UnsupportedContract("missing_explicit_HTFT_selections")
            half, full = [SELECTION_ALIASES.get(part, part) for part in parts]
        if half not in ("home", "draw", "away") or full not in ("home", "draw", "away"):
            raise UnsupportedContract("invalid_HTFT_selections")
        half_win = settle_score(*ht, "1x2", half)["win_fraction"]
        full_win = settle_score(home, away, "1x2", full)["win_fraction"]
        return (1., 0., 0.) if half_win and full_win else (0., 1., 0.)
    if market == "win_either_half":
        if ht is None:
            raise UnsupportedContract("missing_joint_HT_FT_distribution")
        if selection not in ("home", "away"):
            raise UnsupportedContract("invalid_win_either_half_team")
        direction = 1 if selection == "home" else -1
        first_win = direction*(ht[0]-ht[1]) > 0
        second_win = direction*((home-ht[0])-(away-ht[1])) > 0
        return (1., 0., 0.) if first_win or second_win else (0., 1., 0.)
    if q["period"] != "ft":
        if q["period"] not in ("ht", "sh"):
            raise UnsupportedContract("no_matching_model_for_period_"+q["period"])
        if ht is None:
            raise UnsupportedContract("missing_joint_HT_FT_distribution")
        home, away = ht if q["period"] == "ht" else (home-ht[0], away-ht[1])
    if market in SCORE_MARKETS:
        settled = settle_score(home, away, market, selection, line=q.get("line"), score=q.get("score"), team=q.get("team"))
        return settled["win_fraction"], settled["loss_fraction"], settled["void_fraction"]
    if market in ("goal_range", "exact_goals"):
        if q.get("team") not in (None, "home", "away"):
            raise UnsupportedContract("invalid_goal_range_team")
        value = home if q.get("team") == "home" else away if q.get("team") == "away" else home+away
        if market == "exact_goals":
            target = finite(q.get("goals", selection))
            if target < 0 or target != int(target):
                raise UnsupportedContract("invalid_exact_goals")
            won = value == target
        else:
            won = _range(value, q, "min_goals", "max_goals")
            if selection == "no":
                won = not won
    elif market == "winning_margin_range":
        if selection not in ("home", "away", "draw"):
            raise UnsupportedContract("invalid_winning_team")
        margin = home-away if selection == "home" else away-home
        won = home == away if selection == "draw" else margin > 0 and _range(margin, q, "min_margin", "max_margin")
    elif market == "clean_sheet":
        if q.get("team") not in ("home", "away") or selection not in ("yes", "no"):
            raise UnsupportedContract("invalid_clean_sheet_contract")
        opponent_score = away if q["team"] == "home" else home
        won = (opponent_score == 0) == (selection == "yes")
    elif market == "win_to_nil":
        if selection not in ("home", "away"):
            raise UnsupportedContract("invalid_win_to_nil_contract")
        won = home > away and away == 0 if selection == "home" else away > home and home == 0
    else:
        raise UnsupportedContract("not_identifiable_from_final_goal_score")
    return (1., 0., 0.) if won else (0., 1., 0.)


def threshold_bound(q):
    values = [1.]
    for key in ("line", "min_goals", "max_goals", "min_margin", "max_margin", "goals"):
        if q.get(key) is not None:
            values.append(abs(finite(q[key]))+1)
    if q["market"] == "correct_score":
        score = q["score"] if q.get("score") is not None else q["selection"]
        if isinstance(score, str):
            score = score.replace(":", "-").replace("–", "-").split("-")
        values.extend(finite(value)+1 for value in score)
    if q["market"] == "exact_goals" and q.get("goals") is None:
        values.append(finite(q["selection"])+1)
    for leg in q.get("legs", []):
        values.append(threshold_bound(leg))
    bound = math.ceil(max(values))
    if bound > 32:
        raise UnsupportedContract("threshold_above_exact_search_resource_limit_32")
    return bound


def net(parts, odds):
    return parts[0]*(odds-1)-parts[1]


def model_variants(payload):
    variants = payload.get("variants", {})
    if isinstance(variants, list):
        variants = {item["id"]: item for item in variants}
    result = {}
    for name, model in variants.items():
        grid = model.get("grid")
        if grid is None and isinstance(model.get("forecast"), dict):
            grid = model["forecast"].get("grid")
        if not grid:
            continue
        width = len(grid[0])
        if not width or any(len(row) != width for row in grid):
            raise ValueError("nonrectangular_probability_grid")
        mass = sum(sum(finite(p) for p in row) for row in grid)
        if abs(mass-1) > 1e-6 or any(p < 0 for row in grid for p in row):
            raise ValueError("invalid_probability_mass")
        result[name] = {**model, "grid": grid, "probability_mass": mass}
    return result


def evaluated(q, model, parts_cache=None):
    weighted_win = weighted_loss = positive = push = full_win = 0.
    partial = 0.
    if "states" in model:
        key = ("joint", id(model))
        probabilities = model.setdefault("_probabilities", [state[4] for state in model["states"]])
        generate = lambda: [fractions(q, state[2], state[3], ht=(state[0], state[1])) for state in model["states"]]
    else:
        key = (len(model["grid"]), len(model["grid"][0]))
        probabilities = model.setdefault("_probabilities", [p for row in model["grid"] for p in row])
        generate = lambda: [fractions(q, home, away) for home in range(key[0]) for away in range(key[1])]
    parts_cache = parts_cache if parts_cache is not None else {}
    if key not in parts_cache:
        parts_cache[key] = generate()
    for (win, loss, void), probability in zip(parts_cache[key], probabilities):
        weighted_win += probability*win
        weighted_loss += probability*loss
        positive += probability*(win > 0)
        full_win += probability*(win == 1)
        push += probability*(void == 1)
        partial += probability*(0 < win < 1 or 0 < loss < 1)
    expected = weighted_win*(q["odds"]-1)-weighted_loss
    return {"probability_positive_return": positive, "probability_full_win": full_win,
            "probability_push": push, "probability_partial_settlement": partial,
            "weighted_win_probability": weighted_win, "weighted_loss_probability": weighted_loss,
            "fair_decimal_odds": 1+weighted_loss/weighted_win if weighted_win else None,
            "ev_per_100_staked": 100*expected,
            "binary_break_even_probability": 1/q["odds"] if push < EPS and partial < EPS else None,
            "probability_basis": "exploratory_joint_HT_FT_states" if "states" in model else "one_joint_final_goal_score_grid",
            "probability_mass_used": sum(probabilities), "ordinary_tail_probability_omitted": max(0., 1-sum(probabilities))}


def quantile(values, p):
    ordered = sorted(values)
    index = p*(len(ordered)-1)
    lower = int(index)
    upper = min(lower+1, len(ordered)-1)
    return ordered[lower]+(index-lower)*(ordered[upper]-ordered[lower])


def validate_joint_states(states):
    mass = 0.
    for state in states:
        if len(state) != 5:
            raise ValueError("joint_state_requires_HT_home_HT_away_FT_home_FT_away_probability")
        hth, hta, fth, fta, probability = [finite(value) for value in state]
        if any(value < 0 or value != int(value) for value in (hth, hta, fth, fta)) or hth > fth or hta > fta:
            raise ValueError("invalid_HT_FT_score_path")
        if probability < 0:
            raise ValueError("negative_joint_probability")
        mass += probability
    if not states or abs(mass-1) > 1e-6:
        raise ValueError("joint_probability_mass_not_complete_enough_for_price_evaluation")
    return states


def bootstrap_market_key(q):
    market, selection = q["market"], q["selection"]
    if market == "1x2":
        return {"home": "home_win", "draw": "draw", "away": "away_win"}.get(selection)
    if market == "btts":
        return "btts_"+selection
    if market in ("totals", "team_totals"):
        prefix = q.get("team", "")+"_" if market == "team_totals" else ""
        return prefix+selection+"_"+str(float(q["line"])).replace(".", "_")
    if market == "correct_score" and q.get("score") in ([0, 0], (0, 0)):
        return "under_0_5"
    if market == "combo":
        atoms = frozenset(bootstrap_market_key(leg) for leg in q["legs"])
        lookup = {frozenset(("home_win", "btts_yes")): "home_win_and_btts_yes",
                  frozenset(("away_win", "btts_yes")): "away_win_and_btts_yes",
                  frozenset(("draw", "btts_no")): "draw_and_btts_no",
                  frozenset(("btts_no", "under_2_5")): "btts_no_and_under_2_5",
                  frozenset(("btts_yes", "over_2_5")): "btts_yes_and_over_2_5",
                  frozenset(("home_win", "under_3_5")): "home_win_and_under_3_5",
                  frozenset(("away_win", "under_3_5")): "away_win_and_under_3_5"}
        return lookup.get(atoms)
    return None


def price_partitions(raw_quotes):
    groups = collections.defaultdict(list)
    expected = {"1x2": {"home", "draw", "away"}, "totals": {"over", "under"},
                "team_totals": {"over", "under"}, "dnb": {"home", "away"},
                "btts": {"yes", "no"}, "goal_range": {"yes", "no"},
                "count_total_3way": {"over", "exact", "under"}}
    for raw in raw_quotes:
        if raw.get("offered_boost") or raw.get("mapping_status") in ("rules_unverified", "assumed", "unverified"):
            continue
        q = canonical(raw)
        if q["market"] not in expected:
            continue
        key = (q["period"], q["statistic"], q["market"], q.get("line"), q.get("team"), q.get("min_goals"), q.get("max_goals"))
        groups[key].append(q)
    boards = []
    for key, quotes in groups.items():
        by_selection = {}
        for q in quotes:
            odds = finite(q["odds"])
            if odds <= 1:
                continue
            q["odds"] = odds
            if q["selection"] not in by_selection or odds > by_selection[q["selection"]]["odds"]:
                by_selection[q["selection"]] = q
        if set(by_selection) != expected[key[2]]:
            continue
        s = sum(1/q["odds"] for q in by_selection.values())
        conditional = key[2] == "dnb" or key[2] in ("totals", "team_totals") and key[3] % 1 != .5
        boards.append({"period": key[0], "statistic": key[1], "market": key[2], "line": key[3], "team": key[4],
                       "quote_ids": [q["id"] for q in by_selection.values()], "inverse_odds_sum": s,
                       "overround_price_index": s-1,
                       "interpretation": "conditional_or_partial_settlement_price_index" if conditional else "exclusive_complete_outcome_price_index",
                       "is_roi_or_true_expected_loss": False, "verified_rules": False, "executable": False})
    return boards


def synthetic_replications(quotes):
    best = {}
    for q in quotes:
        if q["market"] == "1x2" and (q["selection"] not in best or q["odds"] > best[q["selection"]]["odds"]):
            best[q["selection"]] = q
    rows = []
    for q in quotes:
        is_dnb = q["market"] == "dnb" or q["market"] == "asian_handicap" and q.get("line") == 0
        if is_dnb and q["selection"] in best and "draw" in best:
            draw_fraction = 1/best["draw"]["odds"]
            synthetic = best[q["selection"]]["odds"]*(1-draw_fraction)
            rows.append({"type": "dnb_replication", "quote_id": q["id"], "quoted_odds": q["odds"],
                         "synthetic_odds": synthetic, "quoted_odds_improvement": q["odds"]-synthetic,
                         "components": [{"id": best["draw"]["id"], "capital_fraction": draw_fraction},
                                        {"id": best[q["selection"]]["id"], "capital_fraction": 1-draw_fraction}],
                         "is_profit_proof": False})
        is_dc = q["market"] == "double_chance" or q["market"] == "asian_handicap" and q.get("line") == .5
        if is_dc:
            dc_selection = q["selection"] if q["market"] == "double_chance" else ("home_draw" if q["selection"] == "home" else "draw_away")
            sides = {"home_draw": ("home", "draw"), "draw_away": ("draw", "away"), "home_away": ("home", "away")}.get(dc_selection, ())
            if len(sides) == 2 and all(side in best for side in sides):
                inverse = sum(1/best[side]["odds"] for side in sides)
                rows.append({"type": "double_chance_replication", "quote_id": q["id"], "quoted_odds": q["odds"],
                             "synthetic_odds": 1/inverse, "quoted_odds_improvement": q["odds"]-1/inverse,
                             "components": [{"id": best[side]["id"], "capital_fraction": 1/best[side]["odds"]/inverse} for side in sides],
                             "is_profit_proof": False})
    return rows


def price_analysis(quotes, state_rows, fraction_signatures, certificate, max_triple_legs=18):
    """Exact-score relations and sufficient 2/3-leg long-only covers."""
    by_payoff = {}
    for i, q in enumerate(quotes):
        signature = fraction_signatures[i]
        if signature not in by_payoff or q["odds"] > quotes[by_payoff[signature]]["odds"]:
            by_payoff[signature] = i
    relations, covers = [], []
    for i, j in itertools.combinations(range(len(quotes)), 2):
        a, b = quotes[i], quotes[j]
        if fraction_signatures[i] == fraction_signatures[j]:
            relations.append({"type": "identical_settlement", "quote_ids": [a["id"], b["id"]],
                              "odds": [a["odds"], b["odds"]], "is_profit_proof": False})
        if all(row[i] >= row[j]-EPS for row in state_rows) and any(row[i] > row[j]+EPS for row in state_rows):
            relations.append({"type": "payoff_dominance", "better_id": a["id"], "worse_id": b["id"], "is_profit_proof": False})
        elif all(row[j] >= row[i]-EPS for row in state_rows) and any(row[j] > row[i]+EPS for row in state_rows):
            relations.append({"type": "payoff_dominance", "better_id": b["id"], "worse_id": a["id"], "is_profit_proof": False})
    def priority(i):
        q = quotes[i]
        if q["market"] == "totals":
            return (4 if q.get("line") == 2.5 else 7), abs(q.get("line", 2.5)-2.5), q["id"]
        return {"1x2": 0, "btts": 1, "dnb": 2, "double_chance": 3, "combo": 5,
                "goal_range": 6, "team_totals": 8, "correct_score": 9}.get(q["market"], 10), 0, q["id"]
    indices = sorted(by_payoff.values(), key=priority)
    searched = collections.Counter()
    seen = set()
    for size in (2, 3):
        pool = indices if size == 2 else indices[:max_triple_legs]
        for subset in itertools.combinations(pool, size):
            rows = list(set(tuple(row[i] for i in subset) for row in state_rows))
            if any(max(row) < -EPS for row in rows):
                continue
            searched[str(size)] += 1
            weights, minimum = _pair_solution(rows) if size == 2 else _triple_solution(rows)
            maximum = max(sum(r*w for r, w in zip(row, weights)) for row in rows)
            if minimum < -EPS or maximum <= EPS or min(weights) <= EPS:
                continue
            signature = tuple(quotes[i]["id"] for i in subset)
            if signature in seen:
                continue
            seen.add(signature)
            covers.append({"type": "theoretical_positive_cover" if minimum > EPS else "conditional_non_loss_cover",
                           "legs": [{"id": quotes[i]["id"], "capital_fraction": weight} for i, weight in zip(subset, weights)],
                           "minimum_net_per_100": minimum*100, "maximum_net_per_100": maximum*100,
                           "state_space": certificate, "verified_arbitrage": False, "executable": False,
                           "assumption": "Contratos supuestos compatibles, precios simultáneamente disponibles y todas las patas aceptadas; no acreditado."})
    combo_groups = collections.defaultdict(list)
    for i, q in enumerate(quotes):
        if q["market"] == "combo":
            skeleton = tuple(sorted((leg["market"], str(leg.get("line")), str(leg.get("team")), leg["period"]) for leg in q["legs"]))
            combo_groups[skeleton].append(i)
    combo_partitions = []
    for skeleton, grouped in combo_groups.items():
        best = {}
        for i in grouped:
            signature = fraction_signatures[i]
            if signature not in best or quotes[i]["odds"] > quotes[best[signature]]["odds"]:
                best[signature] = i
        selected = list(best.values())
        if len(selected) < 2:
            continue
        if any(any(parts not in ((1., 0., 0.), (0., 1., 0.)) for parts in fraction_signatures[i]) for i in selected):
            continue
        if not all(sum(fraction_signatures[i][state][0] for i in selected) == 1 for state in range(len(state_rows))):
            continue
        inverse = sum(1/quotes[i]["odds"] for i in selected)
        combo_partitions.append({"contract_skeleton": skeleton, "quote_ids": [quotes[i]["id"] for i in selected],
                                 "inverse_odds_sum": inverse, "overround_price_index": inverse-1,
                                 "exclusive_complete_partition_proven_on_all_score_classes": True,
                                 "is_roi_or_true_expected_loss": False, "executable": False})
        if inverse < 1-EPS:
            weights = [(1/quotes[i]["odds"])/inverse for i in selected]
            net_values = [sum(row[i]*weight for i, weight in zip(selected, weights)) for row in state_rows]
            covers.append({"type": "complete_partition_inverse_price_candidate",
                           "legs": [{"id": quotes[i]["id"], "capital_fraction": weight} for i, weight in zip(selected, weights)],
                           "minimum_net_per_100": min(net_values)*100, "maximum_net_per_100": max(net_values)*100,
                           "state_space": certificate, "verified_arbitrage": False, "executable": False})
    return {"relations": relations, "covers": sorted(covers, key=lambda item: item["minimum_net_per_100"], reverse=True),
            "complete_combo_partitions": combo_partitions,
            "retained_best_settlement_prices": len(indices), "triple_quote_ids": [quotes[i]["id"] for i in indices[:max_triple_legs]],
            "searched_pairs": searched["2"], "searched_triples": searched["3"],
            "triple_leg_limit": max_triple_legs, "triple_search_capped": len(indices) > max_triple_legs,
            "search_exhaustive": False, "complete_normal_score_states": certificate["complete"],
            "external_void_states_included": False, "verified_arbitrages": 0, "executable": False}


def analyze(quote_path, model_path, output_path):
    input_bytes = {str(path): Path(path).read_bytes() for path in (quote_path, model_path)}
    captured = json.loads(input_bytes[str(quote_path)])
    probability_source = json.loads(input_bytes[str(model_path)])
    input_hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in input_bytes.items()}
    archive_dir = ROOT/"data/analysis/arg_betting_inputs"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archives = {}
    for name, raw in input_bytes.items():
        target = archive_dir/(input_hashes[name]+".json")
        if not target.exists():
            target.write_bytes(raw)
        archives[name] = str(target.relative_to(ROOT))
    variants = model_variants(probability_source)
    if not variants:
        raise ValueError("No final-score probability variants supplied")
    raw_quotes = captured.get("quotes", [])
    fixture = captured.get("fixture", probability_source.get("fixture", {}))
    fixture_date = probability_source.get("as_of_date", fixture.get("date", "2026-10-30"))
    if str(captured.get("meta", {}).get("event_id")) != str(probability_source.get("fixture", {}).get("bet365_event_id")):
        raise ValueError("Captured event and forecast event identifiers do not match")
    for name, model in variants.items():
        previous = model.get("training_max_date")
        if not previous or previous >= fixture_date:
            raise ValueError("Missing or leaking training date in model " + name)
    primary = probability_source.get("primary_variant", "window_730")
    if primary not in variants:
        primary = next(iter(variants))
    joint_source = probability_source.get("joint_ht_ft", {})
    timing_model = {"states": validate_joint_states(joint_source["states"])} if joint_source.get("states") else None
    bootstrap_models = [score_grid(draw["home_rate"], draw["away_rate"], draw["rho_applied"]) for draw in probability_source.get("parameter_sensitivity_bootstrap", {}).get("draws", [])]
    normalized, rows = [], []
    ids = set()
    for i, raw in enumerate(raw_quotes):
        record = {"id": str(raw.get("id", raw.get("quote_id", i))), "label": raw.get("label", raw.get("name")),
                  "observed_offer": raw, "status": "data_insufficient", "probability": None, "ev_per_100_staked": None,
                  "executed_bets": 0, "executable": False}
        try:
            offered_odds = finite(raw.get("odds"))
            if offered_odds > 1:
                record.update({"odds": offered_odds, "nominal_break_even_if_binary_no_push": 1/offered_odds})
        except (ValueError, TypeError):
            pass
        try:
            if record["id"] in ids:
                raise ValueError("duplicate_quote_id")
            ids.add(record["id"])
            q = canonical(raw)
            q["id"] = record["id"]
            if q.get("offered_boost") and q.get("promotion_terms_verified") is not True:
                raise UnsupportedContract("promotion_conditions_and_costs_not_verified")
            if q.get("mapping_status") in ("rules_unverified", "assumed", "unverified"):
                raise UnsupportedContract("contract_mapping_or_BetBuilder_settlement_not_verified")
            q["odds"] = finite(q.get("odds"))
            if q["odds"] <= 1:
                raise ValueError("invalid_decimal_odds")
            bound = threshold_bound(q)
            # Validate overflow states as well as model-grid states; ambiguous
            # BetBuilder voids cannot be hidden by a tiny model probability.
            timing = requires_timing(q)
            if timing:
                if timing_model is None:
                    raise UnsupportedContract("missing_joint_HT_FT_distribution")
                methods = {"ht_thinning_exploratory": evaluated(q, timing_model)}
                quote_primary = "ht_thinning_exploratory"
            else:
                for h in range(2*bound+5):
                    for a in range(2*bound+5):
                        fractions(q, h, a)
                quote_primary = primary
                methods = {name: evaluated(q, model) for name, model in variants.items()}
            chosen = methods[quote_primary]
            evs = {name: method["ev_per_100_staked"] for name, method in methods.items()}
            record.update({"status": "modelled_exploratory_timing_contract" if timing else "modelled_final_score_contract", "contract": q,
                           "odds": q["odds"], "probability": chosen["probability_positive_return"],
                           "fair_decimal_odds": chosen["fair_decimal_odds"],
                           "break_even_probability": chosen["binary_break_even_probability"],
                           "ev_per_100_staked": chosen["ev_per_100_staked"], "primary_method": quote_primary,
                           "methods": methods, "minimum_ev_across_methods_per_100": min(evs.values()),
                           "maximum_ev_across_methods_per_100": max(evs.values()),
                           "worst_method": min(evs, key=evs.get), "best_method": max(evs, key=evs.get),
                           "sensitivity_is_confidence_interval": False,
                           "sensitivity_available_method_count": len(methods),
                           "sensitivity_note": "Rango entre ventanas/modelos históricos declarados; no cota validada ni garantía de EV real.",
                           "settlement_note": "P incluye medias ganancias. En reembolsos/cuartos, cuota justa usa fracciones de capital ganadas/perdidas; no 1/P simple."})
            if timing:
                record["timing_model_status"] = probability_source.get("first_half", {}).get("status", "exploratory")
                record["timing_model_warning"] = probability_source.get("first_half", {}).get("warning")
            bootstrap = probability_source.get("parameter_sensitivity_bootstrap", {}).get("markets", {}).get(bootstrap_market_key(q))
            if not timing and bootstrap_models:
                parts_cache = {}
                evaluations = [evaluated(q, model, parts_cache) for model in bootstrap_models]
                ps = [value["probability_positive_return"] for value in evaluations]
                es = [value["ev_per_100_staked"] for value in evaluations]
                record["parameter_bootstrap_sensitivity"] = {"draws": len(evaluations), "probability_p025": quantile(ps, .025),
                    "probability_p50": quantile(ps, .5), "probability_p975": quantile(ps, .975),
                    "ev_per_100_p025": quantile(es, .025), "ev_per_100_p975": quantile(es, .975),
                    "minimum_sampled_ev_per_100": min(es), "maximum_sampled_ev_per_100": max(es),
                    "is_calibrated_true_probability_confidence_interval": False,
                    "note": probability_source.get("parameter_sensitivity_bootstrap", {}).get("interval_label")}
            elif not timing and bootstrap and chosen["binary_break_even_probability"] is not None:
                record["parameter_bootstrap_sensitivity"] = {"probability_p025": bootstrap["p025"],
                    "probability_p50": bootstrap["p50"], "probability_p975": bootstrap["p975"],
                    "ev_per_100_p025": 100*(bootstrap["p025"]*q["odds"]-1),
                    "ev_per_100_p975": 100*(bootstrap["p975"]*q["odds"]-1),
                    "is_calibrated_true_probability_confidence_interval": False,
                    "note": probability_source.get("parameter_sensitivity_bootstrap", {}).get("interval_label")}
            if not timing:
                normalized.append(q)
        except (ValueError, TypeError, KeyError) as exc:
            record["reason"] = str(exc)
        rows.append(record)
    if normalized:
        bound = max(threshold_bound(q) for q in normalized)
        maximum = 2*bound+4
        states = list(itertools.product(range(maximum+1), repeat=2))
        certificate = {"kind": "integer_score_payoff_partition_with_boolean_combinations", "complete": True,
                       "threshold_bound": bound, "max_representative_score": maximum,
                       "overflow_checked": True, "representative_count": len(states),
                       "proof": "All predicates depend on bounded h,a,h+a,h-a thresholds/parity; saturating beyond K preserves every Boolean combination.",
                       "external_void_states_included": False}
        fraction_signatures = [tuple(fractions(q, h, a) for h, a in states) for q in normalized]
        state_rows = [tuple(net(fraction_signatures[i][s], q["odds"]) for i, q in enumerate(normalized)) for s in range(len(states))]
        price_findings = price_analysis(normalized, state_rows, fraction_signatures, certificate)
        price_findings["synthetic_replications"] = synthetic_replications(normalized)
        records_by_id = {row["id"]: row for row in rows}
        for i, q in enumerate(normalized):
            records_by_id[q["id"]]["ordinary_state_minimum_net_per_100"] = 100*min(row[i] for row in state_rows)
            records_by_id[q["id"]]["ordinary_state_maximum_net_per_100"] = 100*max(row[i] for row in state_rows)
    else:
        price_findings = {"relations": [], "covers": [], "verified_arbitrages": 0, "executable": False}
    modelled = [row for row in rows if row["status"].startswith("modelled_")]
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "fixture": fixture,
              "capture_meta": captured.get("meta", {}), "probability_meta": {k: v for k, v in probability_source.items() if k != "variants"},
              "primary_method": primary, "quotes": rows, "price_analysis": price_findings,
              "price_partitions": price_partitions(raw_quotes),
              "summary": {"observed_offers": len(raw_quotes), "modelled_offers": len(modelled),
                          "insufficient_data_offers": len(rows)-len(modelled),
                          "modelled_final_score_contracts": sum(row["status"] == "modelled_final_score_contract" for row in modelled),
                          "modelled_exploratory_timing_contracts": sum(row["status"] == "modelled_exploratory_timing_contract" for row in modelled),
                          "positive_primary_model_ev": sum(row["ev_per_100_staked"] > 0 for row in modelled),
                          "positive_ev_across_supplied_methods": sum(row["minimum_ev_across_methods_per_100"] > 0 for row in modelled),
                          "positive_ev_across_two_FT_windows": sum(row["status"] == "modelled_final_score_contract" and row["minimum_ev_across_methods_per_100"] > 0 for row in modelled),
                          "positive_exploratory_timing_ev": sum(row["status"] == "modelled_exploratory_timing_contract" and row["ev_per_100_staked"] > 0 for row in modelled),
                          "FT_positive_parameter_bootstrap_p025_ev": sum(row.get("parameter_bootstrap_sensitivity", {}).get("ev_per_100_p025", -math.inf) > 0 for row in modelled),
                          "modelled_periods": dict(collections.Counter(row["contract"]["period"] for row in modelled)),
                          "model_uncertainty_is_not_estimated_by_method_range": True,
                          "verified_arbitrages": 0, "executed_bets": 0},
              "ranking": {"highest_primary_model_ev": [row["id"] for row in sorted(modelled, key=lambda row: row["ev_per_100_staked"], reverse=True)],
                          "highest_minimum_method_ev": [row["id"] for row in sorted(modelled, key=lambda row: row["minimum_ev_across_methods_per_100"], reverse=True)],
                          "FT_highest_parameter_bootstrap_p025_ev": [row["id"] for row in sorted((row for row in modelled if "parameter_bootstrap_sensitivity" in row), key=lambda row: row["parameter_bootstrap_sensitivity"]["ev_per_100_p025"], reverse=True)]},
              "limitations": ["Cuotas observadas en una captura; no ejecución ni disponibilidad simultánea comprobada.",
                              "Combinaciones calculadas por intersección del mismo marcador conjunto; nunca por producto de marginales.",
                              "No se generan cuotas Bet365 multiplicando cuotas individuales. Sólo se analiza el precio expresamente capturado.",
                              "El CSV ARG no tiene descanso; HT/2H se añaden sólo mediante el modelo conjunto exploratorio suministrado, basado en 61 eventos de 2026. Su validación es pequeña y seleccionada por equipos.",
                              "No se extrapolan tiros, córners, tarjetas, jugadores ni primeros 10 minutos desde el grid de goles. Promociones sin términos verificados quedan nulas.",
                              "El modelo y sus ventanas pueden compartir errores; EV positivo en todas ellas no demuestra una ventaja rentable.",
                              "Las liquidaciones normales no modelan anulaciones, promociones, impuestos ni restricciones de cuenta."],
              "source_sha256": {**input_hashes, str(Path(__file__)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "input_archives": archives,
              "source_changed_during_analysis": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest for name, digest in input_hashes.items()},
              "executable": False}
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quotes", default=str(ROOT/"data/analysis/bet365_arg_quotes.json"))
    parser.add_argument("--model", default=str(ROOT/"data/analysis/arg_fixture_probabilities.json"))
    parser.add_argument("--output", default=str(ROOT/"data/analysis/arg_betting_numbers.json"))
    args = parser.parse_args()
    report = analyze(args.quotes, args.model, args.output)
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
