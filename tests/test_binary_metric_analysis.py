import math
import unittest

from scripts import binary_metric_math as bm
from scripts.analyze_btts_yes import analyze_rows, settle_btts
from scripts.analyze_under25 import settle_under25


class BinaryMetricAnalysisTests(unittest.TestCase):
    def test_variable_odds_payout_and_empty_selection(self):
        rows = [
            {"win": 1, "odds": 4.0, "start_time_source": "2026-01-01"},
            {"win": 0, "odds": 1.1, "start_time_source": "2026-01-01"},
            {"win": 0, "odds": 1.1, "start_time_source": "2026-01-02"},
        ]
        result = bm.summarize(rows, "odds", bootstrap_iterations=100)
        # One win in three still profits: use the winning price, not mean odds.
        self.assertEqual(result["returned_units"], 4)
        self.assertEqual(result["profit_units"], 1)
        self.assertAlmostEqual(result["roi"], 1/3)
        empty = bm.summarize([], "odds", bootstrap_iterations=100)
        self.assertIsNone(empty["roi"])
        self.assertEqual(empty["staked_units"], 0)

    def test_btts_requires_both_teams_to_score(self):
        self.assertEqual([settle_btts(h, a) for h, a in [(0, 0), (3, 0), (0, 2), (1, 1), (4, 2)]], [0, 0, 0, 1, 1])
        with self.assertRaises(ValueError):
            settle_btts(None, 1)

    def test_under25_settlement_boundary(self):
        self.assertEqual([settle_under25(h, a) for h, a in [(0, 0), (2, 0), (1, 1), (2, 1), (0, 3)]], [1, 1, 1, 0, 0])
        with self.assertRaises(ValueError):
            settle_under25(None, 0)

    def test_calibration_uses_the_selected_side_of_asymmetric_prices(self):
        rows = [{"match_row_id": i, "start_time_source": f"2026-01-0{i+1}",
                 "win": y, "under_odds": 1.5, "over_odds": 3.0}
                for i, y in enumerate([1, 1, 1, 0, 1, 0])]
        result = bm.analyze_rows(rows, "under_odds", "over_odds", bootstrap_iterations=100)
        self.assertAlmostEqual(result["calibration"]["alpha"], math.log(1.5))
        self.assertAlmostEqual(result["observations"][-1]["calibrated_p"], .75)
        self.assertEqual(result["calibration"]["later_period_selected"]["bets"], 2)
        self.assertAlmostEqual(result["calibration"]["later_period_selected"]["profit_units"], -.5)

    def test_whole_boundary_date_is_reserved_for_later_period(self):
        dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-03", "2026-01-03", "2026-01-04"]
        rows = [{"match_row_id": i, "start_time_source": d} for i, d in enumerate(dates)]
        cutoff, train, later = bm.split_by_date(rows)
        self.assertEqual(cutoff, "2026-01-03")
        self.assertEqual(len(train), 2)
        self.assertEqual(len(later), 4)
        self.assertFalse({r["start_time_source"] for r in train} & {r["start_time_source"] for r in later})

    def test_later_results_cannot_change_fitted_probabilities(self):
        rows = [{"match_row_id": i, "start_time_source": f"2026-01-0{i+1}",
                 "win": y, "yes_odds": 2.0, "no_odds": 2.0}
                for i, y in enumerate([1, 1, 1, 0, 1, 1])]
        original = analyze_rows(rows, bootstrap_iterations=100)
        changed = [dict(r, win=0 if i >= 4 else r["win"]) for i, r in enumerate(rows)]
        counterfactual = analyze_rows(changed, bootstrap_iterations=100)
        self.assertAlmostEqual(original["calibration"]["alpha"], math.log(3))
        self.assertEqual(original["calibration"]["alpha"], counterfactual["calibration"]["alpha"])
        self.assertEqual(original["calibration"]["later_period_ev_range"], counterfactual["calibration"]["later_period_ev_range"])
        self.assertNotEqual(original["later_period_flat_stakes"]["profit_units"], counterfactual["later_period_flat_stakes"]["profit_units"])


if __name__ == "__main__":
    unittest.main()
