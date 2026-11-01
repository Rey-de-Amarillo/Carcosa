#!/usr/bin/env python3
"""Joint football price-only portfolio search, with exact no-arbitrage certificates.

Nonnegative stakes sum to one. Every quoted selection retains its own gross
payoff, including quarter-handicap refunds. Correlated selections are never
multiplied. A rational dual probability supported on VALID finite game states
with every contract's expected gross payoff <=1 rules out ANY guaranteed-profit
mixture on the full (unbounded) outcome domain. A finite-grid positive alone is
NOT sufficient: those cases are explicitly unverified, not claimed arbitrages.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
import time
import warnings

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/analysis/sgodds_portfolio_search.json"
REPORT = ROOT / "COMBINACIONES_SGODDS.md"
FT_EXACT = frozenset((h, a) for h in range(6) for a in range(6) if (h, a) != (5, 5))
HT_EXACT = frozenset((h, a) for h in range(3) for a in range(3))
RULES_URL = "https://www.singaporepools.com.sg/en/rules/Pages/pdf/football-betting-game-rules.pdf"
FIRST_NONE, FIRST_HOME, FIRST_AWAY = 0, 1, 2


@dataclass(frozen=True)
class Contract:
    source_field: str
    market: str
    period: str
    selection: str
    line: float | None
    odds: float

    def key(self):
        return self.source_field, self.market, self.period, self.selection, self.line


def asian_parts(line):
    quarters = round(4 * line)
    if abs(quarters / 4 - line) > 1e-10:
        raise ValueError("Only quarter-goal lines are supported")
    if quarters % 2:
        lower = math.floor(line * 2) / 2
        return (lower, lower + .5)
    return (line,)


def settle_sign(sign):
    return (1.0, 0.0) if sign > 0 else (0.0, 1.0) if sign == 0 else (0.0, 0.0)


def winner(h, a):
    return "home" if h > a else "away" if a > h else "draw"


def contract_parts(contract, state):
    """Return (stake fraction winning, stake fraction refunded)."""
    hh, ha, fh, fa, first_ht, first_ft = state
    if contract.market == "ht_ft_result":
        return (float(contract.selection == winner(hh, ha) + "/" + winner(fh, fa)), 0.0)
    h, a, first = (hh, ha, first_ht) if contract.period == "HT" else (fh, fa, first_ft)
    total = h + a
    market, selection = contract.market, contract.selection
    if market.endswith("_1x2"):
        won = selection == winner(h, a)
    elif market.endswith("_correct_score"):
        offered = HT_EXACT if contract.period == "HT" else FT_EXACT
        won = ((h, a) not in offered) if selection == "other" else (h, a) == tuple(map(int, selection.split("-")))
    elif market.endswith("_exact_total_goals"):
        won = total >= int(selection[:-1]) if selection.endswith("+") else total == int(selection)
    elif market.endswith("_btts"):
        won = (h > 0 and a > 0) == (selection == "yes")
    elif market.endswith("_odd_even"):
        won = (total % 2 == 1) == (selection == "odd")
    elif market.endswith("_first_team_to_score"):
        won = first == {"no_goal": FIRST_NONE, "home": FIRST_HOME, "away": FIRST_AWAY}[selection]
    elif market.endswith("_goal_total"):
        parts = [settle_sign(total - line if selection == "over" else line - total) for line in asian_parts(contract.line)]
        return tuple(sum(x[i] for x in parts) / len(parts) for i in (0, 1))
    elif market.endswith("_asian_handicap") or market == "ft_half_goal_handicap_source_label":
        if market == "ft_half_goal_handicap_source_label" and abs(contract.line % 1 - .5) > 1e-10:
            raise ValueError("1/2 Goal contract needs a half-integer handicap")
        margin = h - a if selection == "home" else a - h
        parts = [settle_sign(margin + line) for line in asian_parts(contract.line)]
        return tuple(sum(x[i] for x in parts) / len(parts) for i in (0, 1))
    else:
        raise ValueError("Unsupported market: " + market)
    return float(won), 0.0


def first_choices(h, a):
    if not h and not a:
        return (FIRST_NONE,)
    return tuple(x for x, possible in ((FIRST_HOME, h > 0), (FIRST_AWAY, a > 0)) if possible)


def valid_joint_states(ft_cap=6, ht_cap=3):
    result = []
    for hh in range(ht_cap + 1):
        for ha in range(ht_cap + 1):
            for fh in range(hh, ft_cap + 1):
                for fa in range(ha, ft_cap + 1):
                    for first_ht in first_choices(hh, ha):
                        for first_ft in ((first_ht,) if first_ht else first_choices(fh, fa)):
                            result.append((hh, ha, fh, fa, first_ht, first_ft))
    return tuple(result)


def validate_state(state):
    hh, ha, fh, fa, ht_first, ft_first = state
    return (0 <= hh <= fh and 0 <= ha <= fa and ht_first in first_choices(hh, ha)
            and ft_first in first_choices(fh, fa) and (not ht_first or ht_first == ft_first))


def single_period_complete_bound(contracts):
    """Sufficient score box for one-period payoff equivalence, including tails.

    Outside it, total exceeds every total threshold and the score is 'other'.
    Preserve d=h-a exactly inside difference breakpoints; outside, replace d
    with the same-parity D+1 or D+2. Choose the smaller positive score M>T,E.
    Preserve zero-vs-positive and the feasible first-scoring team. This retains
    total parity, all thresholds, result, exactscore membership, BTTS and AH.
    """
    total = max([9] + [abs(c.line) for c in contracts if c.market.endswith("_goal_total") and c.line is not None])
    diff = max([0] + [abs(c.line) for c in contracts if "handicap" in c.market and c.line is not None])
    return max(7, math.ceil(total) + 2) + math.ceil(diff) + 4


def complete_payoff_superset(contracts, np):
    """Exact complete payoff-pattern representatives, possibly impossible joint pairs.

    Each period is individually complete over unbounded scores. Their Cartesian
    product is a SUPERSET of realizable combined-period patterns. First-goal
    equality when HT has a goal is retained. Proving positive return even on
    this superset proves positive on all real completed-match score histories.
    """
    periods = {c.period for c in contracts}
    if periods == {"FT"} or periods == {"HT"}:
        period = next(iter(periods)); bound = single_period_complete_bound(contracts)
        states = tuple((0, 0, h, a, 0, first) if period == "FT" else (h, a, h, a, first, first)
                       for h in range(bound + 1) for a in range(bound + 1) for first in first_choices(h, a))
        return states, {"type": "complete_single_period", "period": period, "score_bound": bound}
    representatives = {}
    bounds = {}
    for period in ("HT", "FT"):
        selected = [c for c in contracts if c.period == period]
        # HT/FT result contracts also need the result sign, and first-scoring
        # constraints need none/home/away even if no quoted contract uses it.
        prefix = period.lower()
        for selection in ("home", "draw", "away"):
            selected.append(Contract("_dummy_result_" + selection, prefix + "_1x2", period, selection, None, 2))
        for selection in ("no_goal", "home", "away"):
            selected.append(Contract("_dummy_first_" + selection, prefix + "_first_team_to_score", period, selection, None, 2))
        bound = single_period_complete_bound(selected); bounds[period] = bound
        states = tuple((0, 0, h, a, 0, first) if period == "FT" else (h, a, h, a, first, first)
                       for h in range(bound + 1) for a in range(bound + 1) for first in first_choices(h, a))
        _, _, representatives[period] = matrix_template(tuple(c.key() for c in selected), states, np)
    combined = []
    for ht in representatives["HT"]:
        for ft in representatives["FT"]:
            if ht[4] and ht[4] != ft[5]:
                continue
            combined.append((ht[0], ht[1], ft[2], ft[3], ht[4], ft[5]))
    return tuple(combined), {"type": "complete_period_product_superset", "score_bounds": bounds,
                             "allows_impossible_score_decreases": True}


def verify_portfolio_complete(portfolio, *, np, recover_simple_rationals=False):
    contracts = [Contract(p["field"], p["market"], p["period"], p["selection"], p["line"], p["odds"]) for p in portfolio]
    states, domain = complete_payoff_superset(contracts, np)
    w2, r2, representatives = matrix_template(tuple(c.key() for c in contracts), states, np)
    decimals = max(max(0, -Decimal(str(x.odds)).as_tuple().exponent) for x in contracts)
    scale = 10 ** decimals
    ticks = np.asarray([int(Decimal(str(x.odds)) * scale) for x in contracts], dtype=np.int64)
    payoff_ticks = w2.astype(np.int64) * ticks + r2.astype(np.int64) * scale
    weights = np.asarray([p["stake_fraction"] for p in portfolio]); weights /= weights.sum()
    if recover_simple_rationals:
        fractions = [Fraction(float(w)).limit_denominator(1_000_000) for w in weights]
        common = math.lcm(*(f.denominator for f in fractions))
        # Python integers retain exactness even when recovered denominators have
        # a large least common multiple. This path is only for weak candidates.
        stake_counts = np.asarray([f.numerator * (common // f.denominator) for f in fractions], dtype=object)
    else:
        stake_counts = np.rint(weights * 1_000_000_000).astype(np.int64)
    denominator = int(stake_counts.sum())
    numerators = payoff_ticks @ stake_counts
    gross_denominator = 2 * scale * denominator
    worst = int(numerators.argmin()); minimum = int(numerators[worst])
    # A concrete 100-unit budget with cent stakes and every ticket payout rounded
    # DOWN separately, so this does not obtain profit through payout rounding.
    cents = np.floor(weights * 10000).astype(np.int64)
    remainder = 10000 - int(cents.sum())
    ranking = np.argsort(-(weights * 10000 - cents))
    cents[ranking[:remainder]] += 1
    cent_returns = np.floor_divide(payoff_ticks * cents, 2 * scale).sum(axis=1)
    exact_weights = stake_counts / denominator
    haircut = ((w2 * np.asarray([p.odds * .99 for p in contracts]) + r2) / 2) @ exact_weights
    for p, count in zip(portfolio, cents):
        p["stake_on_100_budget"] = int(count) / 100
    return {"domain": domain, "payoff_pattern_count": len(representatives),
            "exact_minimum_gross_numerator": minimum, "exact_gross_denominator": gross_denominator,
            "exact_maximum_gross_numerator": int(numerators.max()),
            "exact_minimum_gross": minimum / gross_denominator,
            "positive_on_all_completed_match_patterns": minimum > gross_denominator,
            "nonnegative_all_and_positive_some_patterns": minimum >= gross_denominator and int(numerators.max()) > gross_denominator,
            "worst_representative_state": list(representatives[worst]),
            "rational_stake_counts": stake_counts.tolist(), "rational_stake_denominator": denominator,
            "minimum_return_on_100_cent_stakes_payouts_rounded_down": int(cent_returns.min()) / 100,
            "minimum_profit_after_0_5pct_capital_cost": minimum / gross_denominator - 1 - .005,
            "minimum_profit_after_1pct_odds_haircut": float(haircut.min()) - 1,
            "minimum_profit_after_haircut_and_capital_cost": float(haircut.min()) - 1 - .005}


def search_weak_portfolio(contracts, states, *, np, linprog):
    """Check no-loss/positive-somewhere portfolios, including whole-line pushes."""
    w2, r2, _ = matrix_template(tuple(c.key() for c in contracts), states, np)
    payoff = (w2 * np.asarray([c.odds for c in contracts]) + r2) / 2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        answer = linprog(-payoff.mean(axis=0), A_ub=-payoff, b_ub=-np.ones(len(payoff)),
                         A_eq=[np.ones(len(contracts))], b_eq=[1], bounds=[(0, None)] * len(contracts),
                         method="highs", options={"threads": 1, "primal_feasibility_tolerance": 1e-9,
                                                  "dual_feasibility_tolerance": 1e-9})
    if not answer.success:
        return {"status": "no_nonloss_portfolio_on_finite_valid_subset", "solver_status": answer.message}
    average = float(-answer.fun)
    if average <= 1 + 1e-8:
        return {"status": "no_positive_average_on_finite_valid_subset", "maximum_average_gross": average,
                "global_weak_absence_asserted": False}
    portfolio = [{"field": c.source_field, "market": c.market, "period": c.period,
                  "selection": c.selection, "line": c.line, "odds": c.odds,
                  "stake_fraction": float(answer.x[i])}
                 for i, c in enumerate(contracts) if answer.x[i] > 1e-8]
    verification = verify_portfolio_complete(portfolio, np=np, recover_simple_rationals=True)
    return {"status": "recorded_price_weak_arbitrage_complete_payoff_verified" if verification["nonnegative_all_and_positive_some_patterns"] else "weak_candidate_not_complete_verified",
            "maximum_average_gross_on_finite_subset": average, "portfolio": portfolio,
            "complete_payoff_verification": verification}


def solve_portfolio(contracts, states, *, np, linprog):
    w2, r2, representatives = matrix_template(tuple(c.key() for c in contracts), states, np)
    odds = np.asarray([c.odds for c in contracts])
    payoff = (w2 * odds + r2) / 2
    n = len(contracts)
    c = np.zeros(n + 1); c[-1] = -1
    constraints = np.column_stack((-payoff, np.ones(len(payoff))))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        solution = linprog(c, A_ub=constraints, b_ub=np.zeros(len(payoff)),
                          A_eq=np.asarray([[1.0] * n + [0.0]]), b_eq=[1.0],
                          bounds=[(0, None)] * n + [(None, None)], method="highs",
                          options={"threads": 1, "primal_feasibility_tolerance": 1e-9,
                                   "dual_feasibility_tolerance": 1e-9})
    if not solution.success:
        return {"status": "solver_failure", "message": solution.message}
    weights = solution.x[:n]
    q = np.maximum(-solution.ineqlin.marginals, 0)
    # Turn the floating dual into a finite rational distribution. Every expected
    # gross payoff is then checked with integer arithmetic, without tolerance.
    counts = np.rint(q * 1_000_000_000).astype(np.int64)
    denominator = int(counts.sum())
    decimals = max(max(0, -Decimal(str(x.odds)).as_tuple().exponent) for x in contracts)
    scale = 10 ** decimals
    odd_ticks = np.asarray([int(Decimal(str(x.odds)) * scale) for x in contracts], dtype=np.int64)
    payoff_ticks = w2.astype(np.int64) * odd_ticks + r2.astype(np.int64) * scale
    expected_numerators = counts @ payoff_ticks
    exact_denominator = 2 * scale * denominator
    exact_max = int(expected_numerators.max())
    support = np.flatnonzero(counts)
    certificate = [{"state": list(representatives[i]), "weight": int(counts[i])} for i in support]
    if not denominator or not all(validate_state(x["state"]) for x in certificate):
        raise ArithmeticError("Invalid dual-state distribution")
    if exact_max <= exact_denominator:
        status = "no_guaranteed_profit_exact_dual"
    elif solution.x[-1] > 1 + 1e-8:
        status = "positive_finite_grid_requires_tail_verification"
    else:
        status = "dual_rounding_unresolved"
    portfolio = [{"field": x.source_field, "market": x.market, "period": x.period,
                  "selection": x.selection, "line": x.line, "odds": x.odds,
                  "stake_fraction": float(weights[j])}
                 for j, x in enumerate(contracts) if weights[j] > 1e-8]
    return {"status": status, "finite_valid_states": len(payoff),
            "finite_grid_optimal_gross": float(solution.x[-1]),
            "finite_grid_primal_min_gross": float((payoff @ weights).min()),
            "rational_dual": {"probability_denominator": denominator,
                              "expected_payoff_denominator": exact_denominator,
                              "maximum_contract_expected_payoff_numerator": exact_max,
                              "maximum_contract_expected_gross": exact_max / exact_denominator,
                              "support": certificate},
            "portfolio_on_finite_grid": portfolio}


_TEMPLATE_CACHE = {}


def matrix_template(keys, states, np):
    signature = keys, states
    if signature in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[signature]
    win, refund = [], []
    for key in keys:
        contract = Contract(*key, 2.0)
        parts = [contract_parts(contract, state) for state in states]
        win.append([round(2 * x[0]) for x in parts])
        refund.append([round(2 * x[1]) for x in parts])
    w2 = np.asarray(win, dtype=np.int16).T
    r2 = np.asarray(refund, dtype=np.int16).T
    _, indices = np.unique(np.column_stack((w2, r2)), axis=0, return_index=True)
    indices.sort()
    result = w2[indices], r2[indices], tuple(states[i] for i in indices)
    if len(_TEMPLATE_CACHE) >= 96:
        _TEMPLATE_CACHE.pop(next(iter(_TEMPLATE_CACHE)))
    _TEMPLATE_CACHE[signature] = result
    return result


def load_rows():
    conn = sqlite3.connect(f"file:{ROOT / 'data/processed/free_football_history.sqlite'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    records = {}
    for raw in conn.execute("SELECT m.match_row_id,m.match_name,m.league,m.start_time_source,m.has_ht_ft_result,p.* FROM sgodds_matches m JOIN sgodds_prices p USING(match_row_id) ORDER BY m.match_row_id,p.source_field"):
        row = dict(raw)
        item = records.setdefault(row["match_row_id"], {k: row[k] for k in ("match_row_id", "match_name", "league", "start_time_source", "has_ht_ft_result")})
        item.setdefault("contracts", []).append(Contract(row["source_field"], row["market"], row["period"], row["selection"],
                                                        float(row["line_source"]) if row["line_source"] is not None else None,
                                                        row["decimal_odds"]))
    conn.close()
    return list(records.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scipy-path", default="/tmp/football-portfolio-scipy")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ft-cap", type=int, default=6)
    parser.add_argument("--ht-cap", type=int, default=3)
    args = parser.parse_args()
    sys.path.insert(0, args.scipy_path)
    import numpy as np
    from scipy.optimize import linprog
    rows = load_rows()
    if args.limit:
        rows = rows[:args.limit]
    states = valid_joint_states(args.ft_cap, args.ht_cap)
    if not all(validate_state(s) for s in states):
        raise ArithmeticError("Generated an invalid game state")
    results, statuses, families = [], Counter(), Counter()
    start = time.monotonic()
    for i, raw in enumerate(rows, 1):
        contracts = raw["contracts"]
        for contract in contracts:
            families[contract.market] += 1
        answer = solve_portfolio(contracts, states, np=np, linprog=linprog)
        metadata = {k: v for k, v in raw.items() if k != "contracts"}
        answer.update(metadata)
        answer["contracts"] = len(contracts)
        answer["quotes_sha256"] = hashlib.sha256(json.dumps([x.__dict__ for x in contracts], sort_keys=True).encode()).hexdigest()
        if answer["status"] == "positive_finite_grid_requires_tail_verification":
            answer["complete_payoff_verification"] = verify_portfolio_complete(answer["portfolio_on_finite_grid"], np=np)
            if answer["complete_payoff_verification"]["positive_on_all_completed_match_patterns"]:
                answer["status"] = "recorded_price_positive_complete_payoff_verified"
        if answer["status"] != "no_guaranteed_profit_exact_dual":
            stable = [c for c in contracts if not c.market.endswith("_goal_total") and "handicap" not in c.market]
            answer["without_mutable_lines"] = solve_portfolio(stable, states, np=np, linprog=linprog)
            answer["without_mutable_lines"]["contracts"] = len(stable)
            answer["mutable_line_pairing_risk"] = any(c.market.endswith("_goal_total") or "handicap" in c.market for c in contracts if c.source_field in {p["field"] for p in answer["portfolio_on_finite_grid"]})
        if answer["status"] == "dual_rounding_unresolved":
            answer["weak_arbitrage_check"] = search_weak_portfolio(contracts, states, np=np, linprog=linprog)
        results.append(answer)
        statuses[answer["status"]] += 1
        if i % 250 == 0:
            print(json.dumps({"processed": i, "statuses": dict(statuses), "elapsed_seconds": round(time.monotonic()-start, 1)}), flush=True)
    proven = [r for r in results if r["status"] == "no_guaranteed_profit_exact_dual"]
    best = max(proven, key=lambda r: r["rational_dual"]["maximum_contract_expected_gross"], default=None)
    positives = [r for r in results if r["status"] == "recorded_price_positive_complete_payoff_verified"]
    best_positive = max(positives, key=lambda r: r["complete_payoff_verification"]["exact_minimum_gross"], default=None)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "source_audit_sha256": hashlib.sha256((ROOT / "data/analysis/sgodds_archive_audit.json").read_bytes()).hexdigest(),
              "source": "SGodds/Singapore Pools recorded opening prices", "rules": RULES_URL,
              "scipy_version": __import__("scipy").__version__, "numpy_version": np.__version__,
              "elapsed_seconds": time.monotonic()-start, "source_match_rows": len(rows),
              "quoted_price_count": sum(families.values()), "market_family_counts": dict(families),
              "state_grid": {"ft_cap_each_team": args.ft_cap, "ht_cap_each_team": args.ht_cap, "raw_valid_states": len(states)},
              "statuses": dict(statuses), "best_global_no_profit_upper_bound": best,
              "best_positive_recorded_price_portfolio": best_positive,
              "positive_recorded_price_portfolios": sum(r["status"] == "recorded_price_positive_complete_payoff_verified" for r in results),
              "positive_portfolios_without_mutable_lines": sum(r.get("without_mutable_lines", {}).get("status") == "positive_finite_grid_requires_tail_verification" for r in results),
              "proof": "For each certified row, an exact rational probability distribution on physically possible HT/FT and first-scoring-team states makes every quoted single contract expected gross <=1. Every nonnegative portfolio has expectation <=1 under that distribution, hence cannot return >1 in every possible outcome. This holds even for states omitted from the finite solver grid. Finite-grid positive values alone are not arbitrage proofs.",
              "scope": ["All quoted 18 SGodds football families jointly, including HT/FT correlations and first-scoring-team order.",
                        "Quarter/whole handicaps and totals include refunds/half stakes; 1/2 Goal uses official signed full-time half-goal handicap.",
                        "Any number of nonnegative straight-bet stakes summing to1; no limit to2or3legs and no multiplication of correlated odds.",
                        "Does not invent an offered accumulator/BetBuilder price, model real probabilities, use exchange lay bets, or include markets absent from this archive.",
                        "Completed-match outcome semantics; exact historical quote simultaneity, actual accessibility, executable limits and all abandonment rules are not independently verified."],
              "results": results}
    OUT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n")
    value = best["rational_dual"]["maximum_contract_expected_gross"] if best else None
    clean_statuses = Counter(r.get("without_mutable_lines", {}).get("status", "implied_by_full_market_certificate") for r in results)
    report["without_mutable_lines_statuses"] = dict(clean_statuses)
    OUT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n")
    REPORT.write_text(f"""# Combinaciones de pagos: SGodds

Se analizaron **{len(rows)} filas de partidos**, **{sum(families.values())} cuotas** y **{len(families)} familias de mercados**, conjuntamente.
Resultado por estado: `{dict(statuses)}`.

**{len(positives)} combinaciones dan beneficio matemático con los números registrados**, verificando también marcadores fuera de la grilla. Esto NO demuestra que esas líneas/cuotas hayan estado disponibles juntas: las oportunidades usan líneas variables cuya asociación con la cuota de apertura está cuestionada por la propia documentación de SGodds.
Al retirar totales con línea, hándicaps asiáticos y el 1/2 Goal, la comprobación queda: `{dict(clean_statuses)}`.

La optimización reparte una unidad entre cualquier cantidad de apuestas simples. Incluye marcador exacto (también «otro»), resultado, goles exactos, over/under, ambos marcan, par/impar, hándicap, primer equipo en marcar, primer tiempo y descanso/final.
Los marcadores y el primer equipo en marcar se tratan como eventos relacionados, nunca como probabilidades independientes.

Para cada fila certificada, una distribución racional sobre resultados válidos limita a 1 la devolución esperada de **cada** contrato. Esto demuestra que ninguna mezcla de esos contratos puede devolver más de 1 en todos los resultados: si pudiera, su expectativa también excedería 1.
No hace falta truncar el universo de marcadores para esta prueba negativa. Un resultado positivo en una grilla finita sí necesitaría comprobar todas las colas; no se declara como arbitraje automáticamente.

Mejor cota superior global certificada de devolución por unidad: {value}.
Las cuotas históricas no se verificaron como ofertas simultáneas ejecutables. No se realizaron apuestas.

En los casos numéricos de devolución mínima 1 se comprueba además beneficio en algún resultado sin perder en otros (arbitraje débil). Si esa comprobación sólo cubre una grilla de estados, no se afirma ausencia global de arbitraje débil.

Código: `scripts/sgodds_portfolio_search.py`; auditoría con certificados enteros por fila: `data/analysis/sgodds_portfolio_search.json`.
Reglas del operador: [Singapore Pools]({RULES_URL}).
""")
    print(json.dumps({"rows": len(rows), "prices": sum(families.values()), "families": len(families),
                      "statuses": dict(statuses), "best_upper_bound": value, "elapsed_seconds": report["elapsed_seconds"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
