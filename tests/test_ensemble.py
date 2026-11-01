import copy
import math
import unittest

from engine.ensemble import blend, consensus, devig, select_candidate


class MarginAndPoolTests(unittest.TestCase):
    def test_proportional_and_power_are_normalized_and_different(self):
        proportional = devig([2., 3., 4.], 'proportional')
        power = devig([2., 3., 4.], 'power')
        self.assertAlmostEqual(proportional['probabilities'][0], 6/13)
        for result in (proportional, power):
            self.assertAlmostEqual(sum(result['probabilities']), 1., places=13)
            self.assertTrue(all(0 < p < 1 for p in result['probabilities']))
        self.assertGreater(power['exponent'], 1.)
        self.assertGreater(power['probabilities'][0], proportional['probabilities'][0])
        self.assertLess(power['probabilities'][2], proportional['probabilities'][2])

    def test_equal_fair_prices_and_underround_remain_coherent(self):
        fair = devig([3., 3., 3.], 'power')
        self.assertAlmostEqual(fair['exponent'], 1., places=12)
        self.assertTrue(all(abs(p-1/3) < 1e-12 for p in fair['probabilities']))
        underround = devig([4., 4., 4.], 'power')
        self.assertLess(underround['exponent'], 1.)
        self.assertAlmostEqual(sum(underround['probabilities']), 1.)

    def test_bad_prices_are_rejected_and_no_bad_book_enters_pool(self):
        for prices in ([2.], [1., 3., 4.], [0., 3., 4.], [math.nan, 3., 4.],
                       [math.inf, 3., 4.], ['garbage', 3., 4.]):
            with self.assertRaises((ValueError, TypeError)):
                devig(prices)
        result = consensus({'A': [2., 3., 4.], 'B': [2.1, 3.2, 3.7],
                            'Avg': [1.4, 4.5, 8.], 'Max': [3., 3., 3.],
                            'BFE': [2., 3., 4.], 'Broken': None,
                            'HugeMargin': [1.01, 1.1, 1.3]})
        self.assertEqual(result['books'], ['A', 'B'])
        self.assertEqual(result['count'], 2)
        self.assertAlmostEqual(sum(result['probabilities']), 1.)

    def test_pool_is_mean_of_book_probabilities_not_mean_of_prices(self):
        books = {'A': [2., 3., 4.], 'B': [2.1, 3.2, 3.7]}
        pool = consensus(books, 'power')
        a, b = (devig(books[name], 'power')['probabilities'] for name in ('A', 'B'))
        for x, y, z in zip(pool['probabilities'], a, b):
            self.assertAlmostEqual(x, (y+z)/2, places=13)
        self.assertEqual(consensus({})['count'], 0)
        self.assertIsNone(consensus({})['probabilities'])

    def test_blend_preserves_simplex_and_does_not_silently_replace_missing_source(self):
        structural, market = [.6, .25, .15], [.45, .30, .25]
        mixed = blend(structural, market, .25)
        self.assertEqual(mixed, [.25*a+.75*b for a, b in zip(structural, market)])
        self.assertAlmostEqual(sum(mixed), 1.)
        self.assertEqual(blend(structural, None, 1.), structural)
        self.assertEqual(blend(None, market, 0.), market)
        self.assertIsNone(blend(structural, None, 0.))
        self.assertIsNone(blend(structural, None, .25))
        self.assertIsNone(blend(None, market, .25))
        self.assertIsNone(blend(None, None, .5))

    def test_blend_checks_required_standalone_vectors(self):
        for vector in ([.5, .5, .5], [-.1, .6, .5], [math.nan, .5, .5]):
            with self.assertRaises(ValueError):
                blend(vector, None, 1.)
            with self.assertRaises(ValueError):
                blend(None, vector, 0.)


class CandidateSelectionTests(unittest.TestCase):
    def test_future_audit_outcomes_and_prices_cannot_change_selection(self):
        rows = [{'date': day, 'structural': [.8, .1, .1],
                 'consensus_power': [.45, .3, .25],
                 'consensus_proportional': [.43, .31, .26], 'outcome': 0}
                for day in ('2022-01-01', '2022-06-01', '2023-01-01')]
        rows += [{'date': '2024-01-01', 'structural': [.9, .05, .05],
                  'consensus_power': [.2, .2, .6],
                  'consensus_proportional': [.2, .2, .6], 'outcome': 2}]
        candidates = [{'id': 'market', 'devig': 'power', 'structural_weight': 0.},
                      {'id': 'structural', 'devig': 'power', 'structural_weight': 1.}]
        original = select_candidate(rows, candidates)
        changed = copy.deepcopy(rows)
        for row in changed:
            if row['date'] >= '2024-01-01':
                row.update({'outcome': 0, 'structural': [.01, .01, .98],
                            'consensus_power': [.99, .005, .005]})
        changed += [{'date': '2026-10-30', 'outcome': 2, 'structural': [.001, .001, .998],
                     'consensus_power': [.999, .0005, .0005], 'consensus_proportional': [.999, .0005, .0005]}
                    for _ in range(100)]
        revised = select_candidate(changed, candidates)
        self.assertEqual(original, revised)
        self.assertEqual(original['selected']['id'], 'structural')
        self.assertEqual(original['selected']['n'], 3)
        self.assertEqual(original['criterion'], 'log_loss')
        self.assertFalse(original['roi_used'])
        self.assertFalse(original['audit_outcomes_used'])


if __name__ == '__main__':
    unittest.main()
