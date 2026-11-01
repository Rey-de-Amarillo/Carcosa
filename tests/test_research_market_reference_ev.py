import copy
import unittest

from scripts.research_market_reference_ev import (
    choose_spec, reference, select_event, settled_return, valid_books,
)


class MarketReferenceValueTests(unittest.TestCase):
    def test_target_quote_cannot_change_its_leave_one_out_reference(self):
        row = dict(date='2024-01-01', h2h=dict(pre={
            'B365':[2.,3.5,4.], 'PS':[2.1,3.4,3.7],
            'BW':[2.1,3.3,3.8], 'WH':[2.15,3.4,3.6]}))
        before=reference(valid_books(row,'h2h'),'B365','h2h')
        row['h2h']['pre']['B365']=[2.5,3.,2.9]
        after=reference(valid_books(row,'h2h'),'B365','h2h')
        self.assertEqual(before,after)
        self.assertNotIn('B365',before['books'])

    def test_aggregates_exchange_stale_pinnacle_and_closing_excluded(self):
        row=dict(date='2025-07-23',h2h=dict(pre={
            'B365':[2.,3.5,4.], 'PS':[2.1,3.4,3.7], 'Max':[2.2,3.8,4.],
            'Avg':[2.2,3.8,4.], 'BFE':[2.2,3.8,4.]},closing={'WH':[2.2,3.8,4.]}))
        self.assertEqual(set(valid_books(row,'h2h')),{'B365'})
        row['date']='2025-07-22'
        self.assertIn('PS',valid_books(row,'h2h'))

    def test_totals_reference_requires_real_other_book(self):
        row=dict(date='2024-01-01',totals25=dict(pre={'B365':[1.9,1.9]}))
        self.assertIsNone(reference(valid_books(row,'totals25'),'B365','totals25'))
        row['totals25']['pre']['PS']=[1.96,1.96]
        self.assertEqual(reference(valid_books(row,'totals25'),'B365','totals25')['books'],['PS'])

    def test_one_event_maximum_and_stress_does_not_reselect(self):
        trades=[dict(id='x',book='B365',market='h2h',side=0,odds=2.,probability=.53,ev=.06,won=True),
                dict(id='x',book='B365',market='totals25',side=0,odds=1.9,probability=.58,ev=.102,won=False)]
        selected=select_event(trades)
        original=copy.deepcopy(selected)
        self.assertEqual(selected['market'],'totals25')
        self.assertEqual(settled_return(selected,.01),-1.)
        self.assertEqual(selected,original)
        self.assertAlmostEqual(settled_return(trades[0],.01),.98)

    def test_final_outcomes_do_not_select_or_refit_calibration(self):
        rows=[]
        for year in range(2017,2023):
            for i in range(120):
                rows.append(dict(date=f'{year}-01-01',p=[.5,.3,.2],target_p=[.48,.3,.22],outcome=i%3))
        before=choose_spec(rows,'h2h')
        for row in rows:
            if row['date']>='2022-01-01':
                row['outcome']=0
        after=choose_spec(rows,'h2h')
        self.assertEqual(before['selected'],after['selected'])
        self.assertEqual(before['candidates'],after['candidates'])
        self.assertNotEqual(before['test'],after['test'])


if __name__=='__main__':
    unittest.main()
