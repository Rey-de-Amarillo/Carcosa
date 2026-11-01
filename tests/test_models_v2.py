import math
import unittest
from copy import deepcopy
from datetime import date, timedelta

from engine.models_v2 import OnlineGoalsV2, replay_predictions, score_grid


def sample_rows(days=170):
    result = []
    teams = [f"T{i}" for i in range(8)]
    for n in range(days):
        day = (date(2020, 1, 1)+timedelta(days=n)).isoformat()
        for match in range(4):
            h, a = teams[(n+match)%8], teams[(n+match+4)%8]
            result.append({"id":f"{n}-{match}","sport":"football","league":"L1","date":day,
                           "home_team":h,"away_team":a,"home_score":(n+match)%4,
                           "away_score":(n+2*match)%3})
    return result


class ScoreGridTests(unittest.TestCase):
    def test_dc_preserves_total_and_goal_marginals(self):
        independent = score_grid(1.7, .9, 0)
        adjusted = score_grid(1.7, .9, -.1)
        self.assertAlmostEqual(sum(map(sum, adjusted["grid"])), 1, places=12)
        self.assertGreater(adjusted["draw"], independent["draw"])
        for index in range(len(adjusted["grid"])):
            self.assertAlmostEqual(sum(adjusted["grid"][index]), sum(independent["grid"][index]), places=12)
        for column in range(len(adjusted["grid"])):
            self.assertAlmostEqual(sum(row[column] for row in adjusted["grid"]),
                                   sum(row[column] for row in independent["grid"]), places=12)

    def test_rho_is_valid_for_extreme_future_fixture(self):
        for lh, la, rho in [(5, .2, -.8), (5, 5, 1), (.2, 5, -1), (.3, .3, .9)]:
            result = score_grid(lh, la, rho)
            self.assertTrue(all(p >= 0 and math.isfinite(p) for row in result["grid"] for p in row))
            self.assertAlmostEqual(result["home"]+result["draw"]+result["away"], 1)
            self.assertGreater(result["retained_probability_mass"], .99999)

    def test_invalid_rates_and_domains_rejected(self):
        for rate in [0, -1, float("nan"), float("inf"), 21]:
            with self.assertRaises(ValueError): score_grid(rate, 1)
        with self.assertRaises(ValueError): score_grid(1, 1, float("nan"))
        with self.assertRaises(ValueError): score_grid(1, 1, max_goals=1)


class JointModelTests(unittest.TestCase):
    def test_scaling_identifiability_preserves_intensities(self):
        attack, defence = {"A":2.,"B":.5}, {"A":3.,"B":2.}
        a, d, bh, ba = OnlineGoalsV2.canonicalize(attack, defence, 1.4, 1.1)
        self.assertAlmostEqual(sum(math.log(v) for v in a.values()), 0)
        self.assertAlmostEqual(sum(math.log(v) for v in d.values()), 0)
        for h, away in [("A","B"),("B","A")]:
            self.assertAlmostEqual(bh*a[h]*d[away], 1.4*attack[h]*defence[away])
            self.assertAlmostEqual(ba*a[away]*d[h], 1.1*attack[away]*defence[h])

    def test_no_same_date_or_future_result_leakage(self):
        rows = sample_rows(170)
        altered = deepcopy(rows)
        cutoff = "2020-05-15"
        for r in altered:
            if r["date"] >= cutoff:
                r["home_score"],r["away_score"] = 15,0
        base = {r["id"]:r for r in replay_predictions(rows) if r["date"] <= cutoff}
        compare = {r["id"]:r for r in replay_predictions(altered) if r["date"] <= cutoff}
        self.assertEqual(base,compare)
        for r in base.values():
            p = r["prediction"]
            if p["training_max_date"]:
                self.assertLess(p["training_max_date"],r["date"])

    def test_batch_order_and_input_order_do_not_change_predictions(self):
        rows = sample_rows(85)
        self.assertEqual(list(replay_predictions(rows)),list(replay_predictions(list(reversed(rows)))))
        m = OnlineGoalsV2(refit_days=1)
        daily = rows[:4]
        m.update_batch(daily)
        with self.assertRaises(ValueError): m.update_batch(daily)
        with self.assertRaises(ValueError): m.predict("T0","T4",daily[0]["date"])

    def test_future_prediction_cannot_be_followed_by_past_update(self):
        model = OnlineGoalsV2()
        model.predict("A","B","2025-02-01")
        with self.assertRaises(ValueError):
            model.update_batch([{"date":"2025-01-31","home_team":"A","away_team":"B","home_score":1,"away_score":0}])

    def test_training_timestamp_tracks_parameters_not_unused_new_results(self):
        model=OnlineGoalsV2(refit_days=14)
        rows=sample_rows(170)
        from itertools import groupby
        for _, batch in groupby(rows,key=lambda r:r["date"]): model.update_batch(list(batch))
        first=model.predict("T1","T5","2020-06-19")
        model.update_batch([{"date":"2020-06-19","home_team":"T1","away_team":"T5","home_score":2,"away_score":1}])
        second=model.predict("T1","T5","2020-06-20")
        self.assertEqual(first["training_max_date"],second["training_max_date"])
        self.assertEqual(second["observed_results_max_date"],"2020-06-19")

    def test_new_season_result_forces_refresh_of_stale_parameters(self):
        model=OnlineGoalsV2(refit_days=14)
        from itertools import groupby
        for _, batch in groupby(sample_rows(170),key=lambda r:r["date"]): model.update_batch(list(batch))
        self.assertFalse(model.predict("T1","T5","2020-09-15")["eligible"])
        model.update_batch([{"date":"2020-09-15","home_team":"T1","away_team":"T5","home_score":2,"away_score":1}])
        fresh=model.predict("T1","T5","2020-09-16")
        self.assertEqual(fresh["training_max_date"],"2020-09-15")
        self.assertTrue(fresh["eligible"])

    def test_neutral_unknown_and_stale_data_abstain(self):
        rows = sample_rows(170)
        model = OnlineGoalsV2(refit_days=1)
        from itertools import groupby
        for _, batch in groupby(rows,key=lambda r:r["date"]): model.update_batch(list(batch))
        prediction = model.predict("T1","T5","2020-06-20")
        self.assertTrue(prediction["eligible"])
        self.assertFalse(model.predict("T1","T5","2020-06-20",neutral=True)["eligible"])
        self.assertFalse(model.predict("unknown","T5","2020-06-20")["eligible"])
        self.assertFalse(model.predict("T1","T5","2021-01-01")["eligible"])

    def test_leagues_are_isolated(self):
        rows = sample_rows(90)
        independent = deepcopy(rows)
        for r in independent:
            r["id"]="other-"+r["id"];r["league"]="OTHER";r["home_score"]=12
        first = {r["id"]:r for r in replay_predictions(rows)}
        mixed = {r["id"]:r for r in replay_predictions(rows+independent) if r["league"]=="L1"}
        self.assertEqual(first,mixed)

    def test_both_venues_contribute_to_strength(self):
        model = OnlineGoalsV2(refit_days=1)
        start = date(2020,1,1)
        # A always plays away; its attack must still be learned for a home game.
        for n in range(150):
            day=(start+timedelta(days=n)).isoformat()
            model.update_batch([{"date":day,"home_team":"B","away_team":"A","home_score":0,"away_score":3}])
        p=model.predict("A","B",(start+timedelta(days=151)).isoformat())
        self.assertGreater(p["home_rate"],p["away_rate"])
        self.assertGreater(p["sample_size"],100)
        self.assertTrue(p["eligible"])


if __name__ == '__main__': unittest.main()
