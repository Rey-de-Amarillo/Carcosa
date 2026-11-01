import math
import unittest
from copy import deepcopy
from datetime import date,timedelta
from itertools import groupby

from engine.stat_markets import (StatCountModel,count_over_probability,observed_counts,
                                 predict_stat_fixture,run_stat_market_evaluation)


def rows_fixture(days=160):
    rows=[];teams=[f"T{i}" for i in range(8)]
    for n in range(days):
        day=(date(2020,1,1)+timedelta(days=n)).isoformat()
        for k in range(4):
            rows.append({"id":f"{n}-{k}","sport":"football","league":"L1","date":day,
                         "home_team":teams[(n+k)%8],"away_team":teams[(n+k+4)%8],
                         "home_score":3,"away_score":2,
                         "home_ht_score":n%2,"away_ht_score":(n+k)%2,
                         "home_corners":1 if n%2 else 12,"away_corners":0 if n%2 else 10,
                         "home_yellow":n%4,"away_yellow":(n+k)%4})
    return rows


class CountDistributionTests(unittest.TestCase):
    def test_negative_binomial_shape_one_matches_geometric_tail(self):
        self.assertAlmostEqual(count_over_probability(3,.5,1),.75)
        self.assertAlmostEqual(count_over_probability(3,3.5,1),.75**4)

    def test_poisson_limit_and_probability_monotonicity(self):
        p=count_over_probability(10,9.5,0)
        expected=1-math.exp(-10)*sum(10**k/math.factorial(k) for k in range(10))
        self.assertAlmostEqual(p,expected)
        self.assertAlmostEqual(p,count_over_probability(10,9.5,1e-8))
        self.assertGreater(count_over_probability(10,8.5,.1),count_over_probability(10,9.5,.1))
        self.assertGreater(count_over_probability(12,9.5,.1),count_over_probability(10,9.5,.1))

    def test_missing_is_not_zero_but_real_zero_is_valid(self):
        self.assertIsNone(observed_counts({"home_corners":"","away_corners":"0"},"corners"))
        self.assertIsNone(observed_counts({"home_corners":None,"away_corners":"2"},"corners"))
        self.assertEqual(observed_counts({"home_corners":"0","away_corners":"0"},"corners"),(0,0))
        with self.assertRaises(ValueError):count_over_probability(float("nan"),8.5)
        with self.assertRaises(ValueError):count_over_probability(10,8.5,-.1)


class StatisticalMarketTests(unittest.TestCase):
    def test_half_time_never_borrows_full_time_goals(self):
        rows=rows_fixture()
        fixture={"sport":"football","league":"L1","date":"2020-06-10","home_team":"T1","away_team":"T5"}
        first=predict_stat_fixture(rows,fixture)["period_half"]
        altered=deepcopy(rows)
        for r in altered:r["home_score"],r["away_score"]=99,99
        second=predict_stat_fixture(altered,fixture)["period_half"]
        self.assertEqual(first,second)
        self.assertAlmostEqual(sum(map(sum,first["grid"])),1)

    def test_same_day_and_future_stat_changes_do_not_leak(self):
        rows=rows_fixture();fixture={"sport":"football","league":"L1","date":"2020-05-15","home_team":"T1","away_team":"T5"}
        first=predict_stat_fixture(rows,fixture)
        changed=deepcopy(rows)
        for r in changed:
            if r["date"]>=fixture["date"]:
                for k in ["home_ht_score","away_ht_score","home_corners","away_corners","home_yellow","away_yellow"]:r[k]=30
        self.assertEqual(first,predict_stat_fixture(changed,fixture))
        for p in first.values():self.assertLess(p["training_max_date"],fixture["date"])

    def test_overdispersion_learned_from_past_and_underdispersion_falls_back(self):
        model=StatCountModel("corners")
        for _,batch in groupby(rows_fixture(),key=lambda r:r["date"]):model.update_batch(list(batch))
        p=model.predict("T1","T5","2020-06-10")
        self.assertGreater(p["alpha"],.1)
        self.assertEqual(p["distribution"],"negative_binomial")
        constant=StatCountModel("corners")
        for n in range(160):
            constant.update_batch([{"date":(date(2020,1,1)+timedelta(days=n)).isoformat(),
                                   "home_team":"A","away_team":"B","home_corners":5,"away_corners":5}])
        self.assertEqual(constant.predict("A","B","2020-06-10")["distribution"],"poisson")

    def test_missing_family_abstains_instead_of_learning_zeroes(self):
        rows=rows_fixture()
        for r in rows:r["home_yellow"]=None;r["away_yellow"]=""
        p=predict_stat_fixture(rows,{"sport":"football","league":"L1","date":"2020-06-10","home_team":"T1","away_team":"T5"})
        self.assertFalse(p["yellow_cards"]["eligible"])
        self.assertEqual(p["yellow_cards"]["league_sample_size"],0)
        self.assertTrue(p["period_half"]["eligible"])
        self.assertTrue(p["corners"]["eligible"])

    def test_metric_families_have_no_fabricated_roi_or_odds(self):
        result=run_stat_market_evaluation(rows_fixture(),audit_start="2020-04-01")
        self.assertEqual(len(result),9)
        for item in result:
            self.assertGreater(item["n"],100)
            self.assertIsNone(item["roi"])
            self.assertEqual(item["odds_events"],0)
            self.assertEqual(item["status"],"research_without_historical_odds")
            self.assertTrue(math.isfinite(item["brier"]))
            self.assertTrue(math.isfinite(item["log_loss"]))

    def test_reordering_or_unrelated_league_cannot_change_report(self):
        rows=rows_fixture(110)
        first=run_stat_market_evaluation(rows,audit_start="2020-03-01")
        self.assertEqual(first,run_stat_market_evaluation(list(reversed(rows)),audit_start="2020-03-01"))
        wrong=deepcopy(rows)
        for r in wrong:r["league"]="OTHER";r["home_corners"]=50
        fixture={"sport":"football","league":"L1","date":"2020-05-01","home_team":"T1","away_team":"T5"}
        self.assertEqual(predict_stat_fixture(rows,fixture),predict_stat_fixture(rows+wrong,fixture))


if __name__=='__main__':unittest.main()
