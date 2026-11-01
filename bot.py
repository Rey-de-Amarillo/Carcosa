#!/usr/bin/env python3
"""Kraken Edge observer: bounded daily odds collection, never bet execution.

python3 bot.py --once                  # default; at most 12 sports per UTC date
python3 bot.py --watch                 # repeat no more often than every 24 hours
python3 bot.py --watch --refresh-data  # also refresh current football archives
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from backend import storage
from backend.providers import OddsAPI
from backend.scanner import save_scan


ROOT = Path(__file__).resolve().parent
WATCHLIST = ("soccer_argentina_primera_division", "soccer_brazil_campeonato",
             "soccer_epl", "basketball_nba")
DAILY_LIMIT = 12
ROTATION_SIZE = 8
MINIMUM_INTERVAL_HOURS = 24
EXTRA_FOOTBALL = {"ARG", "BRA", "USA", "MEX"}


def atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_error(exc: Exception) -> dict:
    # Exception messages can contain HTTP request URLs and private API keys.
    result = {"type": type(exc).__name__}
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        result["http_status"] = code
    return result


@contextmanager
def single_instance(path: Path):
    """Use a kernel lock, not an unreliable test for whether a PID file exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Ya hay una instancia del bot en ejecución.") from None
        lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def select_sports(catalog: list[dict], day: date) -> list[str]:
    """Four priorities plus eight rotating sports, filtered by provider flags."""
    active = {item["key"] for item in catalog
              if isinstance(item, dict) and item.get("active") is True
              and item.get("has_outrights") is False and isinstance(item.get("key"), str)}
    priority = [sport for sport in WATCHLIST if sport in active]
    pool = sorted(active - set(WATCHLIST))
    if pool:
        offset = (day.toordinal() * ROTATION_SIZE) % len(pool)
        rotated = (pool[offset:] + pool[:offset])[:ROTATION_SIZE]
    else:
        rotated = []
    return (priority + rotated)[:DAILY_LIMIT]


def current_season_start(day: date) -> int:
    return day.year if day.month >= 7 else day.year - 1


@contextmanager
def preserve_normalized_outputs(root: Path):
    """Restore the last coherent normalized/report snapshot on pipeline failure.

    Newly downloaded raw files are retained. Their fresh source metadata is
    already persisted before entering this context; derived data rolls back.
    """
    runtime = root / "data/runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    candidates = [root / "data/manifest.json", root / "app/data/report.json",
                  root / "app/data/history.jsonl.gz", root / "data/processed/decisions.jsonl",
                  root / "data/processed/baseball_team_aliases.json",
                  root / "app/data/research.json", root / "data/analysis/research_v2.json",
                  root / "data/analysis/selection_v2.json", root / "data/analysis/integration_v2.jsonl",
                  root / "data/analysis/portfolio_v2.json", root / "config/selected_model_v2.json",
                  root / "data/runtime/prospective_v2.json"]
    candidates += list((root / "data/processed").glob("*.csv"))
    candidates = list(dict.fromkeys(candidates))
    initial_csv = set((root / "data/processed").glob("*.csv"))
    with tempfile.TemporaryDirectory(prefix="bot-refresh-", dir=runtime) as directory:
        backups = {}
        for index, path in enumerate(candidates):
            if path.exists():
                backup = Path(directory) / str(index)
                shutil.copy2(path, backup); backups[path] = backup
        try:
            yield
        except Exception:
            for path in candidates:
                if path in backups:
                    temporary = path.with_suffix(path.suffix+".restore")
                    shutil.copy2(backups[path], temporary); temporary.replace(path)
                elif path.exists():
                    path.unlink()
            for path in set((root / "data/processed").glob("*.csv")) - initial_csv:
                path.unlink()
            raise


def _run_stage(root: Path, name: str, arguments: list[str], runner) -> None:
    result = runner([sys.executable, str(root / "scripts" / name), *arguments],
                    cwd=str(root), capture_output=True, text=True, check=False)
    if result.returncode:
        # Do not print captured subprocess output, which could contain secrets
        # after future provider integrations. The stage and exit code suffice.
        raise RuntimeError(f"Falló {name} (código {result.returncode}).")


def refresh_histories(root: Path, day: date, runner=None) -> dict:
    """Refresh only current football raw files; rebuild other data from cache."""
    from scripts import download_history
    runner = runner or subprocess.run
    before = file_hash(root / "data/processed/matches.csv")
    season = current_season_start(day)
    downloader = download_history.Downloader(refresh=True)
    previous_leagues = download_history.LEAGUES
    # download_football appends the four calendar-season leagues to its global
    # map. Exclude them from the European URL loop on repeated bot cycles.
    download_history.LEAGUES = {key:value for key,value in previous_leagues.items() if key not in EXTRA_FOOTBALL}
    try:
        download_history.download_football(downloader, first_year=season, last_year=season)
    finally:
        download_history.LEAGUES = previous_leagues
    manifest_path = root / "data/manifest.json"
    manifest = read_json(manifest_path, {})
    records = {item["path"]:item for item in manifest.get("files", [])}
    records.update(downloader.records)
    manifest["files"] = sorted(records.values(), key=lambda item:item["path"])
    # These public-download errors contain no provider API key. The bot's audit
    # summary records only counts and typed errors, never exception messages.
    manifest["errors"] = list(manifest.get("errors", [])) + list(downloader.errors)
    atomic_json(manifest_path, manifest)
    with preserve_normalized_outputs(root):
        _run_stage(root, "download_history.py", ["--skip-events", "--last-year", str(season)], runner)
        _run_stage(root, "download_us_sports.py", [], runner)
        after = file_hash(root / "data/processed/matches.csv")
        if after is None:
            raise RuntimeError("La normalización no produjo matches.csv.")
        changed = before != after
        rebuilt = changed or not (root / "app/data/report.json").is_file()
        if rebuilt:
            _run_stage(root, "build_report.py", [], runner)
    if downloader.errors:
        # The canonical rebuild has its own downloader and may replace the
        # manifest's error list. Preserve failures from the explicit fresh pass.
        manifest = read_json(manifest_path,{})
        failures = manifest.setdefault("errors",[])
        known = {(item.get("path"),item.get("checked_at")) for item in failures}
        failures.extend(item for item in downloader.errors if (item.get("path"),item.get("checked_at")) not in known)
        atomic_json(manifest_path,manifest)
    return {"status":"partial" if downloader.errors else "completed", "season_start":season,
            "scope":"current_football_season_and_ARG_BRA_USA_MEX",
            "raw_files_refreshed":len(downloader.records), "download_failures":len(downloader.errors),
            "failed_files":[item.get("path") for item in downloader.errors],
            "matches_changed":changed,"backtest_rebuilt":rebuilt,"matches_sha256":after,
            "nba_and_mlb":"cached_archives_not_current_live_history"}


def update_live_report(path: Path, scan: dict, bot_status: dict, manifest_path: Path) -> bool:
    if not path.is_file():
        return False
    report = read_json(path)
    report["live"] = scan
    if scan.get('prospective') and report.get('research'):
        report['research']['prospective']=scan['prospective']
    report["bot"] = bot_status
    report.setdefault("meta", {}).update({"current_odds_at":scan["generated_at"],
                                           "execution_enabled":False})
    if manifest_path.exists():
        report["data_manifest"] = read_json(manifest_path)
    atomic_json(path, report)
    return True


def run_once(*, root=None, provider=None, refresh_data=False, now=None,
             scan_fn=None, refresh_fn=None, audit_fn=None, cache_fn=None) -> dict:
    """One bounded cycle; dependencies are injectable for network-free tests.

    The CLI owns the process lock. Attempts are persisted BEFORE networking,
    so a crash or restart cannot spend another daily batch automatically.
    """
    root = Path(root or ROOT)
    provider = provider or OddsAPI()
    scan_fn = scan_fn or save_scan
    refresh_fn = refresh_fn or refresh_histories
    audit_fn = audit_fn or storage.log
    cache_fn = cache_fn or storage.cache_get
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("El reloj del bot debe incluir zona horaria.")
    now = now.astimezone(timezone.utc)
    day, stamp = now.date(), now.isoformat()
    state_path = root / "data/runtime/bot_state.json"
    state = read_json(state_path, {"version":1,"days":{}})
    daily = state.setdefault("days",{}).setdefault(day.isoformat(),{"attempted_sports":[]})
    errors, fetched, cache_hits = [], [], []
    history_refresh = {"status":"not_requested","scope":"none",
                       "note":"Este ciclo no actualiza históricos; cuotas nuevas no vuelven actuales los archivos antiguos."}
    if refresh_data:
        if daily.get("history_refresh_attempted"):
            history_refresh = {**daily.get("history_refresh",{}),"status":"already_attempted_today"}
        else:
            daily["history_refresh_attempted"] = stamp
            atomic_json(state_path,state)
            try:
                history_refresh = refresh_fn(root,day)
            except Exception as exc:
                history_refresh = {"status":"failed","scope":"current_football_only",**safe_error(exc)}
                errors.append({"stage":"history_refresh",**safe_error(exc)})
            daily["history_refresh"] = history_refresh
            atomic_json(state_path,state)
    catalog, selected = [], []
    status = provider.status()
    if status.get("configured"):
        try:
            catalog = provider.sports(force=False)["payload"]
        except Exception as exc:
            errors.append({"stage":"catalog",**safe_error(exc)})
            cached = cache_fn("sports")
            catalog = cached["payload"] if cached else []
        selected = select_sports(catalog,day)
        daily["selected_sports"] = selected
        for sport in selected:
            if sport in daily["attempted_sports"] or len(daily["attempted_sports"]) >= DAILY_LIMIT:
                continue
            daily["attempted_sports"].append(sport)
            atomic_json(state_path,state)
            try:
                snapshot = provider.odds(sport=sport,regions="eu",markets="h2h",force=False)
                (cache_hits if snapshot.get("cached") else fetched).append(sport)
            except Exception as exc:
                errors.append({"stage":"odds","sport":sport,**safe_error(exc)})
    else:
        errors.append({"stage":"provider","type":"NotConfigured"})
    bot_status = {"last_cycle_at":stamp,"mode":"observation","execution_enabled":False,
                  "utc_date":day.isoformat(),"selected_sports":selected,
                  "daily_attempted_sports":list(daily["attempted_sports"]),"daily_limit":DAILY_LIMIT,
                  "new_snapshots":len(fetched),"cache_hits":len(cache_hits),"errors":errors,
                  "history_refresh":history_refresh,"minimum_interval_hours":MINIMUM_INTERVAL_HOURS,
                  "monthly_local_budget":status.get("local_monthly_limit"),
                  "policy":"h2h; una región; cuatro prioridades activas y ocho en rotación; sin futuros"}
    try:
        scan = scan_fn(output=root / "data/runtime/live.json")
        bot_status["scan_id"] = scan.get("scan_id")
        bot_status["observations"] = len(scan.get("opportunities",[]))
        bot_status["report_updated"] = update_live_report(root / "app/data/report.json",scan,bot_status,
                                                          root / "data/manifest.json")
        if not bot_status["report_updated"]:
            errors.append({"stage":"report","type":"MissingHistoricalReport",
                           "action":"Ejecutar python3 scripts/build_report.py"})
    except Exception as exc:
        errors.append({"stage":"scan_or_report",**safe_error(exc)})
    daily["last_cycle_at"] = stamp
    daily["last_result"] = bot_status
    atomic_json(state_path,state)
    audit_fn("bot_cycle",bot_status)
    return bot_status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--once",action="store_true",help="Una pasada acotada (modo predeterminado).")
    modes.add_argument("--watch",action="store_true",help="Mantener el proceso y repetir como máximo una vez cada 24 horas.")
    parser.add_argument("--interval-hours",type=float,default=24,
                        help="Intervalo de --watch; mínimo 24 horas, predeterminado 24.")
    parser.add_argument("--refresh-data",action="store_true",
                        help="Actualizar históricos de fútbol actuales, además de observar cuotas.")
    args = parser.parse_args(argv)
    if not args.interval_hours >= MINIMUM_INTERVAL_HOURS or args.interval_hours == float("inf"):
        parser.error("--interval-hours debe ser finito y como mínimo 24.")
    try:
        with single_instance(ROOT / "data/runtime/bot.lock"):
            while True:
                result = run_once(refresh_data=args.refresh_data)
                print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)
                if not args.watch:
                    return 0
                time.sleep(args.interval_hours*3600)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        # Avoid echoing network error URLs or private credentials to a terminal.
        print(json.dumps({"error":safe_error(exc),"message":"El bot se detuvo; revisá la auditoría local."},
                         ensure_ascii=False),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
