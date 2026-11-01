import unittest
from copy import deepcopy
from datetime import date,timedelta
from unittest.mock import patch

from engine.inference_v2 import (clear_inference_cache,inference_cache_info,
                                 predict_fixture_v2)
from engine.models_v2 import OnlineGoalsV2


def history(days=170):
    rows=[];teams=[f"T{i}" for i in range(8)]
    for n in range(days):
        for k in range(4):
            rows.append({"id":f"{n}-{k}","sport":"football","league":"L1",
                         "date":(date(2020,1,1)+timedelta(days=n)).isoformat(),
                         "home_team":teams[(n+k)%8],"away_team":teams[(n+k+4)%8],
                         "home_score":(n+k)%3,"away_score":(n+2*k)%2})
    return rows


class InferenceTests(unittest.TestCase):
    def setUp(self):
        clear_inference_cache()
        self.fixture={"sport":"football","league":"L1","date":"2020-06-20","home_team":"T1","away_team":"T5"}

    def test_current_inference_fits_once_and_shares_across_same_date_teams(self):
        original=OnlineGoalsV2._fit
        calls=[]
        def tracked(model,day):calls.append(day);return original(model,day)
        with patch.object(OnlineGoalsV2,"_fit",tracked):
            first=predict_fixture_v2(history(),self.fixture)
            other=predict_fixture_v2(history(),{**self.fixture,"home_team":"T2","away_team":"T6"})
        self.assertEqual(len(calls),1)
        self.assertTrue(first["eligible"])
        self.assertTrue(other["eligible"])
        self.assertEqual(inference_cache_info()["hits"],1)
        self.assertEqual(first["model_version"],"0.2.0")

    def test_future_rows_and_same_date_scores_are_excluded_from_hash_and_prediction(self):
        rows=history();rows.append({**rows[-1],"id":"future","date":"2020-06-20","home_score":99})
        first=predict_fixture_v2(rows,self.fixture)
        changed=deepcopy(rows);changed[-1]["home_score"]=0;changed[-1]["away_score"]=99
        self.assertEqual(first,predict_fixture_v2(changed,self.fixture))
        self.assertLess(first["training_max_date"],self.fixture["date"])

    def test_changed_score_identity_or_neutrality_invalidates_cache(self):
        rows=history();first=predict_fixture_v2(rows,self.fixture)
        for field,value in [("home_score",12),("home_team","OtherTeam"),("neutral_venue",True)]:
            changed=deepcopy(rows);changed[-1][field]=value
            result=predict_fixture_v2(changed,self.fixture)
            self.assertNotEqual(first["training_fingerprint"],result["training_fingerprint"])
        self.assertEqual(inference_cache_info()["misses"],4)

    def test_other_league_isolation_and_unknown_or_neutral_abstains(self):
        rows=history();other=deepcopy(rows)
        for r in other:r["league"]="OTHER";r["home_score"]=30
        first=predict_fixture_v2(rows,self.fixture)
        self.assertEqual(first,predict_fixture_v2(rows+other,self.fixture))
        self.assertFalse(predict_fixture_v2(rows,{**self.fixture,"home_team":"unknown"})["eligible"])
        self.assertFalse(predict_fixture_v2(rows,{**self.fixture,"neutral_venue":True})["eligible"])

    def test_invalid_dates_scores_and_stale_history_cannot_enable_a_bet(self):
        for day in [None,"2020-13-01","2020-06-20junk","20200620"]:
            p=predict_fixture_v2(history(),{**self.fixture,"date":day})
            self.assertFalse(p["eligible"]);self.assertIsNone(p["home"])
        self.assertFalse(predict_fixture_v2(history(),{**self.fixture,"date":"2021-01-01"})["eligible"])
        invalid=history()
        for row in invalid:row["date"]="invalid"
        p=predict_fixture_v2(invalid,self.fixture)
        self.assertFalse(p["eligible"]);self.assertGreater(p["history_rejected_rows"],0)

    def test_cache_is_bounded_and_reordering_is_stable(self):
        rows=history(30)
        first=predict_fixture_v2(rows,{**self.fixture,"date":"2020-02-01"})
        self.assertEqual(first,predict_fixture_v2(list(reversed(rows)),{**self.fixture,"date":"2020-02-01"}))
        for n in range(36):
            predict_fixture_v2(rows,{**self.fixture,"date":(date(2020,2,1)+timedelta(days=n)).isoformat()})
        self.assertEqual(inference_cache_info()["size"],32)

    def test_non_football_delegates_to_separate_baseline(self):
        rows=[]
        for n in range(30):
            rows.append({"date":(date(2020,1,1)+timedelta(days=n)).isoformat(),"sport":"basketball", "league":"NBA",
                         "home_team":"A","away_team":"B","home_score":100,"away_score":90})
        p=predict_fixture_v2(rows,{"sport":"basketball","league":"NBA","date":"2020-02-02","home_team":"A","away_team":"B"})
        self.assertTrue(p["eligible"])
        self.assertAlmostEqual(p["home"]+p["away"],1)
        self.assertIn("elo",p["model"])
        self.assertFalse(p["ready_for_live"])
        self.assertFalse(p["execution_enabled"])


if __name__=='__main__':unittest.main()
