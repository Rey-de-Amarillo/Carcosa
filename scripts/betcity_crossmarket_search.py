#!/usr/bin/env python3
"""Price-only maximin portfolios for every eligible Betcity research-archive row.

Does not estimate probabilities or use known final scores to choose bets. Source
integer-line settlements are not documented: the maximal search assumes normal
Asian refunds, then rechecks any positive result using strictly binary markets.
No source author code, account, wager, network or existing model is executed.
"""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/analysis/betcity_crossmarket_search.json"
REPORT = ROOT / "COMBINACIONES_BETCITY.md"
NUMERICAL_TOLERANCE = 1e-8


def scientific_imports(path="/tmp/football-portfolio-scipy"):
    if path:
        sys.path.insert(0, path)
    import numpy as np
    from scipy.optimize import linprog
    return np, linprog


@dataclass(frozen=True)
class Contract:
    key: str
    kind: str
    side: str
    line: float | None = None

    @property
    def strict_binary(self):
        return self.line is None or self.line % 1 == .5


@lru_cache(maxsize=1024)
def parse_contract(key):
    if key.startswith("WIN__") and key[5:] in {"P1", "PX", "P2", "1X", "X2", "12"}:
        return Contract(key, "result", key[5:])
    if key in {"BOTH_TEAMS_TO_SCORE__YES", "BOTH_TEAMS_TO_SCORE__NO"}:
        return Contract(key, "btts", key.rsplit("__", 1)[1])
    m = re.fullmatch(r"(?:(P[12])__)?TOTALS__(OVER|UNDER)\((-?\d+(?:\.\d+)?)\)", key)
    if m:
        line = float(m[3])
        if line * 4 != round(line * 4):
            return None
        return Contract(key, "total" if m[1] is None else "team_" + m[1], m[2], line)
    m = re.fullmatch(r"HANDICAP__(P[12])\((-?\d+(?:\.\d+)?)\)", key)
    if m:
        line = float(m[2])
        if line * 4 != round(line * 4):
            return None
        return Contract(key, "handicap", m[1], line)
    return None


def components(line):
    if line * 2 == round(line * 2):
        return ((line, 1.0),)
    return ((math.floor(line * 2) / 2, .5), (math.ceil(line * 2) / 2, .5))


def payoff_parts(contract, home, away):
    """Return fractions of stake won and refunded; remaining stake is lost."""
    if contract.kind == "result":
        selectors = {"P1": home > away, "PX": home == away, "P2": home < away,
                     "1X": home >= away, "X2": home <= away, "12": home != away}
        return float(selectors[contract.side]), 0.0
    if contract.kind == "btts":
        yes = home > 0 and away > 0
        return float(yes if contract.side == "YES" else not yes), 0.0
    won = refund = 0.0
    for line, fraction in components(contract.line):
        if contract.kind == "handicap":
            comparison = (home - away if contract.side == "P1" else away - home) + line
        else:
            count = home + away if contract.kind == "total" else home if contract.kind == "team_P1" else away
            comparison = count - line if contract.side == "OVER" else line - count
        won += fraction * (comparison > 0)
        refund += fraction * (comparison == 0)
    return won, refund


def grid_limit(contracts):
    """Complete finite score-pattern support, not an arbitrary score truncation.

    Let L bound all absolute thresholds and be >=1. If both true scores exceed
    L, team and match totals are above every threshold. Only goal difference can
    matter: clamp it to +/- (L+1), represent with both scores >=L+1, hence <=2L+2.
    If one score <=L and the other >2L+2, clamp the latter to2L+2; every total,
    team-total, result and handicap comparison keeps its sign. BTTS is preserved.
    Thus every unbounded nonnegative integer score has a pattern in this grid.
    No parity/exact-score/first-scorer contracts are silently included here.
    """
    limit = max([1] + [math.ceil(abs(c.line)) for c in contracts if c.line is not None])
    return 2 * limit + 2


def compress_state(home, away, contracts):
    limit = (grid_limit(contracts) - 2) // 2
    if home > limit and away > limit:
        delta = max(-limit-1, min(limit+1, home-away))
        return limit+1+max(delta, 0), limit+1+max(-delta, 0)
    return min(home, 2*limit+2), min(away, 2*limit+2)


def make_pattern(contracts, np):
    bound = grid_limit(contracts)
    states, wins, refunds, seen = [], [], [], set()
    for home in range(bound + 1):
        for away in range(bound + 1):
            parts = tuple(payoff_parts(c, home, away) for c in contracts)
            if parts in seen:
                continue
            seen.add(parts)
            states.append((home, away))
            wins.append([p[0] for p in parts])
            refunds.append([p[1] for p in parts])
    return {"contracts": contracts, "states": states, "bound": bound,
            "wins": np.array(wins, dtype=float), "refunds": np.array(refunds, dtype=float),
            "certificates": []}


def solve_portfolio(pattern, prices, np, linprog):
    matrix = pattern["wins"] * prices + pattern["refunds"]
    n = len(prices)
    answer = linprog(np.r_[np.zeros(n), -1.0],
                     A_ub=np.column_stack((-matrix, np.ones(len(matrix)))),
                     b_ub=np.zeros(len(matrix)), A_eq=np.array([[1.0]*n+[0.0]]), b_eq=[1.0],
                     bounds=[(0, None)]*n+[(None, None)], method="highs")
    if not answer.success:
        raise RuntimeError("Maximin LP failed: " + answer.message)
    weights = np.maximum(answer.x[:n], 0)
    weights /= weights.sum()
    gross = matrix @ weights
    q = np.maximum(-answer.ineqlin.marginals, 0)
    q /= q.sum()
    expected_wins = q @ pattern["wins"]
    expected_refunds = q @ pattern["refunds"]
    dual_bound = float(np.max(expected_wins*prices + expected_refunds))
    return {"minimum_gross_return": float(gross.min()), "weights": weights,
            "dual_bound": dual_bound, "certificate": (expected_wins, expected_refunds),
            "q": q, "gross_returns": gross}


def solve_weak_portfolio(pattern, prices, np, linprog):
    """Find no-loss/all-states with a profit in at least one complete pattern."""
    matrix = pattern["wins"] * prices + pattern["refunds"]
    n = len(prices)
    answer = linprog(-matrix.mean(axis=0), A_ub=-matrix, b_ub=-np.ones(len(matrix)),
                     A_eq=np.array([[1.0]*n]), b_eq=[1.0], bounds=[(0,None)]*n, method="highs")
    if not answer.success:
        return None
    weights = np.maximum(answer.x, 0)
    weights /= weights.sum()
    gross = matrix @ weights
    if gross.min() < 1-NUMERICAL_TOLERANCE or gross.max() <= 1+NUMERICAL_TOLERANCE:
        return None
    return {"minimum_gross_return": float(gross.min()), "maximum_gross_return": float(gross.max()),
            "mean_return_over_uniform_patterns_not_real_probability": float(gross.mean()),
            "weights": weights, "gross_returns": gross, "dual_bound": None}


class OrientationAudit:
    """Check field direction against known scores; never silently relabel prices."""
    def __init__(self):
        self.groups = {}
        self.bins = {}

    @staticmethod
    def add(acc, p, win):
        acc[0] += 1
        acc[1] += p
        acc[2] += win
        acc[3] += (p-win)**2
        acc[4] += ((1-p)-win)**2

    def consume(self, row, markets):
        if not row["has_parseable_final_score"]:
            return
        home, away = row["score_home"], row["score_away"]
        valid = lambda key: isinstance(markets.get(key), (float,int)) and 1 < markets[key] < float("inf")
        for key, price in markets.items():
            c = parse_contract(key)
            if c is None or not c.strict_binary or not valid(key):
                continue
            win, refund = payoff_parts(c, home, away)
            if refund:
                continue
            if c.kind == "btts":
                p = 1/price
            elif c.kind == "result":
                opposite = {"1X": "P2", "X2": "P1", "12": "PX"}
                keys = ["WIN__P1", "WIN__PX", "WIN__P2"] if c.side in {"P1","PX","P2"} else [key, "WIN__"+opposite[c.side]]
                if not all(valid(k) for k in keys):
                    continue
                p = (1/price)/sum(1/markets[k] for k in keys)
            else:
                if c.kind == "handicap":
                    other = "HANDICAP__" + ("P2" if c.side == "P1" else "P1") + f"({-c.line:g})"
                else:
                    other = key.replace("__OVER(", "__UNDER(") if c.side == "OVER" else key.replace("__UNDER(", "__OVER(")
                if not valid(other):
                    continue
                p = (1/price)/(1/price+1/markets[other])
            family = c.kind+"_"+c.side
            self.add(self.groups.setdefault(family,[0,0.,0.,0.,0.]),p,win)
            self.add(self.bins.setdefault((family,min(4,int(p*5))),[0,0.,0.,0.,0.]),p,win)

    @staticmethod
    def stats(acc):
        return {"n": acc[0], "mean_implied_probability": acc[1]/acc[0], "observed_winning_rate": acc[2]/acc[0],
                "brier_given_label": acc[3]/acc[0], "brier_if_label_inverted_diagnostic_only": acc[4]/acc[0]}

    def result(self):
        return {family: {**self.stats(acc), "probability_bins": {
                    f"{b*.2:.1f}..{(b+1)*.2:.1f}": self.stats(v)
                    for (f,b),v in sorted(self.bins.items()) if f==family}}
                for family,acc in sorted(self.groups.items())}


def candidate_detail(row, pattern, prices, solution):
    weights = solution["weights"]
    chosen = [(c, float(price), float(weight)) for c, price, weight in zip(pattern["contracts"], prices, weights) if weight > 1e-9]
    # A concrete rounded $100 allocation is separately checked with Decimal.
    cents = [int(round(weight * 10000)) for _, _, weight in chosen]
    if cents:
        cents[max(range(len(cents)), key=cents.__getitem__)] += 10000 - sum(cents)
    worst = Decimal("Infinity")
    worst_state = None
    for home, away in pattern["states"]:
        gross = Decimal(0)
        for (contract, price, _), stake in zip(chosen, cents):
            won, refund = payoff_parts(contract, home, away)
            gross += Decimal(stake)/100 * (Decimal(str(won))*Decimal(str(price)) + Decimal(str(refund)))
        if gross < worst:
            worst, worst_state = gross, [home, away]
    haircuts = {}
    for haircut in (0.001, 0.005, 0.01, 0.02):
        values = (pattern["wins"] * (prices*(1-haircut)) + pattern["refunds"]) @ weights
        haircuts[str(haircut)] = float(values.min()-1)
    return {"event_row_id": row["event_row_id"], "event": row["event_name"],
            "event_date_source": row["event_date_source"], "league": row["league"],
            "markets_created_source": row["markets_created_source"], "raw_markets_created_source": row["raw_markets_created_source"],
            "scope_flag": row["scope_flag"], "final_score_source_not_used_to_choose": row["final_score_source"],
            "minimum_gross_return": solution["minimum_gross_return"],
            "minimum_net_return": solution["minimum_gross_return"]-1,
            "dual_bound": solution["dual_bound"], "state_grid_bound": pattern["bound"],
            "maximum_gross_return": float(solution["gross_returns"].max()),
            "distinct_payoff_states": len(pattern["states"]),
            "legs": [{"source_key": c.key, "decimal_odds": p, "stake_fraction": w,
                      "rounded_stake_per_100": amount/100, "strict_binary": c.strict_binary}
                     for (c, p, w), amount in zip(chosen, cents)],
            "rounded_100_minimum_return": str(worst), "rounded_100_worst_representative_score": worst_state,
            "price_haircut_net_returns_fixed_weights": haircuts,
            "after_0_5_percent_capital_cost": solution["minimum_gross_return"]-1-.005,
            "simultaneous_executable_prices_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scipy-path", default="/tmp/football-portfolio-scipy")
    parser.add_argument("--limit", type=int, help="Explicit development subset; omitted scans every eligible row")
    parser.add_argument("--progress-every", type=int, default=20000)
    parser.add_argument("--include-unverified-btts", action="store_true", help="Diagnostic only: undo the explicit suspect BTTS-label quarantine")
    args = parser.parse_args()
    np, linprog = scientific_imports(args.scipy_path)
    conn = sqlite3.connect(f"file:{ROOT / 'data/processed/free_football_history.sqlite'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    counts = Counter()
    orientation = OrientationAudit()
    previous_diagnostic = None
    if OUT.exists():
        previous = json.loads(OUT.read_text())
        previous_diagnostic = previous.get("pre_quarantine_diagnostic")
        if not previous.get("btts_label_quarantined", False) and previous.get("development_limit") is None:
            previous_diagnostic = {"counts": previous["counts"],
                                   "strongest_strict_binary_candidate_not_trusted": previous["positive_portfolios_top100_strict_binary"][:1],
                                   "reason_not_trusted": "Source BTTS YES label is inversely oriented against scored outcomes; suspect data semantics, not verified executable arbitrage."}
    families, skipped = Counter(), Counter()
    cache = OrderedDict()
    positive, strict_positive = [], []
    weak_positive, strict_weak_positive = [], []
    best_nonpositive = None
    started = time.monotonic()
    rows = conn.execute("SELECT * FROM betcity_events WHERE scope_flag='no_explicit_scope_flag_unverified' ORDER BY event_row_id" + (" LIMIT ?" if args.limit else ""), (args.limit,) if args.limit else ())
    for raw in rows:
        row = dict(raw)
        counts["eligible_rows_scanned"] += 1
        markets = json.loads(row["markets_json"])
        orientation.consume(row, markets)
        parsed = []
        for key, price in sorted(markets.items()):
            if key.startswith("BOTH_TEAMS_TO_SCORE__") and not args.include_unverified_btts:
                counts["quarantined_btts_price_fields"] += 1
                continue
            contract = parse_contract(key)
            if contract is None:
                skipped[key] += 1
            elif not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 1:
                counts["invalid_prices_excluded"] += 1
            else:
                parsed.append((contract, price))
                families[contract.kind] += 1
        if not parsed:
            counts["rows_without_supported_valid_prices"] += 1
            continue
        keys = tuple(c.key for c, _ in parsed)
        if keys not in cache:
            cache[keys] = make_pattern(tuple(c for c, _ in parsed), np)
            counts["distinct_shapes_built"] += 1
            if len(cache) > 2048:
                cache.popitem(last=False)
        pattern = cache[keys]
        cache.move_to_end(keys)
        prices = np.array([p for _, p in parsed])
        certs = pattern["certificates"]
        if any(float(np.max(win*prices + refund)) <= 1-1e-9 for win, refund in certs):
            counts["rows_certified_no_arb_from_cached_dual"] += 1
            if args.progress_every and counts["eligible_rows_scanned"] % args.progress_every == 0:
                print(json.dumps({"progress": counts["eligible_rows_scanned"], "lp": counts["rows_solved_by_maximin_lp"],
                                  "dual_cached": counts["rows_certified_no_arb_from_cached_dual"],
                                  "positive": counts["positive_under_assumed_asian_refund_rules"],
                                  "seconds": round(time.monotonic()-started, 1)}), flush=True)
            continue
        solution = solve_portfolio(pattern, prices, np, linprog)
        counts["rows_solved_by_maximin_lp"] += 1
        if solution["dual_bound"] < 1-1e-9:
            certs.append(solution["certificate"])
            if len(certs) > 64:
                del certs[0]
        edge = solution["minimum_gross_return"]-1
        if edge > NUMERICAL_TOLERANCE:
            counts["positive_under_assumed_asian_refund_rules"] += 1
            detail = candidate_detail(row, pattern, prices, solution)
            if len(positive) < 100 or edge > min(p["minimum_net_return"] for p in positive):
                positive.append(detail)
                positive.sort(key=lambda p: p["minimum_net_return"], reverse=True)
                del positive[100:]
            strict = [(c, price) for c, price in parsed if c.strict_binary]
            if strict:
                strict_pattern = make_pattern(tuple(c for c, _ in strict), np)
                strict_prices = np.array([p for _, p in strict])
                strict_solution = solve_portfolio(strict_pattern, strict_prices, np, linprog)
                if strict_solution["minimum_gross_return"] > 1+NUMERICAL_TOLERANCE:
                    counts["positive_using_only_strict_binary_markets"] += 1
                    strict_positive.append(candidate_detail(row, strict_pattern, strict_prices, strict_solution))
                    strict_positive.sort(key=lambda p: p["minimum_net_return"], reverse=True)
                    del strict_positive[100:]
        elif solution["dual_bound"] <= 1+NUMERICAL_TOLERANCE:
            counts["lp_no_positive_above_tolerance"] += 1
            if solution["minimum_gross_return"] >= 1-NUMERICAL_TOLERANCE:
                counts["second_lp_weak_arbitrage_checks"] += 1
                weak = solve_weak_portfolio(pattern, prices, np, linprog)
                if weak is not None:
                    counts["weak_no_loss_positive_some_outcomes_under_assumed_refunds"] += 1
                    detail = candidate_detail(row, pattern, prices, weak)
                    weak_positive.append(detail)
                    weak_positive.sort(key=lambda p:p["maximum_gross_return"],reverse=True)
                    del weak_positive[100:]
                    strict = [(c,price) for c,price in parsed if c.strict_binary]
                    if strict:
                        strict_pattern = make_pattern(tuple(c for c,_ in strict), np)
                        strict_prices = np.array([p for _,p in strict])
                        strict_weak = solve_weak_portfolio(strict_pattern, strict_prices, np, linprog)
                        if strict_weak is not None:
                            counts["weak_positive_using_only_strict_binary_markets"] += 1
                            strict_weak_positive.append(candidate_detail(row,strict_pattern,strict_prices,strict_weak))
                            strict_weak_positive.sort(key=lambda p:p["maximum_gross_return"],reverse=True)
                            del strict_weak_positive[100:]
            if best_nonpositive is None or solution["minimum_gross_return"] > best_nonpositive["minimum_gross_return"]:
                best_nonpositive = candidate_detail(row, pattern, prices, solution)
        else:
            counts["numerically_unresolved_rows"] += 1
        if args.progress_every and counts["eligible_rows_scanned"] % args.progress_every == 0:
            print(json.dumps({"progress": counts["eligible_rows_scanned"], "lp": counts["rows_solved_by_maximin_lp"],
                              "dual_cached": counts["rows_certified_no_arb_from_cached_dual"],
                              "positive": counts["positive_under_assumed_asian_refund_rules"],
                              "seconds": round(time.monotonic()-started, 1)}), flush=True)
    total = conn.execute("SELECT count(*) FROM betcity_events").fetchone()[0]
    excluded = dict(conn.execute("SELECT scope_flag,count(*) FROM betcity_events WHERE scope_flag!='no_explicit_scope_flag_unverified' GROUP BY scope_flag"))
    conn.close()
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic()-started,
        "source_rows": total, "excluded_explicit_scope_rows": excluded, "development_limit": args.limit,
        "counts": dict(counts), "supported_price_family_counts": dict(families), "unsupported_keys_counts": dict(skipped),
        "positive_portfolios_top100_assumed_refunds": positive,
        "positive_portfolios_top100_strict_binary": strict_positive, "best_nonpositive_lp_example": best_nonpositive,
        "weak_arbitrage_top100_assumed_refunds": weak_positive,
        "weak_arbitrage_top100_strict_binary": strict_weak_positive,
        "btts_label_quarantined": not args.include_unverified_btts,
        "pre_quarantine_diagnostic": previous_diagnostic,
        "family_label_orientation_audit": orientation.result(),
        "orientation_audit_note": "Normalized probabilities use paired opposing prices or1X2 triple. BTTS has no source NO column, so its raw inverse quote is used. Comparisons are data-quality diagnostics, not strategy fitting. Integer push lines are excluded from direction calibration.",
        "numerical_positive_tolerance": NUMERICAL_TOLERANCE,
        "method": "Maximize minimum gross portfolio return across complete score payout patterns; nonnegative stakes sum to1. Cached LP dual distributions certify no arbitrage under changed prices.",
        "score_domain_proof": grid_limit.__doc__,
        "integer_and_quarter_settlement": "CONDITIONAL standard Asian stake refunds/half settlements; source author code only documents half-lines. Every positive full-set portfolio is rechecked excluding all integer/quarter lines.",
        "weak_arbitrage_method": "For maximin≈1 rows, a second LP maximizes uniform mean gross over every complete payoff pattern subject to each return>=1; uniform pattern weighting is an optimization device, not estimated football probability. Strict maximin<1 or dualbound<1 rules out weak arbitrage too.",
        "limitations": ["Historical source market times and simultaneous executable prices are unverified.",
                        "No wager limits, account acceptance, fees or ability to place all legs were verified.",
                        "Unflagged rows still do not have independently verified regulation football scope.",
                        "Separate books/timestamps/events are never combined; no hypothetical combined-bet odds are multiplied.",
                        "Search covers only market keys present in this source, not player, correct-score, corner or card markets absent here."],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_audit_sha256": hashlib.sha256((ROOT/"data/analysis/betcity_research_archive_audit.json").read_bytes()).hexdigest(),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    REPORT.write_text(f"""# Combinaciones entre cuotas: archivo de investigación Betcity

Filas revisadas: {counts['eligible_rows_scanned']}; mercados de resultado/doble oportunidad, goles, goles por equipo, ambos marcan y hándicap.
Se optimiza la distribución del importe entre todas las selecciones compatibles de cada fila; no se asumen independientes apuestas correlacionadas.

Portafolios con mínimo retorno mayor que1: **{counts['positive_under_assumed_asian_refund_rules']}**, bajo reglas estándar de devolución asiática.
De ellos, filas con una cobertura positiva usando sólo resultados binarios sin devoluciones ambiguas: **{counts['positive_using_only_strict_binary_markets']}**.
Coberturas débiles (no perder en ningún marcador, ganar en alguno): **{counts['weak_no_loss_positive_some_outcomes_under_assumed_refunds']}** bajo devoluciones asiáticas; **{counts['weak_positive_using_only_strict_binary_markets']}** usando sólo resultados binarios.

La columna Betcity `BOTH_TEAMS_TO_SCORE__YES` queda **en cuarentena**, sin intercambiarla por No: muestra orientación inversa a los resultados reales. Otras familias tienen orientación global coherente, lo que no verifica cada cuota individual. El diagnóstico anterior sin cuarentena se conserva como evidencia de calidad de datos, no como una ganancia válida.

{counts['rows_certified_no_arb_from_cached_dual']} filas se descartan mediante certificados duales de probabilidad y {counts['rows_solved_by_maximin_lp']} mediante programación lineal.
El soporte de marcadores es completo para las funciones usadas: límites derivados de cada línea, con prueba de reducción de cualquier marcador entero no acotado. No se descartan marcadores altos.

Se excluyen {sum(excluded.values())} filas con etiquetas explícitas de simulación, variante o duración especial. El resto conserva formato sin verificar.
Los casos positivos son discrepancias matemáticas de un archivo histórico, **no ganancias ejecutables verificadas**. Los tiempos, reglas, liquidez y aceptación de apuestas necesitan verificación.

Datos, asignaciones, peores casos, costos y sensibilidad: `data/analysis/betcity_crossmarket_search.json`.
Reproducir: `python3 scripts/betcity_crossmarket_search.py --scipy-path /tmp/football-portfolio-scipy`.
""")
    print(json.dumps({"finished": True, "counts": result["counts"], "elapsed_seconds": result["elapsed_seconds"],
                      "best_strict_positive": strict_positive[:1], "best_assumed_positive": positive[:1],
                      "audit": str(OUT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
