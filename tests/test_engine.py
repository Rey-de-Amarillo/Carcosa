import csv
import json
import math
import tempfile
import unittest
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from engine.core import (EloModel, LeaguePoisson, check_arbitrage, expected_value,
                         kelly_fraction, poisson_markets, predict_fixture,
                         proper_scores, remove_margin)
from engine.report import build_report, read_matches, temporal_splits


class ProbabilityTests(unittest.TestCase):
    def test_fair_margin_and_expected_return(self):
        result = remove_margin([1.9, 1.9])
        self.assertEqual(result["probabilities"], [0.5, 0.5])
        self.assertAlmostEqual(result["overround"], 2/1.9-1)
        self.assertAlmostEqual(expected_value(.55, 1.9), .045)
        self.assertEqual(kelly_fraction(.4, 2), 0)
        self.assertEqual(kelly_fraction(.99, 2), .01)
        self.assertAlmostEqual(kelly_fraction(.55, 2, cap=1), .025)

    def test_invalid_values_are_rejected(self):
        for odds in [0, 1, -1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError): expected_value(.5, odds)
        for p in [-.1, 1.1, float("nan")]:
            with self.assertRaises(ValueError): expected_value(p, 2)

    def test_poisson_markets_cover_all_outcomes(self):
        p = poisson_markets(1.7, .9)
        self.assertAlmostEqual(p["home"]+p["draw"]+p["away"], 1, places=12)
        self.assertAlmostEqual(p["over25"]+p["under25"], 1, places=12)
        self.assertAlmostEqual(p["first_goal_home"]+p["first_goal_away"]+p["first_goal_none"], 1, places=12)
        self.assertAlmostEqual(p["under25"], math.exp(-2.6)*(1+2.6+2.6**2/2), places=10)
        self.assertAlmostEqual(p["btts_yes"], (1-math.exp(-1.7))*(1-math.exp(-.9)), places=10)
        self.assertGreater(p["retained_probability_mass"], .99999999)

    def test_proper_scores_known_cases(self):
        self.assertEqual(proper_scores([1,0,0], 0)["brier"], 0)
        self.assertEqual(proper_scores([0,1,0], 0)["brier"], 2)
        self.assertAlmostEqual(proper_scores([.25,.5,.25], 1)["log_loss"], -math.log(.5))

    def test_elo_conserves_rating_and_batches_updates(self):
        elo = EloModel()
        elo.update_batch([{"home_team":"A","away_team":"B","home_score":100,"away_score":90}])
        self.assertAlmostEqual(sum(elo.ratings.values()), 3000)
        self.assertGreater(elo.ratings["A"], 1500)
        self.assertLess(elo.ratings["B"], 1500)


class ArbitrageTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,30,12,0,tzinfo=timezone.utc)
        base = {"event_id":"event1","market_id":"winner","line":None,"period":"full_match",
                "rules_id":"tennis-retirement-one-set-v1","expected_outcomes":["A","B"],
                "captured_at":self.now.isoformat(),"odds":2.1,"bookmaker":"sample"}
        self.quotes = [{**base,"outcome":"A"},{**base,"outcome":"B","bookmaker":"other"}]

    def test_complete_synchronized_contract_has_theoretical_arbitrage(self):
        result = check_arbitrage(self.quotes, 100, now=self.now)
        self.assertTrue(result["is_arbitrage"])
        self.assertFalse(result["executable"])
        self.assertAlmostEqual(result["theoretical_profit"], 5)
        self.assertAlmostEqual(sum(leg["stake"] for leg in result["legs"]), 100)

    def test_missing_outcome_different_rules_stale_and_unsynchronized_rejected(self):
        self.assertFalse(check_arbitrage(self.quotes[:1],now=self.now)["is_arbitrage"])
        changed = deepcopy(self.quotes);changed[1]["rules_id"]="all-retirements-void"
        self.assertFalse(check_arbitrage(changed,now=self.now)["is_arbitrage"])
        changed = deepcopy(self.quotes);changed[1]["captured_at"]=(self.now-timedelta(seconds=60)).isoformat()
        self.assertFalse(check_arbitrage(changed,now=self.now)["is_arbitrage"])
        changed = deepcopy(self.quotes);changed[1]["captured_at"]=(self.now-timedelta(seconds=10)).isoformat()
        self.assertFalse(check_arbitrage(changed,now=self.now)["is_arbitrage"])


class ChronologyTests(unittest.TestCase):
    @staticmethod
    def sample_rows():
        rows=[]
        start=date(2020,1,1)
        teams=[f"T{i}" for i in range(8)]
        for day_index in range(120):
            day=(start+timedelta(days=day_index)).isoformat()
            for game in range(4):
                h=teams[(day_index+game)%8];a=teams[(day_index+game+4)%8]
                rows.append({"id":f"{day_index}-{game}","sport":"football","league":"test",
                             "season":"2020","date":day,"home_team":h,"away_team":a,
                             "home_score":(day_index+game)%4,"away_score":(day_index+2*game)%3,
                             "home_odds":2.1,"draw_odds":3.2,"away_odds":3.5,"odds_source":"fixture:test"})
        return rows

    def test_fixture_never_trains_on_same_day_or_future(self):
        history=self.sample_rows()
        fixture={"sport":"football","league":"test","date":"2020-03-20","home_team":"T1","away_team":"T5"}
        baseline=predict_fixture(history,fixture)
        altered=deepcopy(history)
        for row in altered:
            if row["date"] >= fixture["date"]:
                row["home_score"]=99;row["away_score"]=0
        actual=predict_fixture(altered,fixture)
        self.assertEqual(baseline, actual)
        self.assertLess(actual["training_max_date"], fixture["date"])

    def test_league_isolation_and_unknown_teams_abstain(self):
        fixture={"sport":"football","league":"different","date":"2020-05-20","home_team":"T1","away_team":"T5"}
        result=predict_fixture(self.sample_rows(),fixture)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["ready_for_live"])
        self.assertIsNone(result["training_max_date"])

    def test_neutral_football_abstains_and_neutral_elo_has_no_home_bonus(self):
        fixture={"sport":"football","league":"test","date":"2020-05-20","home_team":"T1","away_team":"T5","neutral_venue":True}
        result=predict_fixture(self.sample_rows(),fixture)
        self.assertFalse(result["eligible"])
        self.assertTrue(result["neutral_venue_unsupported"])
        self.assertAlmostEqual(EloModel().predict("A","B",neutral=True)["home"],.5)
        self.assertGreater(EloModel().predict("A","B")["home"],.5)

    def test_hockey_and_baseball_are_explicit_binary_research_models(self):
        for sport, league, target in [("hockey","NHL","winner_including_overtime_and_shootout"),
                                      ("baseball","MLB","winner_including_extra_innings")]:
            history=[]
            for day_index in range(30):
                history.append({"sport":sport,"league":league,"date":(date(2025,1,1)+timedelta(days=day_index)).isoformat(),
                                "home_team":"A","away_team":"B","home_score":4,"away_score":2})
            result=predict_fixture(history,{"sport":sport,"league":league,"date":"2025-02-01","home_team":"A","away_team":"B"})
            self.assertAlmostEqual(result["home"]+result["away"],1)
            self.assertEqual(result["model_target"],target)
            self.assertTrue(result["eligible"])
            self.assertFalse(result["ready_for_live"])

    def test_baseball_doubleheader_ids_are_preserved(self):
        rows=[]
        for game in [1,2]:
            rows.append({"id":f"mlb-{game}","sport":"baseball","league":"MLB","date":"2025-04-05",
                         "home_team":"A","away_team":"B","home_score":3,"away_score":1})
        with tempfile.TemporaryDirectory() as tmp:
            with (Path(tmp)/"matches.csv").open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            parsed,quality=read_matches(tmp)
            self.assertEqual(len(parsed),2)
            self.assertEqual(quality["duplicates_removed"],0)

    def test_report_historical_schema_and_atomic_date_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"matches.csv"
            rows=self.sample_rows()
            with path.open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            parsed,quality=read_matches(tmp)
            split=temporal_splits(parsed)["football"]
            self.assertLess(split["validation_start"],split["test_start"])
            self.assertEqual(quality["accepted"],480)
            history_path=Path(tmp)/"decisions.jsonl"
            report=build_report(tmp,history_output=history_path)
            self.assertFalse(report["model"]["ready_for_live"])
            self.assertEqual(report["opportunities"],[])
            self.assertGreater(report["backtest"]["sample_size"],0)
            self.assertTrue(report["backtest"]["is_simulation"])
            exported=[json.loads(line) for line in history_path.read_text().splitlines()]
            self.assertEqual(len(exported),report["decision_history"]["total"])
            for decision in report["decisions"]:
                self.assertFalse(decision["is_live"])
                self.assertTrue(decision["training_as_of"] < decision["date"])

    def test_no_same_day_result_leaks_into_other_predictions(self):
        rows=self.sample_rows()
        extra={**rows[-1],"id":"zz-same-day","home_team":"T0","away_team":"T1"}
        rows.append(extra)
        def result(records):
            with tempfile.TemporaryDirectory() as tmp:
                with (Path(tmp)/"matches.csv").open("w",newline="") as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
                report=build_report(tmp)
                return next(d for d in report["decisions"] if d["id"]=="zz-same-day")
        before=result(rows)
        changed=deepcopy(rows)
        changed[-2]["home_score"]=18;changed[-2]["away_score"]=0
        after=result(changed)
        self.assertEqual(before["model_probability"],after["model_probability"])


if __name__ == "__main__":
    unittest.main()
