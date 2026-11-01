#!/usr/bin/env python3
"""Recorded-price football covers, exact-score mixtures and descriptive all-field P&L.

No multiplied correlated odds or invented BetBuilder prices. Each cover buys
separate existing quoted selections. All full-domain LP searches are separate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import sqlite3

try:
    from .sgodds_portfolio_search import Contract, contract_parts, first_choices
except ImportError:
    from sgodds_portfolio_search import Contract, contract_parts, first_choices

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/analysis/football_score_combinations.json"
REPORT = ROOT / "COMBINACIONES_MARCADORES.md"


def observed_state(row):
    hh, ha, fh, fa = (row[k] for k in ("ht_home", "ht_away", "ft_home", "ft_away"))
    ht_first = first_choices(hh, ha)[0]
    ft_first = ht_first or first_choices(fh, fa)[0]
    return hh, ha, fh, fa, ht_first, ft_first


def templates(contracts):
    fields = {c.source_field: c for c in contracts}
    result = []
    def add(name, legs, period, proof):
        if len(set(legs)) == len(legs) and all(f in fields for f in legs):
            result.append({"name": name, "fields": legs, "period": period, "coverage_proof": proof})
    for period, win, cs, buckets, btts, parity, first, total, cap, scores in (
        ("FT", "Ft1X2", "Pts", "Tg", "Bg", "Oe", "T1g", "Ou", 9, range(6)),
        ("HT", "Ht1X2", "Htpts", "Httg", "Htbg", "Htoe", "Htt1g", "Htou", 3, range(3)),
    ):
        prefix = period + ": "
        exact = [f"{cs}_{h}{a}" for h in scores for a in scores if f"{cs}_{h}{a}" in fields]
        add(prefix + "1X2", [f"{win}_{i:02d}" for i in (1, 2, 3)], period, "Home, draw and away partition every result.")
        add(prefix + "all exact scores + any other", exact + [cs + "_99"], period,
            "Official listed scores plus ANY OTHER SCORE partition all unbounded scores.")
        add(prefix + "all exact goal buckets", [f"{buckets}_{i:02d}" for i in range(cap + 1)], period,
            f"Buckets 0..{cap-1} and {cap}+ partition all totals, including the unbounded tail.")
        add(prefix + "both teams score yes/no", [btts + "_01", btts + "_02"], period, "An event and its complement.")
        add(prefix + "odd/even goals", [parity + "_01", parity + "_02"], period, "Every nonnegative integer is odd or even.")
        zeros = [cs + "_00", buckets + "_00", first + "_03"]
        under = fields.get(total + "_02")
        if under and under.line == .5:
            zeros.append(total + "_02")
        for zero in zeros:
            add(prefix + "first scoring team + zero via " + zero,
                [first + "_01", first + "_02", zero], period,
                "At least one goal means first scorer home or away; otherwise score is zero.")
        add(prefix + "H/A + draws 0-0,1-1,... + other",
            [win + "_01", win + "_03"] + [f"{cs}_{i}{i}" for i in scores if f"{cs}_{i}{i}" in fields] + [cs + "_99"],
            period, "All non-draws are H/A; every draw is listed or ANY OTHER SCORE (including 5-5 or higher).")
        add(prefix + "BTTS yes + all clean sheets + other",
            [btts + "_01"] + [f for f in exact if f.endswith("_00") or f.split("_")[-1][0] == "0" or f.split("_")[-1][1] == "0"] + [cs + "_99"],
            period, "Both score or one score is zero; unlisted clean sheets are covered by ANY OTHER SCORE.")
        over = fields.get(total + "_01")
        if over and over.line % 1 == .5:
            k = math.floor(over.line)
            add(prefix + "direct total Over/Under", [total + "_01", total + "_02"], period, "Half-goal total has no push and two complementary outcomes.")
            low_scores = [f"{cs}_{h}{a}" for h in range(k+1) for a in range(k+1-h)]
            add(prefix + f"Over {over.line} + every low exact score", [total + "_01"] + low_scores,
                period, "Over wins above line; explicitly enumerate EVERY score at or below the integer cutoff.")
            if k < cap:
                add(prefix + f"Over {over.line} + low goal buckets", [total + "_01"] + [f"{buckets}_{i:02d}" for i in range(k+1)], period,
                    "Over the line or one of the low exact goal totals.")
                add(prefix + f"Under {over.line} + all high buckets including tail", [total + "_02"] + [f"{buckets}_{i:02d}" for i in range(k+1, cap+1)], period,
                    "Under the line or a high goal bucket, including the final unbounded bucket.")
            if over.line == .5:
                for zero in zeros:
                    add(prefix + "Over 0.5 + zero via " + zero, [total + "_01", zero], period,
                        "At least one goal or exact zero goals; no uncovered score.")
        # A result can be bought directly or split across its three HT/FT subcases.
        chosen = []
        for target in range(3):
            direct = [f"{win}_{target+1:02d}"]
            positions = [i*3+target+1 for i in range(3)] if period == "FT" else [target*3+i+1 for i in range(3)]
            split = [f"Htft_{i:02d}" for i in positions]
            alternatives = [v for v in (direct, split) if all(f in fields for f in v)]
            if not alternatives:
                chosen = []
                break
            chosen.extend(min(alternatives, key=lambda v: sum(1/fields[f].odds for f in v)))
        if chosen:
            add(prefix + "cheapest direct-or-HTFT result partition", chosen, period,
                "For each result choose direct quote or all three opposite-period HT/FT branches, then cover all three results.")
    return fields, result


@lru_cache(maxsize=256)
def template_states(period, cap):
    states = []
    for h in range(cap+1):
        for a in range(cap+1):
            if period == "FT":
                for hh in range(min(h, 2)+1):
                    for ha in range(min(a, 2)+1):
                        for first_ht in first_choices(hh, ha):
                            for first_ft in ((first_ht,) if first_ht else first_choices(h, a)):
                                states.append((hh, ha, h, a, first_ht, first_ft))
            else:
                finals = ((max(h, a+1), a), (max(h, a), max(h, a)), (h, max(a, h+1)))
                for first_ht in first_choices(h, a):
                    for fh, fa in finals:
                        for first_ft in ((first_ht,) if first_ht else first_choices(fh, fa)):
                            states.append((h, a, fh, fa, first_ht, first_ft))
    return tuple(states)


@lru_cache(maxsize=1024)
def coverage_minimum(keys, period):
    contracts = [Contract(*key, 2.0) for key in keys]
    # These templates have NO handicap bets. Their tail only depends on parity,
    # zero flags, result sign, first team and saturated total/exact-score buckets.
    # 12 (or greater than all total lines) contains representatives of every such
    # pattern. HT/FT branches retain every feasible opposite-period result sign.
    if any("handicap" in c.market for c in contracts):
        raise ValueError("Template tail proof does not include handicap bets")
    cap = max(12, math.ceil(max([0]+[abs(c.line) for c in contracts if c.line is not None]))+4)
    smallest = math.inf
    for state in template_states(period, cap):
        won = 0
        for c in contracts:
            win, refund = contract_parts(c, state)
            if refund or win not in (0, 1):
                raise ValueError("Template requires binary no-refund selections")
            won += win
        smallest = min(smallest, won)
    return int(smallest)


def evaluate_template(template, fields):
    selected = [fields[f] for f in template["fields"]]
    minimum_winners = coverage_minimum(tuple(c.key() for c in selected), template["period"])
    if minimum_winners < 1:
        raise ValueError("Incomplete cover: " + template["name"])
    inv = sum((Decimal(1)/Decimal(str(c.odds)) for c in selected), Decimal(0))
    weights = [(Decimal(1)/Decimal(str(c.odds)))/inv for c in selected]
    return {**template, "inverse_sum": float(inv), "minimum_winners": minimum_winners,
            "minimum_gross": float(Decimal(minimum_winners)/inv),
            "minimum_net": float(Decimal(minimum_winners)/inv-1),
            "legs": [{"field": c.source_field, "odds": c.odds, "stake_per_100": float(100*w)} for c,w in zip(selected,weights)]}


def stats(records):
    n = len(records)
    returned = sum((r[1] for r in records), Decimal(0))
    return {"bets": n, "returned_units": float(returned), "profit_units": float(returned-n),
            "roi": float(returned/n-1) if n else None}


def main():
    conn = sqlite3.connect(f"file:{ROOT / 'data/processed/free_football_history.sqlite'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    matches = {r["match_row_id"]: dict(r) for r in conn.execute("SELECT * FROM sgodds_matches ORDER BY start_time_source,match_row_id")}
    contracts = defaultdict(list)
    for r in conn.execute("SELECT * FROM sgodds_prices"):
        contracts[r["match_row_id"]].append(Contract(r["source_field"], r["market"], r["period"], r["selection"],
                                                     float(r["line_source"]) if r["line_source"] is not None else None, r["decimal_odds"]))
    conn.close()
    settled = [r for r in matches.values() if r["has_ht_ft_result"]]
    cutoff = settled[len(settled)*2//3]["start_time_source"][:10]
    counts, best_by_template, by_field = Counter(), {}, defaultdict(list)
    positives, best_per_match, skipped = [], [], Counter()
    selected_digest = hashlib.sha256()
    for mid, match in matches.items():
        fields, choices = templates(contracts[mid])
        best = None
        for template in choices:
            result = evaluate_template(template, fields)
            counts[template["name"]] += 1
            witness = {"match_row_id": mid, "match_name": match["match_name"], "start_time_source": match["start_time_source"], **result}
            if template["name"] not in best_by_template or result["minimum_net"] > best_by_template[template["name"]]["minimum_net"]:
                best_by_template[template["name"]] = witness
            if best is None or result["minimum_net"] > best["minimum_net"]:
                best = witness
            if result["minimum_net"] > 1e-10:
                positives.append(witness)
        if best:
            best_per_match.append(best)
        if not match["has_ht_ft_result"]:
            continue
        state = observed_state(match)
        day = match["start_time_source"][:10]
        for contract in contracts[mid]:
            if contract.market.endswith("_first_team_to_score") and contract.selection != "no_goal":
                skipped[contract.source_field] += 1
                continue
            win, refund = contract_parts(contract, state)
            payout = Decimal(str(win))*Decimal(str(contract.odds))+Decimal(str(refund))
            by_field[contract.source_field].append((day,payout))
            selected_digest.update(json.dumps([mid,contract.source_field,contract.odds,win,refund]).encode())
    summaries, train_selected, holdout = {}, [], []
    for field, records in sorted(by_field.items()):
        train = [r for r in records if r[0]<cutoff]
        later = [r for r in records if r[0]>=cutoff]
        summaries[field] = {"full": stats(records), "training": stats(train), "later": stats(later)}
        # An explicitly exploratory training-only selector; no later-field winner selection.
        if len(train)>=200 and stats(train)["profit_units"]>0:
            train_selected.append(field)
            holdout.extend(later)
    holdout.sort(key=lambda x:x[0])
    result = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "source_audit_sha256": hashlib.sha256((ROOT/'data/analysis/sgodds_archive_audit.json').read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "settlement_code_sha256": hashlib.sha256((ROOT/'scripts/sgodds_portfolio_search.py').read_bytes()).hexdigest(),
              "observation_sha256": selected_digest.hexdigest(),
              "matches": len(matches), "settled_matches": len(settled),
              "template_evaluations": sum(counts.values()), "template_counts": dict(counts),
              "positive_complete_covers": len(positives), "positive_witnesses": sorted(positives,key=lambda x:-x['minimum_net'])[:50],
              "best_by_template": best_by_template,
              "best_overall": max(best_per_match,key=lambda x:x['minimum_net']),
              "all_score_settleable_field_backtests": summaries,
              "positive_full_roi_fields": [f for f,x in summaries.items() if x['full']['roi']>0],
              "training_only_exploratory_portfolio": {"rule": "Bet every quoted field with >=200 training observations and positive aggregate training return; no holdout reselection",
                    "cutoff_source_date": cutoff, "selected_fields": train_selected, "later": stats(holdout)},
              "fields_missing_first_goal_order_excluded_from_roi": dict(skipped),
              "limitations": ["Templates are explicit families, not all portfolios: see the separate LP search for arbitrary mixtures.",
                "Every recorded-price positive is conditional on identical settlement scope and simultaneous executable prices, neither verified.",
                "All-field historical ROI scan is exploratory: positive realized return alone does not establish positive mathematical expectation.",
                "No first-team-to-score home/away outcome inferred from final scores; no missing result treated as zero.",
                "No new correlated-parlay or BetBuilder prices are invented."]}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    best=result['best_overall']
    lines=['# Combinaciones de marcadores y goles','',
           f"Se revisaron {result['template_evaluations']} coberturas explícitas en {len(matches)} partidos y {len(counts)} variantes de plantilla. Positivas al precio registrado: **{len(positives)}**.",
           '', 'Incluye ganador/empate/visitante; empate dividido entre 0–0, 1–1, 2–2, 3–3, 4–4 y otro marcador; Over más todos los marcadores bajos; Under más todos los totales altos, incluido el extremo sin límite; ambos marcan; primer equipo en marcar; y sustituciones descanso/final.',
           '', f"Mejor plantilla: {best['name']}, {best['match_name']} ({best['start_time_source']}); piso teórico {100*best['minimum_net']:.6f}%.",
           '', '| Apuesta | Cuota | Importe por 100 |','|---|---:|---:|']
    lines.extend(f"| {leg['field']} | {leg['odds']} | {leg['stake_per_100']:.6f} |" for leg in best['legs'])
    lines.extend(['', 'Una cobertura exige que TODOS los resultados estén incluidos, también los marcadores extremos. Se usan pagos de apuestas separadas y reparto inverso a la cuota; no se multiplican cuotas de sucesos correlacionados.',
          '', f"También se liquidaron históricamente {len(summaries)} selecciones con resultado determinable por marcador. {len(result['positive_full_roi_fields'])} tienen ROI nominal positivo al mirar toda la muestra; esto es exploratorio, no una ventaja probada.",
          '', f"La cartera elegida sólo con el tramo anterior seleccionó {len(train_selected)} campos. Resultado posterior: {result['training_only_exploratory_portfolio']['later']}.",
          '', 'Los campos de primer goleador local/visitante quedan fuera del ROI por falta de orden de goles. El campo ningún gol sí es determinable. Las cuotas no están verificadas como ejecutables o simultáneas.',
          '', 'Resultados, fórmulas de cobertura y datos de cada mejor plantilla: `data/analysis/football_score_combinations.json`.',
          'Código: `python3 scripts/football_score_combinations.py`.'])
    REPORT.write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:result[k] for k in ('matches','settled_matches','template_evaluations','positive_complete_covers','positive_full_roi_fields','training_only_exploratory_portfolio')},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
