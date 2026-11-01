import unittest
from scripts.sgodds_portfolio_search import Contract
from scripts.football_score_combinations import evaluate_template, templates


class ScoreCombinationsTests(unittest.TestCase):
    def test_complementary_over_and_zero_synthetic_profit(self):
        fields = {'Ou_01':Contract('Ou_01','ft_goal_total','FT','over',.5,2.2),
                  'Pts_00':Contract('Pts_00','ft_correct_score','FT','0-0',None,2.2)}
        result=evaluate_template({'name':'synthetic','fields':list(fields),'period':'FT','coverage_proof':'at least one or zero'},fields)
        self.assertAlmostEqual(result['minimum_net'],.1)
        self.assertAlmostEqual(sum(x['stake_per_100'] for x in result['legs']),100)

    def test_covering_only_zero_zero_and_one_one_is_incomplete(self):
        fields={'Pts_00':Contract('Pts_00','ft_correct_score','FT','0-0',None,20),
                'Pts_11':Contract('Pts_11','ft_correct_score','FT','1-1',None,20)}
        with self.assertRaises(ValueError):
            evaluate_template({'name':'gap','fields':list(fields),'period':'FT','coverage_proof':'incorrect'},fields)

    def test_draw_decomposition_must_include_unlisted_draws(self):
        contracts=[Contract('Ft1X2_01','ft_1x2','FT','home',None,4),Contract('Ft1X2_03','ft_1x2','FT','away',None,4)]
        contracts += [Contract(f'Pts_{i}{i}','ft_correct_score','FT',f'{i}-{i}',None,20) for i in range(5)]
        contracts += [Contract('Pts_99','ft_correct_score','FT','other',None,20)]
        fields,choices=templates(contracts)
        template=next(t for t in choices if 'H/A + draws' in t['name'])
        self.assertAlmostEqual(evaluate_template(template,fields)['minimum_net'],.25)
        incomplete={**template,'fields':[f for f in template['fields'] if f!='Pts_99']}
        with self.assertRaises(ValueError):
            evaluate_template(incomplete,fields)


if __name__=='__main__':
    unittest.main()
