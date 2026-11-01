import math
import unittest
from scripts.long_run_ev import expected_log_growth,expected_portfolio_profit,expected_profit_repeated,expected_unit_profit,kelly_fraction


class LongRunEVTests(unittest.TestCase):
    def test_positive_expectation_allows_a_majority_of_losing_bets(self):
        self.assertAlmostEqual(expected_unit_profit(.30,3.5),.05)
        self.assertAlmostEqual(expected_profit_repeated(.30,3.5,100.,1000),5000.)

    def test_correlated_mixtures_cannot_create_ev_from_negative_legs(self):
        # Mutually exclusive events: no independence assumption or multiplication.
        p=[.5,.5]; returns=[[1.8,0],[0,1.8]]
        self.assertAlmostEqual(expected_portfolio_profit(p,returns,[50,50]),-10)

    def test_expected_log_growth_is_positive_with_small_positive_edge_stake(self):
        p,q=.55,2.
        f=kelly_fraction(p,q)
        self.assertAlmostEqual(f,.1)
        self.assertGreater(expected_log_growth(p,q,.1*f),0)
        self.assertLess(expected_log_growth(p,q,.9),0)

    def test_invalid_probability_is_rejected(self):
        with self.assertRaises(ValueError):expected_unit_profit(1.2,2.)
        with self.assertRaises(ValueError):expected_unit_profit(.5,float('nan'))
        with self.assertRaises(ValueError):expected_log_growth(.5,2.,1.)


if __name__=='__main__':unittest.main()
