import random
import unittest

from scripts.betcity_crossmarket_search import (
    compress_state, make_pattern, parse_contract, payoff_parts, scientific_imports, solve_portfolio, solve_weak_portfolio,
)


class BetcityCrossmarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.np, linprog = scientific_imports()
        cls.linprog = staticmethod(linprog)

    def test_synthetic_arbitrage_three_results(self):
        contracts = tuple(map(parse_contract, ["WIN__P1", "WIN__PX", "WIN__P2"]))
        pattern = make_pattern(contracts, self.np)
        answer = solve_portfolio(pattern, self.np.array([3.4,3.4,3.4]), self.np, self.linprog)
        self.assertAlmostEqual(answer["minimum_gross_return"], 3.4/3)
        self.assertAlmostEqual(sum(answer["weights"]), 1)

    def test_integer_draw_refunds_block_strict_profit(self):
        contracts = tuple(map(parse_contract, ["HANDICAP__P1(0)", "HANDICAP__P2(0)"]))
        pattern = make_pattern(contracts, self.np)
        answer = solve_portfolio(pattern, self.np.array([3.0,3.0]), self.np, self.linprog)
        self.assertAlmostEqual(answer["minimum_gross_return"], 1)
        self.assertEqual(payoff_parts(contracts[0], 12,12), (0,1))
        weak = solve_weak_portfolio(pattern, self.np.array([3.0,3.0]), self.np, self.linprog)
        self.assertIsNotNone(weak)
        self.assertAlmostEqual(weak["minimum_gross_return"],1)
        self.assertGreaterEqual(weak["maximum_gross_return"],1.5)
        self.assertAlmostEqual(weak["mean_return_over_uniform_patterns_not_real_probability"],4/3)

    def test_fair_partition_is_not_a_weak_arbitrage(self):
        contracts = tuple(map(parse_contract, ["WIN__P1", "WIN__PX", "WIN__P2"]))
        pattern = make_pattern(contracts,self.np)
        self.assertIsNone(solve_weak_portfolio(pattern,self.np.array([3.,3.,3.]),self.np,self.linprog))

    def test_quarter_lines_preserve_half_loss_and_half_win(self):
        under = parse_contract("TOTALS__UNDER(2.25)")
        over = parse_contract("TOTALS__OVER(2.25)")
        self.assertEqual(payoff_parts(under,1,1), (.5,.5))
        self.assertEqual(payoff_parts(over,1,1), (0,.5))
        home = parse_contract("HANDICAP__P1(-0.25)")
        self.assertEqual(payoff_parts(home,4,4), (0,.5))
        self.assertFalse(home.strict_binary)

    def test_unbounded_scores_map_to_identical_complete_patterns(self):
        contracts = tuple(map(parse_contract, ["WIN__PX", "WIN__1X", "BOTH_TEAMS_TO_SCORE__YES",
            "HANDICAP__P1(-13.5)", "HANDICAP__P2(0)", "TOTALS__UNDER(14.5)",
            "P1__TOTALS__OVER(11.5)", "P2__TOTALS__UNDER(8.5)"]))
        rng = random.Random(21)
        for _ in range(2000):
            home,away = rng.randrange(10000),rng.randrange(10000)
            mapped = compress_state(home,away,contracts)
            self.assertEqual([payoff_parts(c,home,away) for c in contracts],
                             [payoff_parts(c,*mapped) for c in contracts])

    def test_score_gap_is_not_an_arbitrage(self):
        contracts = tuple(map(parse_contract, ["TOTALS__UNDER(0.5)","TOTALS__OVER(1.5)"]))
        pattern = make_pattern(contracts, self.np)
        answer = solve_portfolio(pattern,self.np.array([5.0,5.0]),self.np,self.linprog)
        self.assertAlmostEqual(answer["minimum_gross_return"],0)

    def test_unknown_scope_does_not_silently_enter_model(self):
        self.assertIsNone(parse_contract("PLAYER_GOALS__Haaland"))
        self.assertIsNone(parse_contract("TOTALS__ODD"))


if __name__ == "__main__":
    unittest.main()
