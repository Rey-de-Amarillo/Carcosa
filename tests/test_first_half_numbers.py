import copy
from datetime import date, timedelta
import math
import unittest

from scripts.first_half_numbers import LEAGUE, _fit_half_time_calibration, attach_bet365_snapshot, build_numbers


class FirstHalfNumbersTests(unittest.TestCase):
    def test_future_results_and_fulltime_scores_do_not_change_firsthalf_predictions(self):
        rows = []
        for i in range(140):
            rows.append({"id": str(i), "sport": "football", "league": LEAGUE,
                         "date": (date(2023, 1, 1) + timedelta(days=i)).isoformat(),
                         "home_team": "Home", "away_team": "Away",
                         "home_ht_score": i % 2, "away_ht_score": int(i % 5 == 0),
                         "home_score": 2, "away_score": 1})
        fixtures = [{"id": "fixture", "league": LEAGUE, "date": "2023-06-02",
                     "home_team": "Home", "away_team": "Away"}]
        original = build_numbers(rows, fixtures, as_of_date="2023-06-01", audit_start="2023-05-01")
        changed = copy.deepcopy(rows)
        for row in changed:
            row["home_score"] = 40
            row["away_score"] = 35
        future = copy.deepcopy(changed[-1])
        future.update(id="future", date="2023-06-01", home_ht_score=50, away_ht_score=50)
        changed.append(future)
        result = build_numbers(changed, fixtures, as_of_date="2023-06-01", audit_start="2023-05-01")
        self.assertEqual(original, result)
        self.assertTrue(result["fixtures"][0]["model_eligible"])
        self.assertTrue(all(m["bet365_decimal_odds"] is None for m in result["fixtures"][0]["markets"]))

    def test_missing_half_time_is_not_zero_and_roi_is_absent(self):
        rows = [{"sport": "football", "league": LEAGUE, "date": "2023-01-01",
                 "home_team": "Home", "away_team": "Away", "home_ht_score": "", "away_ht_score": ""}]
        result = build_numbers(rows, [], as_of_date="2023-06-01")
        self.assertEqual(result["history_missing_half_time_counts"], 1)
        self.assertTrue(all(t["n"] == 0 and t["roi"] is None for t in result["test"]))

    def test_ambiguous_bet365_columns_block_ev_and_zero_zero_is_under_half(self):
        report = {"fixtures": [{"home_team": "Chelsea", "away_team": "Man United", "date": "2026-10-31",
                                "expected_first_half_home_goals": .7, "expected_first_half_away_goals": .5,
                                "model_eligible": True, "markets": [{"line": .5}]}], "conditions": []}
        snapshot = {"period": "first_half", "home_team": "Chelsea", "away_team": "Man United",
                    "observed_at": "2026-10-30T13:11:29-03:00", "commence_time": "2026-10-31T09:30:00-03:00",
                    "bookmaker": "bet365_argentina", "source_url": "https://www.bet365.bet.ar/",
                    "capture_method": "direct_browser_observation",
                    "prices": [{"market": "first_half_team_to_score", "team": "home", "selection": "no",
                                "decimal_odds": 2.1, "period_mapping_verified": False},
                               {"market": "first_half_correct_score", "selection": "0-0", "decimal_odds": 3.5}]}
        result = attach_bet365_snapshot(report, snapshot)
        uncertain, score = result["fixtures"][0]["bet365_observed_markets"]
        self.assertIsNone(uncertain["model_expected_net_return_per_unit"])
        self.assertIsNone(uncertain["positive_model_ev"])
        self.assertAlmostEqual(score["model_probability"], math.exp(-1.2))
        self.assertAlmostEqual(score["price_break_even_probability"], 1/3.5)
        self.assertEqual(result["fixtures"][0]["markets"][0]["bet365_under_decimal_odds"], 3.5)

    def test_calibration_fit_is_independent_of_test_outcomes(self):
        training = []
        for probability, successes in ((.2, 2), (.4, 4), (.6, 6), (.8, 8)):
            training += [{"date": "2022-01-01", "p": probability, "y": int(i < successes)} for i in range(10)]
        test = [{"date": "2024-01-01", "p": .7, "baseline_p": .6, "y": i % 2} for i in range(10)]
        first = _fit_half_time_calibration(training, test)
        changed = [{**row, "y": 1 - row["y"]} for row in test]
        second = _fit_half_time_calibration(training, changed)
        self.assertEqual(first["fit"], second["fit"])
        self.assertTrue(first["fit"]["converged"])
        self.assertFalse(first["odds_or_roi_used_for_fit"])


if __name__ == "__main__":
    unittest.main()
