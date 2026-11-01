#!/usr/bin/env python3
"""Import explicitly downloadable Retrosheet MLB game logs, without bookmaker odds.

MLB StatsAPI bulk downloads and NHL website/API scraping are intentionally disabled:
the published permission terms have not authorized this project's bulk collection.
Retrosheet explicitly offers annual ZIP downloads and permits reuse with attribution.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/manifest.json"
DATA = ROOT / "data/processed"
ATTRIBUTION = ('The information used here was obtained free of charge from and is copyrighted by Retrosheet. '
               'Interested parties may contact Retrosheet at "www.retrosheet.org".')
TEAM_NAMES = {
    "ANA": "Los Angeles Angels", "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves",
    "ATH": "Athletics", "OAK": "Athletics", "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox",
    "CHA": "Chicago White Sox", "CHN": "Chicago Cubs", "CHC": "Chicago Cubs", "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians", "COL": "Colorado Rockies", "DET": "Detroit Tigers", "HOU": "Houston Astros",
    "KCA": "Kansas City Royals", "LAN": "Los Angeles Dodgers", "MIA": "Miami Marlins", "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins", "NYA": "New York Yankees", "NYN": "New York Mets", "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates", "SDN": "San Diego Padres", "SEA": "Seattle Mariners", "SFN": "San Francisco Giants",
    "SLN": "St. Louis Cardinals", "TBA": "Tampa Bay Rays", "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays",
    "WAS": "Washington Nationals",
}
FIELDS = ["id", "sport", "league", "season", "date", "home_team", "away_team", "home_score", "away_score",
          "home_odds", "draw_odds", "away_odds", "odds_source", "league_code", "source", "odds_snapshot", "neutral_venue",
          "outcome_scope", "competition_phase", "game_number", "original_date", "completion_date", "innings_played",
          "outs_played", "home_team_source_code", "away_team_source_code", "source_url"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def iso_date(value):
    return datetime.strptime(value, "%Y%m%d").date().isoformat()


def inning_count(linescore):
    """Retrosheet '(10)' is one inning, 'x' is an unbatted inning."""
    tokens = re.findall(r"\(\d+\)|[0-9xX]", linescore)
    return len(tokens) if tokens else ""


def normalize(row, source_url):
    if len(row) < 21:
        return None, "malformed"
    try:
        original_date = iso_date(row[0])
        completion = row[13].split(",", 1)[0] if row[13] else ""
        completion_date = iso_date(completion) if completion else original_date
        home_score, away_score = int(row[10]), int(row[9])
        outs = int(row[11]) if row[11] else ""
    except (ValueError, IndexError):
        return None, "malformed"
    if row[14]:
        return None, "forfeit_or_no_decision"
    if home_score == away_score:
        return None, "tie_no_binary_outcome"
    if home_score < 0 or away_score < 0 or completion_date < original_date:
        return None, "invalid_score_or_completion_date"
    home_code, away_code = row[6], row[3]
    if home_code not in TEAM_NAMES or away_code not in TEAM_NAMES:
        raise ValueError(f"Unknown team code: {home_code}/{away_code}; update identity mapping explicitly")
    innings = max([n for n in (inning_count(row[19]), inning_count(row[20])) if isinstance(n, int)], default="")
    ident = f"retrosheet-{row[0]}-{home_code}-{away_code}-{row[1]}"
    return {"id": ident, "sport": "baseball", "league": "MLB", "season": row[0][:4], "date": completion_date,
            "home_team": TEAM_NAMES[home_code], "away_team": TEAM_NAMES[away_code], "home_score": home_score, "away_score": away_score,
            "home_odds": "", "draw_odds": "", "away_odds": "", "odds_source": "", "league_code": "MLB",
            "source": "Retrosheet", "odds_snapshot": "unavailable", "neutral_venue": "unknown",
            "outcome_scope": "final_including_extra_innings", "competition_phase": "regular_season", "game_number": row[1],
            "original_date": original_date, "completion_date": completion_date, "innings_played": innings,
            "outs_played": outs, "home_team_source_code": home_code, "away_team_source_code": away_code, "source_url": source_url}, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-year", type=int, default=2021)
    parser.add_argument("--last-year", type=int, default=2025, help="Latest annual game-log ZIP advertised by Retrosheet is 2025")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if not (1871 <= args.first_year <= args.last_year <= 2025):
        parser.error("Choose published Retrosheet game-log years between 1871 and 2025; never fabricate 2026 availability")
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"derived": {}, "files": [], "errors": []}
    files = {r["path"]: r for r in manifest.get("files", [])}
    rows, excluded, new_records = [], {}, []
    for year in range(args.first_year, args.last_year + 1):
        url = f"https://www.retrosheet.org/gamelogs/gl{year}.zip"
        relative = f"data/raw/retrosheet/gl{year}.zip"
        path = ROOT / relative
        cached = path.exists() and not args.refresh
        try:
            if cached:
                content = path.read_bytes()
                retrieved_at = files.get(relative, {}).get("retrieved_at", datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
                modified = files.get(relative, {}).get("last_modified")
            else:
                req = Request(url, headers={"User-Agent": "WagerLab-PersonalResearch/0.1"})
                with urlopen(req, timeout=45) as response:
                    content = response.read()
                    modified = response.headers.get("Last-Modified")
                retrieved_at = now()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            archive = ZipFile(io.BytesIO(content))
            members = [n for n in archive.namelist() if n.upper().endswith(".TXT") and f"GL{year}" in n.upper()]
            if len(members) != 1:
                raise ValueError(f"Expected one GL{year}.TXT file, got {members}")
            raw_rows = list(csv.reader(io.StringIO(archive.read(members[0]).decode("utf-8-sig"))))
            count = 0
            for raw in raw_rows:
                normalized, reason = normalize(raw, url)
                if normalized:
                    rows.append(normalized)
                    count += 1
                else:
                    excluded[reason] = excluded.get(reason, 0) + 1
            record = {"path": relative, "provider": "Retrosheet", "url": url, "retrieved_at": retrieved_at,
                      "last_modified": modified, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                      "rows_raw": len(raw_rows), "rows_normalized": count, "license_url": "https://www.retrosheet.org/notice.txt"}
            files[relative] = record
            new_records.append(record)
            print(f"MLB {year}: {count:,} final regular-season games", flush=True)
        except Exception as exc:
            # Fail before publishing a partially complete normalized dataset.
            manifest.setdefault("errors", []).append({"url": url, "path": relative, "error": str(exc), "checked_at": now()})
            atomic_json(MANIFEST, manifest)
            raise SystemExit(f"Retrosheet import stopped; previous matches.csv preserved. {exc}")
    unique = {r["id"]: r for r in rows}
    if len(unique) != len(rows):
        raise SystemExit("Duplicate Retrosheet game IDs: import stopped without changing matches.csv")
    rows.sort(key=lambda r: (r["date"], r["id"]))
    write_csv(DATA / "baseball.csv", rows, FIELDS)
    existing_path = DATA / "matches.csv"
    if existing_path.exists():
        with existing_path.open(encoding="utf-8") as source:
            reader = csv.DictReader(source)
            existing_fields = list(reader.fieldnames or [])
            existing_rows = [r for r in reader if r.get("source") != "Retrosheet"]
    else:
        existing_fields, existing_rows = [], []
    combined = existing_rows + rows
    if len({r["id"] for r in combined}) != len(combined):
        raise SystemExit("Duplicate combined game IDs: import stopped without changing matches.csv")
    combined.sort(key=lambda r: (r["date"], r["id"]))
    combined_fields = existing_fields + [f for f in FIELDS if f not in existing_fields]
    write_csv(existing_path, combined, combined_fields)
    (ROOT / "data/RETROSHEET_ATTRIBUTION.txt").write_text(ATTRIBUTION + "\n", encoding="utf-8")
    atomic_json(DATA / "baseball_team_aliases.json", {"source": "Retrosheet", "mapping": TEAM_NAMES,
                                                     "note": "Franchise renames normalized to current names solely as stable identifiers, not predictive features"})
    dates = [r["date"] for r in combined]
    manifest.setdefault("derived", {})["matches"] = {
        "rows": len(combined), "from": min(dates), "to": max(dates), "sha256": hashlib.sha256(existing_path.read_bytes()).hexdigest(),
        "sports": {s: sum(r["sport"] == s for r in combined) for s in sorted({r["sport"] for r in combined})},
        "with_1x2_odds": sum(bool(r.get("home_odds")) for r in combined),
        "with_ou25_odds": sum(bool(r.get("over25_odds")) for r in combined), "leagues": sorted({r["league"] for r in combined})}
    manifest["derived"]["baseball"] = {
        "rows": len(rows), "from": min(r["date"] for r in rows), "to": max(r["date"] for r in rows),
        "sha256": hashlib.sha256((DATA / "baseball.csv").read_bytes()).hexdigest(),
        "seasons": list(range(args.first_year, args.last_year + 1)), "phase": "regular_season", "odds_available": False,
        "suspended_games_dated_at_completion": sum(r["date"] != r["original_date"] for r in rows),
        "doubleheader_games": sum(r["game_number"] != "0" for r in rows),
        "games_at_least_10_innings": sum(isinstance(r["innings_played"], int) and r["innings_played"] >= 10 for r in rows),
        "excluded": excluded, "attribution": ATTRIBUTION}
    manifest["files"] = sorted(files.values(), key=lambda r: r["path"])
    manifest["generated_at"] = now()
    manifest["source_policies"] = {
        **manifest.get("source_policies", {}),
        "MLB_StatsAPI": {"status": "bulk_permission_required", "terms": "https://gdx.mlb.com/components/copyright.txt", "historical_download_performed": False},
        "NHL_API": {"status": "permission_required_and_http403", "terms": "https://www.nhl.com/info/terms-of-service", "historical_download_performed": False},
        "Retrosheet": {"status": "connected_explicit_download_permission", "terms": "https://www.retrosheet.org/notice.txt", "attribution": ATTRIBUTION}}
    atomic_json(MANIFEST, manifest)
    print(json.dumps(manifest["derived"]["baseball"], ensure_ascii=False, indent=2), flush=True)
    print(f"Updated canonical matches atomically: {len(combined):,}; no invented odds or postgame predictors.", flush=True)


if __name__ == "__main__":
    main()
