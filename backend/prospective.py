"""Immutable forward forecast log and delayed, verifiable result settlement.

This module records forecasts; it never sends bets or enables real execution.
An event's first eligible forecast is frozen before kickoff for each model.
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter,defaultdict
from contextlib import contextmanager
from datetime import date,datetime,timezone,timedelta
from pathlib import Path

from engine.core import canonical_sport


ROOT=Path(__file__).resolve().parents[1]
EPL_LEAGUES={"epl":"England Premier League","english premier league":"England Premier League",
             "england premier league":"England Premier League"}
EPL_TEAMS={"manchester united":"man united","man utd":"man united",
           "manchester city":"man city","tottenham hotspur":"tottenham",
           "nottingham forest":"nott'm forest","brighton and hove albion":"brighton",
           "brighton & hove albion":"brighton","west ham united":"west ham",
           "wolverhampton wanderers":"wolves","leeds united":"leeds",
           "newcastle united":"newcastle"}


def _now(value=None):
    stamp=value or datetime.now(timezone.utc)
    if not isinstance(stamp,datetime) or stamp.tzinfo is None:
        raise ValueError("El reloj debe incluir zona horaria")
    return stamp.astimezone(timezone.utc)


def _stamp(value):
    if not isinstance(value,str):raise ValueError("Falta timestamp")
    parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    if parsed.tzinfo is None:raise ValueError("Timestamp sin zona horaria")
    return parsed.astimezone(timezone.utc)


def _date(value):
    if not isinstance(value,str) or len(value)!=10:raise ValueError("Fecha inválida")
    return date.fromisoformat(value)


def _base(root):return Path(root or ROOT)


def _registry(root):
    path=_base(root)/"data/runtime/prospective_v2.json"
    try:
        payload=json.loads(path.read_text())
        start=_date(payload["start"]);registered=_stamp(payload["registered_at"])
        model_hash=payload["model_hash"]
        if not isinstance(model_hash,str) or not model_hash.strip() or len(model_hash)>256:
            raise ValueError("Modelo no identificado")
        return {"start":start.isoformat(),"registered_at":registered.isoformat(),"model_hash":model_hash.strip()}
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        return None


@contextmanager
def _connect(root=None,db_path=None):
    path=Path(db_path) if db_path is not None else _base(root)/"data/runtime/kraken.sqlite3"
    path.parent.mkdir(parents=True,exist_ok=True)
    connection=sqlite3.connect(path,timeout=30)
    connection.row_factory=sqlite3.Row
    try:
        connection.executescript('''
          CREATE TABLE IF NOT EXISTS prospective_registrations (
            model_hash TEXT PRIMARY KEY,start TEXT NOT NULL,registered_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS prospective_events (
            model_hash TEXT NOT NULL,event_id TEXT NOT NULL,captured_at TEXT NOT NULL,
            kickoff_at TEXT NOT NULL,calendar_date TEXT NOT NULL,sport TEXT NOT NULL,
            league TEXT NOT NULL,home_team TEXT NOT NULL,away_team TEXT NOT NULL,
            probabilities TEXT NOT NULL,market_probabilities TEXT,
            metadata TEXT NOT NULL,paper_candidate TEXT,
            settled_at TEXT,outcome INTEGER,home_score INTEGER,away_score INTEGER,
            log_loss REAL,brier REAL,market_log_loss REAL,market_brier REAL,paper_profit REAL,
            PRIMARY KEY(model_hash,event_id));
        ''')
        connection.commit()
        with connection:yield connection
    finally:connection.close()


def _freeze_registration(connection,registry):
    connection.execute("INSERT OR IGNORE INTO prospective_registrations VALUES(?,?,?)",
                       (registry["model_hash"],registry["start"],registry["registered_at"]))
    row=connection.execute("SELECT * FROM prospective_registrations WHERE model_hash=?",(registry["model_hash"],)).fetchone()
    return row["start"]==registry["start"] and row["registered_at"]==registry["registered_at"]


def _vector(value,length):
    if not isinstance(value,(list,tuple)) or len(value)!=length:return None
    if any(isinstance(v,bool) for v in value):return None
    try:values=[float(v) for v in value]
    except (ValueError,TypeError):return None
    total=sum(values)
    if any(not math.isfinite(v) or not 0<=v<=1 for v in values) or abs(total-1)>1e-6:return None
    return [v/total for v in values]


def _text(value):return " ".join(value.strip().split()) if isinstance(value,str) else ""


def _identity(sport,league,home,away,calendar_date):
    sport=canonical_sport(sport);league=_text(league)
    if sport=="football":league=EPL_LEAGUES.get(league.casefold(),league)
    h,a=_text(home).casefold(),_text(away).casefold()
    if sport=="football" and league=="England Premier League":
        h,a=EPL_TEAMS.get(h,h),EPL_TEAMS.get(a,a)
    return sport,league.casefold(),h,a,calendar_date


def _eligible_row(row,capture,registry,clock):
    if not isinstance(row,dict):return None,"invalid_row"
    if row.get("source")!="The Odds API" or row.get("mode")!="observation":return None,"not_provider_observation"
    if str(row.get("market","")).casefold() not in ("1x2","ganador","h2h"):return None,"unsupported_market"
    event_id=row.get("event_id")
    if not isinstance(event_id,str) or not event_id.strip() or len(event_id)>256:return None,"missing_event_id"
    if row.get("model_hash") is not None and row["model_hash"]!=registry["model_hash"]:return None,"wrong_model"
    try:
        kickoff=_stamp(row.get("date"));quote=_stamp(row.get("quote_timestamp"))
        # Provider calendar is preserved from its explicit ISO string; no +/-
        # one-day matching or local-time guess is used during settlement.
        calendar_date=_date(row["date"][:10]).isoformat()
        if kickoff<=capture or kickoff<=clock:return None,"kickoff_not_future"
        if calendar_date<registry["start"]:return None,"before_registered_start"
        if quote>clock or not 0<=(capture-quote).total_seconds()<=900:return None,"stale_or_future_quote"
        if row.get("snapshot_at") is not None:
            snapshot=_stamp(row["snapshot_at"])
            if snapshot>capture or snapshot>clock or quote>snapshot:return None,"invalid_snapshot_clock"
        reference_count=row.get("reference_count")
        if isinstance(reference_count,bool) or not isinstance(reference_count,(int,float)) or not math.isfinite(reference_count) or reference_count<3 or int(reference_count)!=reference_count:return None,"insufficient_references"
        sport=canonical_sport(row.get("sport",""));length=3 if sport=="football" else 2
        if not sport:return None,"missing_sport"
        vector=_vector(row.get("forecast_probabilities"),length)
        if vector is None:return None,"invalid_forecast_vector"
        # The event forecast may use the full reference pool, while pricing
        # excludes the bookmaker whose offered odds are being evaluated.
        # Keep both coherent vectors instead of mixing their components.
        priced_vector=(_vector(row["priced_probabilities"],length)
                       if row.get("priced_probabilities") is not None else vector)
        if priced_vector is None:return None,"invalid_priced_forecast_vector"
        labels=("home","draw","away") if length==3 else ("home","away")
        code=row.get("selection_code")
        if code not in labels:return None,"invalid_selection"
        index=labels.index(code)
        if isinstance(row.get("model_probability"),bool) or isinstance(row.get("odds"),bool):return None,"invalid_odds_or_probability"
        p=float(row.get("model_probability"));odds=float(row.get("odds"))
        if not math.isfinite(p) or not 0<=p<=1 or abs(p-priced_vector[index])>1e-6:return None,"incoherent_selection_probability"
        if not math.isfinite(odds) or odds<=1:return None,"invalid_odds"
        home,away,league=(_text(row.get(k)) for k in ("home_team","away_team","league"))
        if not home or not away or not league or home.casefold()==away.casefold():return None,"invalid_participants"
    except (ValueError,TypeError,KeyError,OverflowError):return None,"invalid_timestamp_or_numbers"
    return {"event_id":event_id.strip(),"kickoff_at":kickoff.isoformat(),"calendar_date":calendar_date,
            "sport":sport,"league":league,"home_team":home,"away_team":away,
            "probabilities":vector,"priced_probabilities":priced_vector,
            "market_probabilities":_vector(row.get("forecast_market_probabilities"),length),
            "selection_code":code,"selection_index":index,"selection_probability":p,"odds":odds,
            "ev":p*odds-1,"reference_count":reference_count,"quote_timestamp":quote.isoformat(),
            "snapshot_at":row.get("snapshot_at"),"bookmaker":row.get("bookmaker"),"market":row.get("market"),
            "identity":_identity(sport,league,home,away,calendar_date)},None


def _empty_summary(registry=None,reason=None):
    registry=registry or {}
    return {"start":registry.get("start"),"model_hash":registry.get("model_hash"),
            "registered_at":registry.get("registered_at"),"events":0,"completed_events":0,
            "captured_events":0,"pending_events":0,"log_loss":None,"brier":None,
            "market_events":0,"market_log_loss":None,"market_brier":None,
            "model_log_loss_on_market_events":None,"model_brier_on_market_events":None,
            "paper_bets":0,"paper_captured_candidates":0,"paper_roi":None,"paper_profit":None,
            "paper_mode":"flat_one_unit_hypothetical","live_enabled":False,"execution_enabled":False,
            "reason":reason or "Sin capturas prospectivas elegibles posteriores al inicio registrado."}


def summary(root=None,db_path=None):
    registry=_registry(root)
    if registry is None:return _empty_summary(reason="Registro prospectivo no configurado o inválido.")
    result=_empty_summary(registry)
    with _connect(root,db_path) as connection:
        registration=connection.execute("SELECT * FROM prospective_registrations WHERE model_hash=?",(registry["model_hash"],)).fetchone()
        registration_changed=bool(registration and (registration["start"]!=registry["start"] or registration["registered_at"]!=registry["registered_at"]))
        if registration_changed:
            result.update({"start":registration["start"],"registered_at":registration["registered_at"]})
        rows=connection.execute("SELECT * FROM prospective_events WHERE model_hash=?",(registry["model_hash"],)).fetchall()
    completed=[r for r in rows if r["settled_at"] is not None]
    market=[r for r in completed if r["market_log_loss"] is not None]
    paper=[r for r in completed if r["paper_profit"] is not None]
    result.update({"events":len(completed),"completed_events":len(completed),"captured_events":len(rows),
                   "pending_events":len(rows)-len(completed),"market_events":len(market),
                   "paper_bets":len(paper),"paper_captured_candidates":sum(r["paper_candidate"] is not None for r in rows)})
    for field,items,column in [("log_loss",completed,"log_loss"),("brier",completed,"brier"),
                               ("market_log_loss",market,"market_log_loss"),("market_brier",market,"market_brier"),
                               ("model_log_loss_on_market_events",market,"log_loss"),("model_brier_on_market_events",market,"brier")]:
        result[field]=sum(r[column] for r in items)/len(items) if items else None
    if paper:
        profit=sum(r["paper_profit"] for r in paper)
        result.update({"paper_profit":profit,"paper_roi":profit/len(paper)})
    if completed:result["reason"]="Resultados prospectivos registrados en observación; no habilitan ejecución automática."
    elif rows:result["reason"]="Capturas registradas; todavía no hay resultados finales verificables."
    if registration_changed:result["reason"]="El registro fue modificado después de congelarse; se conserva la muestra original sin añadir eventos."
    return result


def capture_scan(scan,root=None,db_path=None,now=None):
    registry=_registry(root);rejected=Counter();added=0
    if registry is None:return _empty_summary(reason="Registro prospectivo no configurado o inválido.")
    try:
        capture=_stamp(scan.get("generated_at"));clock=_now(now)
        if capture>clock+timedelta(seconds=60):raise ValueError("Captura con reloj futuro")
        if clock-capture>timedelta(seconds=120):raise ValueError("La captura no fue registrada a tiempo")
        if capture<_stamp(registry["registered_at"]):raise ValueError("Captura anterior al registro")
    except (ValueError,TypeError,AttributeError):
        result=summary(root,db_path);result.update({"added_events":0,"rejected_reasons":{"invalid_capture_clock":1}})
        return result
    groups=defaultdict(list)
    for row in scan.get("opportunities",[]):
        eligible,reason=_eligible_row(row,capture,registry,clock)
        if eligible:groups[eligible["event_id"]].append(eligible)
        else:rejected[reason]+=1
    with _connect(root,db_path) as connection:
        if not _freeze_registration(connection,registry):
            rejected["registry_changed_after_freeze"]+=1
        else:
            for event_id,quotes in groups.items():
                identities={(q["identity"],q["kickoff_at"]) for q in quotes}
                if len(identities)!=1:rejected["conflicting_event_identity"]+=1;continue
                quotes.sort(key=lambda q:(q["selection_index"],str(q["bookmaker"] or ""),q["odds"]))
                canonical=quotes[0]
                candidates=[q for q in quotes if 1.2<=q["odds"]<=5 and q["ev"]>=.03]
                candidates.sort(key=lambda q:(-q["ev"],q["selection_index"],str(q["bookmaker"] or "")))
                paper=candidates[0] if candidates else None
                metadata={"selection_policy":"first_eligible_capture; canonical home/draw/away then bookmaker",
                          "paper_policy":"max EV >=3%; decimal odds 1.2..5; one hypothetical unit; one selection/event",
                          "quotes":quotes,"source":"The Odds API","real_money":False,"recorded_at":clock.isoformat(),
                          "alias_rules_version":"explicit_epl_v1","probability_floor_for_log_loss":1e-15}
                cursor=connection.execute('''INSERT OR IGNORE INTO prospective_events
                    (model_hash,event_id,captured_at,kickoff_at,calendar_date,sport,league,home_team,away_team,
                     probabilities,market_probabilities,metadata,paper_candidate)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (registry["model_hash"],event_id,capture.isoformat(),canonical["kickoff_at"],canonical["calendar_date"],
                     canonical["sport"],canonical["league"],canonical["home_team"],canonical["away_team"],
                     json.dumps(canonical["probabilities"]),json.dumps(canonical["market_probabilities"]) if canonical["market_probabilities"] else None,
                     json.dumps(metadata,ensure_ascii=False),json.dumps(paper,ensure_ascii=False) if paper else None))
                added+=cursor.rowcount
    result=summary(root,db_path);result.update({"added_events":added,"rejected_reasons":dict(rejected)})
    return result


def _completed_row(row,event,now):
    try:
        day=_date(row.get("date"));kickoff=_stamp(event["kickoff_at"])
        if day.isoformat()!=event["calendar_date"] or now<kickoff:return None
        status=str(row.get("status","")).strip().casefold()
        if status and status not in ("ft","final","finished","completed"):return None
        final_stamp=next((row[k] for k in ("completed_at","finished_at","final_at") if row.get(k)),None)
        if final_stamp:
            finished=_stamp(final_stamp)
            if finished<kickoff or finished>now:return None
        elif day>=now.date() or kickoff.date()>=now.date():
            # A date-only score cannot prove same-day completion. Delay until
            # both the provider calendar and UTC kickoff day have passed.
            return None
        hs,aws=float(row["home_score"]),float(row["away_score"])
        if any(not math.isfinite(v) or v<0 or int(v)!=v for v in (hs,aws)):return None
        if event["sport"]!="football" and hs==aws:return None
        return int(hs),int(aws)
    except (ValueError,TypeError,KeyError,OverflowError):return None


def settle_from_history(matches_csv=None,root=None,db_path=None,now=None):
    registry=_registry(root)
    if registry is None:return _empty_summary(reason="Registro prospectivo no configurado o inválido.")
    clock=_now(now);path=Path(matches_csv) if matches_csv is not None else _base(root)/"data/processed/matches.csv"
    if not path.is_file():
        result=summary(root,db_path);result["settled_now"]=0;return result
    with _connect(root,db_path) as connection:
        registration_ok=_freeze_registration(connection,registry)
        events=connection.execute("SELECT * FROM prospective_events WHERE model_hash=? AND settled_at IS NULL",(registry["model_hash"],)).fetchall() if registration_ok else []
    if not registration_ok:
        result=summary(root,db_path);result["settled_now"]=0;return result
    wanted={_identity(e["sport"],e["league"],e["home_team"],e["away_team"],e["calendar_date"]) for e in events}
    if not wanted:
        result=summary(root,db_path);result["settled_now"]=0;return result
    index=defaultdict(list)
    with path.open(encoding="utf-8-sig",newline="") as stream:
        for row in csv.DictReader(stream):
            try:day=_date(row.get("date")).isoformat()
            except (ValueError,TypeError):continue
            key=_identity(row.get("sport",""),row.get("league",""),row.get("home_team",""),row.get("away_team",""),day)
            if key in wanted:index[key].append(row)
    settled=0
    with _connect(root,db_path) as connection:
        for event in events:
            key=_identity(event["sport"],event["league"],event["home_team"],event["away_team"],event["calendar_date"])
            scores={score for row in index.get(key,[]) if (score:=_completed_row(row,event,clock)) is not None}
            if len(scores)!=1:continue
            hs,aws=next(iter(scores));vector=json.loads(event["probabilities"])
            outcome=0 if hs>aws else 1 if event["sport"]=="football" and hs==aws else len(vector)-1
            loss=-math.log(max(1e-15,vector[outcome]));brier=sum((p-(i==outcome))**2 for i,p in enumerate(vector))
            market=json.loads(event["market_probabilities"]) if event["market_probabilities"] else None
            mloss=-math.log(max(1e-15,market[outcome])) if market else None
            mbrier=sum((p-(i==outcome))**2 for i,p in enumerate(market)) if market else None
            paper=json.loads(event["paper_candidate"]) if event["paper_candidate"] else None
            profit=(paper["odds"]-1 if paper["selection_index"]==outcome else -1.) if paper else None
            cursor=connection.execute('''UPDATE prospective_events SET settled_at=?,outcome=?,home_score=?,away_score=?,
                log_loss=?,brier=?,market_log_loss=?,market_brier=?,paper_profit=?
                WHERE model_hash=? AND event_id=? AND settled_at IS NULL''',
                (clock.isoformat(),outcome,hs,aws,loss,brier,mloss,mbrier,profit,event["model_hash"],event["event_id"]))
            settled+=cursor.rowcount
    result=summary(root,db_path);result["settled_now"]=settled;return result
