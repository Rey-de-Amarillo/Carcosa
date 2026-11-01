import importlib.util
from pathlib import Path
import sys
import unittest
P=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(P))
import research_first_half_ev as m

def row(day,home,away,hg,ag):
    return {'date':day,'ordinal':m.date.fromisoformat(day).toordinal(),'division':'E0','home':home,'away':away,
'hg':hg,'ag':ag,'ft_hg':hg+1,'ft_ag':ag+1,'y':int(hg+ag>0),'market_p':.5,'ft_home_p':.4,'ft_draw_p':.3}

class FirstHalfEVTests(unittest.TestCase):
    def test_same_day_and_future_labels_cannot_enter_features(self):
        rows=[row('2025-01-01','A','B',1,0),row('2025-01-01','A','C',0,0),row('2025-01-02','A','B',2,0)]
        records,x,_=m.build(rows)
        changed=[dict(r) for r in rows];changed[0].update(hg=9,ag=9,y=1);changed[2].update(hg=8,ag=8,y=1)
        _,xx,_=m.build(changed)
        m.np.testing.assert_equal(x[:2],xx[:2])
        self.assertIsNone(records[1]['training_max_date'])
        self.assertEqual(records[2]['training_max_date'],'2025-01-01')
    def test_synthetic_is_disjoint_equal_payout_and_zero_goal_loss(self):
        c=m.contracts({'Htt1g_01':'3','Htt1g_02':'2','Htt1g_03':'4'})
        anygoal=next(x for x in c if x['side']=='any')
        self.assertAlmostEqual(anygoal['odds'],1.2)
        self.assertAlmostEqual(sum(p['stake'] for p in anygoal['positions']),1.)
        for position in anygoal['positions']:
            self.assertAlmostEqual(position['stake']*position['odds'],anygoal['odds'])
        self.assertEqual(sum(0*p['stake'] for p in anygoal['positions'])-1,-1)
    def test_equivalent_zero_quotes_choose_highest_actual_price(self):
        c=m.contracts({'Htpts_00':'3','Httg_00':'3.5','Htt1g_03':'3.2','Htou_Hcap':'.5','Htou_02':'3.4','Htou_01':'1.3'})
        zero=next(x for x in c if x['side']=='zero')
        self.assertEqual(zero['name'],'Httg_00');self.assertEqual(zero['odds'],3.5)
    def test_non_half_line_is_not_relabelled_half(self):
        c=m.contracts({'Htou_Hcap':'1.5','Htou_01':'1.8','Htou_02':'2.'})
        self.assertEqual(c,[])
    def test_one_contract_per_match_and_ev(self):
        r={'date':'2026-01-01','match_row_id':1,'home':'A','away':'B','prior_team_min':10,'p_any':.6,'p_zero':.4,'y':1,
'contracts':m.contracts({'Htt1g_01':'4','Htt1g_02':'3','Htt1g_03':'3'})}
        s=m.select([r],.03)
        self.assertEqual(len(s),1)
        self.assertEqual(s[0]['side'],'zero')
        self.assertAlmostEqual(s[0]['estimated_ev'],.2)
        self.assertAlmostEqual(s[0]['break_even_p'],1/3)
    def test_stress_uses_original_fixed_positions(self):
        b={'date':'2026-01-01','win':True,'odds':2.,'estimated_ev':.2,'side':'zero'}
        result=m.summarize([b])
        self.assertEqual(result['roi'],1.)
        self.assertAlmostEqual(result['roi_price_haircut_1pct_fixed_positions'],.98)
    def test_calibration_excludes_first_sg_match(self):
        self.assertEqual(m.PROTOCOL['calibration'],'2022-01-01 through 2025-12-29')
        self.assertEqual(m.PROTOCOL['primary_ev_threshold'],.03)
if __name__=='__main__':unittest.main()
