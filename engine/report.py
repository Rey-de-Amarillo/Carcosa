"""Deterministic, chronological historical evaluation and dashboard report.

Usage: python3 -m engine.report --data-dir data/processed --output app/data/report.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timezone
from itertools import groupby
from pathlib import Path

from .core import (ELO_HOME_ADVANTAGE, EloModel, LeaguePoisson, canonical_sport, expected_value,
                   kelly_fraction, probability_sensitivity, proper_scores,
                   remove_margin)


LABELS = {"football": ["Local", "Empate", "Visitante"],
          "basketball": ["Local", "Visitante"], "tennis": ["Participante A", "Participante B"],
          "hockey": ["Local", "Visitante"], "baseball": ["Local", "Visitante"]}
MODEL_VERSION = "0.1.0"


def _finite(value, default=None):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (ValueError, TypeError):
        return default


def _odds(value):
    value = _finite(value)
    return value if value is not None and value > 1 else None


def read_matches(data_dir) -> tuple[list[dict], dict]:
    directory = Path(data_dir)
    paths = sorted(directory.glob("*.csv"))
    # Event-level StatsBomb files and fixture lists must not be mistaken for finals.
    rows, rejected, duplicates, seen = [], Counter(), 0, set()
    files = []
    for path in paths:
        if any(word in path.name.lower() for word in ("fixture", "event", "first_goal")):
            continue
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"date", "home_team", "away_team", "home_score", "away_score"}
            if not required.issubset(set(reader.fieldnames or [])):
                continue
            count = 0
            for raw in reader:
                try:
                    day = date.fromisoformat(str(raw["date"])[:10])
                    hs, aws = _finite(raw["home_score"]), _finite(raw["away_score"])
                    if hs is None or aws is None or hs < 0 or aws < 0 or hs != int(hs) or aws != int(aws):
                        rejected["missing_or_invalid_final_score"] += 1; continue
                    sport = canonical_sport(raw.get("sport", "football"))
                    if sport != "football" and sport not in ELO_HOME_ADVANTAGE:
                        rejected["unsupported_sport"] += 1; continue
                    if sport in ELO_HOME_ADVANTAGE and hs == aws:
                        rejected["non_decisive_binary_result"] += 1; continue
                    if not raw["home_team"].strip() or not raw["away_team"].strip() or raw["home_team"] == raw["away_team"]:
                        rejected["invalid_participants"] += 1; continue
                    key = (sport, raw.get("league", ""), day.isoformat(), raw["home_team"], raw["away_team"])
                    if sport == "baseball":
                        # Doubleheaders contain two legitimate games for the
                        # same participants/date; gamePk distinguishes them.
                        key = (*key, raw.get("id") or raw.get("game_id") or "unknown")
                    if key in seen: duplicates += 1; continue
                    seen.add(key)
                    rid = raw.get("id") or hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:18]
                    record = {**raw, "id": rid, "_day": day, "date": day.isoformat(),
                              "sport": sport, "league": raw.get("league") or "Sin liga",
                              "home_score": int(hs), "away_score": int(aws), "_file": path.name}
                    for name in ("home_odds", "draw_odds", "away_odds", "over25_odds", "under25_odds"):
                        record[name] = _odds(raw.get(name))
                    rows.append(record); count += 1
                except (ValueError, TypeError, KeyError, OverflowError):
                    rejected["invalid_row"] += 1
            files.append({"file": path.name, "rows": count, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    rows.sort(key=lambda row: (row["_day"], row["sport"], row["league"], row["id"]))
    return rows, {"files": files, "accepted": len(rows), "rejected": dict(rejected), "duplicates_removed": duplicates}


def temporal_splits(rows: list[dict]) -> dict:
    result = {}
    for sport in sorted({row["sport"] for row in rows}):
        days = sorted({row["_day"] for row in rows if row["sport"] == sport})
        if not days: continue
        first_validation = days[min(len(days) - 1, int(len(days) * 0.60))]
        first_test = days[min(len(days) - 1, int(len(days) * 0.80))]
        result[sport] = {"train_start": days[0].isoformat(),
                         "validation_start": first_validation.isoformat(),
                         "test_start": first_test.isoformat(), "test_end": days[-1].isoformat(),
                         "rule": "60/20/20 de fechas únicas por deporte; ninguna fecha se divide"}
    return result


def _fold(day: date, split: dict) -> str:
    if day.isoformat() < split["validation_start"]: return "train"
    return "validation" if day.isoformat() < split["test_start"] else "test"


def _outcome(row: dict) -> int:
    if row["sport"] == "football":
        return 0 if row["home_score"] > row["away_score"] else 1 if row["home_score"] == row["away_score"] else 2
    return 0 if row["home_score"] > row["away_score"] else 1


def _market(row: dict) -> dict | None:
    names = ("home_odds", "draw_odds", "away_odds") if row["sport"] == "football" else ("home_odds", "away_odds")
    odds = [row.get(name) for name in names]
    if not all(o is not None for o in odds): return None
    result = remove_margin(odds)
    result["odds"] = odds
    return result


def _metrics(records: list[dict], market=False) -> dict:
    valid = [record for record in records if not market or record.get("market_probs")]
    if not valid:
        return {"n": 0, "brier": None, "log_loss": None, "accuracy": None, "ece": None}
    scored = [proper_scores(r["market_probs"] if market else r["probs"], r["outcome"]) for r in valid]
    bins = _calibration(valid, market)
    n = len(valid)
    return {"n": n, "brier": sum(x["brier"] for x in scored) / n,
            "log_loss": sum(x["log_loss"] for x in scored) / n,
            "accuracy": sum(x["correct"] for x in scored) / n,
            "ece": sum(b["count"] * abs(b["predicted"] - b["observed"]) for b in bins) / n,
            "brier_definition": "Suma de errores cuadrados en todos los resultados; menor es mejor (0–2).",
            "ece_definition": "Calibración de la selección más probable en 10 intervalos; diagnóstico, no prueba de ventaja."}


def _calibration(records: list[dict], market=False) -> list[dict]:
    buckets = defaultdict(list)
    for record in records:
        probs = record.get("market_probs") if market else record["probs"]
        if not probs: continue
        index = max(range(len(probs)), key=probs.__getitem__)
        confidence = probs[index]
        buckets[min(9, int(confidence * 10))].append((confidence, index == record["outcome"]))
    result = []
    for index, values in sorted(buckets.items()):
        n = len(values); observed = sum(v[1] for v in values) / n
        # Wilson score interval describes observed hit rate in this bin only.
        z = 1.96; den = 1 + z * z / n
        mid = (observed + z * z / (2 * n)) / den
        radius = z * math.sqrt(observed * (1 - observed) / n + z * z / (4 * n * n)) / den
        result.append({"bin": f"{index * 10}–{(index + 1) * 10}%", "lower": index / 10,
                       "upper": (index + 1) / 10, "count": n, "n": n,
                       "predicted": sum(v[0] for v in values) / n, "observed": observed,
                       "observed_interval": {"low": max(0.0, mid-radius), "high": min(1.0, mid+radius),
                                             "method": "Wilson 95%; sin ajuste por dependencia"}})
    return result


def _percentile(values: list[float], fraction: float):
    if not values: return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low, high = int(position), min(len(values) - 1, int(position) + 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def _paired_skill_ci(records: list[dict], seed=271828) -> dict:
    daily = defaultdict(lambda: [0.0, 0])
    for record in records:
        if not record.get("market_probs"): continue
        model = proper_scores(record["probs"], record["outcome"])["log_loss"]
        market = proper_scores(record["market_probs"], record["outcome"])["log_loss"]
        daily[record["date"]][0] += market - model
        daily[record["date"]][1] += 1
    days = list(daily.values()); n = sum(day[1] for day in days)
    if not n:
        return {"n": 0, "low": None, "high": None, "mean": None, "passed": False,
                "method": "Bootstrap pareado por fecha; sin cuotas comparables."}
    rng = random.Random(seed); samples = []
    for _ in range(400):
        sample = [rng.choice(days) for _ in days]
        samples.append(sum(x[0] for x in sample) / sum(x[1] for x in sample))
    low, high = _percentile(samples, 0.025), _percentile(samples, 0.975)
    return {"n": n, "days": len(days), "mean": sum(d[0] for d in days) / n,
            "low": low, "high": high, "passed": n >= 500 and len(days) >= 100 and low > 0,
            "method": "400 réplicas bootstrap pareadas por fecha, semilla 271828; mejora de log loss mercado menos modelo.",
            "limitation": "Agrupar por fecha conserva dependencia intradía; no conserva toda dependencia temporal entre fechas."}


def _strategy(records: list[dict], initial=1000.0) -> dict:
    bankroll, peak, worst = initial, initial, 0.0
    trades, curve, daily_returns = [], [{"date": records[0]["date"] if records else None,
                                        "bankroll": initial, "profit": 0.0, "drawdown": 0.0}], []
    for day, group in groupby(sorted(records, key=lambda r: (r["date"], r["id"])), lambda r: r["date"]):
        candidates = []
        for record in group:
            if record["sport"] != "football" or not record.get("odds"): continue
            # A mean across bookmakers is a benchmark, not an offered price.
            if ":Avg:" in str(record.get("odds_source", "")): continue
            evs = [expected_value(p, o) for p, o in zip(record["probs"], record["odds"])]
            selected = max(range(len(evs)), key=evs.__getitem__)
            if evs[selected] >= 0.05:
                fraction = kelly_fraction(record["probs"][selected], record["odds"][selected])
                if fraction > 0: candidates.append((record, selected, fraction, evs[selected]))
        # One 1X2 selection per event. A proportional day cap prevents priority
        # ordering or intraday settlement assumptions from changing allocation.
        exposure = sum(item[2] for item in candidates)
        scale = min(1.0, 0.03 / exposure) if exposure else 1.0
        day_profit = day_turnover = 0.0
        for record, selected, fraction, ev in candidates:
            stake = bankroll * fraction * scale
            won = selected == record["outcome"]
            profit = stake * (record["odds"][selected] - 1) if won else -stake
            trade = {"id": record["id"], "date": day, "selection_index": selected,
                     "stake": stake, "pnl": profit, "profit": profit, "won": won,
                     "odds": record["odds"][selected], "ev": ev,
                     "kelly_fraction": fraction, "actual_fraction": fraction * scale,
                     "outcome": "won" if won else "lost"}
            trades.append(trade); day_profit += profit; day_turnover += stake
        bankroll += day_profit
        peak = max(peak, bankroll)
        drawdown = 1 - bankroll / peak if peak else 0
        worst = max(worst, drawdown)
        if candidates:
            curve.append({"date": day, "bankroll": bankroll, "profit": bankroll-initial, "drawdown": drawdown})
            daily_returns.append((day_profit, day_turnover))
    turnover = sum(t["stake"] for t in trades); profit = bankroll-initial
    samples = []; rng = random.Random(314159)
    for _ in range(400 if daily_returns else 0):
        sampled = [rng.choice(daily_returns) for _ in daily_returns]
        denominator = sum(x[1] for x in sampled)
        if denominator: samples.append(sum(x[0] for x in sampled) / denominator)
    ci = {"low": _percentile(samples, 0.025), "high": _percentile(samples, 0.975),
          "method": "400 réplicas bootstrap por fecha de beneficio/importe histórico; semilla 314159.",
          "limitation": "Variabilidad del backtest condicionado a sus apuestas, sin garantía de rendimiento futuro."}
    return {"initial_bankroll": initial, "final_bankroll": bankroll, "bankroll": bankroll,
            "currency": "unidades simuladas", "profit": profit, "net_profit": profit,
            "roi": profit / turnover if turnover else None,
            "bankroll_return": profit / initial, "turnover": turnover,
            "bets": len(trades), "wins": sum(t["won"] for t in trades),
            "win_rate": sum(t["won"] for t in trades)/len(trades) if trades else None,
            "max_drawdown": worst, "curve": curve, "profit_ci": ci, "trades": trades,
            "is_simulation": True, "strategy": "1X2 EV estimado ≥5%, Kelly ¼, tope 1% por evento y 3% por fecha.",
            "selection_rule_fixed_before_replay": True,
            "assumptions": ["Cuotas históricas de casas identificadas, con snapshot pre-closing o closing según odds_source; sin marca horaria de ejecutabilidad.",
                            "Las cuotas Avg (promedio entre casas) se usan solo como benchmark; no se simulan como precio ejecutable.",
                            "Importes calculados con saldo al inicio de cada fecha; resultados se liquidan al cerrar la fecha.",
                            "Una selección por evento; solo 1X2, sin combinadas ni mercados correlacionados del mismo partido.",
                            "Sin comisiones, impuestos, límites, anulaciones, latencia ni redondeo de importes: no es un P&L real.",
                            "El holdout no se usó para ajustar parámetros; hace falta validación prospectiva independiente."]}


def _decision(record: dict, trade: dict | None, skill: dict) -> dict:
    odds = record.get("odds")
    index = (trade["selection_index"] if trade else
             max(range(len(record["probs"])), key=lambda i: expected_value(record["probs"][i], odds[i])) if odds else
             max(range(len(record["probs"])), key=record["probs"].__getitem__))
    p = record["probs"][index]; o = odds[index] if odds else None
    mp = record["market_probs"][index] if record.get("market_probs") else None
    ev = expected_value(p, o) if o else None
    band = probability_sensitivity(p, record["prediction"]["effective_sample_size"])
    labels = LABELS[record["sport"]]
    selection = record["home_team"] if index == 0 else "Empate" if record["sport"] == "football" and index == 1 else record["away_team"]
    reasons = ["Registro histórico fuera de muestra; no es una oportunidad actual."]
    if not odds: reasons.append("No hay cuota histórica completa para calcular ventaja o rentabilidad.")
    if not skill.get("passed"): reasons.append("No se demostró una mejora robusta frente al mercado en el holdout.")
    if not trade and odds:
        reasons.append("Cuota promedio de varias casas; solo sirve de referencia y no se simula una apuesta a ese precio." if ":Avg:" in str(record.get("odds_source", "")) else "No superó la regla fija EV ≥5% de esta simulación.")
    if trade: reasons.append("Apuesta hipotética generada por la regla del backtest; importe en unidades simuladas.")
    return {"id": record["id"], "event": f"{record['home_team']} vs {record['away_team']}",
            "sport": record["sport"], "league": record["league"], "date": record["date"],
            "home_team": record["home_team"], "away_team": record["away_team"],
            "home_score": record["home_score"], "away_score": record["away_score"],
            "settlement_target": ("winner_including_overtime_and_shootout" if record["sport"] == "hockey" else
                                  "winner_including_extra_innings" if record["sport"] == "baseball" else
                                  "regulation_time_1x2" if record["sport"] == "football" else "final_winner"),
            "market": "1X2" if record["sport"] == "football" else "Ganador", "selection": selection,
            "selection_label": labels[index], "probability": p, "model_probability": p,
            "market_probability": mp, "odds": o, "ev": ev, "edge": p-mp if mp is not None else None,
            "implied_probability": 1/o if o else None, "overround": record.get("overround"),
            "kelly_fraction": kelly_fraction(p, o) if o else 0,
            "stake": trade["stake"] if trade else 0.0, "pnl": trade["pnl"] if trade else 0.0,
            "profit": trade["pnl"] if trade else 0.0, "settled": True,
            "outcome": trade["outcome"] if trade else "no_bet",
            "status": "paper_settled" if trade else "abstain",
            "decision": "Simulada" if trade else "Abstenerse", "reasons": reasons,
            "is_simulation": True, "is_live": False, "fold": record["fold"],
            "sample_size": record["prediction"]["sample_size"],
            "effective_sample_size": record["prediction"]["effective_sample_size"], "uncertainty": band,
            "model": record["prediction"]["model"], "model_version": MODEL_VERSION,
            "training_as_of": record["prediction"].get("training_as_of"),
            "odds_source": record.get("odds_source"), "odds_snapshot": record.get("odds_snapshot"),
            "quote_timestamp": None,
            "explanation": {"probability": "Probabilidad estimada por un modelo, no probabilidad verdadera conocida.",
                            "market": "1/cuota normalizado entre todos los resultados para remover el margen proporcionalmente." if odds else "Sin cuotas comparables.",
                            "ev_formula": f"{p:.6f} × {o:.4f} − 1 = {ev:.6f}" if o else None,
                            "stake_rule": "Kelly ¼ con topes de exposición; no se envió ninguna apuesta.",
                            "uncertainty": band["label"]}}


def _prediction_view(record: dict) -> dict:
    p = record["prediction"]
    view = {"id": record["id"], "event": f"{record['home_team']} vs {record['away_team']}",
            "sport": record["sport"], "league": record["league"], "date": record["date"],
            "home_team": record["home_team"], "away_team": record["away_team"],
            "historical": True, "is_live": False, "model": p["model"], "sample_size": p["sample_size"],
            "model_probability": p["home"], "markets": []}
    if record["sport"] == "football":
        for market, selections, status in [
            ("1X2", [("Local", "home"), ("Empate", "draw"), ("Visitante", "away")], "historical_evaluation"),
            ("Total 2.5 goles", [("Más de 2.5", "over25"), ("Menos de 2.5", "under25")], "historical_evaluation"),
            ("Ambos marcan", [("Sí", "btts_yes"), ("No", "btts_no")], "historical_evaluation"),
            ("Primer gol del equipo", [("Local", "first_goal_home"), ("Visitante", "first_goal_away"), ("Sin goles", "first_goal_none")], "exploratory_unvalidated")]:
            view["markets"].append({"market": market, "status": status, "actionable": False,
                                    "selections": [{"selection": label, "probability": p[key]} for label, key in selections]})
        view.update({"expected_home_goals": p["expected_home_goals"], "expected_away_goals": p["expected_away_goals"],
                     "most_likely_score": p["most_likely_score"]})
    else:
        view["markets"].append({"market": "Ganador", "status": "historical_evaluation", "actionable": False,
                                "selections": [{"selection": "Local", "probability": p["home"]},
                                               {"selection": "Visitante", "probability": p["away"]}]})
    return view


def build_report(data_dir, output_path=None, history_output=None) -> dict:
    rows, quality = read_matches(data_dir)
    splits = temporal_splits(rows)
    leagues, elo, evaluation = {}, {}, []
    recent = defaultdict(lambda: deque(maxlen=80))
    totals = defaultdict(lambda: {"n": 0, "brier": 0.0, "market_n": 0, "market_brier": 0.0})
    for day, day_rows in groupby(rows, lambda row: row["_day"]):
        group = list(day_rows)
        for row in group:
            key = (row["sport"], row["league"])
            if row["sport"] == "football":
                model = leagues.setdefault(key, LeaguePoisson())
                model.advance(day)
            else:
                model = elo.setdefault(key, EloModel(home_advantage=ELO_HOME_ADVANTAGE[row["sport"]]))
            if row["sport"] == "football":
                prediction = model.predict(row["home_team"], row["away_team"])
                if str(row.get("neutral_venue", "false")).lower() in ("true", "1", "yes"):
                    prediction["eligible"] = False
            else:
                neutral = str(row.get("neutral_venue", "false")).lower() in ("true", "1", "yes")
                prediction = model.predict(row["home_team"], row["away_team"], neutral)
            probabilities = ([prediction["home"], prediction["draw"], prediction["away"]]
                             if row["sport"] == "football" else [prediction["home"], prediction["away"]])
            market = _market(row)
            fold = _fold(day, splits[row["sport"]])
            record = {k: v for k, v in row.items() if not k.startswith("_")}
            record.update({"prediction": prediction, "probs": probabilities,
                           "market_probs": market["probabilities"] if market else None,
                           "overround": market["overround"] if market else None,
                           "odds": market["odds"] if market else None, "outcome": _outcome(row), "fold": fold})
            if prediction["eligible"]:
                recent[row["sport"]].append(record)
                if fold != "train": evaluation.append(record)
                if fold == "test" and row["sport"] == "football":
                    for name, key_p, won in [("over25", "over25", row["home_score"]+row["away_score"] > 2),
                                             ("btts", "btts_yes", row["home_score"] > 0 and row["away_score"] > 0)]:
                        item = totals[name]; item["n"] += 1; item["brier"] += (prediction[key_p]-won)**2
                        if name == "over25" and row.get("over25_odds") and row.get("under25_odds"):
                            mp = remove_margin([row["over25_odds"], row["under25_odds"]])["probabilities"][0]
                            item["market_n"] += 1; item["market_brier"] += (mp-won)**2
        # Strict date boundary: no result from this date is used above.
        for row in group:
            if row["sport"] == "football":
                if str(row.get("neutral_venue", "false")).lower() in ("true", "1", "yes"):
                    continue
                leagues[(row["sport"], row["league"])].update(row["home_team"], row["away_team"], row["home_score"], row["away_score"])
        for key, entries in groupby(sorted((r for r in group if r["sport"] != "football"), key=lambda r: (r["sport"], r["league"])), lambda r: (r["sport"], r["league"])):
            elo[key].update_batch(list(entries))

    test = [r for r in evaluation if r["fold"] == "test"]
    football_test = [r for r in test if r["sport"] == "football"]
    comparable = [r for r in football_test if r.get("market_probs")]
    skill = _paired_skill_ci(comparable)
    strategy = _strategy(football_test)
    trade_lookup = {t["id"]: t for t in strategy["trades"]}
    examples = sorted([r for records in recent.values() for r in records if r["fold"] == "test"], key=lambda r: (r["date"], r["id"]), reverse=True)
    decisions = [_decision(r, trade_lookup.get(r["id"]), skill) for r in examples]
    # Include settled paper examples even if recent dates contained no candidates.
    by_id = {r["id"]: r for r in football_test}
    included = {d["id"] for d in decisions}
    for trade in strategy["trades"][-100:]:
        if trade["id"] not in included:
            decisions.append(_decision(by_id[trade["id"]], trade, skill))
    decisions.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    if history_output:
        destination = Path(history_output); destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix+".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            for record in sorted(test, key=lambda r: (r["date"],r["id"]), reverse=True):
                stream.write(json.dumps(_decision(record, trade_lookup.get(record["id"]),skill),ensure_ascii=False,allow_nan=False)+"\n")
        temporary.replace(destination)
    sport_views, coverage = [], []
    for sport in sorted({r["sport"] for r in rows}):
        srows = [r for r in rows if r["sport"] == sport]
        stest = [r for r in test if r["sport"] == sport]
        coverage.append({"sport": sport, "rows": len(srows), "matches": len(srows),
                         "leagues": sorted({r["league"] for r in srows}),
                         "date_from": srows[0]["date"], "date_to": srows[-1]["date"],
                         "with_odds": sum(_market(r) is not None for r in srows),
                         "source_files": sorted({r["_file"] for r in srows}),
                         "status": "historical", "live_available": False})
        sport_views.append({"sport": sport, "name": {"football": "Fútbol", "basketball": "Básquet", "tennis": "Tenis","hockey":"Hockey","baseball":"Béisbol"}.get(sport, sport),
                            "matches": len(srows), "model": "Poisson regularizado" if sport == "football" else "Elo base",
                            "metrics": _metrics(stest), "market_metrics": _metrics(stest, True),
                            "period": splits[sport], "calibration": _calibration(stest),
                            "status": "research", "actionable": False})
    total_markets = {}
    for name, val in totals.items():
        total_markets[name] = {"n": val["n"], "brier_binary": val["brier"]/val["n"] if val["n"] else None,
                               "market_n": val["market_n"],
                               "market_brier_binary": val["market_brier"]/val["market_n"] if val["market_n"] else None,
                               "actionable": False,
                               "note": "Brier binario en 0–1; sin comparación de rentabilidad para este mercado."}
    overview = {"matches": len(rows), "historical_matches": len(rows), "sports": len(coverage),
                "leagues": len({(r["sport"],r["league"]) for r in rows}),
                "with_odds": sum(_market(r) is not None for r in rows), "live_opportunities": 0,
                "paper_bets": strategy["bets"], "paper_profit": strategy["profit"], "paper_roi": strategy["roi"],
                "bankroll": strategy["bankroll"], "max_drawdown": strategy["max_drawdown"],
                "model_status": "research", "ready_for_live": False,
                "date_from": rows[0]["date"] if rows else None, "date_to": rows[-1]["date"] if rows else None}
    backtest = {k:v for k,v in strategy.items() if k != "trades"}
    backtest.update({"metrics": _metrics(football_test), "model_metrics": _metrics(comparable),
                     "market_metrics": _metrics(comparable, True), "baseline": _metrics(comparable, True),
                     "period": splits.get("football", {}), "folds": splits,
                     "sample": len(football_test), "sample_size": len(football_test),
                     "paired_comparison": skill, "calibration": _calibration(football_test),
                     "market_calibration": _calibration(comparable, True), "other_markets": total_markets,
                     "validation_metrics": _metrics([r for r in evaluation if r["sport"] == "football" and r["fold"] == "validation"]),
                     "status": "historical_research", "validated_edge": False,
                     "gate_reason": "La revisión prospectiva y de ejecución sigue pendiente aunque alguna métrica histórica resulte favorable."})
    backtest["by_quote_snapshot"] = []
    for snapshot in sorted({str(r.get("odds_snapshot") or "unspecified") for r in comparable}):
        subset = [r for r in comparable if str(r.get("odds_snapshot") or "unspecified") == snapshot]
        backtest["by_quote_snapshot"].append({"snapshot":snapshot,"n":len(subset),
                                              "model_metrics":_metrics(subset),"market_metrics":_metrics(subset,True)})
    backtest["quote_sources"] = dict(Counter(r.get("odds_source") or "unavailable" for r in comparable))
    report = {
        "meta": {"generated_at": datetime.now(timezone.utc).isoformat(), "version": MODEL_VERSION,
                 "data_mode": "real_historical", "live_enabled": False, "is_simulation": True,
                 "title": "Sports Quant · laboratorio de probabilidades", "deterministic_seed": 271828,
                 "source_notice": "Resultados históricos reales; probabilidades calculadas y P&L hipotético. No se envían apuestas."},
        "overview": overview, "summary": overview, "sports": sport_views,
        "coverage": coverage, "datasets": coverage, "data_quality": quality,
        "opportunities": [], "decisions": decisions,
        "decision_history": {"total":len(test), "displayed":len(decisions),
                             "exported":bool(history_output),"format":"JSONL" if history_output else None},
        "predictions": [_prediction_view(r) for r in examples[:60]],
        "backtest": backtest, "calibration": backtest["calibration"],
        "model": {"version": MODEL_VERSION, "status": "research", "ready_for_live": False,
                  "football": {"name": "Poisson independiente regularizado", "prior_games": 10,
                               "half_life_days": 365, "minimum_league_matches": 120, "minimum_team_matches": 8,
                               "minimum_effective_team_matches": 6,
                               "goal_rate_clip": [0.15,4.5], "score_tail_minimum":16,
                               "known_neutral_venues": "excluded_from_training_and_evaluation; fixture_abstains",
                               "limitations": ["No usa alineaciones, lesiones, xG, clima ni fuerza explícita del calendario.",
                                               "Independencia de goles y tasas homogéneas son simplificaciones.",
                                               "No incluye corrección Dixon–Coles ni se presenta como ese modelo."]},
                  "basketball": {"name": "Elo base", "initial_rating":1500,"k":20,"home_advantage":65,
                                 "limitations": ["Sin ajuste por margen de victoria, plantel, descanso, era o playoffs.",
                                                 "Los históricos sin cuotas no permiten estimar retorno de apuestas."]},
                  "hockey": {"name":"Elo base de investigación","initial_rating":1500,"k":20,"home_advantage":35,
                             "target":"Ganador final, incluyendo prórroga y shootout", "actionable":False,
                             "limitations":["Ventaja local y K provisionales, sin optimización ni validación prospectiva.",
                                             "Sin cuotas históricas no se calcula ROI; no estima ganador en tiempo reglamentario."]},
                  "baseball": {"name":"Elo base de investigación","initial_rating":1500,"k":20,"home_advantage":25,
                               "target":"Ganador final, incluyendo extra innings", "actionable":False,
                               "limitations":["No utiliza pitcher abridor, lineup ni bullpen; K y ventaja local provisionales.",
                                               "Se conservan doubleheaders por game ID; sin cuotas históricas no se calcula ROI."]},
                  "risk": {"kelly_fraction":0.25,"event_cap":0.01,"day_cap":0.03,"minimum_ev":0.05,
                           "bankroll_units":1000,"one_selection_per_event":True,"live_stake":0},
                  "validation": {"split":"60/20/20 por fechas y deporte", "same_day_results_excluded":True,
                                 "online_updates":True,"hyperparameters_tuned_on_test":False,
                                 "market_skill_ci":skill,"prospective_validation_complete":False},
                  "first_goal": {"status":"exploratory_unvalidated", "actionable":False,
                                 "note":"Primer gol de equipo se deriva de tasas Poisson; no estima goleador individual ni minuto.",
                                 "requires":["Datos de eventos y alineaciones","Cuotas comparables con reglas idénticas","Backtest específico y prospectivo"]}},
        "providers": [], "sources": [],
        "alerts": [{"severity":"info","title":"Modo investigación", "message":"No hay cuotas en vivo verificadas ni apuestas enviadas."},
                   {"severity":"warning","title":"Ventaja pendiente de demostrar", "message":"Una probabilidad alta o EV estimado positivo no prueban una ventaja rentable."}],
    }
    if output_path:
        destination = Path(output_path); destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix+".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(destination)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--output", default="app/data/report.json")
    parser.add_argument("--history-output", default=None, help="Exportar todas las decisiones OOS test en JSONL.")
    args = parser.parse_args()
    report = build_report(args.data_dir, args.output,args.history_output)
    print(json.dumps({"output": args.output, "matches": report["overview"]["matches"],
                      "test_matches": report["backtest"]["sample"], "paper_bets":report["backtest"]["bets"],
                      "paper_roi":report["backtest"]["roi"], "ready_for_live":False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
