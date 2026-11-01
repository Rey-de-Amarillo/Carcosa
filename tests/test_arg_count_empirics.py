import unittest
import math
from scripts.arg_count_empirics import evaluate, nb_cdf5, poisson_cdf5


class CountRangeRegressionTests(unittest.TestCase):
    def test_no_range_is_complement_for_actual_corner_count(self):
        quote={'market':'goal_range','statistic':'corners','selection':'No','min_goals':0,'max_goals':5}
        four={'home_corners':2,'away_corners':2}
        seven={'home_corners':3,'away_corners':4}
        self.assertFalse(evaluate(quote,four,'yellow_plus_2red')['success'])
        self.assertTrue(evaluate(quote,seven,'yellow_plus_2red')['success'])

    def test_under_integer_three_way_has_no_push(self):
        q={'market':'count_total_3way','statistic':'corners','selection':'under','line':10}
        self.assertFalse(evaluate(q,{'home_corners':5,'away_corners':5},'yellow_plus_2red')['success'])
        self.assertTrue(evaluate(q,{'home_corners':5,'away_corners':4},'yellow_plus_2red')['success'])

    def test_positive_dispersion_cdf_matches_general_pmf(self):
        mean,alpha=4.019607843137255,.0656310500832863
        shape=1/alpha;prob=shape/(shape+mean)
        independent=sum(math.exp(math.lgamma(k+shape)-math.lgamma(shape)-math.lgamma(k+1)+shape*math.log(prob)+k*math.log1p(-prob)) for k in range(6))
        self.assertAlmostEqual(nb_cdf5(mean,alpha),independent,places=12)

    def test_nb_zero_dispersion_matches_poisson(self):
        self.assertAlmostEqual(nb_cdf5(4.019607843137255,0),poisson_cdf5(4.019607843137255),places=14)
        self.assertEqual(poisson_cdf5(0),1)


if __name__=='__main__':unittest.main()
