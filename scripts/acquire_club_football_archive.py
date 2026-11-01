#!/usr/bin/env python3
"""Archive and audit the public Club Football Match Data CSV, without changing models.

Standard library only. This is a separate personal research archive, not a new
independent source: the match/odds records originate from Football-Data.co.uk.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/club_football_match_data"
AUDIT = ROOT / "data/analysis/club_football_archive_audit.json"
SOURCES = {
    "Matches.csv": "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data/main/data/Matches.csv",
    "README.md": "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data/main/README.md",
    "LICENSE": "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data/main/LICENSE",
    "upstream_data_policy.html": "https://football-data.co.uk/data.php",
}
ODDS_COLUMNS = (
    "OddHome", "OddDraw", "OddAway", "MaxHome", "MaxDraw", "MaxAway",
    "Over25", "Under25", "MaxOver25", "MaxUnder25", "HandiHome", "HandiAway",
)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_bytes(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_bytes(payload)
    temp.replace(path)


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def valid_odds(value):
    value = number(value)
    return value is not None and value > 1


def key(division, match_date, home, away):
    return tuple((value or "").strip() for value in (division, match_date, home, away))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Download source files again instead of using the local archive")
    args = parser.parse_args()
    previous = json.loads(AUDIT.read_text()) if AUDIT.exists() else {}
    prior_files = {entry["filename"]: entry for entry in previous.get("files", [])}
    files = []
    for filename, url in SOURCES.items():
        path = RAW / filename
        if path.exists() and not args.refresh:
            payload = path.read_bytes()
            prior = prior_files.get(filename, {})
            retrieved_at = prior.get("retrieved_at", datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
            modified = prior.get("last_modified")
        else:
            request = Request(url, headers={"User-Agent": "Personal-Football-Archive/1.0"})
            with urlopen(request, timeout=90) as response:
                payload = response.read()
                modified = response.headers.get("Last-Modified")
            retrieved_at = utcnow()
            atomic_bytes(path, payload)
        files.append({
            "filename": filename, "path": str(path.relative_to(ROOT)), "url": url,
            "retrieved_at": retrieved_at, "last_modified": modified,
            "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
        })

    reader = csv.DictReader(io.StringIO((RAW / "Matches.csv").read_text(encoding="utf-8-sig")))
    fields = reader.fieldnames
    identities, divisions = Counter(), Counter()
    statuses = Counter({"future_date_rows": 0, "invalid_or_missing_date_rows": 0})
    dates = []
    odds = {column: {"nonempty": 0, "valid_decimal_gt_1": 0, "invalid_nonempty": 0} for column in ODDS_COLUMNS}
    groups = {"1x2_all_three_valid": 0, "total_2_5_both_valid": 0, "asian_handicap_both_valid": 0}
    settled_groups = dict.fromkeys(groups, 0)
    missing_score_examples = []
    invalid_examples = []
    row_count = 0
    today = datetime.now(timezone.utc).date()
    for row in reader:
        row_count += 1
        identity = key(row.get("Division"), row.get("MatchDate"), row.get("HomeTeam"), row.get("AwayTeam"))
        identities[identity] += 1
        divisions[row.get("Division", "")] += 1
        try:
            match_date = date.fromisoformat(row.get("MatchDate", ""))
            dates.append(match_date.isoformat())
            if match_date > today:
                statuses["future_date_rows"] += 1
        except ValueError:
            statuses["invalid_or_missing_date_rows"] += 1
        scores = [number(row.get(column)) for column in ("FTHome", "FTAway")]
        score_present = all(value is not None and value >= 0 and value.is_integer() for value in scores)
        if score_present:
            statuses["fulltime_score_present_rows"] += 1
        elif all(value is None for value in scores):
            statuses["fulltime_score_missing_rows"] += 1
        else:
            statuses["fulltime_score_invalid_or_partial_rows"] += 1
        if not score_present and len(missing_score_examples) < 20:
            missing_score_examples.append({"csv_line": row_count + 1, "identity": identity, "FTHome": row.get("FTHome"), "FTAway": row.get("FTAway"), "FTResult": row.get("FTResult")})
        statuses["ft_result_" + (row.get("FTResult") or "missing")] += 1
        for column in ODDS_COLUMNS:
            value = row.get(column, "")
            if value is not None and value.strip():
                odds[column]["nonempty"] += 1
                if valid_odds(value):
                    odds[column]["valid_decimal_gt_1"] += 1
                else:
                    odds[column]["invalid_nonempty"] += 1
                    if len(invalid_examples) < 20:
                        invalid_examples.append({"csv_line": row_count + 1, "identity": identity, "column": column, "value": value})
        for group, columns in (
            ("1x2_all_three_valid", ("OddHome", "OddDraw", "OddAway")),
            ("total_2_5_both_valid", ("Over25", "Under25")),
            ("asian_handicap_both_valid", ("HandiHome", "HandiAway")),
        ):
            if all(valid_odds(row.get(column)) for column in columns):
                groups[group] += 1
                if score_present and row.get("FTResult") in ("H", "D", "A"):
                    settled_groups[group] += 1

    existing_path = ROOT / "data/processed/matches.csv"
    comparison = {"path": str(existing_path.relative_to(ROOT)), "method": "Exact division/date/home/away strings; team aliases are NOT resolved, so nonmatches are not proof of independent new events."}
    if existing_path.exists():
        existing_keys = set()
        existing_rows = 0
        with existing_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if row.get("sport") == "football":
                    existing_rows += 1
                    existing_keys.add(key(row.get("league_code"), row.get("date"), row.get("home_team"), row.get("away_team")))
        comparison.update({
            "existing_football_rows": existing_rows,
            "existing_unique_exact_keys": len(existing_keys),
            "archive_unique_keys_already_present_exact": len(set(identities) & existing_keys),
            "archive_unique_keys_not_matched_exact": len(set(identities) - existing_keys),
        })

    upstream_quote = "its use is intended for private individuals only, NOT commerical or data training products using automated bots/scrapers/AI"
    policy_text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", (RAW / "upstream_data_policy.html").read_text())).split())
    audit = {
        "audited_at": utcnow(), "provider": "xgabora Club Football Match Data",
        "repository": "https://github.com/xgabora/Club-Football-Match-Data",
        "upstream_match_and_odds_source": "Football-Data.co.uk",
        "files": files, "rows": row_count, "columns": fields,
        "date_min": min(dates) if dates else None, "date_max": max(dates) if dates else None,
        "divisions_count": len(divisions), "divisions": dict(sorted(divisions.items())),
        "unique_match_identity_count": len(identities),
        "duplicate_identity_extra_rows": sum(count - 1 for count in identities.values()),
        "duplicate_identity_examples": [{"identity": identity, "rows": count} for identity, count in identities.items() if count > 1][:20],
        "row_status": dict(statuses), "odds_columns": odds, "valid_odds_groups": groups,
        "valid_odds_groups_with_fulltime_result": settled_groups,
        "missing_or_invalid_fulltime_score_examples": missing_score_examples,
        "invalid_odds_examples": invalid_examples, "existing_local_comparison": comparison,
        "scope": {
            "odds_markets": ["Full-time 1X2", "Over/under 2.5 full-time goals", "Asian handicap"],
            "bookmaker": "Bet365 columns plus market maxima; check missing and invalid values per market",
            "not_odds_markets": ["half-time", "corners", "cards", "player goalscorer", "custom combinations"],
            "price_timestamp_verified": False,
            "executable_prices_verified": False,
            "statistical_result_fields_are_not_betting_prices": True,
            "independent_of_existing_football_data_source": False,
            "elo_and_form_not_validated_for_leakage_or_training": True,
        },
        "usage_review": {
            "repository_license_label": "MIT (see archived LICENSE)",
            "upstream_policy_url": "https://football-data.co.uk/data.php",
            "upstream_policy_quote": upstream_quote,
            "upstream_policy_quote_verified_in_archived_page_text": upstream_quote in policy_text,
            "note": "A downstream MIT label does not remove upstream restrictions. This separate local archive has not been used to train a model or incorporated into a commercial product. Resolve intended-use permissions before such uses.",
        },
    }
    atomic_bytes(AUDIT, (json.dumps(audit, indent=2, ensure_ascii=False) + "\n").encode())
    print(json.dumps({"audit": str(AUDIT), "csv": str(RAW / "Matches.csv"), "rows": row_count,
                      "unique_identities": len(identities), "dates": [audit["date_min"], audit["date_max"]],
                      "valid_odds_groups": groups, "existing_local_comparison": comparison}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
