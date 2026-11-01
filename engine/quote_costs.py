"""Descriptive cost indices for complete, contemporaneous sportsbook boards.

No probabilities, execution claims or ROI are inferred here. Exchange/DFS
products and incomplete/non-partition runner lists never enter a cost board.
Prices are grouped per capture before aliases are deduplicated, so missing
outcomes cannot be filled with a different snapshot or alternate market.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import re
from statistics import median


_PERIOD = re.compile(r"_(h[12]|q[1-4]|p[1-3]|s[1-5]|ex_ot|rt|ot|1st_[157]_innings|[1-9]_innings)$")
_EXCHANGE_KEYS = ("betfair_ex", "betfair_exchange", "matchbook", "smarkets", "betdaq", "betfair_ex_", "bfe")
_DFS_KEYS = ("prizepicks", "underdog", "pick6", "sleeper", "betr_us_dfs", "draftkings_pick6", "fliff_dfs")
_YES = {"yes", "si", "sí"}
_NO = {"no"}


def _text(value):
    return str(value or "").strip()


def _num(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return float("-inf")
        return parsed.astimezone(timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError):
        return float("-inf")


def _sport(row):
    raw = _text(row.get("sport")).lower()
    key = _text(row.get("sport_key")).lower()
    if key.startswith("americanfootball_"):
        return "american_football"
    if key.startswith("soccer_") or raw in {"soccer", "football", "futbol", "fútbol"}:
        return "football"
    aliases = {"icehockey": "hockey", "ice_hockey": "hockey",
               "americanfootball": "american_football"}
    return aliases.get(raw, raw or key.split("_", 1)[0] or "unknown")


def _excluded(row):
    key = _text(row.get("bookmaker")).lower()
    title = _text(row.get("bookmaker_title")).lower()
    if row.get("exchange") is True or "exchange" in title or any(key == x or key.startswith(x) for x in _EXCHANGE_KEYS):
        return "exchange_fee_or_depth_unknown"
    if row.get("dfs") is True or any(key == x or key.startswith(x) for x in _DFS_KEYS):
        return "dfs_not_decimal_sportsbook_partition"
    return None


def _contract(row):
    """Return canonical contract/outcome, or a documented exclusion reason."""
    key = _text(row.get("market_key")).lower()
    canonical = key.removeprefix("alternate_")
    canonical = re.sub(r"_alternate(?=_|$)", "", canonical)
    match = _PERIOD.search(canonical)
    period = match.group(1) if match else "full_game"
    base = canonical[:match.start()] if match else canonical
    selection = _text(row.get("selection"))
    lower = selection.lower()
    home, away = (_text(row.get(k)).lower() for k in ("home_team", "away_team"))
    participant = _text(row.get("description"))
    line = _num(row.get("line"))
    sport = _sport(row)
    if not key or not selection:
        return None, "missing_market_or_selection"
    if "double_chance" in base or base in {"doublechance", "correct_score", "scorecast", "scorecasts"} or "scorecast" in base:
        return None, "nonexclusive_or_incomplete_partition"
    if any(token in base for token in ("first_goal_scorer", "last_goal_scorer", "first_basket", "1st_td", "first_td", "first_scorer", "last_scorer")):
        return None, "runner_completeness_unverified"
    if base in {"h2h", "h2h_3_way", "draw_no_bet", "dnb"}:
        outcome = ("home" if lower in {home, "home", "1"} else
                   "away" if lower in {away, "away", "2"} else
                   "draw" if lower in {"draw", "tie", "empate", "x"} else None)
        if outcome is None or not home or not away or home == away:
            return None, "unknown_match_outcome"
        dnb = base in {"draw_no_bet", "dnb"}
        three = base == "h2h_3_way" or sport == "football" and not dnb
        expected = ("home", "draw", "away") if three else ("home", "away")
        # Cricket is evaluated after grouping: the draw selection determines
        # whether this *observed* board has two or three quoted outcomes.
        if sport == "cricket" and base == "h2h":
            expected = None
        if dnb:
            canonical = "draw_no_bet" + ("_" + period if period != "full_game" else "")
        if sport == "football" and base == "h2h_3_way":
            canonical = "h2h" + ("_" + period if period != "full_game" else "")
        return {"canonical": canonical, "family": "draw_no_bet" if dnb else "h2h", "period": period,
                "line": None, "participant": None, "outcome": outcome,
                "expected": expected, "payoff": "conditional_no_draw" if dnb else "binary_or_three_way",
                "cricket_contract_unknown": sport == "cricket"}, None
    if base == "btts":
        outcome = "yes" if lower in _YES else "no" if lower in _NO else None
        if outcome is None:
            return None, "unknown_binary_outcome"
        return {"canonical": canonical, "family": "btts", "period": period,
                "line": None, "participant": None, "outcome": outcome,
                "expected": ("yes", "no"), "payoff": "binary_no_push"}, None
    is_player = base.startswith(("player_", "batter_", "pitcher_"))
    if is_player and lower in _YES | _NO:
        if not participant:
            return None, "missing_prop_participant"
        return {"canonical": canonical, "family": "player_yes_no", "period": period,
                "line": line, "participant": participant, "outcome": "yes" if lower in _YES else "no",
                "expected": ("yes", "no"), "payoff": "binary_no_push"}, None
    if "goal_scorer_anytime" in base or "anytime" in base:
        return None, "nonexclusive_runner_list"
    is_totals = base.startswith("totals") or base.startswith("team_totals")
    is_spreads = base.startswith("spreads")
    if is_totals or is_spreads or is_player:
        if line is None:
            return None, "missing_or_nonfinite_line"
        if is_spreads:
            outcome = "home" if lower in {home, "home", "1"} else "away" if lower in {away, "away", "2"} else None
            if outcome is None or not home or not away:
                return None, "unknown_handicap_team"
            # A +1.5 home / -1.5 away pair is one contract, not two.
            line = line if outcome == "home" else -line
            participant = None
            expected, family = ("home", "away"), base
        else:
            outcome = "over" if lower in {"over", "más", "mas"} else "under" if lower in {"under", "menos"} else None
            if outcome is None:
                return None, "unknown_total_outcome"
            if (is_player or base.startswith("team_totals")) and not participant:
                return None, "missing_prop_participant"
            participant = participant or None
            expected = ("over", "under")
            family = "player_totals" if is_player else base
        return {"canonical": canonical, "family": family, "period": period,
                "line": round(line, 8), "participant": participant,
                "outcome": outcome, "expected": expected, "payoff": "line_dependent"}, None
    return None, "unsupported_or_unverified_partition"


def _warning(contract, sport):
    warnings = ["Índice descriptivo de precios; no es ROI ni margen real de cada selección."]
    interpretation = "proportional_no_push_proxy"
    if contract["payoff"] == "conditional_no_draw":
        interpretation = "conditional_on_no_draw"
        warnings.append("DNB: devolución en empate. Índice condicionado a no empate; no margen incondicional ni prueba de arbitraje mediante suma de inversas.")
    line = contract["line"]
    if contract["payoff"] == "line_dependent":
        fraction = abs(line) % 1
        if math.isclose(fraction, 0., abs_tol=1e-8):
            interpretation = "conditional_on_non_push"
            warnings.append("Línea entera: proxy condicionado a no devolución; falta probabilidad de push.")
        elif not math.isclose(fraction, .5, abs_tol=1e-8):
            interpretation = "not_direct_margin_partial_or_unknown_settlement"
            warnings.append("Cuarto u otra línea: pagos parciales/contrato requieren distribución de pagos; no margen directo.")
    if contract.get("cricket_contract_unknown"):
        interpretation = "contract_unknown_price_index_only"
        warnings.append("Cricket: se conserva la partición cotizada; reglas de draw/tie/no result sin verificar.")
    elif contract["family"] == "h2h" and sport != "football" and contract["period"] != "full_game" and contract["expected"] != ("home", "draw", "away"):
        interpretation = "conditional_on_non_push_or_period_rule"
        warnings.append("Ganador de período de dos lados: empate/devolución requiere verificar reglas.")
    return interpretation, " ".join(warnings)


def _quantile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def _summary(boards):
    margins = [b["overround"] for b in boards]
    return {"boards": len(boards), "events": len({b["event_id"] for b in boards}),
            "median_overround": median(margins), "p25": _quantile(margins, .25),
            "p75": _quantile(margins, .75),
            "median_loss_proxy": median(b["proportional_loss_proxy"] for b in boards),
            "bookmakers": len({b["bookmaker"] for b in boards}),
            "family_counts": dict(sorted(Counter(b["market_family"] for b in boards).items())),
            "warning": "Distribución descriptiva de esta composición de contratos; no ranking de rentabilidad."}


def summarize_costs(quotes: list[dict]) -> dict:
    """Summarize complete boards, preserving contract and sample caveats.

    Caller controls snapshot freshness. This function retains capture/update
    metadata and refuses to join sides across those timestamps. Repeated
    featured/alternate quotes of the same exposure count once; newest complete
    capture wins, with deterministic lexical ties (never best-price selection).
    """
    groups, skipped = {}, Counter()
    for row in quotes:
        if not isinstance(row, dict):
            skipped["invalid_row"] += 1
            continue
        excluded = _excluded(row)
        if excluded:
            skipped[excluded] += 1
            continue
        event, book = _text(row.get("event_id")), _text(row.get("bookmaker"))
        odds = _num(row.get("odds"))
        if not event or not book or odds is None or odds <= 1:
            skipped["invalid_identity_or_odds"] += 1
            continue
        contract, reason = _contract(row)
        if reason:
            skipped[reason] += 1
            continue
        sport = _sport(row)
        identity = (event, sport, book, contract["canonical"], contract["period"],
                    contract["line"], contract["participant"])
        capture = tuple(_text(row.get(k)) for k in ("market_key", "region", "last_update", "retrieved_at"))
        group = groups.setdefault((identity, capture), {"row": row, "contract": contract, "sides": {}, "conflict": False, "n": 0})
        group["n"] += 1
        outcome = contract["outcome"]
        if outcome in group["sides"] and group["sides"][outcome] != odds:
            group["conflict"] = True
        group["sides"][outcome] = odds
    complete, incomplete = {}, 0
    for (identity, capture), group in groups.items():
        contract, sides, row = group["contract"], group["sides"], group["row"]
        expected = contract["expected"]
        if expected is None:
            expected = ("home", "draw", "away") if "draw" in sides else ("home", "away")
        if group["conflict"] or set(sides) != set(expected):
            incomplete += 1
            continue
        rank = (_stamp(row.get("last_update")), _stamp(row.get("retrieved_at")), capture)
        if identity in complete and complete[identity][0] >= rank:
            continue
        s = sum(1 / sides[outcome] for outcome in expected)
        interpretation, warning = _warning(contract, identity[1])
        update_stamp, capture_stamp = _stamp(row.get("last_update")), _stamp(row.get("retrieved_at"))
        age = capture_stamp - update_stamp if math.isfinite(update_stamp) and math.isfinite(capture_stamp) else None
        board = {"event_id": identity[0], "sport": identity[1],
                 "sport_key": _text(row.get("sport_key")), "bookmaker": identity[2],
                 "home_team": _text(row.get("home_team")), "away_team": _text(row.get("away_team")),
                 "bookmaker_title": _text(row.get("bookmaker_title")) or identity[2],
                 "market_family": contract["family"], "market_key": contract["canonical"],
                 "source_market_key": _text(row.get("market_key")),
                 "period": contract["period"], "line": contract["line"],
                 "participant": contract["participant"], "outcomes": list(expected),
                 "odds": {outcome: sides[outcome] for outcome in expected},
                 "n": len(expected), "inverse_odds_sum": s, "overround": s - 1,
                 "proportional_loss_proxy": 1 - 1 / s,
                 "cost_interpretation": interpretation, "warning": warning,
                 "region": _text(row.get("region")),
                 "last_update": _text(row.get("last_update")),
                 "retrieved_at": _text(row.get("retrieved_at")),
                 "quote_age_seconds": age,
                 "commence_time": _text(row.get("commence_time")),
                 "verified_rules": row.get("verified_rules") is True,
                 "executable": False}
        complete[identity] = rank, board
    boards = [item[1] for _, item in sorted(complete.items(), key=lambda item: repr(item[0]))]
    by_sport, by_family, by_book = defaultdict(list), defaultdict(list), defaultdict(list)
    for board in boards:
        by_sport[board["sport"]].append(board)
        by_family[(board["sport"], board["market_family"])].append(board)
        by_book[board["bookmaker"]].append(board)
    all_sports = set(by_sport)
    matched = []
    for book, items in sorted(by_book.items()):
        sport_groups = defaultdict(list)
        for board in items:
            sport_groups[board["sport"]].append(board)
        if len(all_sports) >= 2 and set(sport_groups) == all_sports:
            core_groups = {sport: [b for b in sample if b["market_family"] == "h2h" and b["period"] == "full_game"]
                           for sport, sample in sport_groups.items()}
            matched.append({"bookmaker": book, "sports": sorted(sport_groups),
                            "by_sport": [{"sport": sport, **_summary(sample)} for sport, sample in sorted(sport_groups.items())],
                            "h2h_full_game_by_sport": [{"sport": sport, **_summary(sample)} for sport, sample in sorted(core_groups.items()) if sample],
                            "complete_h2h_sport_coverage": all(core_groups.values()),
                            "warning": "Misma casa, pero eventos/mercados no emparejados; no ranking causal de deportes."})
    return {"schema_version": 1, "input_quotes": len(quotes), "boards": boards,
            "by_sport": [{"sport": sport, **_summary(sample)} for sport, sample in sorted(by_sport.items())],
            "by_family": [{"sport": sport, "market_family": family, **_summary(sample)} for (sport, family), sample in sorted(by_family.items())],
            "matched_sportsbooks": matched,
            "skipped_rows_by_reason": dict(sorted(skipped.items())),
            "incomplete_or_conflicting_capture_boards": incomplete,
            "freshness_policy": "Filtrado por el llamador; no se mezclan lados de distintas capturas/updates.",
            "warning": "Muestra descriptiva por casa y contrato; overround y proxy proporcional no son ROI real, probabilidad verdadera ni ventaja demostrada."}
