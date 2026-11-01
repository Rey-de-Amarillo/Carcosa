#!/usr/bin/env python3
"""Acquire the CC BY 4.0 SharpAPI World Cup snapshot, not a season archive."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PAGE_URL = "https://sharpapi.io/datasets"
DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/sharpapi/sports-betting-odds-2026-world-cup-mlb"
DATASET_URL = "https://www.kaggle.com/datasets/sharpapi/sports-betting-odds-2026-world-cup-mlb"
FILE_NAME = "worldcup_2026_odds_snapshot.csv"


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "FootballResearchArchive/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def write_source(content: bytes, target: Path, url: str) -> dict:
    target.write_bytes(content)
    return {"path": str(target.relative_to(ROOT)), "url": url,
            "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def main() -> None:
    directory = ROOT / "data/raw/sharpapi_worldcup_sample"
    directory.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    zip_bytes = download(DOWNLOAD_URL)
    files = [write_source(zip_bytes, directory / "sports-betting-odds-2026-world-cup-mlb.zip", DOWNLOAD_URL)]
    page = download(PAGE_URL)
    files.append(write_source(page, directory / "datasets_source_page.html", PAGE_URL))
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        csv_bytes = archive.read(FILE_NAME)
    files.append(write_source(csv_bytes, directory / FILE_NAME, DOWNLOAD_URL))
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    rows = list(reader)
    market_counts = Counter()
    book_counts = Counter()
    event_counts = Counter()
    fixture_counts = Counter()
    bookmaker_event_counts = Counter()
    missing = Counter()
    id_counts = Counter()
    row_keys = set()
    invalid_prices = []
    nonfinite_or_invalid = 0
    snapshots = set()
    live_counts = Counter()
    fixture_samples = {}
    for row in rows:
        market_counts[row["market_type"]] += 1
        book_counts[row["sportsbook"]] += 1
        event_counts[row["event_id"]] += 1
        bookmaker_event_counts[(row["sportsbook"], row["event_id"])] += 1
        id_counts[row["id"]] += 1
        snapshots.add(row["timestamp"])
        live_counts[row["is_live"]] += 1
        for key, value in row.items():
            if value in (None, ""):
                missing[key] += 1
        row_key = tuple(row[key] for key in ("event_id", "sportsbook", "market_type", "selection",
                                            "selection_type", "line", "timestamp"))
        row_keys.add(row_key)
        try:
            decimal_price = float(row["odds_decimal"])
            valid = math.isfinite(decimal_price) and decimal_price > 1
        except (TypeError, ValueError):
            valid = False
        if not valid:
            nonfinite_or_invalid += 1
            if len(invalid_prices) < 10:
                invalid_prices.append(row)
        # Only count explicit two-team/date fixtures; outright question text is
        # retained in the raw CSV and source-event counts, not called a fixture.
        home = row["home_team"].strip()
        away = row["away_team"].strip()
        date = row["event_start_time"].strip()
        if home and away and date:
            fixture_key = (home, away, date)
            fixture_counts[fixture_key] += 1
            fixture_samples.setdefault(fixture_key, set()).add(row["event_id"])

    # The provider names these two World Cup fixtures on its source page. Two
    # other rows put player names in home_team/away_team and are not fixtures.
    known_pairs = {frozenset(("france", "spain")), frozenset(("england", "argentina"))}
    identified_match_ids = {
        row["event_id"] for row in rows
        if frozenset((row["home_team"].strip().casefold(), row["away_team"].strip().casefold())) in known_pairs
    }

    manifest = {
        "retrieved_at": retrieved_at, "source_page": PAGE_URL,
        "dataset_url": DATASET_URL, "files": files,
        "licence": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution": "SharpAPI", "source": PAGE_URL,
                    "note": "Provider expressly permits commercial use, redistribution and derivatives with attribution."},
        "scope": "A single point-in-time World Cup odds snapshot dated 2026-07-13, not a season history or results dataset. The downloaded ZIP also contains an MLB file which was not imported into this football sample.",
    }
    (directory / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    audit = {
        "retrieved_at": retrieved_at, "source": manifest,
        "csv_path": str((directory / FILE_NAME).relative_to(ROOT)),
        "schema": reader.fieldnames, "odds_rows": len(rows),
        "market_type_count": len(market_counts), "market_type_counts": dict(market_counts.most_common()),
        "sportsbook_or_exchange_count": len(book_counts), "sportsbook_or_exchange_counts": dict(book_counts.most_common()),
        "source_event_id_count": len(event_counts), "source_event_id_counts": dict(event_counts.most_common()),
        "identified_match_count": len(identified_match_ids),
        "identified_match_event_ids": sorted(identified_match_ids),
        "identified_match_odds_rows": sum(event_counts[key] for key in identified_match_ids),
        "raw_two_sided_team_time_tuple_count": len(fixture_counts),
        "raw_two_sided_team_time_tuples": [
            {"home_team": key[0], "away_team": key[1], "event_start_time": key[2],
             "odds_rows": count, "source_event_ids": sorted(fixture_samples[key])}
            for key, count in fixture_counts.most_common()],
        "fixture_count_note": "Two match event IDs identified by France/Spain and England/Argentina, the fixture pairs named on the provider source page. Ten raw team/time tuples also include case/time-format differences, midnight times and two player-v-player outrights; those ten are not ten matches. Match identities and results were not externally reconciled.",
        "capture_timestamp_count": len(snapshots), "capture_min": min(snapshots), "capture_max": max(snapshots),
        "is_live_counts": dict(live_counts), "missing_value_counts": dict(missing),
        "price_record_id_unique_count": len(id_counts),
        "price_record_id_duplicated_values": sum(count > 1 for count in id_counts.values()),
        "price_record_id_extra_rows": sum(count - 1 for count in id_counts.values()),
        "unique_full_price_keys": len(row_keys), "duplicate_full_price_key_rows": len(rows) - len(row_keys),
        "invalid_decimal_price_rows": nonfinite_or_invalid, "invalid_decimal_price_examples": invalid_prices,
        "outcomes_attached": False, "historical_roi_evidence": False,
        "notes": ["Odds rows are prices, not matches.",
                  "Sources mix fixed-odds bookmakers, exchanges and prediction markets; fees and contract rules differ.",
                  "Anytime/first/last scorer, shots, SOT, player cards, corners and half markets are present, but only in this snapshot.",
                  "Original event and player identities are preserved; no assumed settlement or externally joined results.",
                  "Use own row ID and full price key, not the provider's nonunique id alone.",
                  "No profitability or executable arbitrage is inferred from this sample."],
    }
    target = ROOT / "data/analysis/sharpapi_worldcup_sample_audit.json"
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: audit[key] for key in ("odds_rows", "market_type_count", "sportsbook_or_exchange_count",
          "source_event_id_count", "identified_match_count", "invalid_decimal_price_rows",
          "capture_min", "capture_max")}, ensure_ascii=False))
    print(f"Audit written to {target}")


if __name__ == "__main__":
    main()
