from decimal import Decimal
import unittest
from scripts.build_football_combination_report import check_opposite_integer_handicap, check_team_under_match_over


class CombinationMoneyTests(unittest.TestCase):
    def test_team_under_total_over_includes_overlap_and_unbounded_tail(self):
        r=check_team_under_match_over(2.5,2.5,2.22,2.03,47.76,52.24)
        self.assertEqual(Decimal(r['minimum_profit']),Decimal('6.0272'))
        self.assertEqual(Decimal(r['both_return']),Decimal('212.0744'))
        with self.assertRaises(ValueError):
            check_team_under_match_over(1.5,3.5,2.22,2.03,47.76,52.24)

    def test_push_is_zero_profit_not_a_strict_positive_cover(self):
        r=check_opposite_integer_handicap(-1,1,2.20,1.892,46.24,53.76)
        self.assertEqual(Decimal(r['home_side_wins_profit']),Decimal('1.728'))
        self.assertEqual(Decimal(r['away_side_wins_profit']),Decimal('1.71392'))
        self.assertEqual(Decimal(r['minimum_profit']),0)


if __name__=='__main__':
    unittest.main()
