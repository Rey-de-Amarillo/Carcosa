#!/usr/bin/env python3
"""Export cached research prices for the data explorer; no network or wagers.

These records are deliberately separate from regular, verified match odds.
Original labels, status, timestamps, scope and source hashes remain available.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
EVENT_COLUMNS = ["id", "date", "home", "away", "league", "season", "sourceEventId",
                 "eventName", "sourceStartTime", "status", "scope", "sourceFileId", "sourceSeasonId"]
QUOTE_COLUMNS = ["event", "book", "market", "period", "selection", "line", "phase",
                 "odds", "sourceColumn", "sourceRow", "capturedAt", "active", "limit",
                 "playerId", "rawMarketId", "rawMarketName", "rawSelectionId", "quality",
                 "sourceFileId", "priceType", "rawTimestamp", "exchangeMeta", "rawEventId",
                 "rawStartTime", "rawIsLive", "sourceQuoteId", "marketStatus", "runnerStatus",
                 "handicapPresent", "rawOdds", "rawTimeLabel", "rawSelectionType"]
PROVIDERS = {"betcity_research": "Domain-driven soccer probs · archivo de investigación",
             "oddspapi_history": "OddsPapi · histórico temporal",
             "betfair_sample": "Betfair · muestra pública BASIC",
             "sharpapi_snapshot": "SharpAPI · muestra pública"}
PHASE_NAMES = {"archive_time_unknown": "Archivo · hora no verificada",
               "historical_timestamp": "Histórico · actualización de precio",
               "pre_match_source_flag": "Prepartido según fuente",
               "in_play_source_flag": "En vivo según fuente",
               "phase_unknown": "Fase desconocida"}


def safe_url(value):
    """Only publish a credential-free endpoint, never query or user information."""
    try:
        parts = urlsplit(str(value or ""))
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ""
        host = parts.hostname + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except ValueError:
        return ""


def known_timestamp(value):
    """Preserve the exact source string only if it includes an explicit offset."""
    if not isinstance(value, str) or not re.search(r"(?:Z|[+-]\d{2}:?\d{2})$", value, re.I):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
        return value if parsed.tzinfo is not None else None
    except ValueError:
        return None


def numeric(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def valid_price(value):
    return not isinstance(value, bool) and numeric(value) is not None and numeric(value) > 1


def source_bool(value):
    if value is True or value in (1, "True", "true", "1"):
        return True
    if value is False or value in (0, "False", "false", "0"):
        return False
    return None


def source_file(row):
    return {"id": str(row["file_id"]), "provider": PROVIDERS.get(row["source_id"], row["source_id"]),
            "url": safe_url(row["url"]), "retrievedAt": row["retrieved_at"],
            "sha256": row["sha256"], "path": row["path"], "bytes": row["bytes"]}


def market_labels(markets):
    """Some source catalog names repeat for different lines/contract IDs."""
    counts = Counter(markets.values())
    return [{"id": code, "name": f"{name} · {code}" if counts[name] > 1 else name}
            for code, name in sorted(markets.items())]


class Exporter:
    def __init__(self, db, output, max_quotes=250_000):
        self.db, self.output, self.max_quotes = db, Path(output), max_quotes
        self.output.mkdir(parents=True, exist_ok=True)
        self.files = {r["file_id"]: source_file(r) for r in db.execute("SELECT * FROM source_files")}
        self.used_sources, self.books, self.markets, self.phases = set(), {}, {}, set()
        self.partitions, self.events, self.quotes, self.event_index = [], [], [], {}
        self.series = Counter()
        self.total_events = set()
        self.provider_counts = Counter()
        self.league_names, self.season_names = {}, set()

    def book(self, code, name=None):
        self.books[str(code)] = str(name or code)
        return str(code)

    def market(self, code, name):
        self.markets[str(code)] = str(name or code)
        return str(code)

    def begin(self, provider, label, source_id, quality, season=None, league=None, metadata_sources=()):
        self.flush()
        self.provider, self.label, self.source_id, self.quality = provider, label, source_id, quality
        self.season, self.league = season, league
        self.metadata_sources = list(metadata_sources)
        self.used_sources.update([source_id, *self.metadata_sources])

    def append(self, event, quote):
        if len(self.quotes) >= self.max_quotes:
            self.flush()
        identity = event["id"]
        if event.get("league"):
            self.league_names[str(event["league"])] = str(event["league"])
        if event.get("season"):
            self.season_names.add(str(event["season"]))
        if identity not in self.event_index:
            self.event_index[identity] = len(self.events)
            self.events.append([event.get(k) for k in EVENT_COLUMNS])
            self.total_events.add(identity)
        quote["event"] = self.event_index[identity]
        self.phases.add(quote["phase"])
        self.used_sources.add(int(quote["sourceFileId"]))
        self.quotes.append([quote.get(k) for k in QUOTE_COLUMNS])

    def flush(self):
        if not self.quotes:
            return
        self.series[self.provider] += 1
        identifier = f"{self.provider}-{self.series[self.provider]:03d}"
        path = f"research-market-{identifier}.json.gz"
        payload = {"events": {"columns": EVENT_COLUMNS, "rows": self.events},
                   "quotes": {"columns": QUOTE_COLUMNS, "rows": self.quotes}}
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        compressed = gzip.compress(data, compresslevel=6, mtime=0)
        if len(compressed) >= 25_000_000:
            raise ValueError("Partition exceeds 25 MB; lower --max-quotes")
        target = self.output / path
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(compressed)
        temporary.replace(target)
        dates = [row[1] for row in self.events if row[1]]
        books = Counter(row[1] for row in self.quotes)
        markets = Counter(row[2] for row in self.quotes)
        phases = Counter(row[6] for row in self.quotes)
        self.partitions.append({"id": identifier, "path": path,
            "provider": self.provider, "source": self.files[self.source_id],
            "sourceFileIds": [str(n) for n in [self.source_id, *self.metadata_sources]],
            "eventCount": len(self.events), "quoteCount": len(self.quotes),
            "dateMin": min(dates) if dates else None, "dateMax": max(dates) if dates else None,
            "season": self.season, "league": self.league, "label": self.label,
            "books": sorted(books), "markets": sorted(markets), "phases": sorted(phases),
            "bookCounts": dict(books), "marketCounts": dict(markets), "phaseCounts": dict(phases),
            "leagues": sorted({str(r[4]) for r in self.events if r[4]}),
            "seasons": sorted({str(r[5]) for r in self.events if r[5]}),
            "quality": self.quality, "sha256": hashlib.sha256(compressed).hexdigest(),
            "compressedBytes": len(compressed), "uncompressedBytes": len(data)})
        self.provider_counts[self.provider] += len(self.quotes)
        print(f"{identifier}: {len(self.events):,} event records, {len(self.quotes):,} observations", flush=True)
        self.events, self.quotes, self.event_index = [], [], {}

    def finish(self):
        self.flush()
        manifest = {"schemaVersion": 1, "provider": "Archivos de investigación",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "quality": "research_catalog_only_not_verified_executable_regular_match_quotes",
            "crossSourceDeduplication": False, "eventCountMeaning": "distinct_source_records_not_cross_source_unique_matches",
            "sources": [self.files[n] for n in sorted(self.used_sources)],
            "books": [{"code": k, "name": v} for k, v in sorted(self.books.items())],
            "markets": market_labels(self.markets),
            "phases": [{"id": k, "name": PHASE_NAMES[k]} for k in sorted(self.phases)],
            "seasons": sorted(self.season_names),
            "leagues": [{"id": k, "name": v} for k, v in sorted(self.league_names.items())], "partitions": self.partitions,
            "eventCount": len(self.total_events), "quoteCount": sum(p["quoteCount"] for p in self.partitions),
            "providerQuoteCounts": dict(self.provider_counts)}
        path = self.output / "research-market-manifest.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
        return manifest


def event_record(identity, date, home, away, league, source_id, source_file_id,
                 scope, start=None, status=None, name=None, season=None):
    return {"id": identity, "date": str(date or "")[:10] or None, "home": home or "",
            "away": away or "", "league": league or "", "season": str(season or str(date or "")[:4]),
            "sourceEventId": str(source_id), "eventName": name or f"{home or ''} — {away or ''}",
            "sourceStartTime": start, "status": status, "scope": scope, "sourceFileId": str(source_file_id)}


def export_betcity(ex):
    keys = {r["source_key"]: dict(r) for r in ex.db.execute("SELECT * FROM betcity_market_keys")}
    for record in ex.db.execute("SELECT DISTINCT source_file_id,substr(event_date_source,1,4) year FROM betcity_events ORDER BY source_file_id"):
        source_id, year = record["source_file_id"], record["year"]
        ex.begin("betcity_research", f"Betcity · investigación {year} · duración no verificada", source_id,
                 "research_format_and_regulation_duration_unverified", season=year)
        for r in ex.db.execute("SELECT * FROM betcity_events WHERE source_file_id=? ORDER BY event_row_id", (source_id,)):
            home, separator, away = (r["event_name"] or "").partition(" - ")
            event = event_record(f"research:betcity:{r['event_row_id']}", r["event_date_source"], home,
                away if separator else "", r["league"], r["source_id"], source_id, r["scope_flag"],
                start=r["event_date_source"], status="source_result_present" if r["has_parseable_final_score"] else "result_unknown",
                name=r["event_name"], season=year)
            for key, odds in json.loads(r["markets_json"]).items():
                if not valid_price(odds):
                    continue
                definition = keys.get(key, {})
                family = definition.get("market_family") or key.split("__", 1)[0]
                ex.append(event, {"book": ex.book("BETCITY", "Betcity"),
                    "market": ex.market(f"betcity:{family}", f"Betcity · {family}"),
                    "period": definition.get("period_interpretation") or "source_label_unverified",
                    "selection": definition.get("selection_source") or key, "line": numeric(definition.get("line_source")),
                    "phase": "archive_time_unknown", "odds": odds, "sourceColumn": key,
                    "sourceRow": r["source_row_number"], "capturedAt": known_timestamp(r["markets_created_source"]),
                    "rawTimestamp": r["markets_created_source"], "rawMarketId": key, "rawMarketName": family,
                    "rawTimeLabel": r["raw_markets_created_source"], "rawOdds": odds,
                    "rawEventId": r["source_id"], "rawStartTime": r["event_date_source"],
                    "quality": r["scope_flag"] + ";regulation_duration_unverified", "sourceFileId": str(source_id),
                    "priceType": "recorded_bookmaker_price"})


def export_oddspapi(ex):
    fixtures = {r["fixture_id"]: {**json.loads(r["fixture_json"]), "_sourceFileId": r["source_file_id"]}
                for r in ex.db.execute("SELECT * FROM oddspapi_fixture_metadata")}
    catalog = {}
    for r in ex.db.execute("SELECT * FROM oddspapi_market_catalog WHERE sport_id=10"):
        item = json.loads(r["market_json"])
        catalog[str(r["market_id"])] = item
    metadata_sources = [r[0] for r in ex.db.execute("SELECT source_file_id FROM oddspapi_responses WHERE endpoint IN('fixtures','markets','bookmakers')")]
    book_names = {}
    for r in ex.db.execute("SELECT payload_json FROM oddspapi_responses WHERE endpoint='bookmakers'"):
        book_names.update({b["slug"]: b.get("bookmakerName") or b["slug"] for b in json.loads(r[0])})
    for response in ex.db.execute("SELECT * FROM oddspapi_responses WHERE endpoint='historical-odds' ORDER BY fixture_id_source"):
        fid, source_id = response["fixture_id_source"], response["source_file_id"]
        fixture = fixtures.get(fid, {})
        start = fixture.get("startTime")
        league = fixture.get("tournamentName") or fixture.get("tournamentId") or "Unknown"
        event = event_record(f"research:oddspapi:{fid}", start, fixture.get("participant1Name"), fixture.get("participant2Name"),
            league, fid, fixture.get("_sourceFileId", source_id), "source_fixture_no_imported_score", start=start,
            status=fixture.get("statusName"), season=str(start or "")[:4])
        event["sourceSeasonId"] = fixture.get("seasonId")
        ex.begin("oddspapi_history", f"OddsPapi · {event['home']} — {event['away']}", source_id,
                 "temporal_updates_status_limit_preserved_no_imported_match_result", season=event["season"], league=league,
                 metadata_sources=metadata_sources)
        payload = json.loads(response["payload_json"])
        for book, book_data in payload.get("bookmakers", {}).items():
            ex.book(book, book_names.get(book, book))
            for market_id, market_data in book_data.get("markets", {}).items():
                meta = catalog.get(str(market_id), {})
                name = meta.get("marketName") or f"Market {market_id}"
                market = ex.market(f"oddspapi:{market_id}", name)
                outcomes = {str(o["outcomeId"]): o.get("outcomeName") for o in meta.get("outcomes", [])}
                for outcome_id, outcome_data in market_data.get("outcomes", {}).items():
                    for player, ticks in outcome_data.get("players", {}).items():
                        pointer = f"bookmakers/{book}/markets/{market_id}/outcomes/{outcome_id}/players/{player}"
                        for index, tick in enumerate(ticks):
                            if not valid_price(tick.get("price")):
                                continue
                            raw_time = tick.get("createdAt")
                            ex.append(event, {"book": book, "market": market, "period": meta.get("period"),
                                "selection": outcomes.get(str(outcome_id)) or str(outcome_id),
                                "line": meta.get("handicap"), "phase": "historical_timestamp", "odds": tick["price"],
                                "sourceColumn": pointer, "sourceRow": index, "capturedAt": known_timestamp(raw_time),
                                "active": tick.get("active"), "limit": tick.get("limit"), "playerId": str(player),
                                "rawMarketId": str(market_id), "rawMarketName": name, "rawSelectionId": str(outcome_id),
                                "quality": "temporal_update_not_full_simultaneous_snapshot", "sourceFileId": str(source_id),
                                "priceType": "bookmaker_price_update", "rawTimestamp": raw_time,
                                "rawOdds": tick["price"],
                                "exchangeMeta": tick.get("exchangeMeta"), "rawEventId": fid, "rawStartTime": start})
        del payload


def export_betfair(ex):
    markets = {r["market_id"]: dict(r) for r in ex.db.execute("SELECT * FROM betfair_markets")}
    sources = {r["source_file_id"] for r in markets.values()}
    for source_id in sorted(sources):
        ex.begin("betfair_sample", "Betfair BASIC · muestra de un partido · último precio negociado", source_id,
                 "last_traded_price_not_available_back_lay_offer", season="2017")
        ex.book("BFE-LTP", "Betfair Exchange · último precio negociado")
        for r in ex.db.execute("SELECT * FROM betfair_ltp_updates ORDER BY update_id"):
            stored = markets[r["market_id"]]
            if stored["source_file_id"] != source_id or not valid_price(r["ltp"]):
                continue
            meta = json.loads(r["market_definition_at_publication_json"])
            runner = json.loads(r["runner_definition_at_publication_json"])
            event_id = meta.get("eventId") or stored["event_id"]
            name = meta.get("eventName") or stored["event_name"] or ""
            home, separator, away = name.partition(" v ")
            start = meta.get("marketTime") or stored["market_time"]
            event = event_record(f"research:betfair:{event_id}", start, home, away if separator else "", "Betfair sample",
                event_id, source_id, "one_match_public_sample", start=start, status="source_market_status_not_match_result", name=name)
            market_type = meta.get("marketType") or stored["market_type"] or stored["market_id"]
            market_name = meta.get("name") or stored["market_name"] or market_type
            publication = datetime.fromtimestamp(r["publication_ms"] / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z") if r["publication_ms"] is not None else None
            in_play = source_bool(r["in_play"])
            ex.append(event, {"book": "BFE-LTP", "market": ex.market(f"betfair:{market_type}", market_name),
                "period": "source_market_label", "selection": runner.get("name") or str(runner.get("id") or r["runner_key"]),
                "line": runner.get("hc"), "phase": "in_play_source_flag" if in_play is True else "pre_match_source_flag" if in_play is False else "phase_unknown",
                "odds": r["ltp"], "sourceColumn": f"mc/{r['market_id']}/rc/{r['runner_key']}/ltp",
                "sourceRow": r["message_number"], "capturedAt": publication, "active": runner.get("status") == "ACTIVE" if runner.get("status") else None,
                "rawMarketId": r["market_id"], "rawMarketName": market_name, "rawSelectionId": runner.get("id"),
                "quality": "message_publication_time_not_trade_or_executable_offer_time", "sourceFileId": str(source_id),
                "marketStatus": r["market_status_at_publication"], "runnerStatus": runner.get("status"),
                "handicapPresent": "hc" in runner, "rawOdds": r["ltp"],
                "priceType": "last_traded_price", "rawTimestamp": r["publication_ms"], "rawEventId": event_id,
                "rawStartTime": start, "rawIsLive": in_play, "sourceQuoteId": r["update_id"]})


def export_sharp(ex):
    for source in ex.db.execute("SELECT DISTINCT source_file_id FROM sharpapi_quotes ORDER BY source_file_id"):
        source_id = source[0]
        ex.begin("sharpapi_snapshot", "SharpAPI · muestra Mundial · fixtures y preguntas de torneo", source_id,
                 "snapshot_includes_outrights_and_unidentified_contracts_no_imported_results", season="2026")
        for r in ex.db.execute("SELECT * FROM sharpapi_quotes WHERE source_file_id=? ORDER BY quote_row_id", (source_id,)):
            fixture = r["identified_fixture_source_id"]
            identity = f"research:sharpapi:fixture:{fixture}" if fixture else f"research:sharpapi:raw:{r['event_id']}"
            scope = "identified_fixture_no_imported_result" if fixture else "outright_question_or_unidentified_event"
            event = event_record(identity, r["event_start_time"], r["home_team"], r["away_team"], r["league"],
                fixture or r["event_id"], source_id, scope, start=r["event_start_time"], status="result_not_imported")
            book = ex.book(r["sportsbook"], r["sportsbook"])
            market = ex.market(f"sharpapi:{r['market_type']}", r["market_type"])
            live = source_bool(r["is_live"])
            ex.append(event, {"book": book, "market": market, "period": "source_market_label",
                "selection": r["selection"], "line": numeric(r["line"]),
                "phase": "in_play_source_flag" if live is True else "pre_match_source_flag" if live is False else "phase_unknown",
                "odds": r["decimal_odds_valid"], "sourceColumn": "odds_decimal", "sourceRow": r["source_row_number"],
                "capturedAt": known_timestamp(r["timestamp"]), "rawMarketId": r["market_type"], "rawMarketName": r["market_type"],
                "rawSelectionType": r["selection_type"], "quality": scope + ";snapshot_not_verified_executable_offer",
                "sourceFileId": str(source_id), "priceType": "public_odds_snapshot", "rawTimestamp": r["timestamp"],
                "rawOdds": r["odds_decimal"],
                "rawEventId": r["event_id"], "rawStartTime": r["event_start_time"], "rawIsLive": r["is_live"], "sourceQuoteId": r["id"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data/processed/free_football_history.sqlite")
    parser.add_argument("--output", type=Path, default=ROOT / "app/data")
    parser.add_argument("--max-quotes", type=int, default=250_000)
    args = parser.parse_args()
    if args.max_quotes <= 0:
        parser.error("--max-quotes must be positive")
    db = sqlite3.connect("file:" + str(args.db.resolve()) + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    exporter = Exporter(db, args.output, args.max_quotes)
    for function in [export_oddspapi, export_betfair, export_sharp, export_betcity]:
        function(exporter)
    manifest = exporter.finish()
    print(json.dumps({k: manifest[k] for k in ["eventCount", "quoteCount", "providerQuoteCounts"]}))


if __name__ == "__main__":
    main()
