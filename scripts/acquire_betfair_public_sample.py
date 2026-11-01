#!/usr/bin/env python3
"""Acquire and audit Betfair's public, single-match BASIC soccer sample.

No login, credentials or wagers.  LTP is a changed last-traded price, not an
available back/lay offer. Missing fields and unknown handicaps remain missing.
"""
from __future__ import annotations

import argparse
import bz2
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/betfair_public_sample"
OUT = ROOT / "data/analysis/betfair_public_sample_audit.json"
URL = "https://historicdata.betfair.com/files/football-basic-sample.bz2"
DOCS = {
    "basic_ltp_updates": "https://support.developer.betfair.com/hc/en-us/articles/25918481395740-How-is-the-BASIC-Historical-Data-last-price-traded-ltp-updated",
    "jurisdictions": "https://support.developer.betfair.com/hc/en-us/articles/360008664937-Which-jurisdictions-is-Betfair-Exchange-Historical-Data-available-to",
    "market_exclusions": "https://support.developer.betfair.com/hc/en-us/articles/360017615137-Which-markets-aren-t-available-via-Historical-Data",
    "free_basic_tier": "https://betfair-datascientists.github.io/data/usingHistoricDataSite/",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def acquire(url, path, refresh=False):
    metadata_path = path.with_suffix(path.suffix + ".source.json")
    if path.exists() and metadata_path.exists() and not refresh:
        data = path.read_bytes()
        metadata = json.loads(metadata_path.read_text())
        if metadata["sha256"] != digest(data):
            raise ValueError(f"Cached source hash mismatch: {path}")
        return data, metadata
    request = urllib.request.Request(url, headers={"User-Agent": "FootballResearch/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
        metadata = {
            "url": url, "resolved_url": response.url, "retrieved_at": utc_now(),
            "bytes": len(data), "sha256": digest(data),
            "content_type": response.headers.get("Content-Type"),
            "path": str(path.relative_to(ROOT)),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return data, metadata


def runner_key(runner):
    # Absent hc is not silently converted to zero or conflated with explicit null.
    return (runner["id"], "hc" in runner, json.dumps(runner.get("hc"), sort_keys=True))


def parse_sample(data):
    messages = [json.loads(line) for line in bz2.decompress(data).splitlines() if line.strip()]
    markets = {}
    rc_fields = Counter()
    publication_times = []
    for message in messages:
        pt = message.get("pt")
        if pt is not None:
            publication_times.append(pt)
        for change in message.get("mc", []):
            market = markets.setdefault(change["id"], {
                "market_id": change["id"], "definition": {}, "runners": {},
                "ltp_changes": 0, "pre_match_ltp_changes": 0,
                "in_play_ltp_changes": 0, "unknown_phase_ltp_changes": 0,
            })
            definition = change.get("marketDefinition", {})
            market["definition"].update({k: v for k, v in definition.items() if k != "runners"})
            for runner in definition.get("runners", []):
                key = runner_key(runner)
                state = market["runners"].setdefault(key, new_runner(runner))
                state["definition"].update(runner)
            phase = market["definition"].get("inPlay")
            for runner_change in change.get("rc", []):
                rc_fields.update(runner_change.keys())
                if "ltp" not in runner_change:
                    continue
                key = runner_key(runner_change)
                state = market["runners"].setdefault(key, new_runner(runner_change))
                # Metadata may be absent for this exact handicap. Keep it absent.
                price = runner_change["ltp"]
                state["ltp_changes"] += 1
                state["last_observed_ltp"] = price
                state["last_observed_publication_ms"] = pt
                if state["first_observed_publication_ms"] is None:
                    state["first_observed_publication_ms"] = pt
                state["ltp_field_null_count"] += price is None
                market["ltp_changes"] += 1
                if phase is False:
                    state["pre_match_ltp_changes"] += 1
                    state["last_pre_match_ltp"] = price
                    state["last_pre_match_publication_ms"] = pt
                    market["pre_match_ltp_changes"] += 1
                elif phase is True:
                    market["in_play_ltp_changes"] += 1
                else:
                    market["unknown_phase_ltp_changes"] += 1
    result = []
    for market in markets.values():
        market["runners"] = list(market["runners"].values())
        result.append(market)
    known_types = {m["definition"]["marketType"] for m in result if "marketType" in m["definition"]}
    events = {(m["definition"].get("eventId"), m["definition"].get("eventName")) for m in result}
    return {
        "message_count": len(messages), "market_id_count": len(result),
        "known_market_type_count": len(known_types),
        "markets_missing_type_count": sum("marketType" not in m["definition"] for m in result),
        "priced_market_count": sum(m["ltp_changes"] > 0 for m in result),
        "pre_match_priced_market_count": sum(m["pre_match_ltp_changes"] > 0 for m in result),
        "ltp_change_count": sum(m["ltp_changes"] for m in result),
        "pre_match_ltp_change_count": sum(m["pre_match_ltp_changes"] for m in result),
        "runner_change_field_counts": dict(rc_fields),
        "min_publication_ms": min(publication_times), "max_publication_ms": max(publication_times),
        "events": [{"event_id": eid, "event_name": name} for eid, name in sorted(events)],
        "markets": result,
    }


def new_runner(runner):
    return {
        "selection_id": runner["id"], "handicap_present": "hc" in runner,
        "handicap": runner.get("hc"), "definition": {},
        "ltp_changes": 0, "pre_match_ltp_changes": 0, "ltp_field_null_count": 0,
        "first_observed_publication_ms": None, "last_observed_publication_ms": None,
        "last_observed_ltp": None, "last_pre_match_ltp": None,
        "last_pre_match_publication_ms": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    data, source = acquire(URL, RAW / "football-basic-sample.bz2", args.refresh)
    documents = {}
    for name, url in DOCS.items():
        _, documents[name] = acquire(url, RAW / f"{name}.html", args.refresh)
    audit = parse_sample(data)
    audit.update({
        "generated_at": utc_now(), "source": source, "documentation": documents,
        "script_sha256": digest(Path(__file__).read_bytes()),
        "scope": "Official free public BASIC soccer sample; one match, not the full archive.",
        "price_semantics": {
            "price_type": "last_traded_price", "available_back_lay_prices": False,
            "volume_available": False, "published_granularity": "1 minute; LTP sent only on change",
            "timestamp_meaning": "pt is message publication time, not a verified exact trade time",
            "missing_ltp": "Absent means no new LTP update; never replaced by zero.",
            "missing_handicap": "Preserved separately from explicit zero; do not infer a bet line.",
            "settlement": "Final runner status is preserved from market definitions.",
        },
    })
    assert audit["market_id_count"] == len({m["market_id"] for m in audit["markets"]})
    assert audit["ltp_change_count"] == sum(r["ltp_changes"] for m in audit["markets"] for r in m["runners"])
    assert len(audit["events"]) == 1, "Sample scope changed; review before reuse"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: audit[k] for k in ["message_count", "market_id_count", "known_market_type_count", "priced_market_count", "pre_match_priced_market_count", "ltp_change_count", "events"]}, ensure_ascii=False))
    print(f"Audit: {OUT}")


if __name__ == "__main__":
    main()
