"""Causality and accounting checks for the predeclared goals EV research."""
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/'scripts/research_goal_ev.py'
spec=importlib.util.spec_from_file_location('research_goal_ev',P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

def row(i,day,home,away,hg,ag):
    return {'row_id':i,'date':day,'ordinal':m.date.fromisoformat(day).toordinal(),
      'division':'TEST','home':home,'away':away,'hg':hg,'ag':ag,'y':int(hg+ag>2),
      'over_odds':2.,'under_odds':2.,'market_p':.5}

class GoalEVTests(unittest.TestCase):
    def test_current_and_future_results_do_not_change_current_features(self):
        rows=[row(1,'2020-01-01','A','B',1,0),row(2,'2020-01-02','A','C',2,2),row(3,'2020-01-03','A','B',3,1)]
        original=m.build_features(rows)[1]
        changed=[dict(r) for r in rows];changed[1].update(hg=9,ag=8,y=1);changed[2].update(hg=9,ag=9,y=1)
        modified=m.build_features(changed)[1]
        m.np.testing.assert_equal(original[:2],modified[:2])
        self.assertFalse(m.np.array_equal(original[2],modified[2]))
    def test_same_day_all_predictions_precede_all_updates(self):
        rows=[row(1,'2020-01-01','A','B',9,9),row(2,'2020-01-01','A','C',0,0),row(3,'2020-01-02','A','B',1,0)]
        records,features=m.build_features(rows)
        self.assertEqual(records[0]['prior_team_min'],0)
        self.assertEqual(records[1]['prior_team_min'],0)
        self.assertIsNone(records[0]['training_max_date'])
        self.assertIsNone(records[1]['training_max_date'])
        self.assertEqual(records[2]['training_max_date'],'2020-01-01')
    def test_novig_probability_orientation(self):
        over_odds,under_odds=1.5,3.
        p=under_odds/(over_odds+under_odds)
        self.assertAlmostEqual(p,(1/over_odds)/(1/over_odds+1/under_odds))
    def test_one_bet_and_expected_value_formula(self):
        r=row(1,'2023-01-01','A','B',3,1);r['prior_team_min']=10
        r.update(over_odds=2.5,under_odds=2.5)
        bets=m.select_bets([r],[.6],.03)
        self.assertEqual(len(bets),1);self.assertEqual(bets[0]['side'],'over')
        self.assertAlmostEqual(bets[0]['estimated_ev'],.6*2.5-1)
        self.assertAlmostEqual(bets[0]['break_even_p'],.4)
    def test_haircut_keeps_selections_and_exact_return(self):
        bets=[{'row_id':1,'date':'2023-01-01','division':'X','home':'A','away':'B','side':'over','p':.6,'odds':2.,'break_even_p':.5,'estimated_ev':.2,'win':True},
              {'row_id':2,'date':'2023-02-01','division':'X','home':'C','away':'D','side':'under','p':.6,'odds':2.,'break_even_p':.5,'estimated_ev':.2,'win':False}]
        s=m.summarize(bets,bootstrap=20)
        self.assertEqual(s['bets'],2);self.assertEqual(s['roi'],0)
        self.assertAlmostEqual(s['roi_price_haircut_1pct_fixed_selections'],-.01)
    def test_protocol_threshold_is_not_tuned_on_final(self):
        self.assertEqual(m.PROTOCOL['primary_ev_threshold'],.03)
        self.assertEqual(m.PROTOCOL['choice'],'minimum validation log loss; no ROI tuning')
        self.assertEqual(m.PROTOCOL['minimum_prior_team_matches'],10)
    def test_paired_log_loss_identical_predictions(self):
        rows=[{'date':'2022-01-01'},{'date':'2022-02-01'}]
        out=m.paired_loss_comparison(rows,m.np.array([1.,0.]),m.np.array([.6,.4]),m.np.array([.6,.4]))
        self.assertEqual(out['market_loss_minus_model_loss'],0.)
        self.assertEqual(out['month_cluster_95'],[0.,0.])

if __name__=='__main__': unittest.main()
