import unittest

from scripts.analyze_arg_bets import (UnsupportedContract, canonical, evaluated,
                                      fractions, requires_timing, validate_joint_states)


class ArgentinaContractTests(unittest.TestCase):
    def test_team_range_yes_no_are_complements_of_team_not_match_total(self):
        for team in ("home", "away"):
            yes = canonical({"market": "goal_range", "selection": "yes", "period": "full_time",
                             "team": team, "min_goals": 1, "max_goals": 2})
            no = canonical({**yes, "selection": "no"})
            for home in range(7):
                for away in range(7):
                    value = home if team == "home" else away
                    self.assertEqual(fractions(yes, home, away)[0], int(1 <= value <= 2))
                    self.assertEqual(fractions(yes, home, away)[0]+fractions(no, home, away)[0], 1)
            # In 1–5, home is in its interval although match total is outside.
            self.assertEqual(fractions(yes, 1, 5)[0], int(team == "home"))

    def test_draw_and_under25_is_p00_plus_p11_not_product(self):
        grid = [[.2, .1, 0], [.1, .3, 0], [.05, .05, .2]]
        combo = canonical({"market": "combo", "period": "full_time", "odds": 2.2,
                           "legs": [{"market": "1x2", "selection": "draw"},
                                    {"market": "totals", "selection": "under", "line": 2.5}]})
        result = evaluated(combo, {"grid": grid})
        self.assertAlmostEqual(result["probability_positive_return"], .2+.3)
        self.assertAlmostEqual(result["ev_per_100_staked"], 10)
        self.assertNotAlmostEqual(result["probability_positive_return"], .7*.75)
        self.assertEqual(fractions(combo, 2, 2), (0, 1, 0))

    def test_quarter_under25_half_win_integer_push_and_over_half_loss(self):
        under_quarter = canonical({"market": "totals", "selection": "under", "line": 2.25, "period": "full_time", "odds": 2})
        over_quarter = canonical({**under_quarter, "selection": "over"})
        under_integer = canonical({**under_quarter, "line": 2})
        self.assertEqual(fractions(under_quarter, 1, 1), (.5, 0, .5))
        self.assertEqual(fractions(over_quarter, 1, 1), (0, .5, .5))
        self.assertEqual(fractions(under_integer, 1, 1), (0, 0, 1))
        # All probability is on two goals: not a binary win/loss treatment.
        grid = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
        under = evaluated(under_quarter, {"grid": grid})
        over = evaluated(over_quarter, {"grid": grid})
        self.assertAlmostEqual(under["ev_per_100_staked"], 50)
        self.assertAlmostEqual(over["ev_per_100_staked"], -50)
        self.assertIsNone(under["binary_break_even_probability"])

    def test_HT_FT_uses_joint_paths_not_marginal_product(self):
        states = [[0, 0, 0, 0, .2], [0, 0, 1, 0, .1], [1, 0, 1, 0, .2],
                  [1, 0, 1, 1, .15], [0, 1, 0, 1, .2], [0, 0, 1, 1, .15]]
        validate_joint_states(states)
        contract = canonical({"market": "htft", "period": "full_time", "selection": "draw/draw", "odds": 4})
        self.assertTrue(requires_timing(contract))
        result = evaluated(contract, {"states": states})
        self.assertAlmostEqual(result["probability_positive_return"], .35)
        self.assertAlmostEqual(result["ev_per_100_staked"], 40)
        self.assertNotAlmostEqual(result["probability_positive_return"], .45*.5)

    def test_HT_and_second_half_team_to_score_preserve_period(self):
        first = canonical({"market": "team_to_score", "selection": "no", "team": "home", "period": "first_half"})
        second = canonical({"market": "team_to_score", "selection": "yes", "team": "home", "period": "second_half"})
        self.assertEqual(fractions(first, 2, 0, ht=(0, 0)), (1, 0, 0))
        self.assertEqual(fractions(second, 2, 0, ht=(0, 0)), (1, 0, 0))
        self.assertEqual(fractions(first, 2, 0, ht=(1, 0)), (0, 1, 0))
        with self.assertRaisesRegex(UnsupportedContract, "missing_joint"):
            evaluated(first, {"grid": [[1.0]]})

    def test_win_either_half_is_union_with_overlap_not_independent_halves(self):
        states = [[1, 0, 2, 0, .4], [1, 0, 1, 1, .1],
                  [0, 1, 2, 1, .1], [0, 0, 0, 0, .4]]
        validate_joint_states(states)
        contract = canonical({"market": "win_either_half", "selection": "home", "period": "full_time", "odds": 2.5})
        self.assertTrue(requires_timing(contract))
        result = evaluated(contract, {"states": states})
        self.assertAlmostEqual(result["probability_positive_return"], .6)
        self.assertAlmostEqual(result["ev_per_100_staked"], 50)
        self.assertNotAlmostEqual(result["probability_positive_return"], 1-(1-.5)*(1-.5))
        self.assertEqual(fractions(contract, 2, 0, ht=(1, 0)), (1, 0, 0))

    def test_corners_never_use_goal_grid(self):
        contract = canonical({"market": "totals", "selection": "over", "line": 9.5,
                              "statistic": "corners", "period": "full_time", "odds": 2})
        with self.assertRaisesRegex(UnsupportedContract, "no_ARG_model_for_corners"):
            evaluated(contract, {"grid": [[.5, .5]]})

    def test_combo_void_or_half_win_needs_specific_builder_rule(self):
        combo = canonical({"market": "combo", "period": "full_time", "odds": 3,
                           "legs": [{"market": "double_chance", "selection": "home_draw"},
                                    {"market": "dnb", "selection": "home"}]})
        with self.assertRaisesRegex(UnsupportedContract, "requires_Bet365_rule"):
            fractions(combo, 0, 0)
        self.assertEqual(fractions(combo, 0, 1), (0, 1, 0))

    def test_invalid_joint_score_path_and_missing_mass_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_HT_FT_score_path"):
            validate_joint_states([[1, 0, 0, 0, 1]])
        with self.assertRaisesRegex(ValueError, "mass"):
            validate_joint_states([[0, 0, 0, 0, .9]])


if __name__ == "__main__":
    unittest.main()
