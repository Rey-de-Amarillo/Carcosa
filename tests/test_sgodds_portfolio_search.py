import sys
import unittest
import random

from scripts.sgodds_portfolio_search import (
    Contract, contract_parts, first_choices, single_period_complete_bound,
    solve_portfolio, valid_joint_states, validate_state,
    verify_portfolio_complete,
    search_weak_portfolio, complete_payoff_superset,
)


def contract(market, selection, line=None, period="FT", odds=2.0):
    return Contract(market + selection, market, period, selection, line, odds)


class SettlementTests(unittest.TestCase):
    def test_quarter_handicap_half_refunds(self):
        draw = (0, 0, 1, 1, 0, 1)
        home_by_one = (0, 0, 2, 1, 0, 1)
        self.assertEqual(contract_parts(contract("ft_asian_handicap", "home", -.25), draw), (0, .5))
        self.assertEqual(contract_parts(contract("ft_asian_handicap", "away", .25), draw), (.5, .5))
        self.assertEqual(contract_parts(contract("ft_asian_handicap", "home", -.75), home_by_one), (.5, .5))

    def test_quarter_total_and_integer_refund(self):
        two = (0, 0, 1, 1, 0, 1)
        three = (0, 0, 2, 1, 0, 1)
        self.assertEqual(contract_parts(contract("ft_goal_total", "under", 2.25), two), (.5, .5))
        self.assertEqual(contract_parts(contract("ft_goal_total", "over", 2.25), two), (0, .5))
        self.assertEqual(contract_parts(contract("ft_goal_total", "under", 2.75), three), (0, .5))
        self.assertEqual(contract_parts(contract("ft_goal_total", "over", 2), two), (0, 1))

    def test_correct_score_other_is_not_missing_quote_complement(self):
        other = contract("ft_correct_score", "other")
        self.assertEqual(contract_parts(other, (0, 0, 4, 4, 0, 1)), (0, 0))
        self.assertEqual(contract_parts(other, (0, 0, 5, 5, 0, 1)), (1, 0))
        self.assertEqual(contract_parts(other, (0, 0, 16, 16, 0, 1)), (1, 0))
        self.assertEqual(contract_parts(contract("ht_correct_score", "other", period="HT"), (3, 0, 3, 0, 1, 1)), (1, 0))

    def test_first_goal_is_consistent_across_halves(self):
        self.assertFalse(validate_state((1, 0, 1, 1, 1, 2)))
        self.assertTrue(validate_state((0, 0, 1, 1, 0, 2)))
        self.assertTrue(all(validate_state(s) for s in valid_joint_states()))
        c = contract("ht_ft_result", "home/draw", period="HT+FT")
        self.assertEqual(contract_parts(c, (1, 0, 1, 1, 1, 1)), (1, 0))

    def test_unbounded_single_period_payoff_patterns_are_represented(self):
        contracts = [contract("ft_correct_score", "other"), contract("ft_correct_score", "5-4"),
                     contract("ft_goal_total", "over", 5.75), contract("ft_exact_total_goals", "9+"),
                     contract("ft_asian_handicap", "home", -3.25), contract("ft_btts", "yes"),
                     contract("ft_odd_even", "odd"), contract("ft_1x2", "draw"),
                     contract("ft_first_team_to_score", "home")]
        bound = single_period_complete_bound(contracts)
        def pattern(h, a, first):
            return tuple(contract_parts(c, (0, 0, h, a, 0, first)) for c in contracts)
        finite = {pattern(h, a, first) for h in range(bound + 1) for a in range(bound + 1) for first in first_choices(h, a)}
        large = {pattern(h, a, first) for h in range(80) for a in range(80) for first in first_choices(h, a)}
        self.assertTrue(large <= finite)


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, "/tmp/football-portfolio-scipy")
        try:
            import numpy
            from scipy.optimize import linprog
        except ImportError as error:
            raise unittest.SkipTest("Isolated SciPy installation needed") from error
        cls.np, cls.linprog = numpy, staticmethod(linprog)

    def solve(self, contracts, states):
        return solve_portfolio(contracts, tuple(states), np=self.np, linprog=self.linprog)

    def test_synthetic_two_way_arbitrage_is_detected(self):
        contracts = [contract("ft_btts", "yes", odds=2.1), contract("ft_btts", "no", odds=2.1)]
        result = self.solve(contracts, [(0, 0, 0, 0, 0, 0), (0, 0, 1, 1, 0, 1)])
        self.assertAlmostEqual(result["finite_grid_optimal_gross"], 1.05)
        self.assertEqual(result["status"], "positive_finite_grid_requires_tail_verification")

    def test_rational_dual_proves_no_profit(self):
        contracts = [contract("ft_btts", "yes", odds=1.8), contract("ft_btts", "no", odds=1.8)]
        result = self.solve(contracts, [(0, 0, 0, 0, 0, 0), (0, 0, 1, 1, 0, 1)])
        self.assertEqual(result["status"], "no_guaranteed_profit_exact_dual")
        proof = result["rational_dual"]
        self.assertLessEqual(proof["maximum_contract_expected_payoff_numerator"], proof["expected_payoff_denominator"])
        self.assertAlmostEqual(proof["maximum_contract_expected_gross"], .9)

    def test_truncated_score_positive_is_not_claimed_as_real_arbitrage(self):
        contracts = [contract("ft_correct_score", "0-0", odds=2)]
        truncated = self.solve(contracts, [(0, 0, 0, 0, 0, 0)])
        self.assertEqual(truncated["status"], "positive_finite_grid_requires_tail_verification")
        expanded = self.solve(contracts, [(0, 0, 0, 0, 0, 0), (0, 0, 1, 0, 0, 1)])
        self.assertEqual(expanded["status"], "no_guaranteed_profit_exact_dual")

    def test_complete_verification_and_conservative_cent_rounding(self):
        portfolio = [{"field": "a", "market": "ft_btts", "period": "FT", "selection": "yes", "line": None, "odds": 2.1, "stake_fraction": .5},
                     {"field": "b", "market": "ft_btts", "period": "FT", "selection": "no", "line": None, "odds": 2.1, "stake_fraction": .5}]
        answer = verify_portfolio_complete(portfolio, np=self.np)
        self.assertTrue(answer["positive_on_all_completed_match_patterns"])
        self.assertEqual(answer["minimum_return_on_100_cent_stakes_payouts_rounded_down"], 105)
        self.assertAlmostEqual(answer["minimum_profit_after_haircut_and_capital_cost"], .0345)

    def test_integer_push_weak_arbitrage_is_not_missed(self):
        contracts = [contract("ft_goal_total", "under", 2, odds=2.1), contract("ft_goal_total", "over", 2, odds=2.1)]
        states = ((0, 0, 0, 0, 0, 0), (0, 0, 1, 1, 0, 1), (0, 0, 2, 2, 0, 1))
        answer = search_weak_portfolio(contracts, states, np=self.np, linprog=self.linprog)
        self.assertEqual(answer["status"], "recorded_price_weak_arbitrage_complete_payoff_verified")
        proof = answer["complete_payoff_verification"]
        self.assertEqual(proof["exact_minimum_gross_numerator"], proof["exact_gross_denominator"])
        self.assertGreater(proof["exact_maximum_gross_numerator"], proof["exact_gross_denominator"])

    def test_joint_superset_retains_large_correlated_patterns(self):
        contracts = [contract("ft_correct_score", "other"), contract("ht_correct_score", "0-0", period="HT"),
                     contract("ft_goal_total", "over", 4.5), contract("ht_goal_total", "under", 1.5, period="HT"),
                     contract("ht_ft_result", "home/away", period="HT+FT"),
                     contract("ft_first_team_to_score", "home"), contract("ht_first_team_to_score", "home", period="HT")]
        states, _ = complete_payoff_superset(contracts, self.np)
        patterns = {tuple(contract_parts(c, s) for c in contracts) for s in states}
        rng = random.Random(37)
        for _ in range(500):
            hh, ha = rng.randrange(40), rng.randrange(40)
            fh, fa = hh + rng.randrange(40), ha + rng.randrange(40)
            for ht_first in first_choices(hh, ha):
                for ft_first in ((ht_first,) if ht_first else first_choices(fh, fa)):
                    s = hh, ha, fh, fa, ht_first, ft_first
                    self.assertIn(tuple(contract_parts(c, s) for c in contracts), patterns)


if __name__ == "__main__":
    unittest.main()
