import itertools
import unittest
from datetime import datetime, timedelta, timezone

from engine.market_audit import audit_event, portfolio_net, score_state_space
from engine.markets import settle_score


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def quote(market, selection, odds, **kwargs):
    result = {"event_id": "match-1", "market": market, "selection": selection,
              "odds": odds, "bookmaker": "book", "last_update": NOW.isoformat(),
              "period": "90m", "settlement_rules": "football-regulation-v1"}
    result.update(kwargs)
    return result


def positive(result):
    return [candidate for candidate in result["candidates"] if candidate["strictly_positive_under_contract"]]


class ContractAuditTests(unittest.TestCase):
    def test_explicit_null_optional_fields_from_provider_normalizer(self):
        result = audit_event([quote("1x2", s, 3.2, line=None, score=None, team=None) for s in ("home", "draw", "away")], now=NOW)
        self.assertEqual(len(positive(result)), 1)
        exact = audit_event([quote("correct_score", "score", 8, line=None, score=(2, 1)),
                             quote("correct_score", "2-1", 9, line=None, score=None)], now=NOW)
        self.assertTrue(any(r["type"] == "identical_settlement" for r in exact["relations"]))

    def test_complete_three_way_inverse_prices_and_unfilled_status(self):
        result = audit_event([quote("1x2", s, 3.2, quote_id=s) for s in ("home", "draw", "away")], now=NOW)
        self.assertEqual(len(positive(result)), 1)
        candidate = positive(result)[0]
        self.assertAlmostEqual(candidate["inverse_sum"], 3/3.2)
        self.assertAlmostEqual(candidate["minimum_net_return_per_capital"], 1/(3/3.2)-1)
        self.assertFalse(candidate["verified_arbitrage"])
        self.assertFalse(candidate["executable"])
        self.assertIn("unfilled_legs", candidate["validation_flags"])

    def test_missing_result_cannot_be_covered_by_normalizing_two_prices(self):
        result = audit_event([quote("1x2", "home", 10), quote("1x2", "away", 10)], now=NOW)
        self.assertEqual(result["candidates"], [])
        self.assertTrue(any(r["reason"] == "missing_outcomes" for r in result["rejected"]))

    def test_double_chance_overlap_requires_payoff_matrix_and_three_legs(self):
        result = audit_event([quote("double_chance", s, 1.6) for s in ("home_draw", "draw_away", "home_away")], now=NOW)
        self.assertGreater(3/1.6, 1)  # Ordinary inverse-sum test would miss it.
        self.assertEqual(len(positive(result)), 1)
        self.assertEqual(len(positive(result)[0]["legs"]), 3)
        self.assertAlmostEqual(positive(result)[0]["minimum_net_return_per_capital"], 1/15)
        self.assertTrue(any(r["reason"] == "overlapping_outcomes_inverse_sum_invalid" for r in result["rejected"]))

    def test_double_chance_fair_cover_is_not_a_positive_opportunity(self):
        result = audit_event([quote("double_chance", s, 1.5) for s in ("home_draw", "draw_away", "home_away")], now=NOW)
        self.assertEqual(positive(result), [])
        self.assertEqual(result["candidates"], [])

    def test_dnb_positive_without_draw_but_not_strict_sure_profit(self):
        result = audit_event([quote("dnb", s, 2.1) for s in ("home", "away")], now=NOW)
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["type"], "conditional_non_loss_cover")
        self.assertEqual(candidate["minimum_net_return_per_capital"], 0)
        self.assertAlmostEqual(candidate["maximum_net_return_per_capital"], .05)
        self.assertEqual(result["summary"]["synchronized_positive_contract_candidates"], 0)

    def test_asian_integer_refund_and_quarter_half_settlement(self):
        integer = audit_event([quote("asian_handicap", "home", 2.2, line=-1),
                               quote("asian_handicap", "away", 2.2, line=1)], now=NOW)
        self.assertEqual(positive(integer), [])
        self.assertEqual(integer["candidates"][0]["minimum_net_return_per_capital"], 0)
        quarter = audit_event([quote("asian_handicap", "home", 2.2, line=-.25),
                               quote("asian_handicap", "away", 2.2, line=.25)], now=NOW)
        # A .5/.5 allocation only guarantees .05. The exact maximin matrix
        # shifts capital to 16/33 and 17/33, raising the floor to 1/15.
        self.assertAlmostEqual(positive(quarter)[0]["minimum_net_return_per_capital"], 1/15)
        self.assertNotAlmostEqual(positive(quarter)[0]["minimum_net_return_per_capital"], 1/(2/2.2)-1)

    def test_dnb_asian_zero_identical_settlement_is_price_comparison(self):
        result = audit_event([quote("dnb", "home", 1.9, quote_id="dnb"),
                              quote("asian_handicap", "home", 2.0, line=0, quote_id="ah")], now=NOW)
        self.assertEqual(result["candidates"], [])
        self.assertTrue(any(r["type"] == "identical_settlement" for r in result["relations"]))
        dominance = [r for r in result["relations"] if r["type"] == "payoff_dominance"]
        self.assertEqual(dominance[0]["better_quote_id"], "ah")

    def test_replication_draw_stake_is_refund_not_a_win(self):
        result = audit_event([quote("1x2", "home", 2, quote_id="h"), quote("1x2", "draw", 4, quote_id="d"),
                              quote("dnb", "home", 1.6, quote_id="dnb"),
                              quote("double_chance", "home_draw", 1.4, quote_id="dc")], now=NOW)
        dnb = next(r for r in result["relations"] if r["type"] == "dnb_replication")
        dc = next(r for r in result["relations"] if r["type"] == "double_chance_replication")
        self.assertAlmostEqual(dnb["synthetic_odds"], 2*(1-1/4))
        self.assertAlmostEqual(dnb["components"][0]["capital_fraction"], .25)
        self.assertAlmostEqual(dnb["quoted_price_improvement"], .1)
        self.assertAlmostEqual(dc["synthetic_odds"], 1/(1/2+1/4))
        self.assertFalse(dc["is_arbitrage"])

    def test_btts_yes_subset_total_over_one_and_half_is_not_independent(self):
        result = audit_event([quote("btts", "yes", 1.8, quote_id="btts"),
                              quote("totals", "over", 2, line=1.5, quote_id="over")], now=NOW)
        self.assertEqual(result["candidates"], [])
        self.assertTrue(any(r.get("better_quote_id") == "over" and r.get("worse_quote_id") == "btts" for r in result["relations"]))

    def test_middle_positive_inside_interval_still_loses_outside(self):
        result = audit_event([quote("totals", "over", 1.8, line=2.5),
                              quote("totals", "under", 1.8, line=3.5)], now=NOW)
        self.assertEqual(result["candidates"], [])
        middle = next(r for r in result["relations"] if r["type"] == "middle_interval")
        self.assertAlmostEqual(middle["minimum_net_return_per_capital"], -.1)
        self.assertAlmostEqual(middle["maximum_net_return_per_capital"], .8)

    def test_categorical_two_way_market_works_for_other_sports(self):
        result = audit_event([quote("h2h", s, 2.1, expected_outcomes=["alpha", "beta"], sport="tennis")
                              for s in ("alpha", "beta")], now=NOW)
        self.assertAlmostEqual(positive(result)[0]["minimum_net_return_per_capital"], .05)
        self.assertEqual(positive(result)[0]["state_space"]["kind"], "declared_exhaustive_categorical")

    def test_categorical_three_way_can_keep_explicit_participant_names(self):
        outcomes = ["alpha", "draw", "beta"]
        result = audit_event([quote("h2h", s, 3.2, expected_outcomes=outcomes) for s in outcomes], now=NOW)
        self.assertAlmostEqual(positive(result)[0]["minimum_net_return_per_capital"], 1/15)
        self.assertIn("unverified_outcome_partition", positive(result)[0]["validation_flags"])


class QuoteValidityTests(unittest.TestCase):
    def test_different_statistics_and_score_bases_never_share_a_matrix(self):
        for field, value in (("statistic", "corners"), ("settlement_basis", "remaining_score")):
            other = {"statistic": "goals"}
            other[field] = value
            result = audit_event([quote("totals", "over", 3, line=2.5, statistic="goals"),
                                  quote("totals", "under", 3, line=2.5, **other)], now=NOW)
            self.assertEqual(result["candidates"], [])

    def test_in_play_basis_must_be_explicit_and_duplicate_ids_are_rejected(self):
        result = audit_event([quote("totals", "over", 3, line=2.5, in_play=True)], now=NOW)
        self.assertEqual(result["rejected"][0]["reason"], "unsupported_in_play_basis")
        duplicates = audit_event([quote("totals", s, 3, line=2.5, quote_id="same") for s in ("over", "under")], now=NOW)
        self.assertEqual(duplicates["candidates"], [])
        self.assertTrue(any(r["reason"] == "duplicate_quote_id" for r in duplicates["rejected"]))

    def test_duplicate_prices_are_pruned_and_search_caps_are_explicit(self):
        quotes = [quote("totals", s, 2.1+book*.01, line=line, bookmaker=str(book))
                  for book in range(5) for line in (1.5, 2.5, 3.5) for s in ("over", "under")]
        result = audit_event(quotes, now=NOW, max_cross_quotes=2, max_relation_quotes=2)
        self.assertEqual(result["summary"]["retained_best_prices"], 6)
        self.assertEqual(result["summary"]["collapsed_duplicate_prices"], 24)
        self.assertTrue(result["summary"]["cross_search_capped"])
        self.assertTrue(result["summary"]["relation_search_capped"])
        self.assertFalse(result["summary"]["search_exhaustive"])
        self.assertEqual(len(result["coverage"][0]["cross_quote_ids"]), 2)

    def test_incompatible_periods_or_rules_are_never_combined(self):
        for field, value in (("period", "including_extra_time"), ("settlement_rules", "different_abandonment_rule")):
            quotes = [quote("totals", "over", 3, line=2.5), quote("totals", "under", 3, line=2.5, **{field: value})]
            result = audit_event(quotes, now=NOW)
            self.assertEqual(result["candidates"], [])
            self.assertTrue(any(r["reason"] == "incompatible_periods_or_rules_not_compared" for r in result["rejected"]))

    def test_stale_missing_naive_or_future_clocks_are_rejected_by_default(self):
        for timestamp in (None, "2026-10-30T12:00:00", (NOW-timedelta(seconds=901)).isoformat(),
                          (NOW+timedelta(seconds=3)).isoformat()):
            result = audit_event([quote("totals", "over", 3, line=2.5, last_update=timestamp),
                                  quote("totals", "under", 3, line=2.5)], now=NOW)
            self.assertEqual(result["candidates"], [])
            self.assertTrue(result["rejected"])

    def test_unsynchronized_quotes_only_report_price_relation(self):
        result = audit_event([quote("totals", "over", 3, line=2.5, last_update=(NOW-timedelta(seconds=121)).isoformat()),
                              quote("totals", "under", 3, line=2.5)], now=NOW)
        self.assertTrue(positive(result)[0]["relation_only"])
        self.assertIn("unsynchronized_quotes", positive(result)[0]["validation_flags"])
        self.assertEqual(result["summary"]["synchronized_positive_contract_candidates"], 0)

    def test_archived_timestamp_opt_in_never_counts_as_synchronized_opportunity(self):
        result = audit_event([quote("totals", s, 3, line=2.5, last_update=None) for s in ("over", "under")],
                             now=NOW, allow_unverified_timestamps=True)
        self.assertTrue(positive(result)[0]["relation_only"])
        self.assertFalse(positive(result)[0]["synchronized"])
        self.assertEqual(result["summary"]["synchronized_positive_contract_candidates"], 0)

    def test_limits_scale_capital_but_do_not_prove_fills(self):
        result = audit_event([quote("totals", s, 3, line=2.5, available_limit=10, verified_rules=True)
                              for s in ("over", "under")], now=NOW)
        candidate = positive(result)[0]
        self.assertAlmostEqual(candidate["max_capital_from_reported_limits"], 20)
        self.assertFalse(candidate["executable"])
        self.assertFalse(candidate["verified_arbitrage"])


class ExchangeAuditTests(unittest.TestCase):
    def test_lay_capital_means_liability_and_wins_backer_stake_less_fee(self):
        lay = quote("1x2", "home", 4, side="lay", commission_rate=.05)
        self.assertAlmostEqual(portfolio_net([lay], [1], (1, 0)), -1)
        self.assertAlmostEqual(portfolio_net([lay], [1], (0, 1)), .95/3)

    def test_exchange_commission_is_on_market_net_not_each_winning_leg(self):
        common = {"commission_rate": .05, "is_exchange": True, "exchange_market_id": "exchange-123"}
        back, lay = quote("1x2", "home", 3, **common), quote("1x2", "home", 3, side="lay", **common)
        for state in ((1, 0), (0, 0), (0, 1)):
            self.assertAlmostEqual(portfolio_net([back, lay], [1, 2], state), 0)

    def test_near_back_lay_crossing_survives_market_net_commission(self):
        common = {"commission_rate": .02, "is_exchange": True, "exchange_market_id": "exchange-123"}
        result = audit_event([quote("1x2", "home", 3, **common),
                              quote("1x2", "home", 2.99, side="lay", **common)], now=NOW)
        self.assertEqual(len(positive(result)), 1)
        candidate = positive(result)[0]
        lay_stake = 3/2.99
        total_capital = 1+lay_stake*(2.99-1)
        expected = (lay_stake-1)*.98/total_capital
        self.assertAlmostEqual(candidate["minimum_net_return_per_capital"], expected)

    def test_commission_can_erase_an_apparent_back_lay_profit(self):
        result = audit_event([quote("1x2", "home", 3),
                              quote("1x2", "home", 2.99, side="lay", commission_rate=.05)], now=NOW)
        self.assertEqual(positive(result), [])

    def test_exchange_fee_missing_or_inconsistent_rejected(self):
        missing = audit_event([quote("1x2", "home", 3, side="lay")], now=NOW)
        self.assertEqual(missing["rejected"][0]["reason"], "missing_exchange_commission")
        quotes = [quote("1x2", "home", 3, is_exchange=True, commission_rate=.02, exchange_market_id="same"),
                  quote("1x2", "home", 2.9, side="lay", commission_rate=.05, exchange_market_id="same")]
        inconsistent = audit_event(quotes, now=NOW)
        self.assertEqual(inconsistent["candidates"], [])
        self.assertTrue(any(r["reason"] == "inconsistent_exchange_commission" for r in inconsistent["rejected"]))


class ExhaustiveStatesTests(unittest.TestCase):
    def test_overflow_representatives_cover_distant_scores_and_odd_even(self):
        quotes = [quote("totals", "over", 2, line=2.75), quote("team_totals", "under", 2, line=3.25, team="away"),
                  quote("asian_handicap", "home", 2, line=-4.25), quote("european_handicap", "draw", 2, line=-3),
                  quote("winning_margin", "away", 2, line=5), quote("correct_score", "2-4", 2),
                  quote("odd_even", "odd", 2), quote("btts", "yes", 2), quote("1x2", "draw", 2)]
        states, certificate = score_state_space(quotes)
        def vector(state):
            return tuple(settle_score(*state, q["market"], q["selection"], line=q.get("line"), team=q.get("team"))["outcome"] for q in quotes)
        representative_vectors = {vector(state) for state in states}
        for state in itertools.product((0, 1, 2, 3, 4, 5, 9, 10, 49, 50, 99, 100), repeat=2):
            self.assertIn(vector(state), representative_vectors)
        self.assertTrue(certificate["overflow_checked"])
        self.assertTrue(certificate["complete"])
        self.assertGreater(certificate["overflow_representatives"], 0)

    def test_truncated_exact_score_and_under_cannot_hide_high_score_loss(self):
        result = audit_event([quote("correct_score", "0-0", 100), quote("totals", "under", 100, line=2.5)], now=NOW)
        self.assertEqual(result["candidates"], [])

    def test_unsupported_outcome_or_impractical_threshold_not_silently_approximated(self):
        result = audit_event([quote("player_first_goal_scorer", "player", 5), quote("totals", "over", 3, line=1000)], now=NOW)
        reasons = {r["reason"] for r in result["rejected"]}
        self.assertIn("unsupported_settlement", reasons)
        self.assertIn("state_space_too_large", reasons)


if __name__ == "__main__":
    unittest.main()
