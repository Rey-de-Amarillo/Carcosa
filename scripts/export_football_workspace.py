#!/usr/bin/env python3
"""Export the real 1X2 research universe for the private football workspace.

The browser receives compact tables, never credentials or arbitrary raw files.
Prices outside the saved policy's 1.2..5 interval are deliberately retained:
editing that interval in the UI must actually change the universe evaluated.
Exported decision fields use exactly the existing leave-one-book-out power
de-vig implementation. Post-match observations are explicitly marked as such.

Run: python3 scripts/export_football_workspace.py
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.research_market_reference_ev import outcome, valid_books
from scripts.research_robust_reference_ev import reference_scores

OUTPUT = ROOT / "app/data"
EVENT_COLUMNS = [
    "id", "date", "league", "league_name", "season", "home_team", "away_team",
    "home_score", "away_score", "home_ht_score", "away_ht_score",
    "home_corners", "away_corners", "home_yellow", "away_yellow",
    "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target",
]
OFFER_COLUMNS = [
    "event", "book", "side", "odds", "probability", "reference_mean",
    "reference_sd", "references", "ev", "won", "profit",
    "own_probability", "bookmaker_margin",
]
BOOK_NAMES = {
    "B365": "Bet365", "BW": "bwin", "IW": "Interwetten", "LB": "Ladbrokes",
    "PS": "Pinnacle", "VC": "BetVictor", "WH": "William Hill",
    "BF": "Betfair Sportsbook", "1XB": "1xBet", "BFE": "Betfair Exchange",
    "BFD": "Betfred", "BMGM": "BetMGM", "BV": "BetVictor", "CL": "Coral",
    "PP": "Paddy Power", "SKB": "Sky Bet",
}


def clean_number(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def load_matches():
    matches = {}
    with (ROOT / "data/processed/matches.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["sport"] != "football":
                continue
            score = [clean_number(row.get(key)) for key in ("home_score", "away_score")]
            if any(value is None or value < 0 or int(value) != value for value in score):
                continue
            matches[row["id"]] = row
    return matches


def table(path, columns, rows):
    payload = json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode()
    # Fixed gzip mtime makes the derived tables reproducible byte for byte.
    path.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    return {"path": path.name, "rows": len(rows), "columns": columns,
            "encoding": "gzip-json-table", "compressed_bytes": path.stat().st_size,
            "uncompressed_bytes": len(payload),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def offer_tables(offers, events):
    """Year shards stay below the hosting limit and load on period demand."""
    years = sorted({event[1][:4] for event in events})
    parts = []
    for year in years:
        rows = [row for row in offers if events[row[0]][1].startswith(year)]
        info = table(OUTPUT / f"workspace-offers-{year}.json.gz", OFFER_COLUMNS, rows)
        info["year"] = year
        parts.append(info)
    # Remove only this exporter's obsolete monolithic generated table.
    (OUTPUT / "workspace-offers.json.gz").unlink(missing_ok=True)
    return {"rows": len(offers), "columns": OFFER_COLUMNS,
            "encoding": "gzip-json-table-parts", "parts": parts,
            "compressed_bytes": sum(part["compressed_bytes"] for part in parts),
            "uncompressed_bytes": sum(part["uncompressed_bytes"] for part in parts)}


def choose(offers, events):
    """Frozen default policy; exact same deterministic tie break as research."""
    best = {}
    col = {key: index for index, key in enumerate(OFFER_COLUMNS)}
    for offer in offers:
        odd, ev = offer[col["odds"]], offer[col["ev"]]
        if not 1.2 <= odd <= 5 or ev < .03 or len(offer[col["references"]]) < 3:
            continue
        index = offer[0]
        key = (ev, offer[col["book"]], "h2h", -offer[col["side"]])
        if index not in best or key > best[index][0]:
            best[index] = (key, offer)
    return [best[index][1] for index in sorted(best,
            key=lambda i: (events[i][1], events[i][0]))]


def metrics(offers, events):
    if not offers:
        return {"n": 0, "wins": 0, "profit_units": 0, "stake_units": 0,
                "roi": None, "predicted_ev": None, "win_rate": None}
    # Decimal settlement avoids visually surprising 12.779999999999998 units.
    profit = sum((Decimal(str(row[3])) - 1 if row[9] else Decimal(-1))
                 for row in offers)
    n = len(offers)
    return {"n": n, "wins": sum(row[9] for row in offers),
            "profit_units": float(profit), "stake_units": n,
            "roi": float(profit / n), "win_rate": sum(row[9] for row in offers)/n,
            "predicted_ev": sum(row[8] for row in offers)/n,
            "average_odds": sum(row[3] for row in offers)/n,
            "first_date": min(events[row[0]][1] for row in offers),
            "last_date": max(events[row[0]][1] for row in offers)}


def verify(offers, events):
    """Audit exported selections against original ledger, not a new backtest."""
    selected = choose(offers, events)
    ledger = {}
    wanted = {"validation_all_books_minimum", "test_all_books_minimum"}
    with (ROOT / "data/analysis/research_robust_reference_ev.trades.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["scenario"] in wanted:
                key = (row["id"], row["book"], row["side"])
                if key in ledger:
                    raise AssertionError(f"Duplicated ledger selection: {key}")
                ledger[key] = row
    exported = {(events[row[0]][0], row[1], row[2]): row for row in selected}
    if exported.keys() != ledger.keys():
        raise AssertionError(f"UI/ledger selections differ: missing={ledger.keys()-exported.keys()}, "
                             f"extra={exported.keys()-ledger.keys()}")
    for key, row in exported.items():
        source = ledger[key]
        for field, index in [("odds", 3), ("probability", 4), ("reference_mean", 5),
                             ("reference_sd", 6), ("ev", 8)]:
            if row[index] != source[field]:
                raise AssertionError(f"UI/ledger {field} changed for {key}")
        if row[7] != source["references"] or row[9] != source["won"]:
            raise AssertionError(f"UI/ledger references or result changed for {key}")
    validation = [row for row in selected if events[row[0]][1] < "2022-01-01"]
    test = [row for row in selected if events[row[0]][1] >= "2022-01-01"]
    result = {"all": metrics(selected, events), "validation": metrics(validation, events),
              "test": metrics(test, events)}
    expected = json.loads((ROOT / "data/analysis/research_robust_reference_ev.json").read_text())
    for period, scenario in [("validation", "validation_all_books_minimum"),
                             ("test", "test_all_books_minimum")]:
        actual, original = result[period], expected["results"][scenario]
        for key in ["n", "wins", "profit_units", "roi", "predicted_ev"]:
            if not math.isclose(actual[key], original[key], rel_tol=1e-12, abs_tol=1e-12):
                raise AssertionError(f"UI/ledger aggregate differs: {period}/{key}")
    if [result[p]["n"] for p in ("validation", "test", "all")] != [219, 76, 295]:
        raise AssertionError("Frozen policy count changed")
    return result


def dictionary():
    def field(key, label, value_type="number", unit=None, phase="pre", formula=True, **extra):
        return dict(key=key, label=label, type=value_type, unit=unit, phase=phase,
                    available_for_rule=formula, **extra)
    fields = [
        field("date", "Fecha del partido", "date"),
        field("league", "Liga", "category"),
        field("home_team", "Equipo local", "text"),
        field("away_team", "Equipo visitante", "text"),
        field("book", "Casa de apuestas", "category"),
        field("side", "Selección 1 / X / 2", "category"),
        field("odds", "Cuota decimal", unit="decimal"),
        field("probability", "Probabilidad mínima de referencia", unit="probability",
              description="Mínimo de probabilidades power sin margen entre las otras casas; excluye la casa evaluada."),
        field("reference_mean", "Probabilidad media de referencia", unit="probability"),
        field("reference_sd", "Dispersión entre referencias", unit="probability"),
        field("reference_count", "Cantidad de otras casas", "integer", unit="books",
              expression="length(references)"),
        field("probability_break_even", "Probabilidad de equilibrio", unit="probability",
              expression="1 / odds"),
        field("ev", "EV estimado", unit="ratio", expression="probability * odds - 1"),
        field("edge_probability", "Diferencia sobre el equilibrio", unit="probability",
              expression="probability - 1 / odds"),
        field("own_probability", "Probabilidad sin margen de esta casa", unit="probability"),
        field("bookmaker_margin", "Margen de esta casa", unit="ratio",
              expression="sum(1 / quotes_1x2) - 1"),
        field("references", "Casas de referencia", "list"),
        field("won", "Apuesta acertada", "boolean", phase="post", formula=False),
        field("profit", "Beneficio con una unidad", unit="units", phase="post", formula=False,
              expression="won ? odds - 1 : -1"),
    ]
    labels = {"home_score": "Goles local (final)", "away_score": "Goles visitante (final)",
              "home_ht_score": "Goles local (primer tiempo)", "away_ht_score": "Goles visitante (primer tiempo)",
              "home_corners": "Córners local", "away_corners": "Córners visitante",
              "home_yellow": "Amarillas local", "away_yellow": "Amarillas visitante",
              "home_shots": "Tiros local", "away_shots": "Tiros visitante",
              "home_shots_on_target": "Tiros al arco local", "away_shots_on_target": "Tiros al arco visitante"}
    fields.extend(field(key, label, "integer", "count", "post", False)
                  for key, label in labels.items())
    return fields


def export():
    matches = load_matches()
    events, offers, leagues, sources = [], [], {}, {}
    quote_path = ROOT / "data/analysis/quote_history.jsonl"
    seen = set()
    with quote_path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["date"] < "2018-01-01" or row["id"] not in matches:
                continue
            books = valid_books(row, "h2h")
            if len(books) < 4:
                continue
            if row["id"] in seen:
                raise AssertionError(f"Duplicate event: {row['id']}")
            match = matches[row["id"]]
            index = len(events)
            event = {**row, "league": row["league_code"], "league_name": row["league"]}
            event.update({key: clean_number(match.get(key)) for key in EVENT_COLUMNS[7:]})
            events.append([event.get(key) for key in EVENT_COLUMNS])
            seen.add(row["id"])
            leagues[row["league_code"]] = row["league"]
            source = row.get("source", {})
            if source.get("url"):
                sources[source["url"]] = {key: source.get(key) for key in ("url", "sha256", "retrieved_at")}
            score = (event["home_score"], event["away_score"])
            result = outcome(score, "h2h")
            for book, own in books.items():
                refs = reference_scores(books, book)
                assert refs is not None
                for side, odd in enumerate(own["odds"]):
                    probability = refs["minimum"][side]
                    won = result == side
                    offers.append([index, book, side, odd, probability, refs["mean"][side],
                                   refs["sd"][side], refs["books"], probability*odd-1,
                                   won, float(Decimal(str(odd))-1) if won else -1,
                                   own["p"][side], own["overround"]])
    verified = verify(offers, events)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    event_info = table(OUTPUT / "workspace-events.json.gz", EVENT_COLUMNS, events)
    offer_info = offer_tables(offers, events)
    missing = {key: sum(row[i] is None for row in events)
               for i, key in enumerate(EVENT_COLUMNS) if i >= 7}
    books = Counter(row[1] for row in offers)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": "Fútbol · Partidos y cuotas 1X2 comparadas",
        "tables": {"events": event_info, "offers": offer_info},
        "counts": {"events": len(events), "offers": len(offers),
                   "offers_default_odds_range": sum(1.2 <= row[3] <= 5 for row in offers),
                   "leagues": len(leagues), "books": len(books)},
        "date_range": [min(row[1] for row in events), max(row[1] for row in events)],
        "leagues": [{"code": key, "name": leagues[key]} for key in sorted(leagues)],
        "books": [{"code": key, "name": BOOK_NAMES.get(key, key), "offers": books[key]}
                  for key in sorted(books)],
        "missing_values": {"representation": None, "events_by_column": missing},
        "sides": [{"value": 0, "label": "1 · Local"}, {"value": 1, "label": "X · Empate"},
                  {"value": 2, "label": "2 · Visitante"}],
        "fields": dictionary(),
        "periods": [{"id": "test", "label": "2022–2026", "from": "2022-01-01", "to": max(row[1] for row in events)},
                    {"id": "validation", "label": "2018–2021", "from": "2018-01-01", "to": "2021-12-31"},
                    {"id": "all", "label": "Todo el historial", "from": "2018-01-01", "to": max(row[1] for row in events)}],
        "default_formula": {"id": "ev-conservador-3", "name": "EV conservador ≥ 3%", "status": "candidata",
                            "market": "h2h", "minimum_ev": .03, "minimum_reference_books": 3,
                            "minimum_odds": 1.2, "maximum_odds": 5., "stake": 1,
                            "expression": "probability * odds - 1 >= 0.03 && reference_count >= 3 && odds >= 1.2 && odds <= 5",
                            "one_selection_per_event": True,
                            "tie_break": ["highest_ev", "book_descending", "side_ascending"],
                            "verified_results": verified},
        "method": {"market": "1X2 · Resultado final", "snapshot": "pre",
                   "power_devig": True, "target_book_excluded_from_references": True,
                   "minimum_other_real_books": 3, "quote_odds_range": None,
                   "book_overround_range": [-.02, .15],
                   "pinnacle_excluded_from": "2025-07-23", "closing_prices_used": False,
                   "probability_interpretation": "Mínimo entre referencias de mercado sin margen; estimación del modelo de referencia.",
                   "post_match_fields_are_observations": True,
                   "minimum_is_statistical_confidence_bound": False,
                   "policy_introduced_after_prior_test_inspection": True,
                   "price_timestamp_verified": False},
        "sources": {"quote_history_sha256": hashlib.sha256(quote_path.read_bytes()).hexdigest(),
                    "matches_sha256": hashlib.sha256((ROOT / "data/processed/matches.csv").read_bytes()).hexdigest(),
                    "provider": "Football-Data.co.uk", "provider_url": "https://www.football-data.co.uk/",
                    "field_definitions_url": "https://www.football-data.co.uk/notes.txt",
                    "files": list(sources.values())},
        "audit": {"exact_ledger_match": True, "selections_checked": verified["all"]["n"],
                  "reference": "research_robust_reference_ev.trades.jsonl · all_books_minimum",
                  "exporter": "scripts/export_football_workspace.py"},
    }
    (OUTPUT / "workspace.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"counts": manifest["counts"], "tables": manifest["tables"],
                      "verified_results": verified}, ensure_ascii=False))
    return manifest


if __name__ == "__main__":
    export()
