#!/usr/bin/env python3
"""Bounded, read-only OddsPapi acquisition. Never logs credentials or account PII.

No arguments rebuilds the audit from local cache without network. All API calls
are GETs. Paid subscriptions are refused, with a 10-request maximum billable
budget and 25 requests reserved by default. Historical calls are at least 5 s
apart. Raw price/status/limit/timestamps are preserved, with no ROI inference.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/oddspapi_history"
AUDIT = ROOT / "data/analysis/oddspapi_archive_audit.json"
BASE = "https://api.oddspapi.io/v4"
ALLOWED = {"account", "bookmakers", "markets", "tournaments", "fixtures", "historical-odds"}
DOCS = ["https://oddspapi.io/us/docs/" + x for x in
        ("get-historical-odds", "get-fixtures", "get-markets", "get-account", "requests-and-quota")]


class SafeError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def load_key():
    value = os.environ.get("ODDSPAPI_API_KEY", "").strip()
    if value:
        return value
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "ODDSPAPI_API_KEY":
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                else:
                    value = value.split(" #", 1)[0].strip()
                if value:
                    return value
    raise SafeError("ODDSPAPI_API_KEY is not configured; no network calls made.")


def cache_paths(endpoint, params):
    identity = json.dumps([endpoint, params], sort_keys=True, separators=(",", ":")).encode()
    name = f"{endpoint}__{sha(identity)[:16]}"
    return RAW / f"{name}.json", RAW / f"{name}.meta.json"


def cached(endpoint, params):
    path, meta_path = cache_paths(endpoint, params)
    if path.exists() and meta_path.exists():
        data = path.read_bytes()
        meta = json.loads(meta_path.read_text())
        if sha(data) != meta["sha256"]:
            raise SafeError(f"Cache hash mismatch for endpoint {endpoint}.")
        return json.loads(data), meta
    return None


def safe_account(body):
    if not isinstance(body, dict):
        raise SafeError("Unexpected account response shape.")
    subscriptions = body.get("subscriptions")
    if not isinstance(subscriptions, list):
        raise SafeError("Account response has no subscription list.")
    current = body.get("current_subscription_id")
    candidates = [s for s in subscriptions if isinstance(s, dict) and s.get("is_active") is True]
    if current:
        matched = [s for s in candidates if s.get("subscription_id") == current]
        candidates = matched or candidates
    if len(candidates) != 1:
        raise SafeError("Cannot identify exactly one active subscription.")
    sub = candidates[0]
    limit, count = sub.get("request_limit"), sub.get("request_count")
    if not isinstance(limit, int) or isinstance(limit, bool) or not isinstance(count, int):
        raise SafeError("Account quota fields are missing or invalid.")
    # This client only uses the verified Free account, never a paid/trial wallet.
    if sub.get("price") not in (None, 0, "0", "0.00") or not 0 < limit <= 250:
        raise SafeError("Refusing subscription that is not the verified free <=250-request tier.")
    return {"checked_at": now(), "free_tier_verified": True, "request_limit": limit,
            "request_count": count, "remaining": limit - count,
            "auto_renew": sub.get("auto_renew"), "valid_until": sub.get("valid_until"),
            "available_bookmaker_count": len(sub.get("bookmakers", {}))}


class Client:
    def __init__(self, key, budget, reserve, refresh):
        self.key, self.budget, self.reserve, self.refresh = key, budget, reserve, refresh
        self.calls, self.billable, self.last_end = [], 0, {}
        self.account_before = self.account_after = None

    def get(self, endpoint, params=None, bypass_cache=False):
        if endpoint not in ALLOWED:
            raise SafeError("Endpoint is not in the read-only allowlist.")
        params = params or {}
        if any("key" in str(k).lower() or "token" in str(k).lower() for k in params):
            raise SafeError("Credentials must not be passed as ordinary request parameters.")
        if endpoint != "account" and not self.refresh and not bypass_cache:
            hit = cached(endpoint, params)
            if hit is not None:
                return hit[0]
        billable = endpoint not in {"account", "historical-odds"}
        if endpoint != "account":
            if self.account_before is None:
                raise SafeError("Check the free account before acquiring data.")
            if self.account_before["remaining"] - self.billable <= 0:
                raise SafeError("Quota exhausted; historical endpoint would also be blocked.")
            if billable and (self.billable >= self.budget or
                             self.account_before["remaining"] - self.billable - 1 < self.reserve):
                raise SafeError("Billable request cap or reserved quota reached.")
        delay = {"historical-odds": 5.05, "fixtures": 2.05}.get(endpoint, 1.05)
        time.sleep(max(0, self.last_end.get(endpoint, -math.inf) + delay - time.monotonic()))
        if billable:
            self.billable += 1  # Reserve attempts, including failed requests.
        call = {"endpoint": endpoint, "params": params, "started_at": now(), "billable": billable}
        self.calls.append(call)
        query = urllib.parse.urlencode({**params, "apiKey": self.key})
        request = urllib.request.Request(BASE + "/" + endpoint + "?" + query,
                                         headers={"Accept": "application/json", "User-Agent": "FootballResearch/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read(128 * 1024 * 1024 + 1)
                call["http_status"] = response.status
                etag = response.headers.get("ETag")
            if len(data) > 128 * 1024 * 1024:
                raise SafeError("Response exceeds the bounded 128 MiB download limit.")
            body = json.loads(data)
            if endpoint == "account":
                # Never write the account payload, email, API key or subscription IDs.
                return safe_account(body)
            if self.key.encode() in data:
                raise SafeError("Response unexpectedly includes a credential; it was not archived.")
            path, meta_path = cache_paths(endpoint, params)
            path.write_bytes(data)
            write_json(meta_path, {"endpoint": endpoint, "base_url": BASE + "/" + endpoint,
                                  "params": params, "retrieved_at": now(), "sha256": sha(data),
                                  "bytes": len(data), "http_status": call["http_status"],
                                  "etag": etag, "path": str(path.relative_to(ROOT))})
            return body
        except urllib.error.HTTPError as error:
            call["http_status"] = error.code
            # Exception text and response bodies may contain the authenticated URL.
            raise SafeError(f"HTTP {error.code} from {endpoint}; credentials and body suppressed.") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            call["error_type"] = type(error).__name__
            raise SafeError(f"Request to {endpoint} failed ({type(error).__name__}); details suppressed.") from None
        finally:
            self.last_end[endpoint] = time.monotonic()
            call["finished_at"] = now()


def valid_fixture(fixture):
    return (isinstance(fixture, dict) and fixture.get("sportId") == 10 and
            fixture.get("statusId") == 2 and isinstance(fixture.get("fixtureId"), str))


def selection_audit(rows):
    if not isinstance(rows, list):
        return {"unexpected_shape": type(rows).__name__, "snapshot_count": 0}
    field_counts, states, stamps, prices, ordered = Counter(), Counter(), [], [], []
    for row in rows:
        if not isinstance(row, dict):
            states["non_object_snapshot"] += 1
            continue
        for field in ("price", "limit", "createdAt", "active", "exchangeMeta"):
            field_counts[f"{field}_absent" if field not in row else
                         f"{field}_null" if row[field] is None else f"{field}_present"] += 1
        active = row.get("active")
        states["absent" if "active" not in row else "null" if active is None else
               "true" if active is True else "false" if active is False else "other"] += 1
        stamp = row.get("createdAt")
        if isinstance(stamp, str):
            try:
                instant = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if instant.tzinfo is not None:
                    normalized = instant.astimezone(timezone.utc).isoformat()
                    stamps.append(normalized)
                    if isinstance(row.get("price"), (int, float)) and not isinstance(row.get("price"), bool):
                        ordered.append((normalized, row["price"]))
            except ValueError:
                states["invalid_timestamp"] += 1
        if isinstance(row.get("price"), (int, float)) and not isinstance(row.get("price"), bool):
            prices.append(row["price"])
    ordered.sort(key=lambda x: x[0])
    return {"snapshot_count": len(rows), "field_counts": dict(field_counts),
            "active_states": dict(states), "first_created_at": min(stamps) if stamps else None,
            "last_created_at": max(stamps) if stamps else None,
            "min_price": min(prices) if prices else None, "max_price": max(prices) if prices else None,
            "consecutive_price_changes": sum(a[1] != b[1] for a, b in zip(ordered, ordered[1:])),
            "timeline_in_raw_response": True}


def build_audit(run):
    entries, fixtures, market_catalog = [], {}, {}
    for path in sorted(RAW.glob("*.meta.json")):
        meta = json.loads(path.read_text())
        raw_path = ROOT / meta["path"]
        data = raw_path.read_bytes()
        if sha(data) != meta["sha256"]:
            raise SafeError("Archived response failed SHA256 validation.")
        obj = json.loads(data)
        entries.append((meta, obj))
        if meta["endpoint"] == "fixtures" and isinstance(obj, list):
            fixtures.update({str(f["fixtureId"]): f for f in obj if isinstance(f, dict) and "fixtureId" in f})
        if meta["endpoint"] == "markets" and isinstance(obj, list):
            market_catalog.update({str(m["marketId"]): m for m in obj if isinstance(m, dict) and "marketId" in m})
    histories = []
    for meta, obj in entries:
        if meta["endpoint"] != "historical-odds":
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("bookmakers"), dict):
            raise SafeError("Unexpected historical-odds shape in archived response.")
        fid = str(obj.get("fixtureId", meta["params"].get("fixtureId")))
        item = {"fixture_id": fid, "fixture": fixtures.get(fid), "source": meta, "bookmakers": []}
        for slug, book in obj["bookmakers"].items():
            summary = {"slug": slug, "markets": []}
            for mid, market in book.get("markets", {}).items():
                market_summary = {"market_id": mid, "catalog": market_catalog.get(str(mid)), "selections": []}
                for oid, outcome in market.get("outcomes", {}).items():
                    for pid, rows in outcome.get("players", {}).items():
                        market_summary["selections"].append({"outcome_id": oid, "player_id": pid,
                                                            **selection_audit(rows)})
                summary["markets"].append(market_summary)
            item["bookmakers"].append(summary)
        item["snapshot_count"] = sum(s["snapshot_count"] for b in item["bookmakers"] for m in b["markets"] for s in m["selections"])
        histories.append(item)
    audit = {"generated_at": now(), "documentation": DOCS, "last_run": run,
             "source_response_count": len(entries), "history_response_count": len(histories),
             "unique_history_fixture_count": len({h["fixture_id"] for h in histories}),
             "snapshot_count": sum(h["snapshot_count"] for h in histories),
             "histories": histories, "sources": [meta for meta, _ in entries],
             "semantics": ["Original JSON price/active/limit/status/null fields and timelines are retained.",
                           "createdAt is the provider's recorded timestamp, not proof of executable odds.",
                           "Finished fixtures may have hasOdds=false; it is not a historical-coverage filter.",
                           "Snapshots can repeat unchanged prices; they are not necessarily price moves.",
                           "No inferred missing outcomes, player names, settlement grades or ROI."]}
    write_json(AUDIT, audit)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", action="store_true", help="Acquire/cache bookmakers, markets and soccer tournaments.")
    parser.add_argument("--discover", action="store_true", help="Acquire one bounded list of finished soccer fixtures.")
    parser.add_argument("--sample", action="store_true", help="Metadata, discover, then acquire up to five nonempty histories.")
    parser.add_argument("--fixture-id", action="append", default=[], help="Repeat for fixture IDs already in acquired metadata.")
    parser.add_argument("--bookmakers", default="pinnacle,draftkings", help="One to three verified bookmaker slugs.")
    parser.add_argument("--outcome-id", type=int, help="One documented outcome filter; mandatory for betfair-ex.")
    parser.add_argument("--player-id", type=int, help="Optional documented player filter.")
    parser.add_argument("--from-date", default="2026-10-16")
    parser.add_argument("--to-date", default="2026-10-22")
    parser.add_argument("--tournament-slug", default="premier-league")
    parser.add_argument("--category-slug", default="england")
    parser.add_argument("--max-billable", type=int, choices=range(11), default=10)
    parser.add_argument("--reserve", type=int, default=25)
    parser.add_argument("--refresh", action="store_true", help="Refresh cached responses; paid-cap safeguards still apply.")
    parser.add_argument("--offline", action="store_true", help="Only rebuild audit from local raw cache; no key needed.")
    args = parser.parse_args()
    network = (args.metadata or args.discover or args.sample or bool(args.fixture_id)) and not args.offline
    RAW.mkdir(parents=True, exist_ok=True)
    lock = (RAW / ".acquisition.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SafeError("Another acquisition client is running.") from None
    run = {"started_at": now(), "network_requested": network, "max_billable": args.max_billable,
           "reserve": args.reserve, "calls": [], "errors": []}
    client = None
    try:
        if network:
            if args.reserve < 0:
                raise SafeError("Quota reserve must be nonnegative.")
            books = list(dict.fromkeys(s.strip() for s in args.bookmakers.split(",") if s.strip()))
            if not 1 <= len(books) <= 3 or any(not re.fullmatch(r"[a-z0-9_.+-]+", s) for s in books):
                raise SafeError("Choose one to three valid bookmaker slugs.")
            if "betfair-ex" in books and (len(books) != 1 or args.outcome_id is None):
                raise SafeError("Provider requires betfair-ex alone and exactly one --outcome-id.")
            client = Client(load_key(), args.max_billable, args.reserve, args.refresh)
            client.account_before = client.get("account")
            run["account_before"] = client.account_before
            if args.metadata or args.sample:
                client.get("bookmakers")
                client.get("markets", {"language": "en"})
                client.get("tournaments", {"sportId": 10, "language": "en"})
            if args.discover or args.sample:
                tournament_hit = cached("tournaments", {"sportId": 10, "language": "en"})
                if not tournament_hit:
                    raise SafeError("Acquire metadata first to resolve the football tournament.")
                matches = [t for t in tournament_hit[0] if t.get("tournamentSlug") == args.tournament_slug and t.get("categorySlug") == args.category_slug]
                if len(matches) != 1:
                    raise SafeError("Tournament slug/category did not identify exactly one acquired tournament.")
                try:
                    start = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc)
                    end = datetime.fromisoformat(args.to_date).replace(tzinfo=timezone.utc)
                except ValueError:
                    raise SafeError("Invalid date window.") from None
                if not (datetime(2026, 1, 1, tzinfo=timezone.utc) <= start < end <= datetime.now(timezone.utc)) or (end - start).days >= 10:
                    raise SafeError("Use a completed 2026 date window shorter than ten days.")
                client.get("fixtures", {"sportId": 10, "tournamentId": matches[0]["tournamentId"],
                                        "from": start.isoformat(), "to": end.isoformat(),
                                        "statusId": 2, "language": "en"})
            if args.sample or args.fixture_id:
                book_hit = cached("bookmakers", {})
                if not book_hit or any(s not in {b.get("slug") for b in book_hit[0]} for s in books):
                    raise SafeError("Requested bookmaker slug is not in acquired bookmaker metadata.")
                available = {}
                for path in RAW.glob("fixtures__*.meta.json"):
                    m = json.loads(path.read_text())
                    hit = cached("fixtures", m["params"])
                    if hit:
                        available.update({f["fixtureId"]: f for f in hit[0] if valid_fixture(f)})
                ids = list(dict.fromkeys(args.fixture_id))
                if any(fid not in available for fid in ids):
                    raise SafeError("Fixture ID is absent from acquired finished-football metadata.")
                if args.sample:
                    ids += [f["fixtureId"] for f in sorted(available.values(), key=lambda x: x.get("startTime", "")) if f["fixtureId"] not in ids]
                success = 0
                for fid in ids[:20]:
                    try:
                        query = {"fixtureId": fid, "bookmakers": ",".join(books)}
                        if args.outcome_id is not None:
                            query["outcomeId"] = args.outcome_id
                        if args.player_id is not None:
                            query["playerId"] = args.player_id
                        body = client.get("historical-odds", query)
                        nonempty = isinstance(body, dict) and any(
                            isinstance(rows, list) and rows
                            for book in body.get("bookmakers", {}).values()
                            for market in book.get("markets", {}).values()
                            for outcome in market.get("outcomes", {}).values()
                            for rows in outcome.get("players", {}).values())
                        if nonempty:
                            success += 1
                    except SafeError as error:
                        run["errors"].append(str(error))
                        if "HTTP 404 " not in str(error):
                            raise
                    if args.sample and success >= 5:
                        break
                run["nonempty_history_responses_this_run"] = success
    finally:
        if client:
            try:
                client.account_after = client.get("account")
                run["account_after"] = client.account_after
            except SafeError as error:
                run["errors"].append(str(error))
            run["calls"] = client.calls
            run["billable_attempts"] = client.billable
        run["finished_at"] = now()
        audit = build_audit(run)
        print(json.dumps({"audit": str(AUDIT), "history_fixtures": audit["unique_history_fixture_count"],
                          "snapshots": audit["snapshot_count"], "billable_attempts": run.get("billable_attempts", 0),
                          "account_before": run.get("account_before"), "account_after": run.get("account_after")}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except SafeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
