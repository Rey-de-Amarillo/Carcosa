"""Cached prior-only fixture inference for the V2 football model.

Cache identity includes the actual training rows, not merely a file path or
team label. No odds, provider credentials or outcome of the fixture are read.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections import OrderedDict
from datetime import date, datetime
from itertools import groupby

from .core import canonical_sport, predict_fixture
from .models_v2 import OnlineGoalsV2


MODEL_VERSION = "0.2.0"
MAX_CACHE_SIZE = 32
_CACHE = OrderedDict()
_LOCK = threading.RLock()
_HITS = 0
_MISSES = 0


def clear_inference_cache():
    global _HITS,_MISSES
    with _LOCK:
        _CACHE.clear();_HITS=0;_MISSES=0


def inference_cache_info():
    with _LOCK:
        return {"hits":_HITS,"misses":_MISSES,"size":len(_CACHE),"maxsize":MAX_CACHE_SIZE}


def _strict_day(value):
    # Date-only source labels do not acquire an implicit timezone. A caller
    # with an ISO kickoff must first choose its explicit modelling calendar.
    if isinstance(value,datetime):
        raise ValueError("Convertí el horario del partido a una fecha de modelado explícita")
    if isinstance(value,date):return value
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        raise ValueError("La fecha debe tener formato YYYY-MM-DD")
    return date.fromisoformat(value)


def _blocked(reason,sport=None,league=None):
    return {"eligible":False,"ready_for_live":False,"execution_enabled":False,
            "model":None,"model_version":MODEL_VERSION,"sport":sport,"league":league,
            "home":None,"draw":None,"away":None,"over25":None,"under25":None,
            "btts_yes":None,"btts_no":None,"home_rate":None,"away_rate":None,
            "expected_home_goals":None,"expected_away_goals":None,
            "training_max_date":None,"sample_size":0,"effective_sample_size":0,
            "probability_source":"unavailable","reasons":[reason]}


def _training_rows(history,fixture,cutoff):
    sport,league=fixture["sport"],fixture["league"]
    accepted=[];rejected=0
    for raw in history:
        if not isinstance(raw,dict):rejected+=1;continue
        if canonical_sport(raw.get("sport","football"))!=sport or raw.get("league","")!=league:
            continue
        try:
            day=_strict_day(raw.get("date"))
            if day>=cutoff:continue
            h,a=raw["home_team"],raw["away_team"]
            if not isinstance(h,str) or not isinstance(a,str) or not h.strip() or not a.strip() or h.strip()==a.strip():
                raise ValueError("Participantes inválidos")
            hs,aws=float(raw["home_score"]),float(raw["away_score"])
            if any(not math.isfinite(v) or v<0 or int(v)!=v for v in (hs,aws)):
                raise ValueError("Marcador inválido")
            if sport!="football" and hs==aws:raise ValueError("Resultado binario no decisivo")
            neutral=str(raw.get("neutral_venue","false")).lower() in ("true","1","yes")
            accepted.append({"id":str(raw.get("id","")),"sport":sport,"league":league,
                             "date":day.isoformat(),"home_team":h.strip(),"away_team":a.strip(),
                             "home_score":int(hs),"away_score":int(aws),"neutral_venue":neutral})
        except (ValueError,TypeError,KeyError,OverflowError):rejected+=1
    accepted.sort(key=lambda r:(r["date"],r["id"],r["home_team"],r["away_team"],r["home_score"],r["away_score"]))
    return accepted,rejected


def _fingerprint(rows):
    payload=[(r["id"],r["date"],r["home_team"],r["away_team"],r["home_score"],r["away_score"],r["neutral_venue"]) for r in rows]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()


def predict_fixture_v2(history_rows,fixture):
    """Return direct probability keys, with strict league/date isolation.

    Football fitting uses all permitted past rows and a SINGLE fit at the
    fixture cutoff. Historical replay uses ``replay_predictions`` instead:
    caching current inference is not a shortcut for evaluating past forecasts.
    """
    global _HITS,_MISSES
    if not isinstance(fixture,dict):return _blocked("Partido inválido")
    sport=canonical_sport(fixture.get("sport","football"));league=fixture.get("league","")
    try:
        cutoff=_strict_day(fixture.get("date"))
        h,a=fixture.get("home_team"),fixture.get("away_team")
        if not isinstance(league,str) or not league.strip():raise ValueError("Falta una liga identificada")
        if not isinstance(h,str) or not isinstance(a,str) or not h.strip() or not a.strip() or h.strip()==a.strip():
            raise ValueError("Participantes inválidos")
    except (ValueError,TypeError):return _blocked("Fecha, liga o participantes inválidos",sport,league)
    normalized={**fixture,"date":cutoff.isoformat(),"sport":sport,"league":league,
                "home_team":h.strip(),"away_team":a.strip()}
    try:
        rows,rejected=_training_rows(history_rows,normalized,cutoff)
    except (TypeError,ValueError):return _blocked("Historial inválido",sport,league)
    digest=_fingerprint(rows)
    if sport!="football":
        try:result=predict_fixture(rows,normalized)
        except (ValueError,TypeError,KeyError):return _blocked("No se pudo evaluar el historial",sport,league)
        result.update({"model_version":MODEL_VERSION,"adapter":"strict_cached_inference_v2",
                       "training_fingerprint":digest,"history_rejected_rows":rejected,
                       "probability_source":"historical_elo_baseline" if result.get("eligible") else "unavailable",
                       "ready_for_live":False,"execution_enabled":False})
        return result
    key=(MODEL_VERSION,sport,league,cutoff.isoformat(),digest)
    with _LOCK:
        model=_CACHE.get(key)
        if model is None:
            _MISSES+=1;model=OnlineGoalsV2()
            for _,batch in groupby(rows,key=lambda r:r["date"]):
                model.update_batch(list(batch))
            # The first predict below performs the single fit. Team names are
            # deliberately not part of the key: same-date league fixtures share it.
            _CACHE[key]=model
            while len(_CACHE)>MAX_CACHE_SIZE:_CACHE.popitem(last=False)
        else:
            _HITS+=1;_CACHE.move_to_end(key)
        result=model.predict(normalized["home_team"],normalized["away_team"],cutoff,
                             normalized.get("neutral_venue",False))
    result.update({"model_version":MODEL_VERSION,"sport":sport,"league":league,
                   "forecast_date":cutoff.isoformat(),"training_fingerprint":digest,
                   "history_rejected_rows":rejected,"history_rows_considered":len(rows),
                   "probability_source":"historical_opponent_adjusted_model_v2" if result.get("eligible") else "unavailable",
                   "ready_for_live":False,"execution_enabled":False,
                   "first_goal_home":None,"first_goal_away":None,"first_goal_none":None,
                   "first_goal_status":"requires_separate_event_model"})
    return result
