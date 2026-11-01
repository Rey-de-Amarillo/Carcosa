import copy
import unittest

from scripts.build_sport_comparison import build_comparison


def sample_row(sport, selection, *, region="eu", odds=1.9, **changes):
    row = {"event_id": sport, "sport": sport, "sport_key": sport + "_league",
           "bookmaker": "common_book", "market_key": "h2h", "selection": selection,
           "home_team": "Home", "away_team": "Away", "odds": odds, "line": None,
           "region": region, "retrieved_at": "2026-10-30T12:00:00Z",
           "last_update": "2026-10-30T11:59:00Z", "commence_time": "2026-10-31T12:00:00Z"}
    row.update(changes)
    return row


class SportComparisonTests(unittest.TestCase):
    def test_region_filter_precedes_freshest_alias_deduplication(self):
        rows = []
        for sport in ("basketball", "tennis"):
            rows += [sample_row(sport, name) for name in ("Home", "Away")]
            rows += [sample_row(sport, name, region="uk", odds=2.5, last_update="2026-10-30T12:00:00Z")
                     for name in ("Home", "Away")]
        sample = {"meta": {"generated_at": "2026-10-30T12:00:00Z"}, "fresh_quotes": rows}
        report = build_comparison(sample)
        self.assertEqual(report["comparison_region"], "eu")
        self.assertTrue(report["region_filter_applied_before_costs_and_dedup"])
        self.assertEqual(report["region_filtered_quote_count"], 4)
        self.assertEqual(len(report["rows"]), 2)
        for row in report["rows"]:
            self.assertEqual(row["regions_observed"], ["eu"])
            self.assertGreater(row["median_overround"], 0)
        self.assertEqual(report, build_comparison(copy.deepcopy(sample)))

    def test_missing_eu_side_is_not_completed_with_uk_and_horizon_is_enforced(self):
        rows = [sample_row("basketball", "Home"), sample_row("basketball", "Away", region="uk")]
        rows += [sample_row("tennis", name, commence_time="2026-11-08T12:00:00Z") for name in ("Home", "Away")]
        report = build_comparison({"meta": {"generated_at": "2026-10-30T12:00:00Z"}, "fresh_quotes": rows})
        self.assertEqual(report["rows"], [])
        self.assertEqual(report["horizon_h2h_full_game_board_count"], 0)


if __name__ == "__main__":
    unittest.main()
