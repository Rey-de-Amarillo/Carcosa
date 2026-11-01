#!/usr/bin/env python3
"""Archive and audit the public data accompanying DOI 10.3390/math13243976.

Requires pyarrow, which may be supplied without a global installation through
--pyarrow-path. No author modelling code is executed. Prices and results remain
separate from the project's existing model and betting recommendations.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "cuamckuu/domain-driven-soccer-probs"
PAPER = "https://www.mdpi.com/2227-7390/13/24/3976"
DOI = "10.3390/math13243976"


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "FootballResearchArchive/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def archive_file(url: str, target: Path) -> dict:
    content = request_bytes(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return {"url": url, "path": str(target.relative_to(ROOT)),
            "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def family(key: str) -> str:
    if key.startswith("P1__TOTALS__"):
        return "home_team_goals"
    if key.startswith("P2__TOTALS__"):
        return "away_team_goals"
    if key.startswith("TOTALS__"):
        return "match_total_goals"
    if key.startswith("HANDICAP__"):
        return "goal_handicap"
    if key.startswith("WIN__"):
        return "match_result_and_double_chance"
    if key.startswith("BOTH_TEAMS_TO_SCORE__"):
        return "both_teams_to_score"
    return "unmapped"


def scope_flag(league: str) -> str:
    """Conservative flags from explicit league labels, not a sport validator."""
    if re.search(r"cyber|esoccer|efootball|virtual|simulat|\bSRL\b|кибер|вирту|электрон|e-sport|\bpes\b|ФИФА", league, re.I):
        return "simulated_or_cyber"
    if re.search(r"\bWMF\b|\bEMF\b|\b[4-8][xх×][4-8]\b|футзал|пляж|мини.футбол|futsal|beach", league, re.I):
        return "small_sided_or_variant"
    if re.search(r"минут|тайм", league, re.I):
        return "explicit_custom_duration"
    return "no_explicit_scope_flag_unverified"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyarrow-path", help="Directory containing an isolated pyarrow installation")
    args = parser.parse_args()
    if args.pyarrow_path:
        sys.path.insert(0, args.pyarrow_path)
    try:
        pq = importlib.import_module("pyarrow.parquet")
    except ImportError as error:
        raise SystemExit("pyarrow is required; provide an isolated installation using --pyarrow-path.") from error

    retrieved_at = datetime.now(timezone.utc).isoformat()
    raw_directory = ROOT / "data/raw/domain_driven_soccer_probs"
    raw_directory.mkdir(parents=True, exist_ok=True)
    repository_info = json.loads(request_bytes(f"https://api.github.com/repos/{REPOSITORY}"))
    commit = json.loads(request_bytes(f"https://api.github.com/repos/{REPOSITORY}/commits/master"))["sha"]
    source_base = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}"
    files = [archive_file(f"{source_base}/{name}", raw_directory / name)
             for name in ("events_parquet.zip", "EvalProbsCleanCode.py")]
    manifest = {
        "retrieved_at": retrieved_at, "repository": f"https://github.com/{REPOSITORY}",
        "commit": commit, "paper_url": PAPER, "doi": DOI,
        "repository_license_metadata": repository_info.get("license"), "files": files,
        "attribution": "Data accompanying Domain-Driven Identification of Football Probabilities, DOI 10.3390/math13243976; original authors and repository retain attribution.",
        "licence_note": "Public research download. The article is openly published, but this repository has no explicit data licence file; do not infer commercial/training/redistribution permission.",
    }
    # Preserve provenance without executing the downloaded modelling program.
    code = (raw_directory / "EvalProbsCleanCode.py").read_text()
    manifest["bookmaker_attribution"] = {
        "name": "betcity", "evidence": "Author code labels all_markets_by_bk = {'betcity': all_markets}",
        "explicit_bookmaker_column_in_data": False,
        "code_label_present": "{'betcity': all_markets}" in code,
    }
    (raw_directory / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    rows = 0
    unique_event_keys = set()
    unique_result_keys = set()
    unique_unflagged_result_keys = set()
    unique_source_ids = set()
    duplicate_examples = []
    league_counts = Counter()
    key_counts = Counter()
    valid_key_counts = Counter()
    family_counts = Counter()
    family_event_counts = Counter()
    invalid_examples = []
    unknown_examples = []
    result_invalid_examples = []
    result_invalid_values = Counter()
    scope_result_counts = Counter()
    dates = []
    quote_dates = []
    partitions = []
    rows_with_result = rows_with_valid_price = quote_after_start = quote_equal_start = 0
    quote_before_start = missing_quote_time = missing_start_time = 0
    rows_without_nonnull_market = market_count_mismatches = 0
    nonnull_price_rows = valid_price_rows = invalid_price_rows = 0
    possible_variant_leagues = Counter()
    result_score_max = 0

    with zipfile.ZipFile(raw_directory / "events_parquet.zip") as archive:
        for member in archive.infolist():
            if not member.filename.endswith(".parquet"):
                continue
            destination = raw_directory / member.filename
            destination.resolve().relative_to(raw_directory.resolve())
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
            parquet = pq.ParquetFile(destination)
            schema = parquet.schema_arrow
            market_keys = [item.name for item in schema.field("markets").type]
            partitions.append({"path": str(destination.relative_to(ROOT)),
                               "rows": parquet.metadata.num_rows, "bytes": member.file_size,
                               "columns": schema.names, "market_field_count": len(market_keys),
                               "schema": str(schema.remove_metadata())})
            for batch in parquet.iter_batches(batch_size=512):
                for row in batch.to_pylist():
                    rows += 1
                    match_date = row.get("date")
                    quote_date = row.get("markets_created")
                    if match_date is not None:
                        dates.append(match_date)
                    else:
                        missing_start_time += 1
                    if quote_date is not None:
                        quote_dates.append(quote_date)
                    else:
                        missing_quote_time += 1
                    if match_date is not None and quote_date is not None:
                        if quote_date > match_date:
                            quote_after_start += 1
                        elif quote_date == match_date:
                            quote_equal_start += 1
                        else:
                            quote_before_start += 1
                    league = row.get("league") or ""
                    league_counts[league] += 1
                    if re.search(r"мини.футбол|футзал|пляж|\b[4-8][xх×][4-8]\b|кибер", league, re.I):
                        possible_variant_leagues[league] += 1
                    event_key = (str(match_date), league, row.get("event"))
                    if event_key in unique_event_keys and len(duplicate_examples) < 10:
                        duplicate_examples.append(event_key)
                    unique_event_keys.add(event_key)
                    unique_source_ids.add(row.get("id"))
                    score = row.get("final_score") or ""
                    valid_score = bool(re.fullmatch(r"\d+:\d+", score))
                    scope_result_counts[(scope_flag(league), valid_score)] += 1
                    if valid_score:
                        rows_with_result += 1
                        unique_result_keys.add(event_key)
                        if scope_flag(league) == "no_explicit_scope_flag_unverified":
                            unique_unflagged_result_keys.add(event_key)
                        result_score_max = max(result_score_max, *map(int, score.split(":")))
                    else:
                        result_invalid_values[score] += 1
                        if len(result_invalid_examples) < 10:
                            result_invalid_examples.append({"id": row.get("id"), "score": score})
                    nonnull = {key: value for key, value in (row.get("markets") or {}).items() if value is not None}
                    if len(nonnull) != row.get("markets_cnt"):
                        market_count_mismatches += 1
                    if not nonnull:
                        rows_without_nonnull_market += 1
                    row_valid = False
                    event_families = set()
                    for key, value in nonnull.items():
                        nonnull_price_rows += 1
                        key_counts[key] += 1
                        key_family = family(key)
                        family_counts[key_family] += 1
                        event_families.add(key_family)
                        if key_family == "unmapped" and key not in unknown_examples and len(unknown_examples) < 30:
                            unknown_examples.append(key)
                        if isinstance(value, (float, int)) and 1 < value < float("inf"):
                            valid_price_rows += 1
                            valid_key_counts[key] += 1
                            row_valid = True
                        else:
                            invalid_price_rows += 1
                            if len(invalid_examples) < 10:
                                invalid_examples.append({"id": row.get("id"), "market": key, "price": value})
                    rows_with_valid_price += row_valid
                    family_event_counts.update(event_families)

    scope_counts = Counter()
    scope_leagues = {}
    for league, count in league_counts.items():
        flag = scope_flag(league)
        scope_counts[flag] += count
        if flag != "no_explicit_scope_flag_unverified":
            scope_leagues[league] = {"flag": flag, "rows": count}
    audit = {
        "retrieved_at": retrieved_at, "source": manifest,
        "event_rows": rows, "unique_event_date_league_keys": len(unique_event_keys),
        "duplicate_event_date_league_rows": rows - len(unique_event_keys),
        "unique_source_ids": len(unique_source_ids), "source_id_alone_is_unique": len(unique_source_ids) == rows,
        "duplicate_event_examples": duplicate_examples,
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
        "leagues": len(league_counts), "league_counts": dict(league_counts.most_common()),
        "possible_variant_leagues": dict(possible_variant_leagues.most_common()),
        "scope_flag_row_counts": dict(scope_counts), "scope_flagged_leagues": scope_leagues,
        "scope_flag_note": "Flags inspect all source league labels for explicit cyber, virtual, WMF/EMF/small-sided or duration terms. An unflagged row is not independently verified regulation football. Youth/women/amateur/friendlies are retained, with no assumed eligibility for a particular sportsbook rule.",
        "football_scope_note": "The author calls this a football archive. Full-time 90-minute settlement and regulation-format competition status are not independently verified per row.",
        "rows_with_parseable_final_score": rows_with_result,
        "rows_without_parseable_final_score": rows - rows_with_result,
        "unique_event_keys_with_parseable_result": len(unique_result_keys),
        "unique_event_keys_with_parseable_result_and_no_explicit_scope_flag": len(unique_unflagged_result_keys),
        "scope_and_result_row_counts": [{"scope": key[0], "parseable_final_score": key[1], "rows": count}
                                       for key, count in scope_result_counts.items()],
        "invalid_final_score_values": dict(result_invalid_values),
        "invalid_result_examples": result_invalid_examples, "highest_team_score": result_score_max,
        "rows_with_valid_decimal_price": rows_with_valid_price,
        "rows_without_nonnull_market": rows_without_nonnull_market,
        "markets_cnt_mismatch_rows": market_count_mismatches,
        "priced_outcome_rows_nonnull": nonnull_price_rows,
        "priced_outcome_rows_valid_decimal_gt_1": valid_price_rows,
        "priced_outcome_rows_invalid_decimal": invalid_price_rows,
        "invalid_price_examples": invalid_examples,
        "distinct_nonnull_market_keys": len(key_counts),
        "market_key_nonnull_counts": dict(sorted(key_counts.items())),
        "market_key_valid_price_counts": dict(sorted(valid_key_counts.items())),
        "family_nonnull_price_counts": dict(family_counts),
        "family_event_counts": dict(family_event_counts), "unmapped_keys_sample": unknown_examples,
        "quote_time": {"earliest": min(quote_dates).isoformat() if quote_dates else None,
                       "latest": max(quote_dates).isoformat() if quote_dates else None,
                       "before_event_start": quote_before_start, "equal_event_start": quote_equal_start,
                       "after_event_start": quote_after_start,
                       "missing_event_start": missing_start_time, "missing_quote_time": missing_quote_time,
                       "independently_verified": False,
                       "note": "Source date and markets_created have no timezone attached. The source also includes raw_markets_created without a year. Do not infer executable prices or reliable ordering without validation."},
        "partitions": partitions,
        "not_present": ["player names or player odds", "goalscorer odds", "first-half odds and results",
                        "corners odds", "cards odds", "arbitrary same-match combinations", "wager amounts or volume"],
        "semantic_notes": ["P1 and P2 mean home and away teams, not first and second half.",
                           "Integer handicaps and totals require push-aware settlement.",
                           "Some observed markets are one-sided; never fabricate an opposite price.",
                           "Matching event names and scores are source-reported and not externally reconciled.",
                           "No author model was executed and no profitability claim follows from data availability."],
    }
    output = ROOT / "data/analysis/betcity_research_archive_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: audit[key] for key in ("event_rows", "unique_event_date_league_keys",
          "date_min", "date_max", "leagues", "priced_outcome_rows_nonnull", "priced_outcome_rows_valid_decimal_gt_1",
          "rows_with_parseable_final_score", "family_event_counts", "quote_time")}, ensure_ascii=False))
    print(f"Audit written to {output}")


if __name__ == "__main__":
    main()
