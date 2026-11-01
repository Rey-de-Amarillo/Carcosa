import unittest

from scripts.oddspapi_temporal_arb import Group, build_groups, full_partition, portfolio, stamp, sweep_group


def quote(at, price, active=True, limit=1000):
    return {"createdAt":f"2026-01-01T00:{at:02d}:00+00:00", "price":price,"active":active,"limit":limit}


class TemporalArbitrageTests(unittest.TestCase):
    def pair(self, a, b):
        group=Group("test",("Yes","No"))
        group.add("Yes",("a","1","1","0"),a)
        group.add("No",("b","1","2","0"),b)
        return group

    def test_old_and_new_noncontemporaneous_prices_are_not_paired(self):
        group=self.pair([quote(0,2.2),quote(1,1.5)], [quote(0,1.5),quote(2,2.2)])
        stats,_=sweep_group(group,stamp("2026-01-01T00:10:00Z"),(300,))
        self.assertEqual(stats[300]["strict_positive_intervals"],0)

    def test_inactive_and_postkickoff_prices_do_not_create_opportunity(self):
        group=self.pair([quote(0,1.5),quote(1,2.2,False),quote(3,3.0)], [quote(0,2.2)])
        stats,_=sweep_group(group,stamp("2026-01-01T00:02:00Z"),(300,))
        self.assertEqual(stats[300]["strict_positive_intervals"],0)

    def test_stale_leg_is_excluded(self):
        group=self.pair([quote(0,2.2)], [quote(3,2.2)])
        stats,_=sweep_group(group,stamp("2026-01-01T00:10:00Z"),(60,300))
        self.assertEqual(stats[60]["strict_positive_intervals"],0)
        self.assertGreater(stats[300]["strict_positive_intervals"],0)

    def test_true_two_leg_cover_and_rounded_stakes(self):
        group=self.pair([quote(0,2.2)], [quote(0,2.2)])
        stats,_=sweep_group(group,stamp("2026-01-01T00:02:00Z"),(300,))
        candidate=stats[300]["top"][0]
        self.assertAlmostEqual(candidate["guaranteed_price_only_roi"],.1)
        self.assertEqual(candidate["stakes_per_100"],[50,50])
        self.assertAlmostEqual(candidate["worst_profit_on_100_rounded"],10)

    def test_integer_push_prevents_strict_profit_but_quarter_is_graded(self):
        integer=portfolio([2.2,2.2],"count_asian",2.0)
        quarter=portfolio([2.2,2.2],"count_asian",2.25)
        self.assertAlmostEqual(integer["guaranteed_price_only_roi"],0)
        self.assertGreater(quarter["guaranteed_price_only_roi"],0)
        self.assertLess(quarter["guaranteed_price_only_roi"],.1)
        self.assertAlmostEqual(quarter["guaranteed_price_only_roi"],1/15)
        negative_quarter=portfolio([2.2,2.2],"difference_asian",-1.25)
        self.assertAlmostEqual(negative_quarter["guaranteed_price_only_roi"],1/15)

    def test_integer_push_cent_rounding_also_maximizes_nonpush_floor(self):
        result=portfolio([2.2,1.892],"difference_asian",-1.0)
        self.assertEqual(result["stakes_per_100"],[46.24,53.76])
        self.assertAlmostEqual(result["worst_profit_on_100_rounded"],0)
        self.assertAlmostEqual(result["worst_nonpush_profit_on_100_rounded"],1.71392)

    def test_double_chance_uses_two_winners_per_result_not_independent_legs(self):
        result=portfolio([1.6,1.6,1.6],"double_chance")
        self.assertAlmostEqual(result["guaranteed_price_only_roi"],1.6*2/3-1)
        self.assertAlmostEqual(sum(result["weights"]),1)

    def test_cumulative_scorer_and_incomplete_score_lists_not_partitions(self):
        self.assertIsNone(full_partition({"marketType":"players-goals","outcomes":[{"outcomeId":1,"outcomeName":"0"},{"outcomeId":2,"outcomeName":"1+"},{"outcomeId":3,"outcomeName":"2+"}]}))
        self.assertIsNone(full_partition({"marketType":"correctscore","outcomes":[{"outcomeId":1,"outcomeName":"0:0"},{"outcomeId":2,"outcomeName":"1:0"}]}))

    def test_score_prefix_requires_over_tail_not_a_truncated_score_grid(self):
        cat={"1":{"marketId":1,"marketType":"correctscore","period":"fulltime","outcomes":[{"outcomeId":1,"outcomeName":"0:0"}]},
             "2":{"marketId":2,"marketType":"totals","period":"fulltime","handicap":.5,"outcomes":[{"outcomeId":2,"outcomeName":"Over"},{"outcomeId":3,"outcomeName":"Under"}]}}
        raw={"bookmakers":{"a":{"markets":{"1":{"outcomes":{"1":{"players":{"0":[quote(0,4.0)]}}}}}}}}
        groups,_=build_groups(raw,cat)
        self.assertNotIn("correct_scores_plus_over:fulltime:max_total:0",groups)
        raw["bookmakers"]["a"]["markets"]["2"]={"outcomes":{"2":{"players":{"0":[quote(0,2.0)]}}}}
        groups,_=build_groups(raw,cat)
        group=groups["correct_scores_plus_over:fulltime:max_total:0"]
        self.assertEqual(set(group.labels),{"0:0","OVER_TAIL"})


if __name__=="__main__":
    unittest.main()
