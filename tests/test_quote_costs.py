import copy
import math
import unittest

from engine.quote_costs import summarize_costs


def quote(selection, odds=1.9, **changes):
    row = {"event_id": "e", "sport": "football", "sport_key": "soccer_epl",
           "home_team": "Home FC", "away_team": "Away FC", "bookmaker": "book_a",
           "bookmaker_title": "Book A", "market_key": "totals", "selection": selection,
           "description": None, "line": 2.5, "odds": odds,
           "last_update": "2026-10-30T12:00:00Z", "retrieved_at": "2026-10-30T12:01:00Z",
           "region": "eu", "commence_time": "2026-10-31T12:00:00Z", "exchange": False, "dfs": False}
    row.update(changes)
    return row


def pair(**changes):
    return [quote("Over", **changes), quote("Under", **changes)]


class QuoteCostTests(unittest.TestCase):
    def test_two_and_three_outcomes_can_have_identical_margin(self):
        rows = [quote(name, 2.85, market_key="h2h", line=None)
                for name in ("Home FC", "Draw", "Away FC")]
        rows += [quote(name, 1.9, event_id="b", sport="basketball", sport_key="basketball_nba", market_key="h2h", line=None)
                 for name in ("Home FC", "Away FC")]
        result = summarize_costs(rows)
        self.assertEqual(len(result["boards"]), 2)
        a, b = result["boards"]
        self.assertAlmostEqual(a["overround"], b["overround"])
        self.assertAlmostEqual(a["proportional_loss_proxy"], .05)
        self.assertEqual(len(result["matched_sportsbooks"]), 1)
        self.assertFalse(a["executable"])

    def test_nonexclusive_or_incomplete_runner_lists_never_become_costs(self):
        rows = []
        for key in ("double_chance", "player_goal_scorer_anytime", "player_first_goal_scorer", "correct_score"):
            rows += [quote(x, market_key=key, line=None) for x in ("A", "B", "C")]
        result = summarize_costs(rows)
        self.assertEqual(result["boards"], [])
        self.assertEqual(sum(result["skipped_rows_by_reason"].values()), len(rows))

    def test_missing_side_is_not_normalized_or_borrowed_from_another_book(self):
        result = summarize_costs([quote("Over"), quote("Under", bookmaker="book_b")])
        self.assertEqual(result["boards"], [])
        self.assertEqual(result["by_sport"], [])
        self.assertEqual(result["incomplete_or_conflicting_capture_boards"], 2)
        self.assertEqual(summarize_costs([])["matched_sportsbooks"], [])

    def test_side_lines_must_match_and_handicap_signs_are_opposite(self):
        good = [quote("Home FC", market_key="spreads", line=-1.5),
                quote("Away FC", market_key="spreads", line=1.5)]
        board = summarize_costs(good)["boards"][0]
        self.assertEqual(board["line"], -1.5)
        self.assertEqual(set(board["odds"]), {"home", "away"})
        bad = copy.deepcopy(good)
        bad[1]["line"] = -1.5
        self.assertEqual(summarize_costs(bad)["boards"], [])
        self.assertEqual(summarize_costs([quote("Over", line=2.5), quote("Under", line=3.5)])["boards"], [])

    def test_integer_and_quarter_lines_do_not_claim_direct_margin(self):
        integer = summarize_costs(pair(line=2))["boards"][0]
        quarter = summarize_costs(pair(line=2.25))["boards"][0]
        half = summarize_costs(pair(line=2.5))["boards"][0]
        self.assertEqual(integer["cost_interpretation"], "conditional_on_non_push")
        self.assertEqual(quarter["cost_interpretation"], "not_direct_margin_partial_or_unknown_settlement")
        self.assertEqual(half["cost_interpretation"], "proportional_no_push_proxy")

    def test_exchange_and_dfs_excluded_even_without_explicit_flags(self):
        rows = pair(bookmaker="betfair_ex_eu") + pair(bookmaker="prizepicks")
        rows += pair(bookmaker="another", exchange=True) + pair(bookmaker="yet_another", dfs=True)
        rows += pair(bookmaker="betfair_sb_uk")
        result = summarize_costs(rows)
        self.assertEqual(len(result["boards"]), 1)
        self.assertEqual(result["boards"][0]["bookmaker"], "betfair_sb_uk")
        self.assertEqual(sum(result["skipped_rows_by_reason"].values()), 8)

    def test_player_yes_no_and_totals_require_same_participant(self):
        rows = [quote("Yes", market_key="player_goal_scorer_anytime", description="Player A", line=None),
                quote("No", market_key="player_goal_scorer_anytime", description="Player B", line=None)]
        self.assertEqual(summarize_costs(rows)["boards"], [])
        rows[1]["description"] = "Player A"
        self.assertEqual(len(summarize_costs(rows)["boards"]), 1)
        rows = pair(market_key="player_shots_on_target", description="Player A", line=1.5)
        rows += pair(market_key="player_shots_on_target", description="Player B", line=1.5)
        self.assertEqual(len(summarize_costs(rows)["boards"]), 2)
        for row in rows:
            row["description"] = None
        self.assertEqual(summarize_costs(rows)["boards"], [])

    def test_no_mixing_periods_or_capture_timestamps(self):
        rows = [quote("Over"), quote("Under", market_key="totals_h1")]
        self.assertEqual(summarize_costs(rows)["boards"], [])
        rows[1]["market_key"] = "totals"
        rows[1]["last_update"] = "2026-10-30T12:00:01Z"
        self.assertEqual(summarize_costs(rows)["boards"], [])
        rows[1]["last_update"] = rows[0]["last_update"]
        rows[1]["retrieved_at"] = "2026-10-30T12:01:01Z"
        self.assertEqual(summarize_costs(rows)["boards"], [])

    def test_dedup_featured_alternate_uses_freshest_complete_not_best(self):
        older = pair(odds=2.0)
        newer = pair(odds=1.8, market_key="alternate_totals", last_update="2026-10-30T12:00:30Z")
        rows = older + newer + copy.deepcopy(newer)
        expected = summarize_costs(rows)
        self.assertEqual(len(expected["boards"]), 1)
        board = expected["boards"][0]
        self.assertEqual(board["odds"], {"over": 1.8, "under": 1.8})
        self.assertEqual(board["market_key"], "totals")
        self.assertEqual(expected, summarize_costs(list(reversed(rows))))
        incomplete_new = [quote("Over", odds=3., last_update="2026-10-30T12:00:40Z")]
        self.assertEqual(summarize_costs(older + incomplete_new)["boards"][0]["odds"]["over"], 2.)

    def test_alternate_player_alias_and_regulation_periods_are_not_miscounted(self):
        rows = pair(market_key="player_shots", description="Player A")
        rows += pair(market_key="player_shots_alternate", description="Player A")
        self.assertEqual(len(summarize_costs(rows)["boards"]), 1)
        rows = pair(market_key="totals_ex_ot") + pair(market_key="totals")
        boards = summarize_costs(rows)["boards"]
        self.assertEqual({b["period"] for b in boards}, {"ex_ot", "full_game"})

    def test_soccer_requires_draw_and_three_way_other_sport_requires_all_three(self):
        rows = [quote(x, market_key="h2h", line=None) for x in ("Home FC", "Away FC")]
        self.assertEqual(summarize_costs(rows)["boards"], [])
        for row in rows:
            row.update(sport="hockey", sport_key="icehockey_nhl", market_key="h2h_3_way")
        self.assertEqual(summarize_costs(rows)["boards"], [])
        rows.append(quote("Draw", sport="hockey", sport_key="icehockey_nhl", market_key="h2h_3_way", line=None))
        self.assertEqual(len(summarize_costs(rows)["boards"]), 1)

    def test_draw_no_bet_is_conditional_no_draw_and_needs_both_prices(self):
        rows = [quote(x, 2.1, market_key="draw_no_bet", line=None)
                for x in ("Home FC", "Away FC")]
        self.assertEqual(summarize_costs(rows[:1])["boards"], [])
        board = summarize_costs(rows)["boards"][0]
        self.assertEqual(board["market_family"], "draw_no_bet")
        self.assertEqual(board["cost_interpretation"], "conditional_on_no_draw")
        self.assertIn("devolución en empate", board["warning"])
        self.assertIn("ni prueba de arbitraje", board["warning"])
        self.assertLess(board["overround"], 0)
        self.assertFalse(board["executable"])

    def test_different_statistic_boards_and_cricket_unknown_rules_are_labeled(self):
        rows = pair(market_key="totals_corners") + pair(market_key="totals_cards")
        self.assertEqual(len(summarize_costs(rows)["by_family"]), 2)
        rows = [quote(x, sport="cricket", sport_key="cricket_test", market_key="h2h", line=None)
                for x in ("Home FC", "Draw", "Away FC")]
        board = summarize_costs(rows)["boards"][0]
        self.assertEqual(board["n"], 3)
        self.assertEqual(board["cost_interpretation"], "contract_unknown_price_index_only")

    def test_nonfinite_prices_and_conflicting_duplicate_captures_are_excluded(self):
        for bad in (math.inf, math.nan, 1., -2., True):
            self.assertEqual(summarize_costs([quote("Over", bad), quote("Under")])["boards"], [])
        rows = pair() + [quote("Over", 2.2)]
        self.assertEqual(summarize_costs(rows)["boards"], [])


if __name__ == "__main__":
    unittest.main()
