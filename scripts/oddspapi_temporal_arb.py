#!/usr/bin/env python3
"""Price-only, pre-kickoff cover search in the downloaded OddsPapi histories.

Uses complete outcome partitions, not independent probabilities or multiplied
correlated odds. No API calls, wagers or model changes. Historical active prices
are not proof of simultaneous execution, matching rules or available liquidity.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/analysis/oddspapi_archive_audit.json"
OUT = ROOT / "data/analysis/oddspapi_temporal_arb.json"
REPORT = ROOT / "COMBINACIONES_ODDSPAPI.md"
FRESHNESS_SECONDS = (60, 300, 3600, 86400)
EPS = 1e-10


def stamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp lacks timezone")
    return round(dt.timestamp() * 1_000_000)


def iso(value):
    return datetime.fromtimestamp(value / 1_000_000, timezone.utc).isoformat()


def salta(value):
    return datetime.fromtimestamp(value / 1_000_000, timezone.utc).astimezone(ZoneInfo("America/Argentina/Salta")).isoformat()


@dataclass
class Group:
    name: str
    labels: tuple
    kind: str = "partition"
    line: float | None = None
    sources: dict = field(default_factory=lambda: defaultdict(dict))
    source_markets: set = field(default_factory=set)

    def add(self, label, key, rows):
        if label in self.labels:
            self.sources[label][key] = rows
            self.source_markets.add(key[1])


def full_partition(catalog):
    """Only catalog types whose listed outcomes are known complete partitions."""
    outcomes = {str(o["outcomeId"]): o["outcomeName"] for o in catalog.get("outcomes", [])}
    names = set(outcomes.values())
    kind = catalog.get("marketType", "")
    line = float(catalog.get("handicap") or 0)
    if kind in {"1x2", "1x2-corners", "1x2-bookings", "spreads-european"} and names == {"1", "X", "2"}:
        return tuple((n, oid) for n in ("1", "X", "2") for oid, name in outcomes.items() if name == n), "partition", None
    if names in ({"Yes", "No"}, {"Odd", "Even"}):
        return tuple((name, oid) for oid, name in outcomes.items()), "partition", None
    if kind in {"firstgoal", "lastgoal"} and names == {"1", "2", "No Goal"}:
        return tuple((n, oid) for n in ("1", "2", "No Goal") for oid, name in outcomes.items() if name == n), "partition", None
    if kind == "highestscoringh" and names == {"1st", "X", "2nd"}:
        return tuple((name, oid) for oid, name in outcomes.items()), "partition", None
    if names == {"Over", "Under"} and ("totals" in kind):
        return tuple((n, oid) for n in ("Over", "Under") for oid, name in outcomes.items() if name == n), "count_asian", line
    if names == {"1", "2"} and kind in {"spreads", "spreads-corners", "spreads-bookings", "drawnobet"}:
        return tuple((n, oid) for n in ("1", "2") for oid, name in outcomes.items() if name == n), "difference_asian", line
    return None


def asian_return(margin, odds):
    return odds if margin > EPS else 0.0 if margin < -EPS else 1.0


def asian_pair_matrix(prices, line, kind):
    """Critical integer values and both constant tails give all pair payoffs."""
    twice = line * 2
    split_lines = (math.floor(twice) / 2, math.ceil(twice) / 2)
    if kind == "count_asian":
        values = range(0, max(2, math.ceil(max(split_lines)) + 2) + 1)
        sign = -1
    else:
        center = -line
        values = range(math.floor(center) - 2, math.ceil(center) + 3)
        sign = 1
    matrix = []
    for value in values:
        positive = sum(asian_return(value + sign * h, prices[0]) for h in split_lines) / 2
        negative = sum(asian_return(-value - sign * h, prices[1]) for h in split_lines) / 2
        item = (positive, negative)
        if item not in matrix:
            matrix.append(item)
    return matrix


def optimize_pair(matrix):
    """Exact 1-D maximin: lower envelope of affine scenario payout functions."""
    candidates = {0.0, 1.0}
    for a, b in matrix:
        for c, d in matrix:
            denom = (a - b) - (c - d)
            if abs(denom) > EPS:
                x = (d - b) / denom
                if 0 <= x <= 1:
                    candidates.add(x)
    weight = max(candidates, key=lambda x: min(a*x + b*(1-x) for a, b in matrix))
    return (weight, 1-weight)


def portfolio(prices, kind="partition", line=None):
    inverse = sum(1/q for q in prices)
    if kind == "partition":
        weights = tuple((1/q)/inverse for q in prices)
        matrix = [tuple(q if j == i else 0.0 for j in range(len(prices))) for i, q in enumerate(prices)]
    elif kind == "double_chance":
        # 1X,12,2X overlap. Each ordinary result wins exactly two positions.
        matrix = [(prices[0],prices[1],0),(prices[0],0,prices[2]),(0,prices[1],prices[2])]
        options = [tuple((1/q)/inverse for q in prices)]
        for excluded in range(3):
            divisor=sum(1/q for i,q in enumerate(prices) if i!=excluded)
            options.append(tuple(0 if i==excluded else (1/q)/divisor for i,q in enumerate(prices)))
        weights=max(options,key=lambda w:min(sum(a*b for a,b in zip(row,w)) for row in matrix))
    else:
        matrix = asian_pair_matrix(prices, line, kind)
        weights = tuple((1/q)/inverse for q in prices) if line % .5 == 0 else optimize_pair(matrix)
    gross = min(sum(a*w for a, w in zip(row, weights)) for row in matrix)
    haircut_prices = [q*.99 for q in prices]
    if kind == "partition":
        haircut_matrix = [tuple(q if j == i else 0.0 for j in range(len(prices))) for i, q in enumerate(haircut_prices)]
    elif kind == "double_chance":
        a,b,c=haircut_prices
        haircut_matrix=[(a,b,0),(a,0,c),(0,b,c)]
    else:
        haircut_matrix = asian_pair_matrix(haircut_prices, line, kind)
    haircut = min(sum(a*w for a, w in zip(row, weights)) for row in haircut_matrix)
    cents = [int((Decimal(str(w)) * 10000).to_integral_value(rounding=ROUND_FLOOR)) for w in weights]
    for j in sorted(range(len(weights)), key=lambda i: weights[i]*10000-cents[i], reverse=True)[:10000-sum(cents)]:
        cents[j] += 1
    def exact_rounded_min(allocation):
        return min(sum(Decimal(str(a))*Decimal(c)/100 for a, c in zip(row, allocation)) for row in matrix)
    def exact_nonpush_min(allocation):
        payouts=[sum(Decimal(str(a))*Decimal(c)/100 for a,c in zip(row,allocation)) for row in matrix if any(abs(a-1)>EPS for a in row)]
        return min(payouts) if payouts else Decimal(100)
    if len(weights)==2:
        center=math.floor(weights[0]*10000)
        choices=[(c,10000-c) for c in range(max(0,center-2),min(10000,center+3)+1)]
        cents=max(choices,key=lambda c:(exact_rounded_min(c),exact_nonpush_min(c)))
    rounded_min = exact_rounded_min(cents)
    all_gross=[sum(a*w for a,w in zip(row,weights)) for row in matrix]
    haircut_all_gross=[sum(a*w for a,w in zip(row,weights)) for row in haircut_matrix]
    nonpush=[gross for row,gross in zip(matrix,all_gross) if any(abs(a-1)>EPS for a in row)]
    return {"inverse_sum": inverse, "weights": weights, "worst_gross_return": gross,
            "guaranteed_price_only_roi": gross-1, "roi_after_0_5pct_capital_cost": gross-1-.005,
            "roi_after_1pct_price_haircut": haircut-1,
            "roi_after_both_stresses": haircut-1-.005,
            "stakes_per_100": [c/100 for c in cents],
            "worst_return_on_100_rounded": float(rounded_min),
            "worst_profit_on_100_rounded": float(rounded_min-100),
            "worst_nonpush_profit_on_100_rounded":float(exact_nonpush_min(cents)-100),
            "cent_rounding_method":"two-leg neighboring-cent maximin" if len(weights)==2 else "largest remainder; not globally optimized",
            "scenario_gross_returns":all_gross,"worst_nonpush_roi":min(nonpush)-1 if nonpush else None,
            "scenario_roi_after_0_5pct_capital_cost":[g-1-.005 for g in all_gross],
            "scenario_roi_after_1pct_price_haircut":[g-1 for g in haircut_all_gross],
            "scenario_roi_after_both_stresses":[g-1-.005 for g in haircut_all_gross],
            "scenario_gross_per_unit": matrix}


def build_groups(raw, catalog):
    groups, excluded = {}, Counter()

    def group(name, labels, kind="partition", line=None):
        if name not in groups:
            groups[name] = Group(name, tuple(labels), kind, line)
        return groups[name]

    for book, book_data in raw["bookmakers"].items():
        for mid, market in book_data.get("markets", {}).items():
            cat = catalog.get(mid)
            if not cat:
                excluded["missing_catalog"] += 1
                continue
            outcomes = {str(o["outcomeId"]): o["outcomeName"] for o in cat.get("outcomes", [])}
            partition = full_partition(cat)
            period, typ = cat.get("period"), cat.get("marketType", "")
            for oid, outcome in market.get("outcomes", {}).items():
                label = outcomes.get(oid)
                for pid, rows in outcome.get("players", {}).items():
                    key = (book, mid, oid, pid)
                    if partition:
                        labeled, kind, line = partition
                        g = group(f"direct:{mid}:player:{pid}", [x[0] for x in labeled], kind, line)
                        g.add(label, key, rows)
                    else:
                        excluded["not_a_complete_direct_partition:" + typ] += 1
                    # Exact count k and cumulative k+ are overlapping if all added.
                    # Build only {0,...,k-1,k+}, an exhaustive disjoint partition.
                    if typ.startswith("exactscore") or typ.startswith("players-"):
                        labels = set(outcomes.values())
                        if "0" in labels:
                            for k in range(1, 11):
                                needed = [str(i) for i in range(k)] + [f"{k}+"]
                                if set(needed) <= labels:
                                    group(f"count_partition:{mid}:player:{pid}:tail:{k}", needed).add(label, key, rows)
                    if pid != "0" or period not in {"fulltime", "p1", "p2"}:
                        continue
                    # Result/DC/half-goal handicap payoffs share the same outcome
                    # events. DC is overlapping and uses its actual payout matrix.
                    scalar="goals" if typ in {"1x2","doublechance","spreads"} else "corners" if typ in {"1x2-corners","spreads-corners"} else "bookings" if typ in {"1x2-bookings","spreads-bookings"} else None
                    if scalar and typ.startswith("1x2") and label in {"1","X","2"}:
                        group(f"canonical_result:{scalar}:{period}",("1","X","2")).add(label,key,rows)
                        group(f"result_complement:{scalar}:{period}:{label}",("Yes","No")).add("Yes",key,rows)
                    if typ=="doublechance" and label in {"1X","12","2X","X2"}:
                        label="2X" if label=="X2" else label
                        group(f"double_chance_three:{period}",("1X","12","2X"),"double_chance").add(label,key,rows)
                        target={"1X":"2","12":"X","2X":"1"}[label]
                        group(f"result_complement:goals:{period}:{target}",("Yes","No")).add("No",key,rows)
                    if scalar and typ.startswith("spreads") and not typ.endswith("european"):
                        line=float(cat.get("handicap") or 0)
                        if abs(line+.5)<EPS:
                            group(f"result_complement:{scalar}:{period}:1",("Yes","No")).add("Yes" if label=="1" else "No",key,rows)
                            if label=="1":group(f"canonical_result:{scalar}:{period}",("1","X","2")).add("1",key,rows)
                        elif abs(line-.5)<EPS:
                            group(f"result_complement:{scalar}:{period}:2",("Yes","No")).add("Yes" if label=="2" else "No",key,rows)
                            if label=="2":group(f"canonical_result:{scalar}:{period}",("1","X","2")).add("2",key,rows)
                    # Equivalent binary goal events, preserving period and scope.
                    if typ in {"totals", "teamtotals-team1", "teamtotals-team2"} and label in {"Over", "Under"}:
                        line = float(cat.get("handicap") or 0)
                        if line % 1 == .5:
                            scalar = "goals" if typ == "totals" else typ
                            group(f"equivalent:{scalar}:{period}:line:{line}", ("Over", "Under")).add(label, key, rows)
                    scalar = "goals" if typ == "exactscore" else "teamtotals-team1" if typ == "exactscore-team1" else "teamtotals-team2" if typ == "exactscore-team2" else None
                    if scalar and label:
                        if label == "0":
                            group(f"equivalent:{scalar}:{period}:line:0.5", ("Over", "Under")).add("Under", key, rows)
                        elif label.endswith("+") and label[:-1].isdigit():
                            line = int(label[:-1])-.5
                            group(f"equivalent:{scalar}:{period}:line:{line}", ("Over", "Under")).add("Over", key, rows)
                    if typ in {"toscore-team1", "toscore-team2", "cleansheet-team1", "cleansheet-team2"} and label in {"Yes", "No"}:
                        team = "team1" if typ.endswith("team1") else "team2"
                        if typ.startswith("cleansheet"):
                            team = "team2" if team == "team1" else "team1"
                            economic = "Under" if label == "Yes" else "Over"
                        else:
                            economic = "Over" if label == "Yes" else "Under"
                        group(f"equivalent:teamtotals-{team}:{period}:line:0.5", ("Over", "Under")).add(economic, key, rows)
                    if typ == "correctscore" and label == "0:0" or typ in {"firstgoal", "lastgoal"} and label == "No Goal":
                        group(f"equivalent:goals:{period}:line:0.5", ("Over", "Under")).add("Under", key, rows)
                    # Complete low-score cells + an over-goals tail. No score cap.
                    for n in range(7):
                        needed = [f"{h}:{a}" for h in range(n+1) for a in range(n+1-h)] + ["OVER_TAIL"]
                        target = group(f"correct_scores_plus_over:{period}:max_total:{n}", needed)
                        if typ == "correctscore" and label in needed:
                            target.add(label, key, rows)
                        if typ == "totals" and label == "Over" and abs(float(cat.get("handicap") or 0)-(n+.5)) < EPS:
                            target.add("OVER_TAIL", key, rows)
                        if typ == "exactscore" and label == f"{n+1}+":
                            target.add("OVER_TAIL", key, rows)
    return {k:g for k,g in groups.items() if all(g.sources.get(label) for label in g.labels)}, excluded


def valid_price(row):
    value = row.get("price")
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 1


def resolve_updates(updates):
    """Conflicting same-key/same-time updates are conservatively removed."""
    if any(row.get("active") is not True or not valid_price(row) for row in updates):
        return None
    return min(updates, key=lambda r:r["price"])


def candidate_record(group, legs, at, end, age, result):
    known = all(isinstance(row.get("limit"), (int,float)) and row["limit"] >= 100*w for (_,_,row),w in zip(legs,result["weights"]))
    return {"group":group.name,"kind":group.kind,"line":group.line,
            "at_utc":iso(at),"recorded_valid_until_utc":iso(end),"interval_seconds":max(0,(end-at)/1_000_000),
            "at_salta":salta(at),"recorded_valid_until_salta":salta(end),
            "freshness_seconds":age,"all_leg_limits_cover_stake_100":known,**result,
            "legs":[{"economic_selection":label,"bookmaker":key[0],"market_id":key[1],
                     "outcome_id":key[2],"player_id":key[3],"price":row["price"],
                     "quoted_at_utc":iso(quoted_at),"age_seconds":(at-quoted_at)/1_000_000,
                     "limit_source":row.get("limit"),"limit_field_present":"limit" in row,
                     "last_recorded_snapshot":row,
                     "stake_per_100":stake} for label,(key,quoted_at,row),stake in zip(group.labels,legs,result["stakes_per_100"])]}


def sweep_group(group, cutoff, freshnesses=FRESHNESS_SECONDS):
    events, source_label = [], {}
    for label, sources in group.sources.items():
        for key, rows in sources.items():
            source_label[key] = label
            for row in rows:
                try:
                    at = stamp(row["createdAt"])
                except (KeyError, ValueError, TypeError):
                    continue
                if at < cutoff:
                    events.append((at, key, row))
    events.sort(key=lambda r:r[0])
    state, stats = {}, {age:{"evaluated_intervals":0,"strict_positive_intervals":0,
                            "strict_positive_intervals_at_least_1s":0,"strict_positive_intervals_at_least_5s":0,
                            "strict_positive_intervals_at_least_30s":0,"nonnegative_push_cover_intervals":0,
                            "known_capacity_100_intervals":0,"top":[],"top_at_least_5s":[],"top_push_covers":[],
                            "top_closest_nonpositive_partition":[]} for age in freshnesses}
    i = 0
    while i < len(events):
        at = events[i][0]
        batch = defaultdict(list)
        while i < len(events) and events[i][0] == at:
            _, key, row = events[i]
            batch[key].append(row)
            i += 1
        for key, updates in batch.items():
            resolved = resolve_updates(updates)
            if resolved is None:
                state.pop(key, None)
            else:
                state[key] = (at, resolved)
        next_at = events[i][0] if i < len(events) else cutoff
        for age, stat in stats.items():
            best = {}
            for key, (quoted_at, row) in state.items():
                if at-quoted_at > age*1_000_000:
                    continue
                limit = row.get("limit")
                if isinstance(limit, (int, float)) and limit <= 0:
                    continue
                label = source_label[key]
                prior = best.get(label)
                if prior is None or (row["price"], quoted_at) > (prior[2]["price"], prior[1]):
                    best[label] = (key, quoted_at, row)
            if not all(label in best for label in group.labels):
                continue
            stat["evaluated_intervals"] += 1
            legs = [best[label] for label in group.labels]
            prices = [row["price"] for _, _, row in legs]
            inverse = sum(1/q for q in prices)
            end = min(next_at, cutoff, *(quoted_at+age*1_000_000 for _, quoted_at, _ in legs))
            duration = max(0, (end-at)/1_000_000)
            # Necessary for profit when exclusive win scenarios exist. Also avoids
            # expensive Asian maximin calculations for ordinary negative margins.
            if inverse >= (2 if group.kind=="double_chance" else 1)-EPS:
                nearest = stat["top_closest_nonpositive_partition"]
                if duration >= 5 and (group.kind == "partition" or group.line is not None and group.line % 1 == .5) and (not nearest or inverse < nearest[0]["inverse_sum"]):
                    result = portfolio(prices, group.kind, group.line)
                    nearest[:] = [candidate_record(group,legs,at,end,age,result)]
                continue
            result = portfolio(prices, group.kind, group.line)
            roi = result["guaranteed_price_only_roi"]
            if roi < -EPS or duration <= 0:
                continue
            if roi <= EPS:
                stat["nonnegative_push_cover_intervals"] += 1
                stat["top_push_covers"].append(candidate_record(group,legs,at,end,age,result))
                stat["top_push_covers"].sort(key=lambda r:r["inverse_sum"])
                del stat["top_push_covers"][5:]
                continue
            stat["strict_positive_intervals"] += 1
            for seconds in (1,5,30):
                stat[f"strict_positive_intervals_at_least_{seconds}s"] += int(duration >= seconds)
            known = all(isinstance(row.get("limit"), (int,float)) and row["limit"] >= 100*w for (_,_,row),w in zip(legs,result["weights"]))
            stat["known_capacity_100_intervals"] += int(known)
            record = candidate_record(group,legs,at,end,age,result)
            for key, eligible in (("top",True),("top_at_least_5s",duration>=5)):
                if eligible:
                    stat[key].append(record)
                    stat[key].sort(key=lambda r:r["guaranteed_price_only_roi"],reverse=True)
                    del stat[key][5:]
    return stats, len(events)


def main():
    audit = json.loads(AUDIT.read_text())
    catalogs = {}
    for h in audit["histories"]:
        for b in h["bookmakers"]:
            for m in b["markets"]:
                if m.get("catalog"):
                    catalogs[m["market_id"]] = m["catalog"]
    results = []
    totals = {age:{"evaluated_intervals":0,"strict_positive_intervals":0,
                   "strict_positive_intervals_at_least_1s":0,"strict_positive_intervals_at_least_5s":0,
                   "strict_positive_intervals_at_least_30s":0,"nonnegative_push_cover_intervals":0,
                   "known_capacity_100_intervals":0,"positive_groups":0,"top":[],"top_at_least_5s":[],
                   "top_push_covers":[],"top_closest_nonpositive_partition":[]} for age in FRESHNESS_SECONDS}
    for h in audit["histories"]:
        source = h["source"]
        data = (ROOT/source["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise ValueError("Historical source SHA mismatch")
        raw = json.loads(data)
        fixture = h["fixture"]
        cutoff = stamp(fixture["startTime"])
        groups, excluded = build_groups(raw,catalogs)
        fixture_result = {"fixture_id":h["fixture_id"],"home":fixture["participant1Name"],"away":fixture["participant2Name"],
                          "scheduled_kickoff_utc":fixture["startTime"],"source":source,
                          "group_count":len(groups),"supported_source_market_ids":sorted({mid for g in groups.values() for mid in g.source_markets}),
                          "excluded_direct_contracts":dict(excluded),"group_summary":[]}
        for name,g in groups.items():
            stats, count = sweep_group(g,cutoff)
            fixture_result["group_summary"].append({"group":name,"kind":g.kind,"required_outcome_count":len(g.labels),"pre_kickoff_source_rows":count,
                                                    "freshness":{str(age):{k:v for k,v in stat.items() if not k.startswith("top")} for age,stat in stats.items()}})
            for age, stat in stats.items():
                target = totals[age]
                for key in stat:
                    if key.startswith("top"):
                        for record in stat[key]:
                            record.update({"fixture_id":h["fixture_id"],"home":fixture["participant1Name"],"away":fixture["participant2Name"]})
                            for leg in record["legs"]:
                                cat=catalogs.get(leg["market_id"],{})
                                leg.update({"market_name":cat.get("marketName"),"market_type":cat.get("marketType"),
                                            "catalog_period":cat.get("period"),"catalog_handicap":cat.get("handicap"),
                                            "outcome_name":next((o.get("outcomeName") for o in cat.get("outcomes",[]) if str(o.get("outcomeId"))==leg["outcome_id"]),None)})
                                if record["guaranteed_price_only_roi"] >= -EPS:
                                    ticks=raw["bookmakers"][leg["bookmaker"]]["markets"][leg["market_id"]]["outcomes"][leg["outcome_id"]]["players"][leg["player_id"]]
                                    future=[t for t in ticks if stamp(t["createdAt"])>stamp(record["at_utc"])]
                                    leg["next_recorded_update_after_portfolio_time"]=min(future,key=lambda t:stamp(t["createdAt"])) if future else None
                        target[key].extend(stat[key])
                        if key in {"top_push_covers","top_closest_nonpositive_partition"}:
                            target[key].sort(key=lambda r:r["inverse_sum"])
                        else:
                            target[key].sort(key=lambda r:r["guaranteed_price_only_roi"],reverse=True)
                        del target[key][10:]
                    else:
                        target[key] += stat[key]
                target["positive_groups"] += int(stat["strict_positive_intervals"]>0)
        results.append(fixture_result)
        print(json.dumps({"fixture":h["fixture_id"],"groups":len(groups),"positive_intervals_60s_total":totals[60]["strict_positive_intervals"]}),flush=True)
    output = {"generated_at":datetime.now(timezone.utc).isoformat(),"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "source_audit_sha256":hashlib.sha256(AUDIT.read_bytes()).hexdigest(),"fixture_count":len(results),
              "source_snapshot_count":audit["snapshot_count"],"catalog_market_count":len(catalogs),
              "freshness_summary":{str(k):v for k,v in totals.items()},"fixtures":results,
              "scope":["Pre-scheduled-kickoff only, active prices; all updates at a common timestamp are applied before evaluation.",
                       "Full direct partitions; Asian quarter and integer push scenarios are evaluated, not treated as simple win/loss.",
                       "Exact-count cumulative labels are partitioned, never all summed as mutually exclusive.",
                       "Cross-market identical no-goal/team-goal payouts preserve period; low exact scores plus an over-goals tail cover all unbounded scores.",
                       "No general all-market LP, player-event dependency portfolio, incomplete scorer-list coverage, or arbitrary correlated parlay multiplication asserted.",
                       "Historical source active flags/freshness/limits do not establish executable simultaneous prices or identical bookmaker void/participation rules.",
                       "Candidate intervals overlap; counts are not independent bets or realized profit."],
              "verified_executable_opportunities":0}
    OUT.write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n")
    lines=["# Combinaciones históricas OddsPapi", "", "Se compararon cinco partidos antes del inicio programado, con precios activos de Pinnacle y DraftKings. Los intervalos se reconstruyen cronológicamente; no se usan cuotas finales ni se mezclan partidos.",
           "", "| Antigüedad máxima de cada precio | Intervalos positivos | Duran ≥5 segundos | Grupos con señal | Capacidad de 100 documentada |", "|---|---:|---:|---:|---:|"]
    for age,t in totals.items():
        lines.append(f"| {age}s | {t['strict_positive_intervals']} | {t['strict_positive_intervals_at_least_5s']} | {t['positive_groups']} | {t['known_capacity_100_intervals']} |")
    best=totals[60]["top_at_least_5s"]
    if best:
        b=best[0]
        lines += ["",f"Mejor señal con precios de hasta 60s y duración ≥5s: **{b['home']}–{b['away']}**, {b['group']}, {b['at_utc']}. Retorno mínimo teórico {100*b['guaranteed_price_only_roi']:.4f}% sobre capital; con recorte del 1% en cuotas y costo del 0,5%, {100*b['roi_after_both_stresses']:.4f}%.","", "| Selección | Casa | Cuota | Apuesta sobre 100 |", "|---|---|---:|---:|"]
        for leg in b["legs"]:
            lines.append(f"| {leg['economic_selection']} | {leg['bookmaker']} | {leg['price']} | {leg['stake_per_100']:.2f} |")
    older_strict=totals[3600]["top_at_least_5s"]
    if not best and older_strict:
        b=older_strict[0]
        lines += ["",f"Señal estrictamente positiva condicional, admitiendo una cotización anterior de 38 minutos: **{b['home']}–{b['away']}**, {b['at_salta']} ({b['interval_seconds']:.3f}s registrados). Ipswich gana el primer tiempo a 10,04 en Pinnacle, frente a Manchester City o empate al descanso a 1,111 en DraftKings. La suma inversa es {b['inverse_sum']:.10f}; beneficio mínimo continuo {100*b['guaranteed_price_only_roi']:.5f} por cada 100.",
                  "",f"Con apuestas de {b['stakes_per_100'][0]:.2f} y {b['stakes_per_100'][1]:.2f}, beneficio mínimo redondeado {b['worst_profit_on_100_rounded']:.5f} por cada 100. Un costo de capital del 0,5% elimina el beneficio estricto; también lo elimina un recorte del 1% de las cuotas. La cotización antigua seguía marcada activa en el historial hasta después del inicio, pero no se confirmó aceptación por las casas."]
    closest=totals[60]["top_closest_nonpositive_partition"]
    if closest:
        b=closest[0]
        lines += ["",f"Partición completa más cercana al equilibrio entre las examinadas con precios de hasta 60s y duración ≥5s: {b['home']}–{b['away']}, {b['group']}, {b['at_utc']}. Retorno mínimo {100*b['guaranteed_price_only_roi']:.4f}% (negativo).", "", "| Selección | Casa | Cuota | Apuesta sobre 100 |", "|---|---|---:|---:|"]
        for leg in b["legs"]:
            lines.append(f"| {leg['economic_selection']} | {leg['bookmaker']} | {leg['price']} | {leg['stake_per_100']:.2f} |")
    weak=totals[3600]["top_push_covers"]
    if weak:
        b=weak[0]
        lines += ["",f"Cobertura con devolución: {b['home']}–{b['away']}, {b['group']}, {b['at_utc']}. Suma inversa {b['inverse_sum']:.8f}; el escenario de devolución deja beneficio mínimo cero. Aparece sólo admitiendo precios de hasta una hora; no se encontró con ventanas de 60s o 300s."]
        lines += ["", "Estos cinco intervalos corresponden a una misma cobertura asiática, no a cinco oportunidades independientes. La antigüedad de una cotización no demuestra que estuviera retirada: se conserva el último registro activo y la actualización siguiente.",
                  "", "| Intervalo UTC | Intervalo Salta | Cuotas | Beneficio por 100 fuera de devolución, sin redondeo |", "|---|---|---|---:|"]
        for r in sorted(weak,key=lambda r:r["at_utc"]):
            lines.append(f"| {r['at_utc']} a {r['recorded_valid_until_utc']} | {r['at_salta']} a {r['recorded_valid_until_salta']} | {', '.join(str(x['price']) for x in r['legs'])} | {100*r['worst_nonpush_roi']:.5f} |")
        lines += ["", f"En la mejor pareja, apostar {b['stakes_per_100'][0]:.2f} a Man City −1 al descanso (DraftKings {b['legs'][0]['price']}) y {b['stakes_per_100'][1]:.2f} al lado contrario (Pinnacle {b['legs'][1]['price']}) devuelve 100 si City llega al descanso ganando por exactamente un gol, y al menos {100+b['worst_nonpush_profit_on_100_rounded']:.5f} en otro marcador. Las dos posiciones son del mismo hándicap −1 para el equipo local, período p1.",
                  "", "Este beneficio es condicional a disponibilidad, aceptación y reglas coincidentes. Los límites de DraftKings no vienen informados; no se verificó ejecución. Un costo fijo de capital del 0,5% convierte el caso de devolución en pérdida; eso no prueba por sí solo expectativa negativa en los otros resultados."]
    lines += ["", "Se comprueban particiones completas, goles y marcadores exactos bajos cubiertos por una cola Over, equivalencias de ningún gol y goles por equipo, y devoluciones asiáticas. Las listas de goleadores de una sola cara y los resultados acumulados superpuestos no se tratan como particiones completas.",
              "", "Son candidatos matemáticos sobre registros históricos, no ganancias ejecutadas ni ofertas confirmadas. La disponibilidad simultánea, identidad de reglas, límites y capacidad real siguen sin verificar. Los recuentos incluyen intervalos solapados; no son apuestas independientes.",
              "", "Detalle de posiciones, escenarios, fechas, límites, estrés y hashes: `data/analysis/oddspapi_temporal_arb.json`.", "Código: `python3 scripts/oddspapi_temporal_arb.py`."]
    REPORT.write_text("\n".join(lines)+"\n")
    print(json.dumps({"report":str(REPORT),"freshness":{str(k):{z:v for z,v in t.items() if not z.startswith('top')} for k,t in totals.items()}},indent=2),flush=True)


if __name__ == "__main__":
    main()
