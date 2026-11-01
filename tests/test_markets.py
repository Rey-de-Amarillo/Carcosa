import math
import unittest

from engine.markets import (evaluate_market, expected_net_return, first_goal_team_probabilities,
                            generalized_kelly, joint_event_probability, market_distribution,
                            net_return, settle_score, split_line)


GRID = [[.2, .1, 0], [.2, .1, 0], [.1, .3, 0]]


class FractionalSettlementTests(unittest.TestCase):
    def test_quarter_line_splits_positive_and_negative(self):
        self.assertEqual(split_line(-1.25), (-1.5, -1.0))
        self.assertEqual(split_line(-.75), (-1.0, -.5))
        self.assertEqual(split_line(.25), (0, .5))
        self.assertEqual(split_line(2.75), (2.5, 3))
        self.assertEqual(split_line(2.5), (2.5,))

    def test_asian_handicap_partial_win_loss_and_refund(self):
        examples = [(2, 1, 'home', -1.25, 'half_loss', -.5),
                    (2, 1, 'home', -.75, 'half_win', .5),
                    (1, 1, 'away', .25, 'half_win', .5),
                    (1, 1, 'away', -.25, 'half_loss', -.5),
                    (2, 1, 'home', -1, 'push', 0)]
        for home, away, selection, line, outcome, value in examples:
            with self.subTest(line=line, selection=selection):
                result = settle_score(home, away, 'asian_handicap', selection, line=line)
                self.assertEqual(result['outcome'], outcome)
                self.assertEqual(sum(result[k] for k in ('win_fraction', 'loss_fraction', 'void_fraction')), 1)
                self.assertEqual(net_return(result, 2), value)

    def test_total_quarter_lines_settle_stake_not_binary_outcome(self):
        for line, score, over_outcome, under_outcome in [(2.25, 2, 'half_loss', 'half_win'),
                                                        (2.75, 3, 'half_win', 'half_loss'),
                                                        (3, 3, 'push', 'push')]:
            self.assertEqual(settle_score(score, 0, 'totals', 'over', line=line)['outcome'], over_outcome)
            self.assertEqual(settle_score(score, 0, 'totals', 'under', line=line)['outcome'], under_outcome)

    def test_opposite_handicap_and_total_cashflows_at_even_odds(self):
        for home in range(5):
            for away in range(5):
                for quarters in range(-11, 12):
                    line = quarters/4
                    a = settle_score(home, away, 'asian_handicap', 'home', line=line)
                    b = settle_score(home, away, 'asian_handicap', 'away', line=-line)
                    self.assertAlmostEqual(net_return(a, 2)+net_return(b, 2), 0)
                for quarters in range(21):
                    a = settle_score(home, away, 'totals', 'over', line=quarters/4)
                    b = settle_score(home, away, 'totals', 'under', line=quarters/4)
                    self.assertAlmostEqual(net_return(a, 2)+net_return(b, 2), 0)

    def test_european_handicap_and_asian_zero_have_different_contracts(self):
        self.assertEqual(settle_score(1, 1, 'european_handicap', 'home', line=0)['outcome'], 'loss')
        self.assertEqual(settle_score(1, 1, 'european_handicap', 'draw', line=0)['outcome'], 'win')
        self.assertEqual(settle_score(1, 1, 'asian_handicap', 'home', line=0)['outcome'], 'push')


class MarketDistributionTests(unittest.TestCase):
    def test_score_derived_market_probabilities(self):
        cases = [('1x2', 'home', .6), ('1x2', 'draw', .3), ('1x2', 'away', .1),
                 ('double_chance', 'home_draw', .9), ('double_chance', 'home_away', .7),
                 ('btts', 'yes', .4), ('btts', 'no', .6), ('odd_even', 'odd', .6)]
        for market, selection, expected in cases:
            with self.subTest(market=market, selection=selection):
                result = market_distribution(GRID, market, selection)
                self.assertAlmostEqual(result['probability_win'], expected)
                self.assertAlmostEqual(sum(result['probabilities'].values()), 1)
        self.assertAlmostEqual(evaluate_market(GRID, 'correct_score', '2-1')['probability_win'], .3)
        self.assertAlmostEqual(evaluate_market(GRID, 'correct_score', 'score', score=[2, 1])['probability_win'], .3)
        self.assertAlmostEqual(evaluate_market(GRID, 'totals', 'over', line=2.5)['probability_win'], .3)
        self.assertAlmostEqual(evaluate_market(GRID, 'team_totals', 'over', team='home', line=1.5)['probability_win'], .4)

    def test_dnb_ev_accounts_for_void_probability(self):
        result = evaluate_market(GRID, 'dnb', 'home', odds=2)
        self.assertAlmostEqual(result['probabilities']['win'], .6)
        self.assertAlmostEqual(result['probabilities']['push'], .3)
        self.assertAlmostEqual(result['ev'], .5)
        self.assertNotAlmostEqual(result['ev'], result['probability_win']*2-1)
        self.assertAlmostEqual(result['fair_odds'], 1+.1/.6)

    def test_ev_and_fair_price_of_half_settlements(self):
        result = evaluate_market(GRID, 'totals', 'over', odds=2.1, line=2.25)
        self.assertAlmostEqual(result['probabilities']['half_loss'], .2)
        self.assertAlmostEqual(result['probabilities']['win'], .3)
        self.assertAlmostEqual(result['ev'], .3*1.1-.2*.5-.5)
        self.assertAlmostEqual(expected_net_return(result, result['fair_odds']), 0)

    def test_generalized_kelly_matches_binary_and_dnb_solution(self):
        binary = {'win': .6, 'half_win': 0, 'push': 0, 'half_loss': 0, 'loss': .4}
        self.assertAlmostEqual(generalized_kelly(binary, 2, scale=1, cap=1)['full_kelly'], .2)
        dnb = evaluate_market(GRID, 'dnb', 'home', odds=2, kelly_scale=1, kelly_cap=1)
        self.assertAlmostEqual(dnb['full_kelly'], (.6-.1)/(.6+.1))
        self.assertEqual(evaluate_market(GRID, '1x2', 'home', odds=1.1)['kelly_fraction'], 0)
        self.assertEqual(evaluate_market(GRID, '1x2', 'home', odds=2)['kelly_fraction'], .01)

    def test_all_void_is_no_exposure_and_no_fair_price(self):
        result = evaluate_market([[1]], 'totals', 'over', odds=2, line=0)
        self.assertEqual(result['ev'], 0)
        self.assertEqual(result['kelly_fraction'], 0)
        self.assertIsNone(result['fair_odds'])

    def test_correlated_same_match_intersection_uses_joint_distribution(self):
        legs = [{'market': '1x2', 'selection': 'home'}, {'market': 'btts', 'selection': 'yes'}]
        p = joint_event_probability(GRID, legs)
        self.assertAlmostEqual(p, .3)
        self.assertNotAlmostEqual(p, .6*.4)
        self.assertAlmostEqual(joint_event_probability(GRID, [legs[0], legs[0]]), .6)
        with self.assertRaises(ValueError):
            joint_event_probability(GRID, [{'market': 'dnb', 'selection': 'home'}])

    def test_no_truncation_or_unsupported_market_is_silently_hidden(self):
        for grid in ([[.8]], [[float('nan')]], [[1, -1, 1]], [[.5], [.2, .3]], []):
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                market_distribution(grid, '1x2', 'home')
        with self.assertRaises(ValueError):
            evaluate_market(GRID, 'player_first_goal_scorer', 'a player')
        for line in (2.1, float('inf'), float('nan'), True, None):
            with self.subTest(line=line), self.assertRaises(ValueError):
                split_line(line)
        with self.assertRaises(ValueError):
            market_distribution(GRID, 'totals', 'over', line=[2.5])
        for bad_score in (-1, .5, True):
            with self.subTest(score=bad_score), self.assertRaises(ValueError):
                settle_score(bad_score, 0, '1x2', 'home')

    def test_first_goal_team_formula_remains_exploratory_not_player_model(self):
        result = first_goal_team_probabilities(1.2, .8)
        self.assertAlmostEqual(result['home']+result['away']+result['no_goal'], 1)
        self.assertAlmostEqual(result['no_goal'], math.exp(-2))
        self.assertFalse(result['actionable'])
        self.assertIsNone(result['player_first_scorer_probability'])


if __name__ == '__main__':
    unittest.main()
