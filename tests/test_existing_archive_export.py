"""Research explorer export: real cached values, bounded parts and provenance."""
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("existing_archives", ROOT / "scripts/export_existing_betting_archives.py")
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class ExportUtilities(unittest.TestCase):
    def test_authentication_is_never_published_in_source_urls(self):
        self.assertEqual(EXPORT.safe_url("https://user:password@api.example.test/history?apiKey=secret&token=x#private"),
                         "https://api.example.test/history")
        for value in [None, "file:///home/person/key", "not a URL", "https://example.test:bad/path"]:
            self.assertEqual(EXPORT.safe_url(value), "")

    def test_source_times_and_status_are_not_inferred(self):
        exact = "2026-07-13T01:45:33.481436094Z"
        self.assertEqual(EXPORT.known_timestamp(exact), exact)
        self.assertEqual(EXPORT.known_timestamp("2026-07-13T01:45:33+03:00"), "2026-07-13T01:45:33+03:00")
        for value in [None, 1493129993643, "2026-07-13", "2026-07-13T01:45:33", "invalidZ"]:
            self.assertIsNone(EXPORT.known_timestamp(value))
        self.assertIsNone(EXPORT.source_bool(None))
        self.assertIs(EXPORT.source_bool("False"), False)
        self.assertIs(EXPORT.source_bool("True"), True)
        for value in [True, False, None, float("nan"), float("inf"), 1, ""]:
            self.assertFalse(EXPORT.valid_price(value))
        self.assertTrue(EXPORT.valid_price(1.01))
        labels = EXPORT.market_labels({"source:1": "Asian Handicap", "source:2": "Asian Handicap", "source:3": "BTTS"})
        self.assertEqual(len({item["name"] for item in labels}), 3)

    def test_parts_are_bounded_and_repeated_records_are_not_new_events(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE source_files(file_id,source_id,url,retrieved_at,sha256,path,bytes)")
        db.execute("INSERT INTO source_files VALUES(1,'betcity_research','https://example.test/data?token=private','2026-01-01T00:00:00Z',?,'raw.parquet',123)", ("a" * 64,))
        with tempfile.TemporaryDirectory() as temporary:
            ex = EXPORT.Exporter(db, temporary, max_quotes=2)
            ex.begin("betcity_research", "Research sample", 1, "duration_unverified", season="2026")
            ex.book("BC", "Betcity")
            ex.market("raw:result", "Original result")
            event = EXPORT.event_record("research:sample:1", "2026-01-01", "A", "B", "Research league", 1, 1, "duration_unverified")
            for index in range(3):
                ex.append(event, {"book": "BC", "market": "raw:result", "period": "unverified", "selection": str(index),
                    "line": None, "phase": "archive_time_unknown", "odds": 2 + index, "sourceColumn": "OriginalPrice",
                    "sourceRow": index, "sourceFileId": "1", "quality": "duration_unverified"})
            manifest = ex.finish()
            self.assertEqual(manifest["eventCount"], 1)
            self.assertEqual(manifest["quoteCount"], 3)
            self.assertEqual([part["quoteCount"] for part in manifest["partitions"]], [2, 1])
            self.assertEqual([part["eventCount"] for part in manifest["partitions"]], [1, 1])
            self.assertFalse(manifest["crossSourceDeduplication"])
            self.assertEqual(manifest["sources"][0]["url"], "https://example.test/data")
            self.assertEqual(manifest["leagues"], [{"id": "Research league", "name": "Research league"}])
            for part in manifest["partitions"]:
                payload = json.loads(gzip.decompress((Path(temporary) / part["path"]).read_bytes()))
                self.assertTrue(all(row[0] == 0 for row in payload["quotes"]["rows"]))
                columns = payload["quotes"]["columns"]
                self.assertTrue(all(row[columns.index("capturedAt")] is None for row in payload["quotes"]["rows"]))


class ActualCachedExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = ROOT / "app/data"
        cls.manifest = json.loads((cls.folder / "research-market-manifest.json").read_text())
        cls.sources = {source["id"]: source for source in cls.manifest["sources"]}

    def test_manifest_scope_counts_and_source_credentials(self):
        manifest = self.manifest
        self.assertEqual(manifest["provider"], "Archivos de investigación")
        self.assertFalse(manifest["crossSourceDeduplication"])
        self.assertIn("not_cross_source_unique_matches", manifest["eventCountMeaning"])
        self.assertEqual(manifest["quoteCount"], sum(part["quoteCount"] for part in manifest["partitions"]))
        self.assertEqual(set(manifest["providerQuoteCounts"]), {"oddspapi_history", "betfair_sample", "sharpapi_snapshot", "betcity_research"})
        self.assertEqual(manifest["providerQuoteCounts"]["betfair_sample"], 5628)
        self.assertEqual(manifest["providerQuoteCounts"]["sharpapi_snapshot"], 6132)
        self.assertEqual(manifest["providerQuoteCounts"]["oddspapi_history"], 1560124)
        self.assertGreater(manifest["providerQuoteCounts"]["betcity_research"], 4_800_000)
        self.assertEqual(len({part["id"] for part in manifest["partitions"]}), len(manifest["partitions"]))
        self.assertEqual(len({item["name"] for item in manifest["markets"]}), len(manifest["markets"]))
        for source in manifest["sources"]:
            parsed = urlsplit(source["url"])
            self.assertFalse(parsed.query or parsed.fragment or parsed.username or parsed.password)
            self.assertIn(parsed.scheme, {"http", "https"})
            self.assertRegex(source["sha256"], r"^[a-f0-9]{64}$")
        serialized = json.dumps(manifest)
        self.assertNotIn("apiKey", serialized)
        self.assertNotIn("account", " ".join(source["url"] for source in manifest["sources"]))

    def test_every_partition_integrity_contract_and_original_timing(self):
        books = {item["code"] for item in self.manifest["books"]}
        markets = {item["id"] for item in self.manifest["markets"]}
        phases = {item["id"] for item in self.manifest["phases"]}
        event_ids = set()
        counts = {}
        for part in self.manifest["partitions"]:
            compressed = (self.folder / part["path"]).read_bytes()
            self.assertLess(len(compressed), 25_000_000)
            self.assertEqual(hashlib.sha256(compressed).hexdigest(), part["sha256"])
            payload = json.loads(gzip.decompress(compressed))
            ec, qc = payload["events"]["columns"], payload["quotes"]["columns"]
            events, quotes = payload["events"]["rows"], payload["quotes"]["rows"]
            self.assertEqual(len(events), part["eventCount"])
            self.assertEqual(len(quotes), part["quoteCount"])
            self.assertLessEqual(len(quotes), 250_000)
            event_ids.update(row[ec.index("id")] for row in events)
            counts[part["provider"]] = counts.get(part["provider"], 0) + len(quotes)
            for source_id in part["sourceFileIds"]:
                self.assertIn(source_id, self.sources)
            # Sample both boundaries and the middle of every independently
            # hashed block, without retaining millions of Python dictionaries.
            for index in sorted({0, len(quotes) // 2, len(quotes) - 1}):
                q = dict(zip(qc, quotes[index]))
                self.assertEqual(len(quotes[index]), len(qc))
                self.assertTrue(0 <= q["event"] < len(events))
                self.assertIn(q["book"], books)
                self.assertIn(q["market"], markets)
                self.assertIn(q["phase"], phases)
                self.assertIn(q["sourceFileId"], self.sources)
                self.assertTrue(math.isfinite(q["odds"]) and q["odds"] > 1)
                self.assertTrue(q["sourceColumn"])
                self.assertIsInstance(q["sourceRow"], int)
                self.assertTrue(q["quality"])
                self.assertNotIn("probability", qc)
                self.assertNotIn("ev", qc)
                if part["provider"] == "betcity_research":
                    self.assertIsNone(q["capturedAt"])
                    self.assertIn("regulation_duration_unverified", q["quality"])
                    self.assertEqual(q["book"], "BETCITY")
                if part["provider"] == "oddspapi_history":
                    self.assertEqual(q["capturedAt"], q["rawTimestamp"])
                    self.assertIn(q["active"], [None, True, False])
                    self.assertIsNotNone(q["playerId"])
                if part["provider"] == "betfair_sample":
                    self.assertEqual(q["priceType"], "last_traded_price")
                    self.assertIn("publication", q["quality"])
                    self.assertIsNotNone(q["rawTimestamp"])
                if q["capturedAt"] is not None:
                    self.assertEqual(EXPORT.known_timestamp(q["capturedAt"]), q["capturedAt"])
        self.assertEqual(len(event_ids), self.manifest["eventCount"])
        self.assertEqual(counts, self.manifest["providerQuoteCounts"])

    def test_selected_rows_resolve_to_exact_cached_values(self):
        db_path = ROOT / "data/processed/free_football_history.sqlite"
        if not db_path.exists():
            self.skipTest("Private local source cache is not part of a published site")
        db = sqlite3.connect("file:" + str(db_path) + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        for provider in ["betcity_research", "oddspapi_history", "sharpapi_snapshot", "betfair_sample"]:
            part = next(part for part in self.manifest["partitions"] if part["provider"] == provider)
            payload = json.loads(gzip.decompress((self.folder / part["path"]).read_bytes()))
            row = dict(zip(payload["quotes"]["columns"], payload["quotes"]["rows"][0]))
            if provider == "betcity_research":
                record = db.execute("SELECT * FROM betcity_events WHERE source_file_id=? AND source_row_number=?", (int(row["sourceFileId"]), row["sourceRow"])).fetchone()
                self.assertEqual(json.loads(record["markets_json"])[row["sourceColumn"]], row["odds"])
                self.assertEqual(record["markets_created_source"], row["rawTimestamp"])
            elif provider == "sharpapi_snapshot":
                record = db.execute("SELECT * FROM sharpapi_quotes WHERE source_file_id=? AND source_row_number=?", (int(row["sourceFileId"]), row["sourceRow"])).fetchone()
                self.assertEqual(record["decimal_odds_valid"], row["odds"])
                self.assertEqual(record["timestamp"], row["capturedAt"])
                self.assertEqual(record["sportsbook"], row["book"])
            elif provider == "betfair_sample":
                record = db.execute("SELECT * FROM betfair_ltp_updates WHERE update_id=?", (row["sourceQuoteId"],)).fetchone()
                self.assertEqual(record["ltp"], row["odds"])
                self.assertEqual(record["publication_ms"], row["rawTimestamp"])
            else:
                event = dict(zip(payload["events"]["columns"], payload["events"]["rows"][row["event"]]))
                metadata_endpoint = db.execute("SELECT endpoint FROM oddspapi_responses WHERE source_file_id=?", (int(event["sourceFileId"]),)).fetchone()
                self.assertEqual(metadata_endpoint[0], "fixtures", "team/date metadata must point to the fixture source, not the quote response")
                response = db.execute("SELECT payload_json FROM oddspapi_responses WHERE source_file_id=?", (int(row["sourceFileId"]),)).fetchone()
                value = json.loads(response[0])
                for key in row["sourceColumn"].split("/"):
                    value = value[key]
                tick = value[row["sourceRow"]]
                self.assertEqual(tick["price"], row["odds"])
                self.assertEqual(tick["active"], row["active"])
                self.assertEqual(tick["limit"], row["limit"])
                self.assertEqual(tick["createdAt"], row["capturedAt"])
        db.close()


if __name__ == "__main__":
    unittest.main()
