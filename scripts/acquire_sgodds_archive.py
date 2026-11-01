#!/usr/bin/env python3
"""Archive the public SGodds CSV downloads; never changes existing bot inputs."""
from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/sgodds"
AUDIT = ROOT / "data/analysis/sgodds_archive_audit.json"
PAGE = "https://sgodds.com/football/data"
META = {"ID", "Match", "Start Time", "League", "Live Bet", "Result"}
LINES = {"Ah_01_Hcap", "Ah_02_Hcap", "Htah_01_Hcap", "Htah_02_Hcap",
         "Ou_hcap", "Htou_Hcap", "Hg_01_Hcap", "Hg_02_Hcap"}
RESULT = re.compile(r"^HT:(\d+)-(\d+),\s*FT:(\d+)-(\d+)$")
FAMILIES = {
    "Ah": ("ft_asian_handicap", "FT"),
    "Htah": ("ht_asian_handicap", "HT"),
    "Ft1X2": ("ft_1x2", "FT"),
    "Htft": ("ht_ft_result", "HT+FT"),
    "Pts": ("ft_correct_score", "FT"),
    "Tg": ("ft_exact_total_goals", "FT"),
    "T1g": ("ft_first_team_to_score", "FT"),
    "Oe": ("ft_odd_even", "FT"),
    "Ht1X2": ("ht_1x2", "HT"),
    "Htpts": ("ht_correct_score", "HT"),
    "Ou": ("ft_goal_total", "FT"),
    "Htou": ("ht_goal_total", "HT"),
    "Hg": ("ft_half_goal_handicap_source_label", "FT"),
    "Bg": ("ft_btts", "FT"),
    "Htoe": ("ht_odd_even", "HT"),
    "Httg": ("ht_exact_total_goals", "HT"),
    "Htt1g": ("ht_first_team_to_score", "HT"),
    "Htbg": ("ht_btts", "HT"),
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(url, target):
    with urlopen(Request(url, headers={"User-Agent": "PersonalFootballResearch/1.0"}), timeout=40) as response:
        content = response.read(15_000_001)
        if len(content) > 15_000_000:
            raise ValueError("Unexpectedly large download")
        resolved = response.url
        modified = response.headers.get("Last-Modified")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return {"path": str(target.relative_to(ROOT)), "url": url, "resolved_url": resolved,
            "retrieved_at": now(), "last_modified": modified, "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}


def valid_odds(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 1 else None
    except (ValueError, TypeError):
        return None


def field_contract(field, row):
    """Keep the original field and distinguish line values from decimal odds."""
    if field in META or field in LINES:
        return None
    prefix, suffix = field.split("_", 1)
    family, period = FAMILIES[prefix]
    selection, line = suffix, None
    if prefix in {"Ah", "Htah", "Hg"}:
        selection = {"01": "home", "02": "away"}[suffix]
        line = row.get(prefix + "_" + suffix + "_Hcap")
    elif prefix in {"Ft1X2", "Ht1X2"}:
        selection = {"01": "home", "02": "draw", "03": "away"}[suffix]
    elif prefix == "Htft":
        outcomes = [a + "/" + b for a in ("home", "draw", "away") for b in ("home", "draw", "away")]
        selection = outcomes[int(suffix) - 1]
    elif prefix in {"Pts", "Htpts"}:
        selection = "other" if suffix == "99" else suffix[0] + "-" + suffix[1]
    elif prefix in {"Tg", "Httg"}:
        top = "09" if prefix == "Tg" else "03"
        selection = str(int(suffix)) + ("+" if suffix == top else "")
    elif prefix in {"T1g", "Htt1g"}:
        selection = {"01": "home", "02": "away", "03": "no_goal"}[suffix]
    elif prefix in {"Oe", "Htoe"}:
        selection = {"01": "odd", "02": "even"}[suffix]
    elif prefix in {"Ou", "Htou"}:
        selection = {"01": "over", "02": "under"}[suffix]
        line = row.get("Ou_hcap" if prefix == "Ou" else "Htou_Hcap")
    elif prefix in {"Bg", "Htbg"}:
        selection = {"01": "yes", "02": "no"}[suffix]
    return {"market": family, "period": period, "selection": selection, "line_source": line,
            "can_evaluate_from_ht_ft_score": prefix not in {"T1g", "Htt1g", "Hg"}}


def load_rows(record):
    path = ROOT / record["path"]
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != record["sha256"]:
        raise ValueError("Raw archive hash mismatch: " + str(path))
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if not META <= set(reader.fieldnames or []):
        raise ValueError("Unexpected CSV schema: " + str(path))
    return list(reader)


def reconcile_epl(files):
    """Check supplied results against the existing two EPL season CSVs."""
    aliases = {"Manchester City": "Man City", "Manchester Utd": "Man United",
               "Nottingham": "Nott'm Forest", "Wolverhampton": "Wolves", "Hull City": "Hull"}
    reference, sources = [], []
    for season in ("2526", "2627"):
        path = ROOT / "data/raw/football" / (season + "_E0.csv")
        if not path.exists():
            continue
        content = path.read_bytes()
        sources.append({"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(content).hexdigest()})
        for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
            if not row.get("FTHG") or not row.get("FTAG"):
                continue
            date = None
            for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                try:
                    date = datetime.strptime(row["Date"], fmt).date()
                    break
                except ValueError:
                    pass
            if date:
                reference.append((date, row))
    counts, mismatches = Counter(), []
    for record in files:
        for row in load_rows(record):
            score = RESULT.fullmatch(row["Result"].strip())
            if row["League"] != "English Premier" or not score:
                continue
            counts["source_settled_rows"] += 1
            home, away = [aliases.get(t, t) for t in row["Match"].split(" vs ")]
            date = datetime.fromisoformat(row["Start Time"]).date()
            candidates = [r for d, r in reference if abs((d - date).days) <= 1
                          and r["HomeTeam"] == home and r["AwayTeam"] == away]
            if len(candidates) != 1:
                counts["not_uniquely_matched"] += 1
                continue
            counts["uniquely_matched"] += 1
            expected = [candidates[0].get(k, "") for k in ("HTHG", "HTAG", "FTHG", "FTAG")]
            supplied = list(score.groups())
            if expected == supplied:
                counts["matching_ht_and_ft_scores"] += 1
            else:
                counts["mismatching_scores"] += 1
                mismatches.append({"match": row["Match"], "start_time": row["Start Time"],
                                   "source_scores": supplied, "reference_scores": expected})
    return {"counts": dict(counts), "reference_files": sources, "aliases": aliases,
            "date_tolerance_days": 1, "mismatches": mismatches,
            "scope": "Checks results only; does not verify historical quote timing, execution, settlement rules or other leagues."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if AUDIT.exists() and not args.refresh:
        prior = json.loads(AUDIT.read_text())
        files, docs = prior["files"], prior["documents"]
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        folder = RAW / stamp
        docs = [fetch(PAGE, folder / "data.html")]
        html = (ROOT / docs[0]["path"]).read_text()
        links = sorted(set(urljoin(PAGE, h) for h in re.findall(r'href=["\']([^"\']+\.csv(?:\?[^"\']*)?)["\']', html)))
        if not links:
            raise ValueError("No CSV download links found on source page")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            files = list(pool.map(lambda u: fetch(u, folder / u.split("/")[-1]), links))
        for page in ("help", "about", "terms-conditions"):
            docs.append(fetch("https://sgodds.com/" + page, folder / (page + ".html")))

    totals, markets, historical_markets, fields = Counter(), Counter(), Counter(), Counter()
    leagues, identities = {}, Counter()
    invalid_examples, other_results, dates = [], Counter(), []
    for record in files:
        rows = load_rows(record)
        league_counts = Counter()
        for row in rows:
            totals["rows"] += 1
            league_counts[row["League"]] += 1
            identities[(row["League"], row["Start Time"], row["Match"])] += 1
            dates.append(row["Start Time"])
            parsed = RESULT.fullmatch(row["Result"].strip())
            state = "settled_with_ht_ft" if parsed else "pending_or_other"
            totals[state] += 1
            if parsed:
                hh, ha, fh, fa = map(int, parsed.groups())
                totals["score_inconsistency_rows"] += int(hh > fh or ha > fa)
            else:
                other_results[row["Result"]] += 1
            for field, raw in row.items():
                contract = field_contract(field, row)
                if contract is None:
                    continue
                if valid_odds(raw) is not None:
                    totals["valid_decimal_price_observations"] += 1
                    markets[contract["market"]] += 1
                    fields[field] += 1
                    if parsed:
                        totals["settled_valid_decimal_price_observations"] += 1
                        historical_markets[contract["market"]] += 1
                elif raw.strip():
                    totals["nonempty_invalid_odds"] += 1
                    if len(invalid_examples) < 12:
                        invalid_examples.append({"match": row["Match"], "field": field, "value": raw})
        record["rows"] = len(rows)
        record["columns"] = len(rows[0]) if rows else 0
        leagues.update(league_counts)
    totals["unique_match_identities"] = len(identities)
    totals["duplicate_identity_rows"] = sum(c - 1 for c in identities.values())
    report = {
        "provider": "SGodds", "upstream_bookmaker": "Singapore Pools (SGodds help-page attribution)",
        "audited_at": now(), "cost": 0, "account_required": False,
        "files": files, "documents": docs, "totals": dict(totals), "leagues": leagues,
        "source_start_time_min": min(dates), "source_start_time_max": max(dates),
        "markets_price_observations": dict(markets),
        "settled_markets_price_observations": dict(historical_markets),
        "valid_price_counts_by_field": dict(fields), "other_result_states": dict(other_results),
        "invalid_odds_examples": invalid_examples,
        "epl_result_reconciliation": reconcile_epl(files),
        "limitations": [
            "Prices are labelled opening odds by the download page; exact individual quote timestamps are not provided or independently verified.",
            "Start Time is preserved as supplied; source timezone has not been independently verified.",
            "Live Bet is a source match-availability flag, not evidence that these opening prices were in-play.",
            "First-team-to-score prices have no event sequence in this archive and cannot generally be settled from HT/FT scores.",
            "No player-specific scorer, shots, corner or card odds in these CSV files.",
            "SGodds documents possible line inconsistencies in its past display when Singapore Pools changes handicap/total lines; verify original line-price pairing before ROI claims.",
            "Personal local research archive; no explicit open redistribution licence asserted.",
        ],
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"audit": str(AUDIT), "totals": report["totals"], "leagues": leagues,
                      "market_families": len(markets)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
