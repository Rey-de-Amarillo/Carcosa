import copy
import unittest

from scripts.research_robust_reference_ev import candidates,reference_scores


class RobustReferenceTests(unittest.TestCase):
    def books(self):
        return {name:dict(p=p) for name,p in dict(B365=[.5,.3,.2],
                PS=[.6,.25,.15],BW=[.5,.3,.2],WH=[.4,.35,.25]).items()}

    def test_exact_scores_and_lower_score_for_all_reference_models(self):
        books=self.books();result=reference_scores(books,'B365')
        self.assertAlmostEqual(result['mean'][0],.5)
        self.assertAlmostEqual(result['minimum'][0],.4)
        self.assertAlmostEqual(result['sd'][0],(.02/3)**.5)
        self.assertAlmostEqual(result['mean_minus_one_sd'][0],.5-(.02/3)**.5)
        for side in range(3):
            for b in result['books']:
                self.assertLessEqual(result['minimum'][side],books[b]['p'][side])

    def test_target_excluded_and_three_references_required(self):
        books=self.books();before=reference_scores(books,'B365')
        books['B365']['p']=[.1,.8,.1]
        self.assertEqual(before,reference_scores(books,'B365'))
        del books['PS']
        self.assertIsNone(reference_scores(books,'B365'))

    def test_outcome_cannot_change_ev_or_reference_policy(self):
        row=dict(id='a',date='2024-01-01',league_code='E0',home_team='A',away_team='B',
                 h2h=dict(pre={'B365':[2.,3.5,4.],'PS':[2.1,3.4,3.7],
                               'BW':[2.1,3.3,3.8],'WH':[2.15,3.4,3.6]}))
        first=candidates(row,{'a':(1,0)})
        second=candidates(row,{'a':(0,1)})
        for policy in first:
            self.assertTrue(first[policy])
            for a,b in zip(first[policy],second[policy]):
                self.assertEqual({k:v for k,v in a.items() if k!='won'},
                                 {k:v for k,v in b.items() if k!='won'})


if __name__=='__main__':
    unittest.main()
