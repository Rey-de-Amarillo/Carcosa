"""Meaningful chronology, pricing and payout checks for conditional 1X2 research."""
import importlib.util
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('research_result_ev', Path(__file__).resolve().parents[1] / 'scripts/research_result_ev.py')
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)
np = mod.np


class ResultEVTests(unittest.TestCase):
    def history(self):
        start = date(2010, 1, 1)
        return [mod.Match(start + timedelta(days=7 * i), 'E0', 'H', 'A', 1, 0, (2., 3.4, 4.), i) for i in range(12)]

    def test_current_and_same_date_result_cannot_enter_features(self):
        matches = self.history()
        matches += [mod.Match(matches[-1].day, 'E0', 'H', 'B', 6, 0, (1.5, 4., 6.), 20)]
        x1, p1, _, _, meta1, _ = mod.build_dataset(matches)
        modified = self.history()
        modified[-1].hg, modified[-1].ag = 0, 8
        modified += [mod.Match(modified[-1].day, 'E0', 'H', 'B', 0, 9, (1.5, 4., 6.), 20)]
        x2, p2, _, _, meta2, _ = mod.build_dataset(modified)
        np.testing.assert_array_equal(x1, x2)
        np.testing.assert_array_equal(p1, p2)
        self.assertEqual(meta1, meta2)

    def test_future_result_changes_only_future_features(self):
        matches = self.history()
        x1 = mod.build_dataset(matches)[0]
        matches[-2].hg, matches[-2].ag = 0, 7
        x2 = mod.build_dataset(matches)[0]
        np.testing.assert_array_equal(x1[:-1], x2[:-1])
        self.assertFalse(np.array_equal(x1[-1], x2[-1]))

    def test_one_bet_best_ev_and_decimal_payout_haircut(self):
        trades = mod.choose_bets(np.asarray([[.6, .3, .1]]), np.asarray([[2., 4., 4.]]), np.asarray([0]),
                                [{'date': '2023-01-01'}], .03)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]['selection'], 'H')
        self.assertAlmostEqual(trades[0]['profit'], 1.)
        self.assertAlmostEqual(trades[0]['expected_profit_per_unit'], .2)
        self.assertAlmostEqual(trades[0]['profit_after_1pct_odds_haircut'], .98)

    def test_mere_high_win_probability_is_not_value(self):
        trades = mod.choose_bets(np.asarray([[.77, .13, .1]]), np.asarray([[1.2, 4., 5.]]), np.asarray([0]), [{}], .03)
        self.assertEqual(trades, [])

    def test_market_baseline_has_no_ev_under_positive_margin(self):
        odds = np.asarray([[2., 3.4, 4.]])
        implied = 1 / odds
        market = implied / implied.sum(axis=1, keepdims=True)
        self.assertEqual(mod.choose_bets(market, odds, np.asarray([0]), [{}], 0.), [])

    def test_underround_quote_group_is_quarantined(self):
        trades = mod.choose_bets(np.asarray([[.6, .3, .1]]), np.asarray([[2.39, 5.72, 10.84]]), np.asarray([0]), [{}], .03)
        self.assertEqual(trades, [])

    def test_one_winner_does_not_create_degenerate_positive_evidence(self):
        summary = mod.trade_summary([{'date': '2023-01-01', 'profit': 1., 'won': 1,
                                     'break_even_probability': .5, 'model_probability': .6,
                                     'odds': 2., 'expected_profit_per_unit': .2,
                                     'profit_after_1pct_odds_haircut': .98}])
        self.assertIsNone(summary['roi_month_cluster_bootstrap95'])
        self.assertFalse(summary['positive_expected_value_supported'])


if __name__ == '__main__':
    unittest.main()
