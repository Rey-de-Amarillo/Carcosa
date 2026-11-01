#!/usr/bin/env python3
"""Build a separate, source-preserving SQLite research archive from downloaded files.

No existing model inputs, recommendations or ROI are changed. No network calls.
Parquet support is optional outside the isolated --pyarrow-path installation.
"""
from __future__ import annotations

import argparse
import bz2
import csv
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import acquire_sgodds_archive as sg
import acquire_betfair_public_sample as bf
import acquire_betcity_research_archive as bc

DB = ROOT / "data/processed/free_football_history.sqlite"
AUDIT = ROOT / "data/analysis/free_football_database_audit.json"
REPORT = ROOT / "DATOS_FUTBOL_GRATUITOS.md"
AUDITS = {
    "club_football": ROOT / "data/analysis/club_football_archive_audit.json",
    "sgodds": ROOT / "data/analysis/sgodds_archive_audit.json",
    "betfair_sample": ROOT / "data/analysis/betfair_public_sample_audit.json",
    "betcity_research": ROOT / "data/analysis/betcity_research_archive_audit.json",
    "sharpapi_snapshot": ROOT / "data/analysis/sharpapi_worldcup_sample_audit.json",
}
ODDSPAPI_AUDIT = ROOT / "data/analysis/oddspapi_archive_audit.json"
AUDITS["oddspapi_history"] = ODDSPAPI_AUDIT


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def valid_decimal(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 1 else None
    except (TypeError, ValueError):
        return None


def iso(value):
    return value.isoformat() if value is not None else None


def add_file(db, source, record, *, retrieved_at=None, container=None):
    path = ROOT / record["path"]
    sha256 = digest(path)
    if record.get("sha256") and sha256 != record["sha256"]:
        raise ValueError(f"Source archive hash mismatch: {path}")
    row = db.execute("INSERT INTO source_files(source_id,path,url,sha256,bytes,retrieved_at,container_json,metadata_json) VALUES(?,?,?,?,?,?,?,?)", (
        source, record["path"], record.get("url", record.get("base_url")), sha256, path.stat().st_size,
        record.get("retrieved_at", retrieved_at), dumps(container) if container else None, dumps(record),
    ))
    return row.lastrowid


def setup(db, audits):
    db.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE sources(source_id TEXT PRIMARY KEY,audit_path TEXT,audit_sha256 TEXT,audit_json TEXT NOT NULL);
    CREATE TABLE source_files(file_id INTEGER PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(source_id),
       path TEXT NOT NULL,url TEXT,sha256 TEXT NOT NULL,bytes INTEGER NOT NULL,retrieved_at TEXT,container_json TEXT,metadata_json TEXT NOT NULL);
    CREATE TABLE archive_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    """)
    for source, audit in audits.items():
        db.execute("INSERT INTO sources VALUES(?,?,?,?)", (source, str(AUDITS[source].relative_to(ROOT)), digest(AUDITS[source]), dumps(audit)))
    metadata = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "cross_source_event_deduplication": "not_performed; do not sum source rows as unique football matches",
        "usage": "Separate local personal-research archive; source restrictions remain in sources.audit_json",
        "profitability": "No returns, trading strategy, model training or verified executable-price claims",
    }
    db.executemany("INSERT INTO archive_metadata VALUES(?,?)", metadata.items())


def import_club(db, audit):
    file_ids = {r["filename"]: add_file(db, "club_football", r) for r in audit["files"]}
    columns = audit["columns"]
    db.execute("CREATE TABLE cf_matches(row_id INTEGER PRIMARY KEY,source_file_id INTEGER NOT NULL REFERENCES source_files(file_id),source_row_number INTEGER NOT NULL," + ",".join(quote_identifier(c) + " TEXT" for c in columns) + ")")
    statement = "INSERT INTO cf_matches(source_file_id,source_row_number," + ",".join(map(quote_identifier, columns)) + ") VALUES(" + ",".join("?" for _ in range(len(columns) + 2)) + ")"
    with (ROOT / "data/raw/club_football_match_data/Matches.csv").open(newline="", encoding="utf-8-sig") as stream:
        batch = []
        for line_number, row in enumerate(csv.DictReader(stream), 2):
            batch.append((file_ids["Matches.csv"], line_number, *[row.get(c) or None for c in columns]))
            if len(batch) == 2000:
                db.executemany(statement, batch)
                batch.clear()
        if batch:
            db.executemany(statement, batch)
    contracts = [
        ("OddHome", "Bet365", "ft_1x2", "home", None),
        ("OddDraw", "Bet365", "ft_1x2", "draw", None),
        ("OddAway", "Bet365", "ft_1x2", "away", None),
        ("MaxHome", "market_maximum", "ft_1x2", "home", None),
        ("MaxDraw", "market_maximum", "ft_1x2", "draw", None),
        ("MaxAway", "market_maximum", "ft_1x2", "away", None),
        ("Over25", "Bet365", "ft_goal_total", "over", "2.5"),
        ("Under25", "Bet365", "ft_goal_total", "under", "2.5"),
        ("MaxOver25", "market_maximum", "ft_goal_total", "over", "2.5"),
        ("MaxUnder25", "market_maximum", "ft_goal_total", "under", "2.5"),
        ("HandiHome", "Bet365", "ft_asian_handicap", "home", "home_handicap_field"),
        ("HandiAway", "Bet365", "ft_asian_handicap", "away", "home_handicap_field"),
    ]
    selects = []
    for field, bookmaker, market, selection, line in contracts:
        line_sql = '"HandiSize"' if line == "home_handicap_field" else ("NULL" if line is None else "'2.5'")
        line_basis = "home_handicap" if line == "home_handicap_field" else ("match_total_goals" if line else "none")
        quoted = quote_identifier(field)
        selects.append(f"SELECT row_id AS match_row_id,source_file_id,source_row_number,'{field}' AS source_field,'{bookmaker}' AS bookmaker,'{market}' AS market,'FT' AS period,'{selection}' AS selection,{line_sql} AS line_source,'{line_basis}' AS line_basis,CAST({quoted} AS REAL) AS decimal_odds FROM cf_matches WHERE CAST({quoted} AS REAL)>1 AND CAST({quoted} AS REAL)<1e308")
    db.execute("CREATE VIEW cf_prices AS " + " UNION ALL ".join(selects))
    db.execute('CREATE INDEX cf_matches_date ON cf_matches("MatchDate")')
    db.execute('CREATE INDEX cf_matches_division_date ON cf_matches("Division","MatchDate")')


def import_sgodds(db, audit):
    db.executescript("""
    CREATE TABLE sgodds_matches(match_row_id INTEGER PRIMARY KEY,source_file_id INTEGER NOT NULL REFERENCES source_files(file_id),source_row_number INTEGER NOT NULL,
      source_match_id TEXT,match_name TEXT,league TEXT,start_time_source TEXT,live_bet_source TEXT,result_source TEXT,
      has_ht_ft_result INTEGER NOT NULL,ht_home INTEGER,ht_away INTEGER,ft_home INTEGER,ft_away INTEGER,raw_row_json TEXT NOT NULL);
    CREATE TABLE sgodds_prices(price_id INTEGER PRIMARY KEY,match_row_id INTEGER NOT NULL REFERENCES sgodds_matches(match_row_id),
      source_field TEXT NOT NULL,market TEXT NOT NULL,period TEXT NOT NULL,selection TEXT NOT NULL,line_source TEXT,
      decimal_odds REAL NOT NULL CHECK(decimal_odds>1),source_value TEXT,can_evaluate_from_ht_ft_score INTEGER NOT NULL,
      UNIQUE(match_row_id,source_field));
    """)
    for record in audit["files"]:
        file_id = add_file(db, "sgodds", record)
        for line_number, row in enumerate(sg.load_rows(record), 2):
            parsed = sg.RESULT.fullmatch(row["Result"].strip())
            scores = tuple(map(int, parsed.groups())) if parsed else (None,) * 4
            inserted = db.execute("INSERT INTO sgodds_matches(source_file_id,source_row_number,source_match_id,match_name,league,start_time_source,live_bet_source,result_source,has_ht_ft_result,ht_home,ht_away,ft_home,ft_away,raw_row_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                file_id, line_number, row["ID"], row["Match"], row["League"], row["Start Time"], row["Live Bet"], row["Result"], int(parsed is not None), *scores, dumps(row)))
            prices = []
            for field, raw in row.items():
                contract = sg.field_contract(field, row)
                value = valid_decimal(raw)
                if contract is None or value is None:
                    continue
                prices.append((inserted.lastrowid, field, contract["market"], contract["period"], contract["selection"], contract["line_source"], value, raw, int(contract["can_evaluate_from_ht_ft_score"])))
            db.executemany("INSERT INTO sgodds_prices(match_row_id,source_field,market,period,selection,line_source,decimal_odds,source_value,can_evaluate_from_ht_ft_score) VALUES(?,?,?,?,?,?,?,?,?)", prices)
    for doc in audit["documents"]:
        add_file(db, "sgodds", doc)
    db.execute("CREATE INDEX sgodds_prices_market ON sgodds_prices(market,selection,line_source)")
    db.execute("CREATE INDEX sgodds_matches_date ON sgodds_matches(start_time_source)")


def runner_key(runner):
    return dumps(bf.runner_key(runner))


def import_betfair(db, audit):
    file_id = add_file(db, "betfair_sample", audit["source"])
    for doc in audit["documentation"].values():
        add_file(db, "betfair_sample", doc)
    db.executescript("""
    CREATE TABLE betfair_markets(market_id TEXT PRIMARY KEY,source_file_id INTEGER NOT NULL REFERENCES source_files(file_id),event_id TEXT,event_name TEXT,
       market_type TEXT,market_name TEXT,market_time TEXT,final_definition_json TEXT NOT NULL);
    CREATE TABLE betfair_runners(market_id TEXT NOT NULL REFERENCES betfair_markets(market_id),runner_key TEXT NOT NULL,selection_id INTEGER,
       handicap_present INTEGER NOT NULL,handicap_json TEXT NOT NULL,runner_name TEXT,final_status TEXT,summary_json TEXT NOT NULL,
       PRIMARY KEY(market_id,runner_key));
    CREATE TABLE betfair_ltp_updates(update_id INTEGER PRIMARY KEY,market_id TEXT NOT NULL,runner_key TEXT NOT NULL,
       message_number INTEGER NOT NULL,publication_ms INTEGER,ltp REAL,in_play INTEGER,market_status_at_publication TEXT,
       market_definition_at_publication_json TEXT NOT NULL,runner_definition_at_publication_json TEXT NOT NULL,
       FOREIGN KEY(market_id,runner_key) REFERENCES betfair_runners(market_id,runner_key));
    """)
    for market in audit["markets"]:
        definition = market["definition"]
        db.execute("INSERT INTO betfair_markets VALUES(?,?,?,?,?,?,?,?)", (market["market_id"], file_id, definition.get("eventId"), definition.get("eventName"), definition.get("marketType"), definition.get("name"), definition.get("marketTime"), dumps(definition)))
        for runner in market["runners"]:
            key = dumps((runner["selection_id"], runner["handicap_present"], json.dumps(runner["handicap"], sort_keys=True)))
            db.execute("INSERT INTO betfair_runners VALUES(?,?,?,?,?,?,?,?)", (market["market_id"], key, runner["selection_id"], int(runner["handicap_present"]), dumps(runner["handicap"]), runner["definition"].get("name"), runner["definition"].get("status"), dumps(runner)))
    # marketDefinition and runner metadata are partial updates. Preserve prior
    # values; never infer missing inPlay, handicap, metadata or LTP as zero.
    states = {}
    data = (ROOT / audit["source"]["path"]).read_bytes()
    updates = []
    for message_number, line in enumerate(bz2.decompress(data).splitlines(), 1):
        if not line.strip():
            continue
        message = json.loads(line)
        for change in message.get("mc", []):
            market_id = change["id"]
            state = states.setdefault(market_id, {"definition": {}, "runners": {}})
            definition = change.get("marketDefinition", {})
            state["definition"].update({k: v for k, v in definition.items() if k != "runners"})
            for runner in definition.get("runners", []):
                state["runners"].setdefault(runner_key(runner), {}).update(runner)
            for runner in change.get("rc", []):
                if "ltp" not in runner:
                    continue
                key = runner_key(runner)
                phase = state["definition"].get("inPlay")
                updates.append((market_id, key, message_number, message.get("pt"), runner["ltp"], int(phase) if phase is not None else None,
                    state["definition"].get("status"), dumps(state["definition"]), dumps(state["runners"].get(key, {}))))
    db.executemany("INSERT INTO betfair_ltp_updates(market_id,runner_key,message_number,publication_ms,ltp,in_play,market_status_at_publication,market_definition_at_publication_json,runner_definition_at_publication_json) VALUES(?,?,?,?,?,?,?,?,?)", updates)
    db.execute("CREATE INDEX betfair_ltp_market_time ON betfair_ltp_updates(market_id,publication_ms)")
    db.execute("CREATE VIEW betfair_named_ltp_updates AS SELECT u.*,m.event_id,m.event_name,m.market_type,m.market_name,r.runner_name,r.final_status,r.handicap_present,r.handicap_json,'last_traded_price_change' AS price_semantics FROM betfair_ltp_updates u JOIN betfair_markets m USING(market_id) JOIN betfair_runners r USING(market_id,runner_key)")


def import_betcity(db, audit, pyarrow_path):
    if pyarrow_path:
        sys.path.insert(0, pyarrow_path)
    pq = importlib.import_module("pyarrow.parquet")
    manifest = audit["source"]
    source_files = manifest["files"]
    for record in source_files:
        add_file(db, "betcity_research", record, retrieved_at=manifest["retrieved_at"])
    zip_record = next(r for r in source_files if r["path"].endswith(".zip"))
    db.executescript("""
    CREATE TABLE betcity_events(event_row_id INTEGER PRIMARY KEY,source_file_id INTEGER NOT NULL REFERENCES source_files(file_id),source_row_number INTEGER NOT NULL,
      source_id INTEGER,event_name TEXT,event_date_source TEXT,league TEXT,final_score_source TEXT,score_home INTEGER,score_away INTEGER,
      has_parseable_final_score INTEGER NOT NULL,markets_created_source TEXT,raw_markets_created_source TEXT,markets_cnt_source INTEGER,
      scope_flag TEXT NOT NULL,markets_json TEXT NOT NULL CHECK(json_valid(markets_json)));
    CREATE TABLE betcity_market_keys(source_key TEXT PRIMARY KEY,market_family TEXT NOT NULL,selection_source TEXT,line_source TEXT,
      period_interpretation TEXT NOT NULL);
    """)
    all_keys = set()
    for partition in audit["partitions"]:
        path = ROOT / partition["path"]
        record = {"path": partition["path"], "url": zip_record["url"], "archive_member": str(path.relative_to(ROOT / "data/raw/domain_driven_soccer_probs"))}
        file_id = add_file(db, "betcity_research", record, retrieved_at=manifest["retrieved_at"], container={"path": zip_record["path"], "sha256": zip_record["sha256"], "member": record["archive_member"]})
        parquet = pq.ParquetFile(path)
        all_keys.update(field.name for field in parquet.schema_arrow.field("markets").type)
        row_number = 0
        for batch in parquet.iter_batches(batch_size=1024):
            records = []
            for row in batch.to_pylist():
                row_number += 1
                score = row.get("final_score") or ""
                parsed = re.fullmatch(r"(\d+):(\d+)", score)
                scores = tuple(map(int, parsed.groups())) if parsed else (None, None)
                nonnull_markets = {k: v for k, v in (row.get("markets") or {}).items() if v is not None}
                records.append((file_id, row_number, row.get("id"), row.get("event"), iso(row.get("date")), row.get("league"), row.get("final_score"), *scores,
                    int(parsed is not None), iso(row.get("markets_created")), row.get("raw_markets_created"), row.get("markets_cnt"), bc.scope_flag(row.get("league") or ""), dumps(nonnull_markets)))
            db.executemany("INSERT INTO betcity_events(source_file_id,source_row_number,source_id,event_name,event_date_source,league,final_score_source,score_home,score_away,has_parseable_final_score,markets_created_source,raw_markets_created_source,markets_cnt_source,scope_flag,markets_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", records)
        assert row_number == partition["rows"]
    keys = []
    for source_key in sorted(all_keys):
        selection = source_key.split("__")[-1]
        line_match = re.search(r"\(([^)]+)\)$", source_key)
        keys.append((source_key, bc.family(source_key), selection, line_match.group(1) if line_match else None, "full_match_source_label; regulation duration unverified; P1/P2=home/away"))
    db.executemany("INSERT INTO betcity_market_keys VALUES(?,?,?,?,?)", keys)
    db.execute("CREATE VIEW betcity_prices AS SELECT e.event_row_id,e.source_file_id,e.source_row_number,e.source_id,e.event_name,e.event_date_source,e.league,e.markets_created_source,e.scope_flag,e.has_parseable_final_score,j.key AS source_key,k.market_family,k.selection_source,k.line_source,CAST(j.value AS REAL) AS decimal_odds FROM betcity_events e JOIN json_each(e.markets_json) j JOIN betcity_market_keys k ON k.source_key=j.key WHERE j.type IN('real','integer') AND CAST(j.value AS REAL)>1 AND CAST(j.value AS REAL)<1e308")
    db.execute("CREATE INDEX betcity_events_date ON betcity_events(event_date_source)")
    db.execute("CREATE INDEX betcity_events_scope ON betcity_events(scope_flag)")


def scalar(db, sql):
    return db.execute(sql).fetchone()[0]


def import_sharpapi(db, audit):
    file_ids = {}
    for record in audit["source"]["files"]:
        file_ids[record["path"]] = add_file(db, "sharpapi_snapshot", record, retrieved_at=audit["retrieved_at"])
    columns = audit["schema"]
    db.execute("CREATE TABLE sharpapi_quotes(quote_row_id INTEGER PRIMARY KEY,source_file_id INTEGER NOT NULL REFERENCES source_files(file_id),source_row_number INTEGER NOT NULL,identified_fixture_source_id INTEGER NOT NULL,decimal_odds_valid REAL NOT NULL CHECK(decimal_odds_valid>1)," + ",".join(quote_identifier(c) + " TEXT" for c in columns) + ")")
    statement = "INSERT INTO sharpapi_quotes(source_file_id,source_row_number,identified_fixture_source_id,decimal_odds_valid," + ",".join(map(quote_identifier, columns)) + ") VALUES(" + ",".join("?" for _ in range(len(columns) + 4)) + ")"
    fixture_ids = set(audit["identified_match_event_ids"])
    records = []
    with (ROOT / audit["csv_path"]).open(newline="", encoding="utf-8-sig") as stream:
        for row_number, row in enumerate(csv.DictReader(stream), 2):
            decimal = valid_decimal(row.get("odds_decimal"))
            if decimal is None:
                raise ValueError("SharpAPI sample has unexpected invalid odds; audit before import")
            records.append((file_ids[audit["csv_path"]], row_number, int(row.get("event_id") in fixture_ids), decimal, *[row.get(c) for c in columns]))
    db.executemany(statement, records)
    db.execute("CREATE INDEX sharpapi_quotes_market ON sharpapi_quotes(market_type,sportsbook,event_id)")


def import_oddspapi(db, audit):
    """Optional acquired responses only. No API calls or account/key reads."""
    db.executescript("""
    DROP VIEW IF EXISTS oddspapi_history_ticks;
    DROP VIEW IF EXISTS oddspapi_market_catalog;
    DROP VIEW IF EXISTS oddspapi_fixture_metadata;
    DROP TABLE IF EXISTS oddspapi_responses;
    """)
    db.execute("DELETE FROM source_files WHERE source_id='oddspapi_history'")
    db.execute("DELETE FROM sources WHERE source_id='oddspapi_history'")
    db.execute("INSERT INTO sources VALUES(?,?,?,?)", ("oddspapi_history", str(ODDSPAPI_AUDIT.relative_to(ROOT)), digest(ODDSPAPI_AUDIT), dumps(audit)))
    db.execute("CREATE TABLE oddspapi_responses(response_id INTEGER PRIMARY KEY,source_file_id INTEGER NOT NULL REFERENCES source_files(file_id),endpoint TEXT NOT NULL,params_json TEXT NOT NULL,fixture_id_source TEXT,payload_json TEXT NOT NULL CHECK(json_valid(payload_json)))")
    for record in audit["sources"]:
        file_id = add_file(db, "oddspapi_history", record)
        payload = json.loads((ROOT / record["path"]).read_bytes())
        fixture_id = str(payload.get("fixtureId", record.get("params", {}).get("fixtureId", ""))) if isinstance(payload, dict) else None
        db.execute("INSERT INTO oddspapi_responses(source_file_id,endpoint,params_json,fixture_id_source,payload_json) VALUES(?,?,?,?,?)", (
            file_id, record["endpoint"], dumps(record.get("params", {})), fixture_id, dumps(payload)))
    db.executescript("""
    CREATE INDEX oddspapi_responses_endpoint ON oddspapi_responses(endpoint,fixture_id_source);
    CREATE VIEW oddspapi_market_catalog AS
      SELECT r.response_id,r.source_file_id,j.key AS source_array_index,
        CAST(json_extract(j.value,'$.marketId') AS TEXT) AS market_id,
        json_extract(j.value,'$.marketName') AS market_name,
        json_extract(j.value,'$.sportId') AS sport_id,
        json_extract(j.value,'$.marketType') AS market_type,
        json_extract(j.value,'$.period') AS period_source,
        json_extract(j.value,'$.handicap') AS handicap_source,
        json_extract(j.value,'$.playerProp') AS player_prop_source,
        j.value AS market_json
      FROM oddspapi_responses r JOIN json_each(r.payload_json) j
      WHERE r.endpoint='markets';
    CREATE VIEW oddspapi_fixture_metadata AS
      SELECT r.response_id,r.source_file_id,j.key AS source_array_index,
        CAST(json_extract(j.value,'$.fixtureId') AS TEXT) AS fixture_id,
        json_extract(j.value,'$.sportId') AS sport_id,
        json_extract(j.value,'$.statusId') AS status_id_source,
        json_extract(j.value,'$.startTime') AS start_time_source,
        json_extract(j.value,'$.trueStartTime') AS true_start_time_source,
        j.value AS fixture_json
      FROM oddspapi_responses r JOIN json_each(r.payload_json) j
      WHERE r.endpoint='fixtures';
    CREATE VIEW oddspapi_history_ticks AS
      SELECT r.response_id,r.source_file_id,r.fixture_id_source AS fixture_id,
        book.key AS bookmaker,market.key AS market_id,outcome.key AS outcome_id,
        player.key AS player_id_source,tick.key AS source_snapshot_index,
        json_extract(tick.value,'$.createdAt') AS created_at_source,
        json_type(tick.value,'$.price') AS price_json_type,
        json_extract(tick.value,'$.price') AS price_source,
        CASE WHEN json_type(tick.value,'$.price') IN('integer','real')
          AND json_extract(tick.value,'$.price')>1
          AND json_extract(tick.value,'$.price')<1e308
          THEN CAST(json_extract(tick.value,'$.price') AS REAL) END AS decimal_odds,
        json_type(tick.value,'$.active') AS active_json_type,
        json_extract(tick.value,'$.active') AS active_source,
        json_type(tick.value,'$.limit') AS limit_json_type,
        json_extract(tick.value,'$.limit') AS limit_source,
        json_extract(tick.value,'$.exchangeMeta') AS exchange_meta_source,
        tick.value AS snapshot_json
      FROM oddspapi_responses r
      JOIN json_each(r.payload_json,'$.bookmakers') book
      JOIN json_each(book.value,'$.markets') market
      JOIN json_each(market.value,'$.outcomes') outcome
      JOIN json_each(outcome.value,'$.players') player
      JOIN json_each(player.value) tick
      WHERE r.endpoint='historical-odds';
    """)


def validate_oddspapi(db, audit):
    checks = {
        "oddspapi_response_files": scalar(db, "SELECT COUNT(*) FROM oddspapi_responses"),
        "oddspapi_history_response_files": scalar(db, "SELECT COUNT(*) FROM oddspapi_responses WHERE endpoint='historical-odds'"),
        "oddspapi_history_snapshot_rows": scalar(db, "SELECT COUNT(*) FROM oddspapi_history_ticks"),
        "oddspapi_history_fixture_ids": scalar(db, "SELECT COUNT(DISTINCT fixture_id_source) FROM oddspapi_responses WHERE endpoint='historical-odds'"),
        "oddspapi_ticks_with_valid_decimal_odds": scalar(db, "SELECT COUNT(*) FROM oddspapi_history_ticks WHERE decimal_odds IS NOT NULL"),
    }
    assert checks["oddspapi_response_files"] == audit["source_response_count"]
    assert checks["oddspapi_history_response_files"] == audit["history_response_count"]
    assert checks["oddspapi_history_snapshot_rows"] == audit["snapshot_count"]
    assert checks["oddspapi_history_fixture_ids"] == audit["unique_history_fixture_count"]
    return checks


def validate(db, audits):
    checks = {}
    expected = {
        "cf_matches": audits["club_football"]["rows"],
        "sgodds_matches": audits["sgodds"]["totals"]["rows"],
        "sgodds_prices": audits["sgodds"]["totals"]["valid_decimal_price_observations"],
        "betfair_markets": audits["betfair_sample"]["market_id_count"],
        "betfair_ltp_updates": audits["betfair_sample"]["ltp_change_count"],
        "betcity_events": audits["betcity_research"]["event_rows"],
        "betcity_prices": audits["betcity_research"]["priced_outcome_rows_valid_decimal_gt_1"],
        "sharpapi_quotes": audits["sharpapi_snapshot"]["odds_rows"],
    }
    for table, expected_count in expected.items():
        count = scalar(db, f"SELECT COUNT(*) FROM {table}")
        assert count == expected_count, (table, count, expected_count)
        checks[table] = count
    checks["cf_prices"] = scalar(db, "SELECT COUNT(*) FROM cf_prices")
    assert checks["cf_prices"] == sum(c["valid_decimal_gt_1"] for c in audits["club_football"]["odds_columns"].values())
    checks["sgodds_with_ht_ft_result"] = scalar(db, "SELECT COUNT(*) FROM sgodds_matches WHERE has_ht_ft_result=1")
    assert checks["sgodds_with_ht_ft_result"] == audits["sgodds"]["totals"]["settled_with_ht_ft"]
    checks["betfair_pre_match_ltp_updates"] = scalar(db, "SELECT COUNT(*) FROM betfair_ltp_updates WHERE in_play=0")
    assert checks["betfair_pre_match_ltp_updates"] == audits["betfair_sample"]["pre_match_ltp_change_count"]
    checks["betcity_with_parseable_score"] = scalar(db, "SELECT COUNT(*) FROM betcity_events WHERE has_parseable_final_score=1")
    assert checks["betcity_with_parseable_score"] == audits["betcity_research"]["rows_with_parseable_final_score"]
    checks["betcity_scope_counts"] = dict(db.execute("SELECT scope_flag,COUNT(*) FROM betcity_events GROUP BY scope_flag"))
    assert checks["betcity_scope_counts"] == audits["betcity_research"]["scope_flag_row_counts"]
    checks["sharpapi_market_types"] = scalar(db, "SELECT COUNT(DISTINCT market_type) FROM sharpapi_quotes")
    assert checks["sharpapi_market_types"] == audits["sharpapi_snapshot"]["market_type_count"]
    checks["sharpapi_identified_fixture_price_rows"] = scalar(db, "SELECT COUNT(*) FROM sharpapi_quotes WHERE identified_fixture_source_id=1")
    assert checks["sharpapi_identified_fixture_price_rows"] == audits["sharpapi_snapshot"]["identified_match_odds_rows"]
    checks["sharpapi_identified_fixture_source_ids"] = scalar(db, "SELECT COUNT(DISTINCT event_id) FROM sharpapi_quotes WHERE identified_fixture_source_id=1")
    assert checks["sharpapi_identified_fixture_source_ids"] == audits["sharpapi_snapshot"]["identified_match_count"]
    checks["sharpapi_unique_full_price_keys"] = scalar(db, "SELECT COUNT(*) FROM(SELECT event_id,sportsbook,market_type,selection,selection_type,line,timestamp FROM sharpapi_quotes GROUP BY event_id,sportsbook,market_type,selection,selection_type,line,timestamp)")
    assert checks["sharpapi_unique_full_price_keys"] == audits["sharpapi_snapshot"]["unique_full_price_keys"]
    checks["integrity_check"] = scalar(db, "PRAGMA integrity_check")
    assert checks["integrity_check"] == "ok"
    checks["foreign_key_violations"] = len(list(db.execute("PRAGMA foreign_key_check")))
    assert checks["foreign_key_violations"] == 0
    example_query = "SELECT m.match_name,m.result_source,p.line_source,p.decimal_odds FROM sgodds_prices p JOIN sgodds_matches m USING(match_row_id) WHERE m.has_ht_ft_result=1 AND p.market='ht_goal_total' AND p.selection='over' AND CAST(p.line_source AS REAL)=0.5 ORDER BY m.start_time_source,m.match_row_id LIMIT 3"
    examples = [dict(zip(("match", "result", "line", "decimal_odds"), row)) for row in db.execute(example_query)]
    assert examples, "Expected actual first-half over 0.5 goal prices"
    checks["sgodds_first_half_goal_examples"] = examples
    return checks


def write_report(audit, sources):
    checks = audit["checks"]
    reconciliation = sources["sgodds"].get("epl_result_reconciliation", {}).get("counts", {})
    result_qa = f"Se contrastaron {reconciliation.get('source_settled_rows', 0)} resultados de Premier League: {reconciliation.get('matching_ht_and_ft_scores', 0)} coincidieron en marcador de descanso y final con los CSV locales, con alias documentados y tolerancia de fecha de un día. Esta comprobación no verifica cuotas ni otros campeonatos."
    api_row = ""
    api_note = ""
    api_sql = ""
    if "oddspapi_history_snapshot_rows" in checks:
        api_row = f"| OddsPapi, Pinnacle + DraftKings | {checks['oddspapi_history_fixture_ids']:,} IDs de partidos finalizados según API, sin marcadores importados | {checks['oddspapi_history_snapshot_rows']:,} observaciones históricas | Mercados por partido y jugador, con marcas de tiempo, actividad y límites originales |\n"
        api_note = "OddsPapi se incorpora desde la cuenta gratuita: cinco partidos de Premier League del 17/10/2026, con historial de Pinnacle y DraftKings. Las observaciones repetidas se conservan: no son 1,56 millones de apuestas diferentes ni cambios de precio. Los IDs de jugadores no se convierten en nombres inventados. `active`, `limit`, campos nulos/ausentes y `createdAt` quedan conservados. Algunos nombres de mercado incluyen prórroga; no se presupone liquidación a 90 minutos ni se inventan resultados. La consulta de historial fue gratuita; la auditoría registra 4/250 solicitudes consumidas al terminar.\n"
        api_sql = """\n-- Historial real adquirido por partido/casa/mercado/selección/jugador:
SELECT fixture_id,bookmaker,market_id,outcome_id,player_id_source,
       created_at_source,decimal_odds,active_json_type,active_source,
       limit_json_type,limit_source
FROM oddspapi_history_ticks LIMIT 20;

-- Consultar etiqueta y alcance de un mercado conservado en el catálogo:
SELECT market_id,market_name,period_source,handicap_source,player_prop_source
FROM oddspapi_market_catalog WHERE sport_id=10 AND market_id='101';
"""
    content = f"""# Datos gratuitos de fútbol descargados

Base consultable: `data/processed/free_football_history.sqlite` ({audit['database_bytes']:,} bytes).
Se conserva cada proveedor por separado. **Las filas de distintas fuentes no se suman como partidos únicos.**

| Fuente | Registros conservados | Precios válidos | Cobertura |
|---|---:|---:|---|
| Club Football Match Data / Football-Data | {checks['cf_matches']:,} partidos; 238.854 con marcador | {checks['cf_prices']:,} celdas de cuotas, incluidos máximos del mercado | 1X2, total 2,5 y hándicap; 2000–2026 |
| SGodds / Singapore Pools | {checks['sgodds_matches']:,} partidos; {checks['sgodds_with_ht_ft_result']:,} con HT y FT | {checks['sgodds_prices']:,} precios | 18 familias: primer tiempo, resultado exacto, goles exactos, BTTS, HT/FT, primer equipo en marcar, hándicap; 2025–2026 |
| Archivo de investigación atribuido a Betcity | {checks['betcity_events']:,} filas; {checks['betcity_with_parseable_score']:,} con marcador interpretable | {checks['betcity_prices']:,} precios | Totales por partido/equipo, hándicap, resultado/doble oportunidad y ambos marcan; 2022–2025 |
| Muestra pública oficial de Betfair BASIC | **1 partido**, {checks['betfair_markets']:,} mercados | {checks['betfair_ltp_updates']:,} cambios de último precio negociado | Middlesbrough–Manchester City, 30/04/2017; muestra de formato, no archivo masivo |
| Instantánea pública de SharpAPI | **2 fixtures identificados**, además de contratos de torneo/preguntas; sin resultados | {checks['sharpapi_quotes']:,} precios; {checks['sharpapi_market_types']:,} tipos de mercado, 20 fuentes | Goleadores, remates, tarjetas de jugadores, córners, primeros tiempos y más; captura del 13/07/2026 |
{api_row}

El primer tiempo en SGodds sí tiene cuotas históricas: `Htou_01` y `Htou_02` son over/under con su línea original `Htou_Hcap`. Las filas pendientes conservan resultado nulo. Los precios de primer equipo en marcar no pueden liquidarse en general solamente con HT/FT; faltan secuencias de goles.

{result_qa}

El archivo Betcity conserva todas las filas originales, incluso duplicados y competiciones señaladas: 23 ciber/simuladas, 33 de variantes y 58 con duración personalizada. **Los otros 422.064 registros también tienen formato y duración sin verificar**. Su `id` original se repite; se usa una clave de fila propia. `P1/P2` significa equipo local/visitante. Las fechas no tienen zona horaria y la antelación real de las cuotas no está verificada.

Los archivos grandes guardan sus precios en columnas u objetos originales y ofrecen vistas largas (`cf_prices`, `betcity_prices`), sin copiar millones de precios. Betfair conserva por separado cada selección y hándicap; sus metadatos parciales se acumulan en orden, y `pt` es publicación del mensaje. LTP es una operación previa: no representa una oferta ejecutable ni liquidez disponible.

No se encontraron en los CSV/Parquet grandes cuotas históricas de jugadores, córners o tarjetas. **La instantánea SharpAPI sí contiene esos precios**, pero no una temporada ni resultados: 5.501 filas corresponden a los dos IDs de fixture identificados (Francia–España e Inglaterra–Argentina); los otros contratos incluyen apuestas de torneo, preguntas y comparaciones entre jugadores. Los 250 `event_id` de origen no representan 250 partidos. Sus 16 colisiones de `id` se conservan sin deduplicar precios diferentes. La muestra Betfair permite inspeccionar mercados disponibles en **ese solo partido**. No se inventan cuotas de combinadas multiplicando cuotas individuales.

{api_note}

Football-Data limita el uso a particulares y excluye productos comerciales o de entrenamiento automatizado; la licencia MIT del recopilador no sustituye las condiciones originales. SGodds no aporta licencia abierta de redistribución. Betcity tiene descarga pública de investigación, sin licencia explícita de datos. SharpAPI declara CC BY 4.0, con atribución a SharpAPI. Las condiciones, URL, fecha de descarga y SHA-256 quedan en `sources` y `source_files`; los archivos originales siguen locales.

## Consultas útiles

```sql
-- Cuotas de un gol o más durante el primer tiempo, con HT/FT reales:
SELECT m.match_name, m.start_time_source, p.decimal_odds, m.ht_home, m.ht_away
FROM sgodds_prices p JOIN sgodds_matches m USING(match_row_id)
WHERE p.market='ht_goal_total' AND p.selection='over'
  AND CAST(p.line_source AS REAL)=0.5 AND m.has_ht_ft_result=1
ORDER BY m.start_time_source LIMIT 20;

-- Inventario de los 18 mercados de SGodds:
SELECT market, COUNT(*) FROM sgodds_prices GROUP BY market;

-- Precios de ambos marcan en Betcity; no implica duración o ejecución verificadas:
SELECT event_name, event_date_source, source_key, decimal_odds, scope_flag
FROM betcity_prices WHERE market_family='both_teams_to_score' LIMIT 20;

-- Últimos precios negociados publicados antes de pasar a en vivo, muestra Betfair:
SELECT event_name, market_name, runner_name, publication_ms, ltp
FROM betfair_named_ltp_updates WHERE in_play=0
ORDER BY publication_ms DESC LIMIT 20;

-- Procedencia exacta:
SELECT source_id, path, url, retrieved_at, sha256 FROM source_files;

-- Precios de goleadores/jugadores en la instantánea; no contiene resultados:
SELECT sportsbook, home_team, away_team, market_type, selection,
       decimal_odds_valid, timestamp
FROM sharpapi_quotes
WHERE identified_fixture_source_id=1
  AND market_type IN('anytime_goal_scorer','first_goal_scorer','player_cards')
LIMIT 20;
{api_sql}
```

Reconstrucción sin descargas ni cambios al modelo:

```bash
python3 scripts/build_free_football_database.py --pyarrow-path /tmp/football-research-pyarrow
```

Verificaciones: `PRAGMA integrity_check = ok`, claves foráneas sin errores y recuentos reconciliados con {len(sources)} auditorías fuente. No se calcularon retornos ni se entrenó el bot con esta incorporación.
"""
    REPORT.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyarrow-path", default="/tmp/football-research-pyarrow")
    parser.add_argument("--append-oddspapi", action="store_true", help="Atomically append/update acquired OddsPapi JSON only; no network calls")
    args = parser.parse_args()
    audits = {source: json.loads(path.read_text()) for source, path in AUDITS.items() if source != "oddspapi_history"}
    if ODDSPAPI_AUDIT.exists():
        api_audit = json.loads(ODDSPAPI_AUDIT.read_text())
        if api_audit.get("history_response_count", 0) >= 5 and api_audit.get("unique_history_fixture_count", 0) >= 5 and api_audit.get("snapshot_count", 0) > 0:
            audits["oddspapi_history"] = api_audit
    if args.append_oddspapi and "oddspapi_history" not in audits:
        raise SystemExit("Five acquired nonempty OddsPapi histories are not ready; existing database unchanged.")
    DB.parent.mkdir(parents=True, exist_ok=True)
    temp = DB.with_suffix(".sqlite.tmp")
    if temp.exists():
        temp.unlink()
    previous = None
    if args.append_oddspapi:
        if not DB.exists() or not AUDIT.exists():
            raise SystemExit("Build the base database before appending OddsPapi.")
        previous = json.loads(AUDIT.read_text())
        if digest(DB) != previous["database_sha256"]:
            raise ValueError("Existing database hash differs from its verified audit")
        shutil.copy2(DB, temp)
    db = sqlite3.connect(temp)
    try:
        if not args.append_oddspapi:
            setup(db, audits)
            import_club(db, audits["club_football"])
            print("Club Football imported", flush=True)
            import_sgodds(db, audits["sgodds"])
            print("SGodds imported", flush=True)
            import_betfair(db, audits["betfair_sample"])
            print("Betfair sample imported", flush=True)
            import_betcity(db, audits["betcity_research"], args.pyarrow_path)
            print("Betcity imported", flush=True)
            import_sharpapi(db, audits["sharpapi_snapshot"])
            print("SharpAPI snapshot imported", flush=True)
        else:
            db.execute("PRAGMA foreign_keys=ON")
        if "oddspapi_history" in audits:
            import_oddspapi(db, audits["oddspapi_history"])
            print("OddsPapi acquired JSON imported", flush=True)
        db.commit()
        checks = dict(previous["checks"]) if previous else validate(db, audits)
        if "oddspapi_history" in audits:
            checks.update(validate_oddspapi(db, audits["oddspapi_history"]))
        if previous:
            checks["integrity_check"] = scalar(db, "PRAGMA integrity_check")
            checks["foreign_key_violations"] = len(list(db.execute("PRAGMA foreign_key_check")))
            assert checks["integrity_check"] == "ok" and checks["foreign_key_violations"] == 0
    except Exception:
        db.close()
        raise
    db.close()
    temp.replace(DB)
    audit = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(), "database": str(DB.relative_to(ROOT)),
        "database_bytes": DB.stat().st_size, "database_sha256": digest(DB),
        "sqlite_version": sqlite3.sqlite_version, "script_sha256": digest(Path(__file__)),
        "source_audits": {source: {"path": str(AUDITS[source].relative_to(ROOT)), "sha256": digest(AUDITS[source])} for source in audits},
        "cross_source_event_deduplication_performed": False,
        "no_cross_source_unique_match_total_asserted": True,
        "no_models_or_existing_inputs_changed": True, "checks": checks,
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    write_report(audit, audits)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
