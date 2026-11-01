import math
import unittest

from scripts.bet365_numbers import fit_platt, platt_probability


class ProbabilityCalibrationTests(unittest.TestCase):
    def test_constant_event_frequency_removes_spurious_probability_separation(self):
        probabilities = [.1]*10 + [.5]*10 + [.9]*10
        outcomes = ([1]*3 + [0]*7)*3
        fit = fit_platt(probabilities, outcomes)
        self.assertTrue(fit['converged'])
        self.assertAlmostEqual(fit['intercept'], math.log(.3/.7), places=7)
        self.assertAlmostEqual(fit['slope'], 0, places=7)
        for p in (.001, .5, .999):
            self.assertAlmostEqual(platt_probability(p, fit), .3, places=7)

    def test_identity_and_extreme_probabilities_stay_finite(self):
        identity = {'intercept': 0, 'slope': 1}
        for p in (0, .01, .5, .99, 1):
            result = platt_probability(p, identity)
            self.assertTrue(math.isfinite(result))
            self.assertAlmostEqual(p, result, places=10)

    def test_unidentifiable_or_invalid_training_is_rejected(self):
        for probabilities, outcomes in [([.5]*4, [0,1,0,1]),
                                         ([.2,.3,.4], [1,1,1]),
                                         ([.2,float('nan'),.4], [0,1,0])]:
            with self.assertRaises(ValueError):
                fit_platt(probabilities, outcomes)


if __name__ == '__main__':
    unittest.main()
