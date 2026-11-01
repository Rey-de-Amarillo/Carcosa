"""Small, dependency-free probability and risk primitives.

Every probability in this module is conditional on a statistical model. The
functions do not turn a model estimate into a known probability of winning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable


ELO_HOME_ADVANTAGE = {"basketball": 65.0, "hockey": 35.0, "baseball": 25.0, "tennis": 0.0}


def _probability(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("La probabilidad debe ser finita y estar entre 0 y 1.")
    return value


def decimal_odds(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 1:
        raise ValueError("La cuota decimal debe ser finita y mayor que 1.")
    return value


def remove_margin(odds: Iterable[float]) -> dict:
    """Proportional removal; this assumption does not estimate true probabilities."""
    values = [decimal_odds(o) for o in odds]
    if len(values) < 2:
        raise ValueError("Se necesitan todos los resultados mutuamente excluyentes.")
    implied = [1 / o for o in values]
    total = sum(implied)
    return {
        "probabilities": [p / total for p in implied],
        "implied_probabilities": implied,
        "overround": total - 1,
        "method": "proportional",
    }


def expected_value(probability: float, odds: float) -> float:
    """Expected net return per unit staked, before unmodelled execution costs."""
    return _probability(probability) * decimal_odds(odds) - 1


def kelly_fraction(probability: float, odds: float, fraction: float = 0.25,
                   cap: float = 0.01) -> float:
    if not 0 <= fraction <= 1 or not 0 <= cap <= 1:
        raise ValueError("Fracción de Kelly y límite deben estar entre 0 y 1.")
    odds = decimal_odds(odds)
    value = expected_value(probability, odds) / (odds - 1)
    return min(cap, max(0.0, value * fraction))


def probability_sensitivity(probability: float, effective_sample: float) -> dict:
    """A transparent sensitivity band, deliberately NOT a calibrated confidence CI.

    Team-match counts are not Bernoulli replications of a future match. The
    binomial-style radius is a conservative diagnostic and never a claim about
    frequentist coverage of the unknown true probability.
    """
    p = _probability(probability)
    radius = min(0.35, 1.96 * math.sqrt(max(p * (1 - p), 0.01) /
                                     max(1.0, effective_sample)))
    return {"low": max(0.0, p - radius), "high": min(1.0, p + radius),
            "method": "heuristic_sensitivity_not_calibrated",
            "label": "Banda de sensibilidad; no es un intervalo de confianza validado"}


def poisson_markets(home_rate: float, away_rate: float) -> dict:
    """Independent Poisson match scores, with explicit tail truncation reporting."""
    if any(not math.isfinite(r) or r <= 0 for r in (home_rate, away_rate)):
        raise ValueError("Las tasas de gol deben ser positivas y finitas.")
    if max(home_rate, away_rate) > 20:
        raise ValueError("Tasas fuera del dominio previsto para fútbol.")
    max_goals = max(16, int(max(home_rate, away_rate) +
                            9 * math.sqrt(max(home_rate, away_rate))))
    def masses(rate: float) -> list[float]:
        result = [math.exp(-rate)]
        for k in range(1, max_goals + 1):
            result.append(result[-1] * rate / k)
        return result
    hp, ap = masses(home_rate), masses(away_rate)
    retained_mass = sum(hp) * sum(ap)
    home = draw = away = over25 = btts = 0.0
    best = (0.0, 0, 0)
    for h, ph in enumerate(hp):
        for a, pa in enumerate(ap):
            p = ph * pa / retained_mass
            if h > a: home += p
            elif h == a: draw += p
            else: away += p
            if h + a > 2: over25 += p
            if h and a: btts += p
            if p > best[0]: best = (p, h, a)
    no_goal = math.exp(-home_rate - away_rate)
    return {
        "home": home, "draw": draw, "away": away,
        "over25": over25, "under25": 1 - over25,
        "btts_yes": btts, "btts_no": 1 - btts,
        "first_goal_home": home_rate / (home_rate + away_rate) * (1 - no_goal),
        "first_goal_away": away_rate / (home_rate + away_rate) * (1 - no_goal),
        "first_goal_none": no_goal,
        "expected_home_goals": home_rate, "expected_away_goals": away_rate,
        "most_likely_score": f"{best[1]}–{best[2]}",
        "most_likely_score_probability": best[0],
        "retained_probability_mass": retained_mass,
        "first_goal_assumption": "Procesos Poisson homogéneos e independientes; exploratorio sin validación por eventos.",
    }


@dataclass
class TeamGoals:
    hg: float = 0.0
    hf: float = 0.0
    ha: float = 0.0
    ag: float = 0.0
    af: float = 0.0
    aa: float = 0.0
    seen: int = 0

    def decay(self, factor: float) -> None:
        for key in ("hg", "hf", "ha", "ag", "af", "aa"):
            setattr(self, key, getattr(self, key) * factor)


@dataclass
class LeaguePoisson:
    """Venue-specific goal rates, shrinkage to league means, temporal decay.

    This is a baseline empirical-Bayes-style rate model, not a fitted Dixon–Coles
    implementation. Hyperparameters are fixed before the historical replay.
    """
    prior_games: float = 10.0
    half_life_days: float = 365.0
    teams: dict[str, TeamGoals] = field(default_factory=dict)
    games: float = 0.0
    home_goals: float = 0.0
    away_goals: float = 0.0
    seen: int = 0
    as_of: date | None = None
    last_result_date: date | None = None

    def advance(self, day: date) -> None:
        if self.as_of is not None:
            if day < self.as_of:
                raise ValueError("El modelo solo puede avanzar cronológicamente.")
            factor = 2 ** (-(day - self.as_of).days / self.half_life_days)
            self.games *= factor
            self.home_goals *= factor
            self.away_goals *= factor
            for team in self.teams.values(): team.decay(factor)
        self.as_of = day

    def predict(self, home: str, away: str) -> dict:
        h, a = self.teams.get(home, TeamGoals()), self.teams.get(away, TeamGoals())
        # Weak fixed league prior only matters before the warm-up threshold.
        base_h = (self.home_goals + 1.45 * 20) / (self.games + 20)
        base_a = (self.away_goals + 1.15 * 20) / (self.games + 20)
        k = self.prior_games
        home_attack = (h.hf + k * base_h) / (h.hg + k) / base_h
        away_defence = (a.aa + k * base_h) / (a.ag + k) / base_h
        away_attack = (a.af + k * base_a) / (a.ag + k) / base_a
        home_defence = (h.ha + k * base_a) / (h.hg + k) / base_a
        lh = min(4.5, max(0.15, base_h * home_attack * away_defence))
        la = min(4.5, max(0.15, base_a * away_attack * home_defence))
        markets = poisson_markets(lh, la)
        effective = min(h.hg + h.ag, a.hg + a.ag)
        markets.update({"sample_size": min(h.seen, a.seen),
                        "effective_sample_size": effective,
                        "league_sample_size": self.seen,
                        "eligible": self.seen >= 120 and min(h.seen, a.seen) >= 8 and effective >= 6,
                        "training_as_of": self.last_result_date.isoformat() if self.last_result_date else None,
                        "model": "poisson_regularized_v1"})
        return markets

    def update(self, home: str, away: str, home_goals: int, away_goals: int) -> None:
        h = self.teams.setdefault(home, TeamGoals())
        a = self.teams.setdefault(away, TeamGoals())
        h.hg += 1; h.hf += home_goals; h.ha += away_goals; h.seen += 1
        a.ag += 1; a.af += away_goals; a.aa += home_goals; a.seen += 1
        self.games += 1; self.home_goals += home_goals; self.away_goals += away_goals
        self.seen += 1
        self.last_result_date = self.as_of


@dataclass
class EloModel:
    ratings: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    k: float = 20.0
    home_advantage: float = 65.0

    def predict(self, home: str, away: str, neutral: bool = False) -> dict:
        home_rating, away_rating = self.ratings.get(home, 1500.0), self.ratings.get(away, 1500.0)
        advantage = 0 if neutral else self.home_advantage
        p = 1 / (1 + 10 ** ((away_rating - home_rating - advantage) / 400))
        n = min(self.counts.get(home, 0), self.counts.get(away, 0))
        return {"home": p, "away": 1 - p, "sample_size": n,
                "effective_sample_size": min(n, 100), "eligible": n >= 10,
                "home_rating": home_rating, "away_rating": away_rating,
                "model": "elo_baseline_v1"}

    def update_batch(self, matches: list[dict]) -> None:
        # All deltas are computed before any same-day result updates a rating.
        deltas: dict[str, float] = {}
        counts: dict[str, int] = {}
        for match in matches:
            h, a = match["home_team"], match["away_team"]
            result = 1.0 if match["home_score"] > match["away_score"] else 0.0
            neutral = str(match.get("neutral_venue", "false")).lower() in ("true", "1", "yes")
            delta = self.k * (result - self.predict(h, a, neutral)["home"])
            deltas[h] = deltas.get(h, 0.0) + delta
            deltas[a] = deltas.get(a, 0.0) - delta
            counts[h] = counts.get(h, 0) + 1; counts[a] = counts.get(a, 0) + 1
        for team, delta in deltas.items():
            self.ratings[team] = self.ratings.get(team, 1500.0) + delta
            self.counts[team] = self.counts.get(team, 0) + counts[team]


def proper_scores(probabilities: list[float], outcome: int) -> dict:
    if not probabilities or outcome not in range(len(probabilities)):
        raise ValueError("Resultado inválido.")
    for value in probabilities: _probability(value)
    if abs(sum(probabilities) - 1) > 1e-6:
        raise ValueError("Las probabilidades deben sumar 1.")
    return {"brier": sum((p - (i == outcome)) ** 2 for i, p in enumerate(probabilities)),
            "log_loss": -math.log(max(1e-12, probabilities[outcome])),
            "correct": int(max(range(len(probabilities)), key=probabilities.__getitem__) == outcome)}


def check_arbitrage(quotes: list[dict], bankroll: float = 100.0,
                    max_age_seconds: int = 30, max_skew_seconds: int = 5,
                    now: datetime | None = None) -> dict:
    """Only theoretical arbitrage for a complete, identical settlement contract.

    Required quote fields: event_id, market_id, line, period, rules_id,
    outcome, expected_outcomes, odds, captured_at, bookmaker.
    No bet is submitted. A detected price inequality is not a filled position.
    """
    if not quotes or bankroll <= 0 or not math.isfinite(bankroll):
        return {"is_arbitrage": False, "reason": "Cotizaciones o capital inválidos."}
    keys = ("event_id", "market_id", "line", "period", "rules_id")
    first = quotes[0]
    if any(k not in first for k in keys) or not first.get("rules_id"):
        return {"is_arbitrage": False, "reason": "Falta contrato de liquidación verificable."}
    if any(any(q.get(k) != first[k] for k in keys) for q in quotes):
        return {"is_arbitrage": False, "reason": "Eventos, líneas, períodos o reglas incompatibles."}
    expected = set(first.get("expected_outcomes", []))
    if len(expected) < 2 or any(set(q.get("expected_outcomes", [])) != expected for q in quotes):
        return {"is_arbitrage": False, "reason": "No se conoce el conjunto completo de resultados."}
    if {q.get("outcome") for q in quotes} != expected:
        return {"is_arbitrage": False, "reason": "Faltan resultados para cubrir el mercado."}
    best = {}
    times = []
    try:
        for q in quotes:
            decimal_odds(q["odds"])
            stamp = datetime.fromisoformat(q["captured_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None: raise ValueError("timestamp sin zona")
            times.append(stamp)
            if q["outcome"] not in best or q["odds"] > best[q["outcome"]]["odds"]:
                best[q["outcome"]] = q
        current = now or datetime.now(times[0].tzinfo)
        ages = [(current - stamp).total_seconds() for stamp in times]
        if min(ages) < -2 or max(ages) > max_age_seconds:
            return {"is_arbitrage": False, "reason": "Cotizaciones vencidas o con reloj inconsistente."}
        if (max(times) - min(times)).total_seconds() > max_skew_seconds:
            return {"is_arbitrage": False, "reason": "Cotizaciones sin sincronización suficiente."}
    except (ValueError, TypeError, KeyError):
        return {"is_arbitrage": False, "reason": "Cuotas o marcas de tiempo inválidas."}
    inverse = sum(1 / q["odds"] for q in best.values())
    if inverse >= 1:
        return {"is_arbitrage": False, "reason": "La suma de probabilidades implícitas no es menor que 1.",
                "inverse_sum": inverse}
    legs = [{"outcome": outcome, "bookmaker": q.get("bookmaker"), "odds": q["odds"],
             "stake": bankroll / (q["odds"] * inverse)} for outcome, q in best.items()]
    return {"is_arbitrage": True, "executable": False, "inverse_sum": inverse,
            "theoretical_return": 1 / inverse - 1, "theoretical_profit": bankroll * (1 / inverse - 1),
            "legs": legs, "reason": "Desigualdad teórica; falta confirmar límites, disponibilidad y ejecución de todas las patas."}


def canonical_sport(value: str) -> str:
    aliases = {"soccer": "football", "fútbol": "football", "futbol": "football",
               "basket": "basketball", "basquet": "basketball", "básquet": "basketball",
               "ice_hockey": "hockey", "ice hockey": "hockey", "nhl": "hockey", "mlb": "baseball",
               "béisbol": "baseball", "beisbol": "baseball"}
    return aliases.get(str(value).strip().lower(), str(value).strip().lower())


def predict_fixture(history_rows: list[dict], fixture: dict) -> dict:
    """Train an auditable baseline strictly before a requested fixture's date.

    A rating is never transported across leagues. Team identifiers must match
    the normalized provider identifiers; unknown teams trigger abstention.
    This helper is intentionally read-only and never fetches odds or places bets.
    """
    fixture_day = date.fromisoformat(str(fixture["date"])[:10])
    sport = canonical_sport(fixture.get("sport", "football"))
    league = fixture.get("league", "")
    rows = []
    for row in history_rows:
        if canonical_sport(row.get("sport", "football")) != sport or row.get("league", "") != league:
            continue
        try:
            day = date.fromisoformat(str(row["date"])[:10])
            hs, aws = int(float(row["home_score"])), int(float(row["away_score"]))
            if sport == "football" and str(row.get("neutral_venue", "false")).lower() in ("true", "1", "yes"):
                continue
            if sport in ELO_HOME_ADVANTAGE and hs == aws:
                continue
            if day < fixture_day and hs >= 0 and aws >= 0:
                rows.append({**row, "_day": day, "home_score": hs, "away_score": aws})
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    rows.sort(key=lambda row: (row["_day"], str(row.get("id", ""))))
    if sport == "football":
        model = LeaguePoisson()
        for row in rows:
            model.advance(row["_day"])
            model.update(row["home_team"], row["away_team"], row["home_score"], row["away_score"])
        model.advance(fixture_day)
        prediction = model.predict(fixture["home_team"], fixture["away_team"])
    elif sport in ELO_HOME_ADVANTAGE:
        model = EloModel(home_advantage=ELO_HOME_ADVANTAGE[sport])
        from itertools import groupby
        for _, group in groupby(rows, lambda row: row["_day"]):
            model.update_batch(list(group))
        neutral = str(fixture.get("neutral_venue", "false")).lower() in ("true", "1", "yes")
        prediction = model.predict(fixture["home_team"], fixture["away_team"], neutral)
    else:
        return {"eligible": False, "model": None, "reasons": ["Deporte sin modelo implementado."]}
    last = rows[-1]["_day"] if rows else None
    age = (fixture_day - last).days if last else None
    reasons = []
    neutral_football = sport == "football" and str(fixture.get("neutral_venue", "false")).lower() in ("true", "1", "yes")
    if neutral_football:
        prediction["eligible"] = False
        reasons.append("Cancha neutral: el baseline Poisson por localía no está validado para este contexto.")
    if not prediction.get("eligible"):
        reasons.append("Historial insuficiente de la liga o de alguno de los participantes.")
    if age is None or age > 45:
        reasons.append("El historial está desactualizado para una decisión actual.")
    prediction.update({"training_max_date": last.isoformat() if last else None,
                       "model_age_days": age, "sport": sport, "league": league,
                       "neutral_venue_unsupported": neutral_football,
                       "reasons": reasons, "ready_for_live": False,
                       "live_block_reason": "Modelo de investigación; requiere validación temporal y cotización verificable."})
    if sport == "hockey": prediction["model_target"] = "winner_including_overtime_and_shootout"
    if sport == "baseball": prediction["model_target"] = "winner_including_extra_innings"
    return prediction
