#!/usr/bin/env python3
"""Download auditable free sports data. Python 3.10+, standard library only.

No scrape bypass, account creation, bookmaker execution, or paid API calls.
Raw archives stay local; the manifest preserves source URLs and SHA-256 hashes.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import threading
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
PROCESSED = ROOT / "data/processed"
MANIFEST = ROOT / "data/manifest.json"
LEAGUES = {
    "E0": "England Premier League", "E1": "England Championship",
    "SP1": "Spain La Liga", "I1": "Italy Serie A", "D1": "Germany Bundesliga",
    "F1": "France Ligue 1", "N1": "Netherlands Eredivisie",
    "P1": "Portugal Primeira Liga", "B1": "Belgium First Division A",
    "T1": "Turkey Super Lig", "SC0": "Scotland Premiership",
}
BOOKMAKERS = {"B365": "Bet365", "BFD": "Betfred", "BV": "BetVictor", "BW": "Bwin",
              "PP": "Paddy Power", "SKB": "Sky Bet", "BFE": "Betfair Exchange", "Avg": "Market average"}
BASE_FIELDS = ["id", "sport", "league", "season", "date", "home_team", "away_team",
               "home_score", "away_score", "home_odds", "draw_odds", "away_odds", "odds_source"]
EXTRA_FIELDS = ["league_code", "source", "odds_snapshot", "over25_odds", "under25_odds", "odds25_source",
                "home_ht_score", "away_ht_score", "home_corners", "away_corners", "home_yellow", "away_yellow",
                "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target", "neutral_venue"]
LOCK = threading.Lock()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def csv_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Undecodable data")


def numeric(v, *, odds=False):
    try:
        f = float(v)
        if not math.isfinite(f) or (odds and f <= 1):
            return ""
        return f
    except (ValueError, TypeError):
        return ""


def date_iso(text: str) -> str:
    for form in ("%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), form).date().isoformat()
        except (ValueError, AttributeError):
            continue
    return ""


def match_id(sport, league, date, home, away):
    return hashlib.sha256("|".join([sport, league, date, home, away]).encode()).hexdigest()[:20]


class Downloader:
    def __init__(self, refresh=False):
        self.refresh = refresh
        self.records = {}
        self.errors = []
        self.previous = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
        self.prior_files = {v["path"]: v for v in self.previous.get("files", [])}

    def fetch(self, url, relative, provider):
        path = ROOT / relative
        try:
            cached = path.exists() and not self.refresh
            if cached:
                data = path.read_bytes()
                retrieved = self.prior_files.get(relative, {}).get("retrieved_at", datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
                modified = self.prior_files.get(relative, {}).get("last_modified")
            else:
                request = Request(url, headers={"User-Agent": "KrakenEdge-Research/0.1 (personal sports analytics; no betting execution)"})
                with urlopen(request, timeout=45) as response:
                    data = response.read()
                    modified = response.headers.get("Last-Modified")
                retrieved = utcnow()
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix(path.suffix + ".part")
                temp.write_bytes(data)
                temp.replace(path)
            rec = {"path": relative, "provider": provider, "url": url, "retrieved_at": retrieved,
                   "last_modified": modified, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if relative.endswith(".csv"):
                rec["rows_raw"] = sum(1 for _ in csv.DictReader(io.StringIO(csv_text(data))))
            with LOCK:
                self.records[relative] = rec
            return data, rec
        except Exception as exc:
            with LOCK:
                self.errors.append({"url": url, "path": relative, "error": str(exc), "checked_at": utcnow()})
            return None, None


def pick_football_odds(row, *, closing=False):
    for prefix in ("B365", "Avg", "PS"):
        if prefix == "PS" and date_iso(row.get("Date", "")) >= "2025-07-23":
            continue
        suffix = "C" if closing else ""
        vals = [numeric(row.get(prefix + suffix + side), odds=True) for side in ("H", "D", "A")]
        if all(v != "" for v in vals):
            return vals + [f"football-data.co.uk:{prefix}:{'closing' if closing else 'pre-closing'}"]
    return ["", "", "", ""]


def pick_ou_odds(row):
    for prefix in ("B365", "Avg", "P"):
        if prefix == "P" and date_iso(row.get("Date", "")) >= "2025-07-23":
            continue
        vals = [numeric(row.get(prefix + side), odds=True) for side in (">2.5", "<2.5")]
        if all(v != "" for v in vals):
            return vals + [f"football-data.co.uk:{prefix}:pre-closing"]
    return ["", "", ""]


def football_row(row, code, season, *, extra=False):
    date = date_iso(row.get("Date", ""))
    home, away = row.get("Home" if extra else "HomeTeam", ""), row.get("Away" if extra else "AwayTeam", "")
    hs, aws = numeric(row.get("HG" if extra else "FTHG")), numeric(row.get("AG" if extra else "FTAG"))
    if not date or not home or not away or hs == "" or aws == "" or date > datetime.now(timezone.utc).date().isoformat():
        return None
    odds = pick_football_odds(row, closing=extra)
    ou = pick_ou_odds(row) if not extra else ["", "", ""]
    result = dict(zip(BASE_FIELDS, [match_id("football", code, date, home, away), "football", LEAGUES.get(code, code),
                                   row.get("Season", season) if extra else season, date, home, away, int(hs), int(aws), *odds]))
    result.update({"league_code": code, "source": "football-data.co.uk", "odds_snapshot": "closing" if extra else "pre-closing",
                   "over25_odds": ou[0], "under25_odds": ou[1], "odds25_source": ou[2], "neutral_venue": "unknown"})
    for source, target in [("HTHG", "home_ht_score"), ("HTAG", "away_ht_score"), ("HC", "home_corners"),
                           ("AC", "away_corners"), ("HY", "home_yellow"), ("AY", "away_yellow"),
                           ("HS", "home_shots"), ("AS", "away_shots"), ("HST", "home_shots_on_target"), ("AST", "away_shots_on_target")]:
        result[target] = numeric(row.get(source))
    return result


def download_football(downloader, first_year=2015, last_year=2026):
    tasks = []
    for year in range(first_year, last_year + 1):
        code = f"{year % 100:02d}{(year + 1) % 100:02d}"
        for league in LEAGUES:
            tasks.append((f"https://www.football-data.co.uk/mmz4281/{code}/{league}.csv", f"data/raw/football/{code}_{league}.csv", league, f"{year}/{year + 1}"))
    for league in ("ARG", "BRA", "USA", "MEX"):
        tasks.append((f"https://www.football-data.co.uk/new/{league}.csv", f"data/raw/football/{league}.csv", league, ""))
    LEAGUES.update({"ARG": "Argentina Liga Profesional", "BRA": "Brazil Serie A", "USA": "USA MLS", "MEX": "Mexico Liga MX"})
    results = []

    def process(task):
        url, path, league, season = task
        data, rec = downloader.fetch(url, path, "football-data.co.uk")
        if data is None:
            return []
        rows = []
        for row in csv.DictReader(io.StringIO(csv_text(data))):
            normalized = football_row(row, league, season, extra=not season)
            if normalized:
                rows.append(normalized)
        rec["rows_normalized"] = len(rows)
        return rows

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for rows in pool.map(process, tasks):
            results.extend(rows)
    return results


def download_basketball(downloader):
    data, rec = downloader.fetch("https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/nbaallelo.csv",
                                 "data/raw/basketball/nbaallelo.csv", "FiveThirtyEight")
    if data is None:
        return []
    results = []
    for row in csv.DictReader(io.StringIO(csv_text(data))):
        if row.get("_iscopy") != "0" or row.get("lg_id") != "NBA":
            continue
        try:
            date = datetime.strptime(row.get("date_game", ""), "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        if not date or date < "1990-01-01":
            continue
        home, away = row["team_id"], row["opp_id"]
        hs, aws = row["pts"], row["opp_pts"]
        if row["game_location"] == "A":
            home, away, hs, aws = away, home, aws, hs
        result = {"id": "nba-" + row["game_id"], "sport": "basketball", "league": "NBA", "season": row["year_id"], "date": date,
                  "home_team": home, "away_team": away, "home_score": int(hs), "away_score": int(aws), "home_odds": "",
                  "draw_odds": "", "away_odds": "", "odds_source": "", "league_code": "NBA", "source": "FiveThirtyEight/Basketball-Reference",
                  "odds_snapshot": "unavailable", "neutral_venue": str(row["game_location"] == "N").lower()}
        results.append(result)
    rec["rows_normalized"] = len(results)
    return results


def download_fixtures(downloader):
    # Fixtures are intentionally refreshed even when the historical archive is cached.
    prior = downloader.refresh
    downloader.refresh = True
    data, rec = downloader.fetch("https://www.football-data.co.uk/fixtures.csv", "data/raw/football/fixtures.csv", "football-data.co.uk")
    downloader.refresh = prior
    if data is None:
        return [], []
    fixtures, offers = [], []
    for row in csv.DictReader(io.StringIO(csv_text(data))):
        date, home, away, code = date_iso(row.get("Date", "")), row.get("HomeTeam", ""), row.get("AwayTeam", ""), row.get("Div", "")
        if not date or not home or not away:
            continue
        ident = match_id("football", code, date, home, away)
        o = pick_football_odds(row)
        ou = pick_ou_odds(row)
        f = {"id": ident, "sport": "football", "league": LEAGUES.get(code, code), "league_code": code, "date": date,
             "time": row.get("Time", ""), "home_team": home, "away_team": away, "home_odds": o[0], "draw_odds": o[1], "away_odds": o[2],
             "odds_source": o[3], "over25_odds": ou[0], "under25_odds": ou[1], "odds25_source": ou[2],
             "source": rec["url"], "retrieved_at": rec["retrieved_at"], "source_last_modified": rec["last_modified"] or "",
             "kickoff_reliable": "false", "kickoff_timezone": "unknown", "odds_timestamp": "",
             "snapshot_warning": "CSV periódico; zona horaria y timestamp de cada cuota no confirmados"}
        fixtures.append(f)
        for prefix, title in BOOKMAKERS.items():
            for suffix, market, line in [("", "h2h", ""), ("OU", "totals", "2.5")]:
                outcomes = ("H", "D", "A") if not suffix else (">2.5", "<2.5")
                vals = [numeric(row.get(prefix + outcome), odds=True) for outcome in outcomes]
                if not all(v != "" for v in vals):
                    continue
                for outcome, odds in zip(outcomes, vals):
                    offers.append({"event_id": ident, "sport": "football", "league_code": code, "date": date, "time": row.get("Time", ""),
                                   "home_team": home, "away_team": away, "bookmaker": title, "bookmaker_key": prefix,
                                   "market": market, "selection": {"H": "home", "D": "draw", "A": "away", ">2.5": "over", "<2.5": "under"}[outcome],
                                   "line": line, "odds": odds, "retrieved_at": rec["retrieved_at"], "odds_timestamp": "",
                                   "kickoff_reliable": "false", "source": rec["url"], "snapshot_type": "periodic-csv",
                                   "is_executable_quote": "false", "is_market_average": str(prefix == "Avg").lower()})
    rec["rows_normalized"] = len(fixtures)
    return fixtures, offers


def download_events(downloader):
    base = "https://raw.githubusercontent.com/hudl/open-data/master/data"
    data, rec = downloader.fetch(base + "/matches/43/106.json", "data/raw/statsbomb/worldcup2022_matches.json", "StatsBomb Open Data")
    if data is None:
        return []
    matches = json.loads(data)

    def process(match):
        mid = match["match_id"]
        events_bytes, event_rec = downloader.fetch(f"{base}/events/{mid}.json", f"data/raw/statsbomb/events/{mid}.json", "StatsBomb Open Data")
        if events_bytes is None:
            return None
        events = json.loads(events_bytes)
        # 90-minute markets exclude extra time and penalty shootouts.
        goals = [e for e in events if e.get("period", 0) <= 2 and
                 ((e.get("type", {}).get("name") == "Shot" and e.get("shot", {}).get("outcome", {}).get("name") == "Goal")
                  or e.get("type", {}).get("name") == "Own Goal Against")]
        goals.sort(key=lambda e: (e.get("period", 0), e.get("index", 0)))
        first = goals[0] if goals else None
        home = match["home_team"]["home_team_name"]
        away = match["away_team"]["away_team_name"]
        scoring_team = first.get("team", {}).get("name", "") if first else "none"
        own_goal = bool(first and first.get("type", {}).get("name") == "Own Goal Against")
        if own_goal:
            scoring_team = away if scoring_team == home else home
        return {"id": f"statsbomb-{mid}", "sport": "football", "league": "FIFA World Cup", "season": "2022", "date": match["match_date"],
                "home_team": home, "away_team": away, "first_goal_team": scoring_team,
                "first_goal_player": first.get("player", {}).get("name", "") if first and not own_goal else "",
                "first_goal_minute": first.get("minute", "") if first else "", "first_goal_second": first.get("second", "") if first else "",
                "first_goal_own_goal": str(own_goal).lower(), "regulation_goal_count": len(goals), "periods_included": "1,2",
                "source": f"https://github.com/hudl/open-data/blob/master/data/events/{mid}.json", "attribution": "StatsBomb Open Data",
                "betting_odds_available": "false", "model_validation_status": "dataset_only_not_validated"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = [v for v in pool.map(process, matches) if v]
    rec["rows_normalized"] = len(results)
    return results


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Refresh raw archives instead of using local cache")
    parser.add_argument("--first-year", type=int, default=2015)
    parser.add_argument("--last-year", type=int, default=2026)
    parser.add_argument("--skip-events", action="store_true", help="Skip StatsBomb 2022 World Cup event files")
    parser.add_argument("--fixtures-only", action="store_true", help="Refresh upcoming fixtures without downloading histories")
    args = parser.parse_args()
    downloader = Downloader(args.refresh or args.fixtures_only)
    matches = []
    if not args.fixtures_only:
        matches.extend(download_football(downloader, args.first_year, args.last_year))
        matches.extend(download_basketball(downloader))
        unique = {row["id"]: row for row in matches}
        matches = sorted(unique.values(), key=lambda r: (r["date"], r["id"]))
        write_csv(PROCESSED / "matches.csv", matches, BASE_FIELDS + EXTRA_FIELDS)
        print(f"Historical matches: {len(matches):,}", flush=True)
    fixtures, offers = download_fixtures(downloader)
    write_csv(PROCESSED / "fixtures.csv", fixtures)
    write_csv(PROCESSED / "fixtures_odds.csv", offers)
    print(f"Upcoming fixtures: {len(fixtures):,}; quoted selections: {len(offers):,}", flush=True)
    events = []
    if not args.skip_events and not args.fixtures_only:
        events = download_events(downloader)
        write_csv(PROCESSED / "first_goals.csv", events)
        print(f"First-goal event histories: {len(events):,}", flush=True)
    old_files = downloader.prior_files
    old_files.update(downloader.records)
    summary = {}
    for path in sorted(PROCESSED.glob("*.csv")):
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        dates = sorted(r.get("date", "") for r in rows if r.get("date"))
        summary[path.stem] = {"rows": len(rows), "from": dates[0] if dates else None, "to": dates[-1] if dates else None,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if path.stem == "matches":
            summary[path.stem]["sports"] = {sport: sum(r["sport"] == sport for r in rows) for sport in sorted({r["sport"] for r in rows})}
            summary[path.stem]["with_1x2_odds"] = sum(bool(r.get("home_odds")) for r in rows)
            summary[path.stem]["with_ou25_odds"] = sum(bool(r.get("over25_odds")) for r in rows)
            summary[path.stem]["leagues"] = sorted({r["league"] for r in rows})
    atomic_json(MANIFEST, {"generated_at": utcnow(), "budget": "free-only", "derived": summary,
                           "files": sorted(old_files.values(), key=lambda v: v["path"]), "errors": downloader.errors,
                           "notes": ["No bookmaker account was created; no bets placed.",
                                     "Raw Football-Data and StatsBomb data is downloaded for local research; preserve original terms and attribution.",
                                     "Each odds record is an observed historical/periodic price, never a guarantee of execution.",
                                     "NBA archive ends in 2015 and contains no bookmaker odds."]})
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if downloader.errors:
        print(f"Download failures recorded in manifest: {len(downloader.errors)}", flush=True)


if __name__ == "__main__":
    main()
