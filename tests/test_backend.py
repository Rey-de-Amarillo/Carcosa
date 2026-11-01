"""Behavioral checks for the local ledger, audit trail and free-credit limits.

All tests use an isolated temporary database and never query a paid provider.
"""

import json
import csv
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend import paper, scanner, storage
from backend.providers import OddsAPI, flatten_odds


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "store.sqlite3"
        # Initialize schema before deliberately concurrent credit reservations.
        with storage.connect(self.db):
            pass

    def test_concurrent_credit_reservations_never_exceed_free_limit(self):
        def reserve(_):
            try:
                storage.reserve_credits(1, 3, self.db)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(16)))
        self.assertEqual(sum(results), 3)
        self.assertEqual(storage.credits_used(self.db), 3)

    def test_cache_refresh_preserves_immutable_snapshot_history(self):
        first = [{"id": "match", "price": 2.0}]
        second = [{"id": "match", "price": 2.2}]
        storage.cache_put("odds:test:eu:h2h", first, {"remaining": "499"}, self.db)
        storage.cache_put("odds:test:eu:h2h", second, {"remaining": "498"}, self.db)
        history = storage.snapshot_history("odds:test:eu:h2h", self.db)
        self.assertEqual(len(history), 2)
        self.assertEqual({x["payload"][0]["price"] for x in history}, {2.0, 2.2})
        self.assertEqual(len({x["id"] for x in history}), 2)
        self.assertEqual(storage.cache_get("odds:test:eu:h2h", self.db)["payload"], second)

    def test_scan_refresh_preserves_explained_decision_history(self):
        root = Path(self.directory.name)
        (root / "engine").mkdir()
        for name in ("core.py", "report.py"):
            (root / "engine" / name).write_text("# Isolated reproducibility fixture\n")
        (root / "data/processed").mkdir(parents=True)
        (root / "data/processed/matches.csv").write_text("id,sport\nfixture,football\n")
        payloads = [{"generated_at": f"2026-10-30T12:00:0{index}+00:00", "mode": "observation",
                     "events": [], "quote_events": 0, "quotes": 0,
                     "opportunities": [{"id": "event:home", "model_probability": probability,
                                        "stake": 0, "status": "blocked", "reasons": ["Research"]}],
                     "execution_enabled": False}
                    for index, probability in enumerate((.55, .60))]
        with (patch.object(storage, "DB_PATH", self.db), patch.object(storage, "ROOT", root),
              patch.object(scanner, "build_scan", side_effect=payloads)):
            scanner.save_scan(Path(self.directory.name) / "live.json")
            scanner.save_scan(Path(self.directory.name) / "live.json")
        history = storage.scan_history(path=self.db)
        self.assertEqual(len(history), 2)
        archived = [storage.scan_get(item["id"], self.db) for item in history]
        self.assertEqual({x["opportunities"][0]["model_probability"] for x in archived}, {.55, .60})
        self.assertTrue(all(x["opportunities"][0]["stake"] == 0 for x in archived))


class PaperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "paper.sqlite3"

    def values(self, **changes):
        values = {"request_id": str(uuid.uuid4()), "event_id": "provider-event-1",
                  "event": "Home vs Away", "selection": "Home", "market": "1X2",
                  "odds": 2.0, "probability": .55, "stake": 10.0}
        values.update(changes)
        return values

    def test_retry_and_settlement_are_idempotent(self):
        values = self.values()
        first = paper.create(values, self.db)
        self.assertEqual(paper.create(values, self.db), first)
        self.assertEqual(len(paper.list_bets(self.db)), 1)
        settled = paper.settle(first["id"], "won", self.db)
        self.assertEqual(settled["profit"], 10.0)
        self.assertEqual(paper.settle(first["id"], "won", self.db), settled)
        with self.assertRaises(ValueError):
            paper.settle(first["id"], "lost", self.db)
        self.assertAlmostEqual(paper.equity(self.db), 1010.0)

    def test_losses_reduce_equity_and_future_single_bet_cap(self):
        first = paper.create(self.values(), self.db)
        paper.settle(first["id"], "lost", self.db)
        self.assertAlmostEqual(paper.equity(self.db), 990.0)
        with self.assertRaises(ValueError):
            paper.create(self.values(event_id="another", stake=10.0), self.db)
        record = paper.create(self.values(event_id="another", stake=9.9), self.db)
        self.assertAlmostEqual(record["stake"], 9.9)

    def test_same_event_id_cannot_bypass_exposure_by_changing_label(self):
        paper.create(self.values(event="Home vs Away"), self.db)
        paper.create(self.values(event="Different display name", selection="Away"), self.db)
        with self.assertRaises(ValueError):
            paper.create(self.values(event="Another label", stake=1), self.db)

    def test_total_open_exposure_is_bounded(self):
        for index in range(10):
            paper.create(self.values(event_id=f"event-{index}", event=f"Match {index}"), self.db)
        with self.assertRaises(ValueError):
            paper.create(self.values(event_id="extra", stake=1), self.db)

    def test_nonfinite_numeric_values_and_real_mode_are_rejected(self):
        for number in (float("nan"), float("inf"), -1):
            with self.assertRaises(ValueError):
                paper.create(self.values(stake=number), self.db)
        with self.assertRaises(ValueError):
            storage.save_settings({"mode": "live"}, self.db)


class QuoteProvenanceTests(unittest.TestCase):
    def quote(self, selection, odds):
        return {"selection": selection, "odds": odds, "bookmaker": "sample", "market": "h2h"}

    def test_incomplete_football_market_is_not_normalized_as_two_way(self):
        quotes = [self.quote("Home", 2.0), self.quote("Away", 3.0)]
        self.assertIsNone(scanner.h2h_market_probabilities(quotes, "Home", "Away", "football"))
        quotes.append(self.quote("Draw", 4.0))
        result = scanner.h2h_market_probabilities(quotes, "Home", "Away", "football")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(sum(result.values()), 1.0)
        self.assertAlmostEqual(result["Home"], (1/2)/(1/2+1/3+1/4))

    def test_duplicate_or_wrong_participant_does_not_complete_market(self):
        quotes = [self.quote("Home", 2.0), self.quote("Home", 3.0), self.quote("Away", 4.0)]
        self.assertIsNone(scanner.h2h_market_probabilities(quotes, "Home", "Away", "football"))
        quotes = [self.quote("Home", 2.0), self.quote("Other opponent", 2.0)]
        self.assertIsNone(scanner.h2h_market_probabilities(quotes, "Home", "Away", "basketball"))

    def test_naive_timestamps_do_not_acquire_an_invented_timezone(self):
        self.assertIsNone(scanner.iso_time("2026-10-30T12:00:00"))
        self.assertIsNone(scanner.iso_time("not a timestamp"))
        parsed = scanner.iso_time("2026-10-30T09:00:00-03:00")
        self.assertEqual(parsed.isoformat(), "2026-10-30T12:00:00+00:00")

    def test_flatten_preserves_lines_and_excludes_lay_market(self):
        snapshot = {"created_at": "2026-10-30T12:00:00+00:00", "payload": [{
            "id": "event", "sport_key": "basketball_nba", "home_team": "Home", "away_team": "Away",
            "bookmakers": [{"key": "sample", "title": "Sample", "markets": [
                {"key": "totals", "outcomes": [{"name": "Over", "point": 210.5, "price": 1.9},
                                                  {"name": "Under", "point": 210.5, "price": 1.9}]},
                {"key": "h2h_lay", "outcomes": [{"name": "Home", "price": 1.2}]}]}]}]}
        flattened = flatten_odds(snapshot)
        self.assertEqual(len(flattened), 2)
        self.assertEqual({x["line"] for x in flattened}, {210.5})
        self.assertTrue(all(not x["executable"] for x in flattened))

    def test_provider_cache_does_not_spend_a_credit_or_make_a_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "quota.sqlite3"
            storage.cache_put("odds:soccer_epl:eu:h2h", [], {"remaining": "499"}, db)
            adapter = OddsAPI(key="test-not-a-real-secret", db_path=db)
            with patch("backend.providers.urlopen", side_effect=AssertionError("Network is forbidden in test")):
                result = adapter.odds("soccer_epl")
            self.assertTrue(result["cached"])
            self.assertEqual(storage.credits_used(db), 0)

    def test_ineligible_model_does_not_display_an_actionable_probability(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            db = directory / "scan.sqlite3"
            tomorrow = (datetime.now(timezone.utc)+timedelta(days=1)).date().isoformat()
            history = {"id":"history","sport":"football","league":"test","date":"2020-01-01",
                       "home_team":"Home","away_team":"Away","home_score":"1","away_score":"0"}
            fixture = {"id":"fixture","sport":"football","league":"test","date":tomorrow,
                       "home_team":"Home","away_team":"Away","home_odds":"2.0","draw_odds":"3.0",
                       "away_odds":"4.0","source":"test","odds_source":"test"}
            for name, row in [("matches.csv",history),("fixtures.csv",fixture)]:
                with (directory/name).open("w",newline="") as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(row));writer.writeheader();writer.writerow(row)
            prediction={"home":.8,"draw":.1,"away":.1,"eligible":False,"model_age_days":1,
                        "sample_size":2,"effective_sample_size":2,"model":"test",
                        "training_max_date":"2020-01-01","reasons":["Insufficient history test marker"]}
            with patch.object(storage,"DB_PATH",db), patch.object(scanner,"predict_fixture",return_value=prediction):
                scan=scanner.build_scan(directory)
            self.assertEqual(len(scan["opportunities"]),3)
            for observation in scan["opportunities"]:
                self.assertIsNone(observation["model_probability"])
                self.assertIsNone(observation["ev"])
                self.assertEqual(observation["stake"],0)
                self.assertEqual(observation["status"],"blocked")
                self.assertIn("Insufficient history test marker",observation["reasons"])


if __name__ == "__main__":
    unittest.main()
