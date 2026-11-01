import csv
import json
import math
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path

from backend.prospective import capture_scan,settle_from_history,summary


class ProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'data/runtime').mkdir(parents=True)
        self.db=self.root/'test.sqlite3'
        self.clock=datetime(2026,10,30,12,tzinfo=timezone.utc)
        self.registration={"start":"2026-10-31","registered_at":"2026-10-30T11:00:00Z","model_hash":"model-fixed","events":0}
        self.registry=self.root/'data/runtime/prospective_v2.json';self.registry.write_text(json.dumps(self.registration))
        self.quote={"event_id":"match-1","sport":"football","league":"England Premier League",
                    "home_team":"Chelsea","away_team":"Manchester United","date":"2026-10-31T18:00:00Z",
                    "market":"1X2","source":"The Odds API","mode":"observation",
                    "forecast_probabilities":[.55,.25,.20],"forecast_market_probabilities":[.5,.3,.2],
                    "selection_code":"home","model_probability":.55,"odds":2.,"reference_count":4,
                    "quote_timestamp":"2026-10-30T11:59:00Z","snapshot_at":"2026-10-30T11:59:30Z",
                    "bookmaker":"B1"}
        self.scan={"generated_at":"2026-10-30T12:00:00Z","opportunities":[self.quote]}

    def capture(self,scan=None,now=None):
        return capture_scan(scan or self.scan,root=self.root,db_path=self.db,now=now or self.clock)

    def write_history(self,rows):
        path=self.root/'matches.csv'
        fields=sorted({k for r in rows for k in r})
        with path.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        return path

    def result_row(self,**changes):
        return {"sport":"football","league":"England Premier League","date":"2026-10-31",
                "home_team":"Chelsea","away_team":"Man United","home_score":2,"away_score":1,**changes}

    def settle(self,path,now):
        return settle_from_history(path,root=self.root,db_path=self.db,now=now)

    def test_future_forecast_is_captured_once_before_start(self):
        first=self.capture();second=self.capture()
        self.assertEqual(first['added_events'],1);self.assertEqual(second['added_events'],0)
        self.assertEqual(second['captured_events'],1);self.assertEqual(second['events'],0)
        self.assertEqual(second['pending_events'],1)
        self.assertFalse(second['live_enabled'])

    def test_stale_future_quotes_insufficient_refs_and_old_start_rejected(self):
        cases=[{"quote_timestamp":"2026-10-30T11:44:00Z"},
               {"quote_timestamp":"2026-10-30T12:00:01Z"},
               {"reference_count":2},{"reference_count":3.5},
               {"date":"2026-10-30T18:00:00Z"},
               {"forecast_probabilities":[.7,.3,.2]},
               {"model_probability":.7}]
        for changes in cases:
            scan=deepcopy(self.scan);scan['opportunities'][0].update(changes)
            self.assertEqual(self.capture(scan)['captured_events'],0)

    def test_post_start_and_backdated_registration_are_rejected(self):
        after=datetime(2026,10,31,20,tzinfo=timezone.utc)
        scan=deepcopy(self.scan);scan['generated_at']=after.isoformat()
        scan['opportunities'][0].update(quote_timestamp=after.isoformat(),snapshot_at=after.isoformat())
        self.assertEqual(self.capture(scan,after)['captured_events'],0)
        # Replaying a plausible pre-match JSON after observing the result is
        # still a late registration, even if its declared capture time is old.
        self.assertEqual(self.capture(self.scan,after)['captured_events'],0)
        before=deepcopy(self.scan);before['generated_at']='2026-10-30T10:00:00Z'
        self.assertEqual(self.capture(before,datetime(2026,10,30,10,tzinfo=timezone.utc))['captured_events'],0)

    def test_first_vector_and_price_cannot_be_rewritten(self):
        self.capture()
        changed=deepcopy(self.scan);changed['opportunities'][0].update(forecast_probabilities=[.9,.05,.05],model_probability=.9,odds=4.)
        self.capture(changed)
        path=self.write_history([self.result_row()]);result=self.settle(path,datetime(2026,11,1,12,tzinfo=timezone.utc))
        self.assertAlmostEqual(result['log_loss'],-math.log(.55))
        self.assertAlmostEqual(result['brier'],.45**2+.25**2+.2**2)
        self.assertEqual(result['paper_bets'],1);self.assertAlmostEqual(result['paper_roi'],1.)

    def test_no_same_day_or_before_kickoff_settlement_without_final_time(self):
        self.capture();path=self.write_history([self.result_row()])
        for clock in [self.clock,datetime(2026,10,31,17,tzinfo=timezone.utc),datetime(2026,10,31,22,tzinfo=timezone.utc)]:
            result=self.settle(path,clock)
            self.assertEqual(result['events'],0);self.assertEqual(result['pending_events'],1)
        self.assertEqual(self.settle(path,datetime(2026,11,1,tzinfo=timezone.utc))['events'],1)

    def test_explicit_final_time_is_verifiable_and_future_final_is_rejected(self):
        self.capture();clock=datetime(2026,10,31,21,tzinfo=timezone.utc)
        path=self.write_history([self.result_row(completed_at='2026-10-31T22:00:00Z',status='final')])
        self.assertEqual(self.settle(path,clock)['events'],0)
        path=self.write_history([self.result_row(completed_at='2026-10-31T20:00:00Z',status='final')])
        self.assertEqual(self.settle(path,clock)['events'],1)

    def test_settlement_is_immutable_and_market_comparison_is_paired(self):
        self.capture();path=self.write_history([self.result_row()]);clock=datetime(2026,11,1,tzinfo=timezone.utc)
        first=self.settle(path,clock)
        self.assertAlmostEqual(first['market_log_loss'],-math.log(.5))
        self.assertEqual(first['market_events'],1)
        self.assertEqual(first['model_log_loss_on_market_events'],first['log_loss'])
        path=self.write_history([self.result_row(home_score=0,away_score=3)])
        second=self.settle(path,clock)
        self.assertEqual(second['settled_now'],0)
        for key in ['log_loss','brier','paper_roi','paper_profit']:self.assertEqual(first[key],second[key])

    def test_paper_candidate_is_one_max_ev_selection_with_its_own_vector(self):
        scan=deepcopy(self.scan)
        draw=deepcopy(self.quote);draw.update(selection_code='draw',model_probability=.3,
                                            forecast_probabilities=[.5,.3,.2],odds=4.5,bookmaker='B2')
        scan['opportunities'].append(draw);self.capture(scan)
        path=self.write_history([self.result_row(home_score=1,away_score=1)])
        result=self.settle(path,datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertAlmostEqual(result['log_loss'],-math.log(.25))
        self.assertEqual(result['paper_bets'],1);self.assertAlmostEqual(result['paper_profit'],3.5)

    def test_global_forecast_is_scored_while_loo_vector_prices_candidate(self):
        scan=deepcopy(self.scan);quote=scan['opportunities'][0]
        quote.update(forecast_probabilities=[.4,.3,.3],priced_probabilities=[.45,.3,.25],
                     model_probability=.45,odds=2.5)
        captured=self.capture(scan)
        self.assertEqual(captured['captured_events'],1)
        path=self.write_history([self.result_row()])
        result=self.settle(path,datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertAlmostEqual(result['log_loss'],-math.log(.4))
        self.assertAlmostEqual(result['paper_profit'],1.5)
        with sqlite3.connect(self.db) as connection:
            paper=json.loads(connection.execute('SELECT paper_candidate FROM prospective_events').fetchone()[0])
        self.assertEqual(paper['priced_probabilities'],[.45,.3,.25])
        self.assertAlmostEqual(paper['selection_probability'],.45)

    def test_outside_paper_price_range_is_scored_without_fabricating_bet(self):
        scan=deepcopy(self.scan);scan['opportunities'][0]['odds']=10.
        self.capture(scan);path=self.write_history([self.result_row()])
        result=self.settle(path,datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertEqual(result['events'],1);self.assertEqual(result['paper_bets'],0);self.assertIsNone(result['paper_roi'])

    def test_wrong_or_ambiguous_identity_remains_pending(self):
        self.capture();clock=datetime(2026,11,1,tzinfo=timezone.utc)
        for rows in [[self.result_row(league='OTHER')],[self.result_row(away_team='Manchester Utd')],
                     [self.result_row(),self.result_row(home_score=0,away_score=2)],
                     [self.result_row(status='inprogress')],[self.result_row(status='aet')]]:
            path=self.write_history(rows);self.assertEqual(self.settle(path,clock)['events'],0)
        path=self.write_history([self.result_row()])
        self.assertEqual(self.settle(path,clock)['events'],1)

    def test_registry_start_is_frozen_even_when_a_file_is_edited(self):
        self.capture();changed=dict(self.registration,start='2026-10-30')
        self.registry.write_text(json.dumps(changed))
        result=self.capture()
        self.assertEqual(result['added_events'],0);self.assertEqual(result['captured_events'],1)
        self.assertEqual(result['start'],'2026-10-31')

    def test_binary_sport_uses_two_probabilities_and_winner(self):
        scan=deepcopy(self.scan);quote=scan['opportunities'][0]
        quote.update(sport='basketball',league='NBA',home_team='A',away_team='B',market='Ganador',
                     forecast_probabilities=[.6,.4],forecast_market_probabilities=[.55,.45],model_probability=.6)
        self.capture(scan)
        path=self.write_history([{'sport':'basketball','league':'NBA','date':'2026-10-31',
                                  'home_team':'A','away_team':'B','home_score':100,'away_score':95}])
        result=self.settle(path,datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertAlmostEqual(result['log_loss'],-math.log(.6));self.assertAlmostEqual(result['brier'],.32)


if __name__=='__main__':unittest.main()
