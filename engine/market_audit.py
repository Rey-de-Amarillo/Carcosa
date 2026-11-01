"""Price-only audit of coherent betting contracts; no orders and no forecasts.

The finite score representatives below cover *all* nonnegative integer scores
for the supported settlement functions, including a certified overflow region.
An attractive inequality is never reported as a filled/executable arbitrage.
"""
from __future__ import annotations

import itertools
import json
import math
from collections import defaultdict
from datetime import datetime, timezone

from engine.markets import MARKET_ALIASES, SELECTION_ALIASES, settle_score, split_line

EPS = 1e-9
SCORE_MARKETS = {"1x2", "double_chance", "dnb", "btts", "correct_score",
                 "totals", "team_totals", "asian_handicap", "european_handicap",
                 "odd_even", "winning_margin"}
EXPECTED = {"1x2": ("home", "draw", "away"), "btts": ("yes", "no"),
            "odd_even": ("odd", "even"), "totals": ("over", "under"),
            "team_totals": ("over", "under"), "dnb": ("home", "away"),
            "european_handicap": ("home", "draw", "away")}
AUDIT_ALIASES = {"alternate_totals": "totals", "alternate_spreads": "asian_handicap",
                 "alternate_team_totals": "team_totals"}


def _number(value):
    if isinstance(value, bool):
        raise ValueError("boolean_numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite_numeric")
    return result


def _stamp(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("missing_timestamp")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("naive_timestamp")
    return result.astimezone(timezone.utc)


def _key(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _normalize(quote, index, now, max_age_seconds, allow_unverified_timestamps):
    q = dict(quote)
    q["quote_id"] = str(q.get("quote_id", index))
    q["market"] = str(q.get("market", q.get("market_id", ""))).strip().lower()
    q["market"] = MARKET_ALIASES.get(q["market"], q["market"])
    q["market"] = AUDIT_ALIASES.get(q["market"], q["market"])
    raw_selection = str(q.get("selection", q.get("outcome", ""))).strip().lower()
    q["selection"] = SELECTION_ALIASES.get(raw_selection, raw_selection)
    q["odds"] = _number(q.get("odds"))
    if q["odds"] <= 1:
        raise ValueError("invalid_odds")
    q["side"] = str(q.get("side", "back")).lower()
    if q["side"] not in ("back", "lay"):
        raise ValueError("invalid_side")
    is_exchange = q["side"] == "lay" or q.get("is_exchange", False)
    commission = q.get("commission_rate", q.get("commission"))
    if commission is None and is_exchange:
        raise ValueError("missing_exchange_commission")
    q["commission_rate"] = _number(commission or 0)
    if not 0 <= q["commission_rate"] < 1:
        raise ValueError("invalid_commission")
    q["period"] = str(q.get("period", "")).strip().lower()
    q["statistic"] = str(q.get("statistic", q.get("score_basis", "match_score"))).strip().lower()
    if q.get("in_play") is True and not q.get("settlement_basis"):
        raise ValueError("unsupported_in_play_basis")
    q["settlement_basis"] = str(q.get("settlement_basis", "whole_period_score"))
    q["settlement_rules"] = q.get("settlement_rules", q.get("rules_id"))
    if not q.get("event_id") or not q["period"] or not q["settlement_rules"]:
        raise ValueError("missing_contract")
    if not q.get("bookmaker"):
        raise ValueError("missing_bookmaker")
    q["_flags"] = []
    try:
        q["_stamp"] = _stamp(q.get("last_update", q.get("captured_at")))
        age = (now - q["_stamp"]).total_seconds()
        if age < -2:
            raise ValueError("future_timestamp")
        if age > max_age_seconds:
            raise ValueError("stale_quote")
    except (ValueError, TypeError) as exc:
        code = str(exc) if str(exc) in {"missing_timestamp", "naive_timestamp", "future_timestamp", "stale_quote"} else "invalid_timestamp"
        if not allow_unverified_timestamps:
            raise ValueError(code) from None
        q["_stamp"] = None
        q["_flags"].append(code)
    if q.get("line") is not None:
        q["line"] = _number(q["line"])
    expected = q.get("expected_outcomes")
    if expected:
        expected = tuple(sorted(set(SELECTION_ALIASES.get(str(v).strip().lower(), str(v).strip().lower()) for v in expected)))
    q["_generic"] = bool(expected) and (q["market"] not in SCORE_MARKETS or
                      (q["market"] == "1x2" and set(expected) != {"home", "draw", "away"}))
    if q["_generic"]:
        q["expected_outcomes"] = expected
        if len(q["expected_outcomes"]) < 2 or q["selection"] not in q["expected_outcomes"]:
            raise ValueError("invalid_expected_outcomes")
    elif q["market"] not in SCORE_MARKETS:
        raise ValueError("unsupported_settlement")
    else:
        # Validate selections, quarter lines, team identifiers and exact scores.
        settle_score(0, 0, q["market"], q["selection"], line=q.get("line"),
                     score=q.get("score"), team=q.get("team"))
        if q["market"] in ("totals", "team_totals") and q["line"] < 0:
            raise ValueError("negative_total_line")
    q["_scope"] = (str(q["event_id"]), q["period"], _key(q["settlement_rules"]), q["statistic"], q["settlement_basis"])
    q["_contract"] = _contract(q)
    if q["commission_rate"]:
        # An explicit market ID allows back/lay winnings to be netted correctly.
        # Without it commission is charged per leg, a conservative lower bound.
        q["_fee_group"] = (str(q["bookmaker"]), str(q["event_id"]),
                           str(q.get("exchange_market_id", "isolated:" + q["quote_id"])))
    else:
        q["_fee_group"] = None
    return q


def _contract(q):
    line = q.get("line")
    if q["market"] == "asian_handicap":
        line = line if q["selection"] == "home" else -line
    return (q["market"], line, q.get("team"),
            tuple(q.get("expected_outcomes", ())) if q.get("_generic") else ())


def _score_bound(quotes):
    """K bounds every threshold; [0, 2K+4]^2 contains each payoff class.

    If both coordinates exceed K, all individual/total/exact-score predicates
    are saturated. Preserve the difference while it lies in [-K,K], otherwise
    replace it by K+1 or K+2 of the same parity. Put the lower coordinate at
    K+1. If just one coordinate exceeds K, retain the other and perform the
    same saturation/parity operation. This proves the overflow coverage; it
    is not a Poisson-tail approximation or a maximum possible football score.
    """
    bound = 1
    for q in quotes:
        if q.get("line") is not None:
            bound = max(bound, math.ceil(abs(q["line"])) + 1)
        if q["market"] == "correct_score":
            score = q["score"] if q.get("score") is not None else q["selection"]
            if isinstance(score, str):
                score = score.replace(":", "-").replace("–", "-").split("-")
            bound = max(bound, *(int(v) for v in score))
    if bound > 64:
        raise ValueError("state_space_too_large")
    return bound


def score_state_space(quotes):
    """Return exhaustive payoff representatives, not outcome probabilities."""
    bound = _score_bound(quotes)
    maximum = 2 * bound + 4
    states = [(h, a) for h in range(maximum + 1) for a in range(maximum + 1)]
    return states, {"kind": "integer_score_payoff_partition", "complete": True,
                    "threshold_bound": bound, "max_representative_score": maximum,
                    "representative_count": len(states), "overflow_checked": True,
                    "overflow_representatives": sum(h > bound or a > bound for h, a in states),
                    "proof": "saturated_thresholds_and_preserved_difference_parity",
                    "external_void_states_included": False}


def _fractions(q, state):
    if q["_generic"]:
        if state not in q["expected_outcomes"]:
            raise ValueError("unknown_categorical_state")
        return (1., 0.) if state == q["selection"] else (0., 1.)
    result = settle_score(*state, q["market"], q["selection"], line=q.get("line"),
                          score=q.get("score"), team=q.get("team"))
    return result["win_fraction"], result["loss_fraction"]


def _raw_return(q, fractions):
    win, loss = fractions
    if q["side"] == "lay":
        # One unit of CAPITAL is liability, not the backer's stake.
        return loss / (q["odds"] - 1) - win
    return win * (q["odds"] - 1) - loss


def portfolio_net(quotes, stakes, state):
    """Net P/L per capital weights, with commission on positive market net.

    Quotes accepted by this public helper are the same normalized input schema
    as audit_event. ``stakes`` mean capital committed: lay liability for lays.
    No fees/taxes other than the supplied commission rate are inferred.
    """
    normalized = []
    for index, quote in enumerate(quotes):
        if "_fee_group" in quote:
            normalized.append(quote)
        else:
            normalized.append(_normalize(quote, index, datetime.now(timezone.utc), math.inf, True))
    if len(stakes) != len(normalized):
        raise ValueError("stake_length_mismatch")
    if len({q["_scope"] for q in normalized}) > 1:
        raise ValueError("incompatible_portfolio_contracts")
    groups, rates, total = defaultdict(float), {}, 0.
    for q, weight in zip(normalized, stakes):
        weight = _number(weight)
        if weight < 0:
            raise ValueError("negative_capital")
        value = weight * _raw_return(q, _fractions(q, state))
        if q["_fee_group"] is None:
            total += value
        else:
            group = q["_fee_group"]
            if group in rates and abs(rates[group] - q["commission_rate"]) > EPS:
                raise ValueError("inconsistent_exchange_commission")
            groups[group] += value
            rates[group] = q["commission_rate"]
    return total + sum(value - rates[group] * max(0., value) for group, value in groups.items())


def _constraints(quotes, raw_rows):
    """Net commission is piecewise linear: take its exact lower envelope."""
    groups = sorted(set(q["_fee_group"] for q in quotes if q["_fee_group"] is not None))
    positions = {group: index for index, group in enumerate(groups)}
    rows = set()
    for raw in raw_rows:
        for mask in range(1 << len(groups)):
            row = tuple(value * (1 - q["commission_rate"] if q["_fee_group"] is not None
                        and mask & (1 << positions[q["_fee_group"]]) else 1.)
                        for q, value in zip(quotes, raw))
            rows.add(tuple(round(value, 12) for value in row))
    rows = sorted(rows)
    # A componentwise larger row cannot bind the minimum on nonnegative weights.
    return [row for row in rows if not any(other != row and all(a <= b for a, b in zip(other, row))
                                            for other in rows)]


def _pair_solution(rows):
    points = {0., 1.}
    for first, second in itertools.combinations(rows, 2):
        denominator = (first[0] - first[1]) - (second[0] - second[1])
        if abs(denominator) > 1e-12:
            x = (second[1] - first[1]) / denominator
            if -EPS <= x <= 1 + EPS:
                points.add(min(1., max(0., x)))
    best = max(points, key=lambda x: min(row[0] * x + row[1] * (1 - x) for row in rows))
    weights = (best, 1 - best)
    return weights, min(sum(a*b for a, b in zip(row, weights)) for row in rows)


def _triple_solution(rows):
    points = {(1., 0., 0.), (0., 1., 0.), (0., 0., 1.)}
    for omitted in range(3):
        active = [i for i in range(3) if i != omitted]
        weights, _ = _pair_solution([tuple(row[i] for i in active) for row in rows])
        point = [0., 0., 0.]
        for i, weight in zip(active, weights):
            point[i] = weight
        points.add(tuple(point))
    for a, b, c in itertools.combinations(rows, 3):
        u = ((a[0]-a[2])-(b[0]-b[2]), (a[1]-a[2])-(b[1]-b[2]), b[2]-a[2])
        v = ((a[0]-a[2])-(c[0]-c[2]), (a[1]-a[2])-(c[1]-c[2]), c[2]-a[2])
        det = u[0]*v[1] - u[1]*v[0]
        if abs(det) < 1e-12:
            continue
        x, y = (u[2]*v[1]-u[1]*v[2])/det, (u[0]*v[2]-u[2]*v[0])/det
        if x >= -EPS and y >= -EPS and x+y <= 1+EPS:
            point = [max(0., x), max(0., y), max(0., 1-x-y)]
            total = sum(point)
            points.add(tuple(value/total for value in point))
    best = max(points, key=lambda point: min(sum(a*b for a, b in zip(row, point)) for row in rows))
    return best, min(sum(a*b for a, b in zip(row, best)) for row in rows)


def _metadata(quotes, weights, max_skew_seconds):
    flags = set(flag for q in quotes for flag in q["_flags"])
    stamps = [q["_stamp"] for q in quotes]
    if any(stamp is None for stamp in stamps):
        flags.add("unverified_quote_clock")
        skew = None
    else:
        skew = (max(stamps) - min(stamps)).total_seconds()
        if skew > max_skew_seconds:
            flags.add("unsynchronized_quotes")
    if not all(q.get("verified_rules", q.get("rules_verified", False)) is True for q in quotes):
        flags.add("unverified_rules")
    if any(q["_generic"] and q.get("verified_outcomes") is not True for q in quotes):
        flags.add("unverified_outcome_partition")
    if not all(q.get("available_limit") is not None for q in quotes):
        flags.add("unverified_limits")
    flags.add("unfilled_legs")
    max_capital = None
    try:
        capacities = [_number(q["available_limit"]) * (q["odds"]-1 if q["side"] == "lay" else 1) / weight
                      for q, weight in zip(quotes, weights) if weight > EPS]
        if capacities:
            max_capital = max(0., min(capacities))
            if max_capital <= EPS:
                flags.add("unavailable_limit")
    except (ValueError, TypeError, KeyError):
        pass
    return {"validation_flags": sorted(flags), "quote_skew_seconds": skew,
            "synchronized": skew is not None and skew <= max_skew_seconds,
            "relation_only": any(flag in flags for flag in ("unverified_quote_clock", "unsynchronized_quotes")),
            "max_capital_from_reported_limits": max_capital}


def _candidate(quotes, weights, states, certificate, kind, max_skew_seconds, extra=None):
    active = [(q, weight) for q, weight in zip(quotes, weights) if weight > EPS]
    quotes, weights = [q for q, _ in active], [weight for _, weight in active]
    returns = [portfolio_net(quotes, weights, state) for state in states]
    minimum, maximum = min(returns), max(returns)
    result = {"type": kind, "status": "theoretical_price_candidate", "event_id": quotes[0]["event_id"],
              "period": quotes[0]["period"], "statistic": quotes[0]["statistic"],
              "settlement_basis": quotes[0]["settlement_basis"], "settlement_rules": quotes[0]["settlement_rules"],
              "verified_arbitrage": False, "executable": False,
              "strictly_positive_under_contract": minimum > EPS,
              "minimum_net_return_per_capital": max(0., minimum) if abs(minimum) < EPS else minimum,
              "maximum_net_return_per_capital": maximum, "state_space": certificate,
              "legs": [{"quote_id": q["quote_id"], "market": q["market"], "selection": q["selection"],
                        "line": q.get("line"), "team": q.get("team"), "score": q.get("score"),
                        "odds": q["odds"], "side": q["side"], "bookmaker": q["bookmaker"],
                        "last_update": q["_stamp"].isoformat() if q["_stamp"] is not None else None,
                        "source": q.get("source"), "available_limit": q.get("available_limit"),
                        "commission_rate": q["commission_rate"], "capital_fraction": weight,
                        "stake_per_unit_capital": weight/(q["odds"]-1) if q["side"] == "lay" else weight}
                       for q, weight in zip(quotes, weights)],
              "assumption": "Todas las patas se llenan a esos precios y aplican el contrato común; no incluye anulaciones externas, impuestos ni cargos adicionales."}
    result.update(_metadata(quotes, weights, max_skew_seconds))
    if extra:
        result.update(extra)
    return result


def _relations(quotes, fractions, raw_rows, states, max_skew_seconds):
    relations = []
    for i, j in itertools.combinations(range(len(quotes)), 2):
        a, b = quotes[i], quotes[j]
        if a["side"] != "back" or b["side"] != "back":
            continue
        if (a["market"] == b["market"] and a["market"] in ("totals", "team_totals")
                and a.get("team") == b.get("team") and {a["selection"], b["selection"]} == {"over", "under"}):
            over, under = (a, b) if a["selection"] == "over" else (b, a)
            if over["line"] < under["line"]:
                weights, minimum = _pair_solution(_constraints([a, b], [tuple(row[k] for k in (i, j)) for row in raw_rows]))
                payoffs = [portfolio_net([a, b], weights, state) for state in states]
                if minimum < -EPS and max(payoffs) > EPS:
                    relations.append({"type": "middle_interval", "quote_ids": [a["quote_id"], b["quote_id"]],
                                      "over_line": over["line"], "under_line": under["line"],
                                      "capital_fractions": list(weights), "minimum_net_return_per_capital": min(payoffs),
                                      "maximum_net_return_per_capital": max(payoffs), "is_arbitrage": False,
                                      "explanation": "El intervalo puede hacer ganar ambas patas; fuera de él hay pérdida. El EV requiere una distribución validada del total."})
        if fractions[i] == fractions[j]:
            relations.append({"type": "identical_settlement", "quote_ids": [a["quote_id"], b["quote_id"]],
                              "markets": [a["market"], b["market"]], "odds": [a["odds"], b["odds"]],
                              "is_arbitrage": False,
                              "explanation": "Mismas fracciones ganadas/perdidas/reembolsadas; elegir mejor precio no crea cobertura."})
        # Standalone net-of-commission dominance: useful price comparison,
        # never a profit claim or a probability estimate.
        values_a = [r[i] - a["commission_rate"]*max(0., r[i]) for r in raw_rows]
        values_b = [r[j] - b["commission_rate"]*max(0., r[j]) for r in raw_rows]
        if all(x >= y-EPS for x, y in zip(values_a, values_b)) and any(x > y+EPS for x, y in zip(values_a, values_b)):
            better, worse = a, b
        elif all(y >= x-EPS for x, y in zip(values_a, values_b)) and any(y > x+EPS for x, y in zip(values_a, values_b)):
            better, worse = b, a
        else:
            continue
        relations.append({"type": "payoff_dominance", "better_quote_id": better["quote_id"],
                          "worse_quote_id": worse["quote_id"], "is_arbitrage": False,
                          "explanation": "Con igual capital, el primer contrato nunca paga menos en los estados del marcador; requiere precios y reglas compatibles."})
    best = {}
    for q in quotes:
        if q["market"] == "1x2" and q["side"] == "back" and q["commission_rate"] == 0:
            if q["selection"] not in best or q["odds"] > best[q["selection"]]["odds"]:
                best[q["selection"]] = q
    for q in quotes:
        if q["side"] != "back" or q["commission_rate"]:
            continue
        if q["market"] == "double_chance":
            selections = {"home_draw": ("home", "draw"), "draw_away": ("draw", "away"),
                          "home_away": ("home", "away")}[q["selection"]]
            if all(s in best for s in selections):
                inverse = sum(1/best[s]["odds"] for s in selections)
                relations.append({"type": "double_chance_replication", "quote_id": q["quote_id"],
                                  "synthetic_odds": 1/inverse, "quoted_odds": q["odds"],
                                  "quoted_price_improvement": q["odds"]-1/inverse,
                                  "components": [{"quote_id": best[s]["quote_id"], "capital_fraction": 1/best[s]["odds"]/inverse} for s in selections],
                                  "is_arbitrage": False})
        if (q["market"] == "dnb" or q["market"] == "asian_handicap" and q.get("line") == 0) and all(s in best for s in (q["selection"], "draw")):
            draw_stake = 1/best["draw"]["odds"]
            relations.append({"type": "dnb_replication", "quote_id": q["quote_id"],
                              "synthetic_odds": best[q["selection"]]["odds"]*(1-draw_stake),
                              "quoted_price_improvement": q["odds"]-best[q["selection"]]["odds"]*(1-draw_stake),
                              "quoted_odds": q["odds"], "draw_refund": 1.,
                              "components": [{"quote_id": best["draw"]["quote_id"], "capital_fraction": draw_stake},
                                             {"quote_id": best[q["selection"]]["quote_id"], "capital_fraction": 1-draw_stake}],
                              "is_arbitrage": False})
    by_id = {q["quote_id"]: q for q in quotes}
    for relation in relations:
        ids = set(relation.get("quote_ids", []))
        for field in ("quote_id", "better_quote_id", "worse_quote_id"):
            if field in relation:
                ids.add(relation[field])
        ids.update(component["quote_id"] for component in relation.get("components", []))
        selected = [by_id[quote_id] for quote_id in sorted(ids)]
        relation.update(_metadata(selected, [1/len(selected)]*len(selected), max_skew_seconds))
        relation.update({"status": "price_relation", "event_id": selected[0]["event_id"],
                         "period": selected[0]["period"], "statistic": selected[0]["statistic"],
                         "verified_arbitrage": False, "executable": False})
    return relations


def _prune_prices(quotes):
    """Keep the best price for each identical leg; preserve named contracts."""
    best = {}
    for q in quotes:
        identity = (q["_contract"], q["selection"], _key(q.get("score")), q["side"],
                    q["commission_rate"], q["_fee_group"])
        old = best.get(identity)
        if old is None or (q["odds"] > old["odds"] if q["side"] == "back" else q["odds"] < old["odds"]):
            best[identity] = q
    return list(best.values())


def _search_priority(q):
    # A reproducible bounded subset: core result contracts before remote
    # alternate lines. No promise that this ordering finds every portfolio.
    market = q["market"]
    order = {"1x2": 0, "double_chance": 1, "dnb": 2, "btts": 3,
             "totals": 4, "asian_handicap": 5, "team_totals": 6,
             "odd_even": 7, "european_handicap": 8, "winning_margin": 9,
             "correct_score": 10}.get(market, 11)
    distance = abs((q.get("line") or 0)-(2.5 if market in ("totals", "team_totals") else 0))
    return order, distance, q["selection"], q["quote_id"]


def audit_event(quotes, *, now=None, max_age_seconds=900, max_skew_seconds=120,
                allow_unverified_timestamps=False, max_cross_quotes=24, max_relation_quotes=64):
    """Audit price identities and long-only covers; return JSON-safe findings.

    All quotes require event_id, market, selection, odds, bookmaker, period,
    settlement_rules and an aware last_update. Optional line/team/score identify
    settlement. Arbitrary non-score markets additionally require their complete
    expected_outcomes. Exchange quotes require side and commission_rate; a shared
    exchange_market_id enables commission on the market's net profit.

    Pure price relations from historical snapshots may be inspected explicitly
    with allow_unverified_timestamps=True. They are marked relation_only and are
    never counted as synchronized mathematical candidates. Search of cross-market
    portfolios is sufficient, not exhaustive: at most 3 legs, capped quote count.
    """
    quotes = list(quotes)
    now = _stamp(now or datetime.now(timezone.utc))
    if max_age_seconds < 0 or max_skew_seconds < 0 or max_cross_quotes < 2 or max_relation_quotes < 2:
        raise ValueError("invalid_audit_limits")
    result = {"summary": {}, "candidates": [], "relations": [], "rejected": []}
    normalized = []
    quote_ids = set()
    for index, quote in enumerate(quotes):
        if not isinstance(quote, dict):
            result["rejected"].append({"quote_id": str(index), "reason": "invalid_quote"})
            continue
        try:
            q = _normalize(quote, index, now, max_age_seconds, allow_unverified_timestamps)
            if q["quote_id"] in quote_ids:
                raise ValueError("duplicate_quote_id")
            quote_ids.add(q["quote_id"])
            normalized.append(q)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            result["rejected"].append({"quote_id": str(quote.get("quote_id", index)), "reason": str(exc)})
    scopes = defaultdict(list)
    for q in normalized:
        scopes[q["_scope"]].append(q)
    event_scopes = defaultdict(set)
    for scope in scopes:
        event_scopes[scope[0]].add(scope[1:])
    for event, contracts in event_scopes.items():
        if len(contracts) > 1:
            result["rejected"].append({"event_id": event, "reason": "incompatible_periods_or_rules_not_compared", "scope_count": len(contracts)})
    searched_pairs = searched_triples = 0
    search_capped = relation_search_capped = False
    retained_count = 0
    coverage = []
    seen = {}

    def append_candidate(candidate):
        signature = tuple(sorted(leg["quote_id"] for leg in candidate["legs"]))
        if signature not in seen:
            seen[signature] = len(result["candidates"])
            result["candidates"].append(candidate)
        elif candidate["minimum_net_return_per_capital"] > result["candidates"][seen[signature]]["minimum_net_return_per_capital"]+EPS:
            result["candidates"][seen[signature]] = candidate

    for scope, scoped_quotes in scopes.items():
        # Conflicting commission rates within an actual exchange market cannot
        # be silently netted together.
        rates = defaultdict(set)
        for q in scoped_quotes:
            if q["_fee_group"] is not None:
                rates[q["_fee_group"]].add(q["commission_rate"])
        bad_groups = {group for group, values in rates.items() if len(values) > 1}
        if bad_groups:
            for q in scoped_quotes:
                if q["_fee_group"] in bad_groups:
                    result["rejected"].append({"quote_id": q["quote_id"], "reason": "inconsistent_exchange_commission"})
            scoped_quotes = [q for q in scoped_quotes if q["_fee_group"] not in bad_groups]
        scoped_quotes = _prune_prices(scoped_quotes)
        retained_count += len(scoped_quotes)
        blocks = defaultdict(list)
        for q in scoped_quotes:
            # Different categorical partitions cannot be compared without a
            # joint state mapping; score-derived families share one scoreboard.
            block = ("generic", q["_contract"]) if q["_generic"] else ("score",)
            blocks[block].append(q)
        for block, block_quotes in blocks.items():
            try:
                if block[0] == "score":
                    states, certificate = score_state_space(block_quotes)
                else:
                    states = list(block_quotes[0]["expected_outcomes"])
                    certificate = {"kind": "declared_exhaustive_categorical", "complete": True,
                                   "representative_count": len(states), "overflow_checked": None,
                                   "external_void_states_included": False}
            except (ValueError, TypeError) as exc:
                result["rejected"].append({"event_id": scope[0], "reason": str(exc)})
                continue
            fractions = [tuple(_fractions(q, state) for state in states) for q in block_quotes]
            raw_rows = [tuple(_raw_return(q, fractions[i][s]) for i, q in enumerate(block_quotes)) for s in range(len(states))]
            if block[0] == "score":
                relation_indices = sorted(range(len(block_quotes)), key=lambda i: _search_priority(block_quotes[i]))[:max_relation_quotes]
                relation_search_capped |= len(block_quotes) > max_relation_quotes
                result["relations"].extend(_relations([block_quotes[i] for i in relation_indices],
                                                     [fractions[i] for i in relation_indices],
                                                     [tuple(row[i] for i in relation_indices) for row in raw_rows],
                                                     states, max_skew_seconds))
            contracts = defaultdict(list)
            for q in block_quotes:
                contracts[q["_contract"]].append(q)
            for contract, contract_quotes in contracts.items():
                market = contract[0]
                expected = contract_quotes[0].get("expected_outcomes") if block[0] == "generic" else EXPECTED.get(market)
                if market == "asian_handicap":
                    expected = ("home", "away")
                if expected is None:
                    # Double chance's three outcomes overlap. Correct-score and
                    # winning-margin lists need explicit tail selections to sum.
                    if market == "double_chance":
                        result["rejected"].append({"event_id": scope[0], "market": market, "reason": "overlapping_outcomes_inverse_sum_invalid"})
                    continue
                best = {}
                for q in contract_quotes:
                    if q["side"] != "back":
                        continue
                    effective = 1+(q["odds"]-1)*(1-q["commission_rate"])
                    selection = q["selection"]
                    if selection not in best or effective > best[selection][0]:
                        best[selection] = (effective, q)
                missing = sorted(set(expected)-set(best))
                if missing:
                    result["rejected"].append({"event_id": scope[0], "market": market, "line": contract[1], "reason": "missing_outcomes", "missing": missing})
                    continue
                chosen = [best[s][1] for s in expected]
                inverse = sum(1/best[s][0] for s in expected)
                if inverse < 1-EPS:
                    weights = [(1/best[s][0])/inverse for s in expected]
                    candidate = _candidate(chosen, weights, states, certificate, "same_market_inverse_sum", max_skew_seconds,
                                           {"inverse_sum": inverse, "inverse_sum_uses_conservative_commission": any(q["commission_rate"] for q in chosen)})
                    # Refunds and half settlements are evaluated on states,
                    # rather than falsely applying 1/inverse-1 to every result.
                    if candidate["minimum_net_return_per_capital"] >= -EPS and candidate["maximum_net_return_per_capital"] > EPS:
                        if not candidate["strictly_positive_under_contract"]:
                            candidate["type"] = "conditional_non_loss_cover"
                        append_candidate(candidate)
            # Retain the best equivalent side/settlement/commission quote. Large
            # prop menus still get the exhaustive same-contract inverse audit.
            unique = {}
            for i, q in enumerate(block_quotes):
                identity = (fractions[i], q["side"], q["commission_rate"], q["_fee_group"])
                old = block_quotes[unique[identity]] if identity in unique else None
                if old is None or (q["odds"] > old["odds"] if q["side"] == "back" else q["odds"] < old["odds"]):
                    unique[identity] = i
            indices = sorted(unique.values(), key=lambda i: _search_priority(block_quotes[i]))
            if len(indices) > max_cross_quotes:
                search_capped = True
                indices = indices[:max_cross_quotes]
            coverage.append({"event_id": scope[0], "period": scope[1], "statistic": scope[3],
                             "settlement_basis": scope[4],
                             "retained_quotes": len(block_quotes), "cross_quote_ids": [block_quotes[i]["quote_id"] for i in indices],
                             "state_space": certificate})
            for size in (2, 3):
                for subset in itertools.combinations(indices, size):
                    selected = [block_quotes[i] for i in subset]
                    raw = list(set(tuple(row[i] for i in subset) for row in raw_rows))
                    # If every leg loses/voids together, strictly positive
                    # coverage is impossible. Keep zero rows to detect pushes.
                    if any(max(row) < -EPS for row in raw):
                        continue
                    constraints = _constraints(selected, raw)
                    if size == 2:
                        searched_pairs += 1
                        weights, minimum = _pair_solution(constraints)
                    else:
                        searched_triples += 1
                        weights, minimum = _triple_solution(constraints)
                    if minimum < -EPS or min(weights) <= EPS:
                        continue
                    candidate = _candidate(selected, weights, states, certificate, "cross_market_cover", max_skew_seconds)
                    if candidate["maximum_net_return_per_capital"] <= EPS:
                        continue
                    if not candidate["strictly_positive_under_contract"]:
                        candidate["type"] = "conditional_non_loss_cover"
                    append_candidate(candidate)
    result["candidates"].sort(key=lambda c: (not c["relation_only"], c["minimum_net_return_per_capital"], c["maximum_net_return_per_capital"]), reverse=True)
    strict = [c for c in result["candidates"] if c["strictly_positive_under_contract"] and not c["relation_only"]]
    result["summary"] = {"input_quotes": len(quotes), "accepted_quotes": len(normalized), "scope_count": len(scopes),
                         "retained_best_prices": retained_count, "collapsed_duplicate_prices": len(normalized)-retained_count,
                         "theoretical_price_candidates": len(result["candidates"]),
                         "synchronized_positive_contract_candidates": len(strict),
                         "verified_arbitrages": 0, "executable": False,
                         "relations": len(result["relations"]), "rejected_checks": len(result["rejected"]),
                         "searched_pairs": searched_pairs, "searched_triples": searched_triples,
                         "cross_search_capped": search_capped, "max_cross_quotes": max_cross_quotes,
                         "relation_search_capped": relation_search_capped, "max_relation_quotes": max_relation_quotes,
                         "search_exhaustive": False, "maximum_cross_market_legs": 3,
                         "no_candidate_does_not_prove_no_arbitrage": True}
    result["coverage"] = coverage
    return result
