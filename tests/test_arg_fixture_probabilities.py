import unittest

from scripts.arg_fixture_probabilities import AS_OF, AWAY, HOME, ht_ft_joint, market_probabilities, timing_fractions, train_forecast


class ArgentinaFixtureProbabilityTests(unittest.TestCase):
    def test_dependent_events_are_summed_from_joint_not_multiplied(self):
        p = market_probabilities([[.4, .1], [.2, .3]])
        self.assertAlmostEqual(p["btts_yes"], .3)
        self.assertAlmostEqual(p["btts_no_and_under_2_5"], .7)
        self.assertAlmostEqual(p["draw_and_btts_no"], .4)
        self.assertNotAlmostEqual(p["draw_and_btts_no"], p["draw"] * p["btts_no"])
        self.assertAlmostEqual(sum(p[k] for k in ("goals_0_to_1", "goals_2_to_3", "goals_4_to_6", "goals_7_plus")), 1.)

    def test_ht_joint_respects_score_order_and_preserves_ft_marginal(self):
        ft = [[.1, .2], [.3, .4]]
        result = ht_ft_joint(ft, .3, .6)
        self.assertAlmostEqual(sum(map(sum, result["ht_grid"])), 1.)
        marginal = [[0., 0.], [0., 0.]]
        for hh, ha, fh, fa, p in result["states"]:
            self.assertLessEqual(hh, fh)
            self.assertLessEqual(ha, fa)
            marginal[fh][fa] += p
        for expected, actual in zip(ft, marginal):
            for a, b in zip(expected, actual):
                self.assertAlmostEqual(a, b)
        self.assertAlmostEqual(result["ht_grid"][0][0], .1 + .2 * .4 + .3 * .7 + .4 * .7 * .4)

    def test_timing_fraction_uses_observed_half_scores(self):
        games = [{"event_id": "past", "home_team": HOME, "away_team": AWAY,
                  "home_score": 4, "away_score": 1, "home_ht_score": 1, "away_ht_score": 0}]
        fractions = timing_fractions(games, HOME, AWAY)
        self.assertEqual(fractions["pooled_ht_goals"], 1)
        self.assertEqual(fractions["pooled_ft_goals"], 5)
        self.assertLess(fractions["q_home"], .5)
        self.assertLess(fractions["q_away"], .5)

    def test_current_or_future_result_never_enters_forecast(self):
        past = [{"date": "2026-10-20", "home_team": HOME, "away_team": AWAY,
                 "home_score": 1, "away_score": 0}]
        future = {"date": AS_OF, "home_team": HOME, "away_team": AWAY, "home_score": 20, "away_score": 20}
        a = train_forecast(past, AS_OF, 730)
        b = train_forecast(past + [future], AS_OF, 730)
        self.assertEqual(a, b)
        self.assertFalse(a["eligible"])


if __name__ == "__main__":
    unittest.main()
