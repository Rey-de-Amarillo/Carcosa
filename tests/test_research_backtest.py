import copy
import math
import unittest

from engine.research_backtest import simulate_h2h, simulate_score_market, _loo_references
from engine.ensemble import consensus


def fixture(rid='one', day='2024-01-01', h=1, a=0):
    return {'id': rid, 'date': day, 'home_team': 'Home', 'away_team': 'Away',
            'home_score': h, 'away_score': a, 'structural': [.6, .2, .2],
            'prediction': {'eligible': True, 'training_max_date': '2023-12-31'},
            'quote': {'h2h': {'pre': {'A': [2.5, 3.5, 3.],
                                      'B': [2., 3.5, 4.],
                                      'C': [2., 3.5, 4.],
                                      'D': [2., 3.5, 4.]},
                               'closing': {'A': [1.1, 6., 8.]}}}}


SPEC = {'devig': 'power', 'structural_weight': 0.}


class ResearchPortfolioTests(unittest.TestCase):
    def test_cached_leave_one_out_is_identical_to_direct_consensus(self):
        books = fixture()['quote']['h2h']['pre']
        for method in ('power', 'proportional'):
            cached = _loo_references(books, method)
            for name in books:
                direct = consensus({book: values for book, values in books.items() if book != name}, method)
                self.assertEqual(cached[name]['books'], direct['books'])
                for x, y in zip(cached[name]['probabilities'], direct['probabilities']):
                    self.assertAlmostEqual(x, y, places=13)

    def test_complete_leave_one_book_out_reference_and_single_position(self):
        r = simulate_h2h([fixture()], SPEC, {})
        self.assertEqual(r['bets'], 1)
        t = r['trades'][0]
        self.assertEqual(t['book'], 'A')
        self.assertEqual(t['selection_index'], 0)
        self.assertEqual(set(t['reference_books']), {'B', 'C', 'D'})
        self.assertTrue(t['reference_excludes_target'])
        self.assertNotEqual(t['market_probability'], .6)

    def test_missing_references_abstains_with_undefined_roi(self):
        row = fixture()
        del row['quote']['h2h']['pre']['D']
        r = simulate_h2h([row], SPEC, {})
        self.assertEqual(r['bets'], 0)
        self.assertIsNone(r['roi'])
        self.assertEqual(r['final_bankroll'], 1000)

    def test_aggregates_exchange_and_lay_never_become_price_or_reference(self):
        row = fixture()
        row['quote']['h2h']['pre'].update({'Max': [2.8, 3.4, 3.5],
                                          'Avg': [2.8, 3.4, 3.5],
                                          'BFE': [2.8, 3.4, 3.5],
                                          'a_lay': [2.8, 3.4, 3.5]})
        r = simulate_h2h([row], SPEC, {})
        t = r['trades'][0]
        self.assertEqual(t['book'], 'A')
        self.assertEqual(set(t['reference_books']), {'B', 'C', 'D'})

    def test_same_day_uses_frozen_equity_and_cap(self):
        rows = [fixture('win'), fixture('loss', h=0, a=1), fixture('next', '2024-01-02')]
        r = simulate_h2h(rows, SPEC, {'max_day_fraction': .003})
        first_day = [t for t in r['trades'] if t['date'] == '2024-01-01']
        self.assertEqual(len(first_day), 2)
        self.assertAlmostEqual(first_day[0]['stake'], 1.5)
        self.assertAlmostEqual(first_day[1]['stake'], 1.5)
        self.assertEqual({t['capital_reference_for_stake'] for t in first_day}, {1000})
        self.assertAlmostEqual(r['trades'][2]['capital_reference_for_stake'], 1000.75)
        self.assertAlmostEqual(sum(t['pnl'] for t in r['trades']), r['profit'])

    def test_haircut_preserves_all_selections_and_all_base_amounts(self):
        rows = [fixture('win'), fixture('next', '2024-01-02'), fixture('loss', '2024-01-03', h=0, a=1)]
        base = simulate_h2h(rows, SPEC, {})
        stress = simulate_h2h(rows, SPEC, {}, price_haircut=.01)
        keys = lambda result: [(t['id'], t['selection_index'], t['book'], t['stake']) for t in result['trades']]
        self.assertEqual(keys(base), keys(stress))
        self.assertLess(stress['profit'], base['profit'])
        self.assertAlmostEqual(stress['base_final_bankroll'], base['final_bankroll'])

    def test_bootstrap_is_reproducible_and_dates_are_clusters(self):
        rows = [fixture(str(i), f'2024-01-{i+1:02d}', h=i % 2, a=1-i % 2) for i in range(5)]
        first = simulate_h2h(rows, SPEC, {})
        second = simulate_h2h(rows, SPEC, {})
        self.assertEqual(first['ci'], second['ci'])
        self.assertEqual(first['ci']['replicates'], 400)
        self.assertEqual(first['date_clusters'], 5)

    def test_target_book_missing_does_not_substitute_another(self):
        self.assertEqual(simulate_h2h([fixture()], SPEC, {}, target_book='not_here')['bets'], 0)

    def test_duplicate_event_and_future_training_are_rejected(self):
        with self.assertRaises(ValueError):
            simulate_h2h([fixture(), fixture()], SPEC, {})
        row = fixture(); row['prediction']['training_max_date'] = row['date']
        with self.assertRaises(ValueError):
            simulate_h2h([row], SPEC, {})

    def test_explicit_ineligible_structural_model_cannot_bet(self):
        row = fixture(); row['prediction']['eligible'] = False
        r = simulate_h2h([row], {'devig': 'power', 'structural_weight': .25}, {})
        self.assertEqual(r['bets'], 0)

    def test_pinnacle_after_cutoff_cannot_complete_a_reference(self):
        row = fixture(day='2026-01-01')
        row['quote']['h2h']['pre']['PS'] = row['quote']['h2h']['pre'].pop('D')
        self.assertEqual(simulate_h2h([row], SPEC, {})['bets'], 0)


class ScorePortfolioTests(unittest.TestCase):
    def test_asian_quarter_line_uses_half_loss_distribution_and_actual_settlement(self):
        row = fixture(h=0, a=0)
        row['prediction']['grid'] = [[.4, 0.], [.6, 0.]]
        row['quote']['asian_handicap'] = {'pre': {book: {'line': -.25, 'home_odds': 2., 'away_odds': 2.}
                                                        for book in ('A', 'B', 'C', 'D')}}
        result = simulate_score_market([row], 'asian_handicap', {})
        self.assertEqual(result['bets'], 1)
        t = result['trades'][0]
        self.assertEqual(t['selection'], 'home')
        self.assertAlmostEqual(t['ev'], .4)
        self.assertEqual(t['settlement']['outcome'], 'half_loss')
        self.assertAlmostEqual(t['pnl'], -.5*t['stake'])

    def test_goal_totals_has_separate_prices_and_missing_refs_do_not_disappear(self):
        row = fixture(h=3, a=0)
        row['prediction']['grid'] = [[0., 0., 0.], [0., 0., 0.], [.6, .4, 0.]]
        row['quote']['totals25'] = {'pre': {book: [2., 2.] for book in ('A', 'B', 'C', 'D')}}
        result = simulate_score_market([row], 'totals25', {})
        self.assertEqual(result['bets'], 1)
        self.assertEqual(result['trades'][0]['selection'], 'under')
        self.assertAlmostEqual(result['trades'][0]['ev'], .2)
        self.assertLess(result['profit'], 0)
        row['quote']['totals25']['pre'].pop('D')
        self.assertEqual(simulate_score_market([row], 'totals25', {})['bets'], 0)


if __name__ == '__main__':
    unittest.main()
