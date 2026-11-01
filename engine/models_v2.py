"""Opponent-adjusted dynamic football scores, using only the Python stdlib.

This is an explicitly approximate regularized Poisson fit, not a reproduction
of the MLE or betting returns in Dixon & Coles (1997). Hyperparameters belong
to a development protocol; a good retrospective score is not a verified edge.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime
from itertools import groupby


def _day(value) -> date:
    return value.date() if isinstance(value, datetime) else value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _finite_positive(value, name):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} debe ser positivo y finito")
    return value


def score_grid(home_rate: float, away_rate: float, rho: float = 0.0,
               max_goals: int | None = None) -> dict:
    """Normalized Dixon–Coles score grid and an explicit retained-tail mass.

    ``rho`` is clamped to the admissible interval for THESE rates, keeping all
    four low-score correction factors positive. A fitted league rho is not
    guaranteed admissible for a new, unusually mismatched fixture.
    """
    lh = _finite_positive(home_rate, "home_rate")
    la = _finite_positive(away_rate, "away_rate")
    rho = float(rho)
    if max(lh, la) > 20 or not math.isfinite(rho):
        raise ValueError("Tasas/rho fuera del dominio del modelo")
    if max_goals is None:
        max_goals = max(16, int(max(lh, la) + 10 * math.sqrt(max(lh, la))))
    if isinstance(max_goals, bool) or int(max_goals) != max_goals or not 2 <= max_goals <= 128:
        raise ValueError("max_goals debe ser un entero entre 2 y 128")
    lower = max(-1 / lh, -1 / la) + 1e-12
    upper = min(1.0, 1 / (lh * la)) - 1e-12
    applied = max(lower, min(upper, rho))

    def masses(rate):
        values = [math.exp(-rate)]
        for k in range(1, int(max_goals) + 1):
            values.append(values[-1] * rate / k)
        return values

    hp, ap = masses(lh), masses(la)
    grid = [[ph * pa for pa in ap] for ph in hp]
    grid[0][0] *= 1 - lh * la * applied
    grid[0][1] *= 1 + lh * applied
    grid[1][0] *= 1 + la * applied
    grid[1][1] *= 1 - applied
    mass = sum(map(sum, grid))
    if mass <= 0 or not math.isfinite(mass):
        raise ValueError("La cuadrícula no tiene masa válida")
    grid = [[p / mass for p in row] for row in grid]
    home = draw = away = over25 = btts = 0.0
    best = (0.0, 0, 0)
    for h, row in enumerate(grid):
        for a, p in enumerate(row):
            if h > a: home += p
            elif h == a: draw += p
            else: away += p
            if h + a > 2: over25 += p
            if h and a: btts += p
            if p > best[0]: best = (p, h, a)
    return {"grid": grid, "home_rate": lh, "away_rate": la,
            "expected_home_goals": lh, "expected_away_goals": la,
            "rho_requested": rho, "rho_applied": applied,
            "retained_probability_mass": mass,
            "home": home, "draw": draw, "away": away,
            "over25": over25, "under25": 1 - over25,
            "btts_yes": btts, "btts_no": 1 - btts,
            "most_likely_score": f"{best[1]}–{best[2]}",
            "most_likely_score_probability": best[0]}


class OnlineGoalsV2:
    """Joint attack/defence fit on past results, refreshed every 14 days.

    Model: lambda_home = base_home * attack_home * defence_away, and the
    symmetric away expression. Parameters are fitted jointly by alternating
    conditional Poisson updates with Gamma shrinkage towards one. Ratings use
    both venues, so a team is not estimated from only half its previous games.

    The output grid uses a low-score rho learned from the same PAST fitting
    window, with a strong zero-centred penalty. Neutral fixtures abstain: the
    home/away intercepts have not been validated for neutral tournaments.
    """

    def __init__(self, prior_strength: float = 12.0,
                 half_life_days: float = 365.0, refit_days: int = 14,
                 rho_mode: str = "fitted", window_days: int = 1095,
                 fit_iterations: int = 12):
        self.prior_strength = _finite_positive(prior_strength, "prior_strength")
        self.half_life_days = _finite_positive(half_life_days, "half_life_days")
        if refit_days < 1 or window_days < 30 or fit_iterations < 1:
            raise ValueError("Intervalos/iteraciones inválidos")
        if rho_mode not in ("fitted", "independent"):
            raise ValueError("rho_mode debe ser fitted o independent")
        self.refit_days = int(refit_days)
        self.window_days = int(window_days)
        self.fit_iterations = int(fit_iterations)
        self.rho_mode = rho_mode
        self.history = []
        self.attack, self.defence = {}, {}
        self.base_home, self.base_away = 1.45, 1.15
        self.rho = 0.0
        self.counts, self.effective_counts = Counter(), {}
        self.last_result_date = self.last_fit_date = self.as_of = self.last_batch_date = None
        self.fit_training_max_date = None
        self.fit_history_size = 0

    @staticmethod
    def canonicalize(attack, defence, bh, ba):
        """Resolve factor scaling without changing any predicted intensity."""
        if not attack:
            return dict(attack), dict(defence), bh, ba
        am = math.exp(sum(math.log(v) for v in attack.values()) / len(attack))
        dm = math.exp(sum(math.log(v) for v in defence.values()) / len(defence))
        return ({k: v / am for k, v in attack.items()},
                {k: v / dm for k, v in defence.items()}, bh * am * dm, ba * am * dm)

    def _fit(self, day):
        window = [(h, a, hg, ag, 2 ** (-(day - d).days / self.half_life_days), d)
                  for d, h, a, hg, ag in self.history if (day-d).days <= self.window_days]
        if not window:
            self.last_fit_date = day
            return
        teams = {x for h, a, *_ in window for x in (h, a)}
        attack = {t: self.attack.get(t, 1.0) for t in teams}
        defence = {t: self.defence.get(t, 1.0) for t in teams}
        gf, ga, counts, effective = Counter(), Counter(), Counter(), Counter()
        total_h = total_a = exposure = 0.0
        for h, a, hg, ag, w, _ in window:
            gf[h] += w * hg; gf[a] += w * ag
            ga[h] += w * ag; ga[a] += w * hg
            counts[h] += 1; counts[a] += 1
            effective[h] += w; effective[a] += w
            total_h += w * hg; total_a += w * ag; exposure += w
        bh, ba = self.base_home, self.base_away
        k = self.prior_strength
        for _ in range(self.fit_iterations):
            expected = Counter()
            for h, a, _, _, w, _ in window:
                expected[h] += w * bh * defence[a]
                expected[a] += w * ba * defence[h]
            attack = {t: (gf[t] + k) / (expected[t] + k) for t in teams}
            expected = Counter()
            for h, a, _, _, w, _ in window:
                expected[a] += w * bh * attack[h]
                expected[h] += w * ba * attack[a]
            defence = {t: (ga[t] + k) / (expected[t] + k) for t in teams}
            exp_h = sum(w * attack[h] * defence[a] for h, a, _, _, w, _ in window)
            exp_a = sum(w * attack[a] * defence[h] for h, a, _, _, w, _ in window)
            bh = (total_h + 10 * 1.45) / (exp_h + 10)
            ba = (total_a + 10 * 1.15) / (exp_a + 10)
        attack, defence, bh, ba = self.canonicalize(attack, defence, bh, ba)
        self.attack, self.defence = attack, defence
        self.base_home, self.base_away = bh, ba
        self.counts, self.effective_counts = counts, effective
        self.fit_history_size, self.last_fit_date = len(window), day
        self.fit_training_max_date = max(item[-1] for item in window)
        self.rho = self._fit_rho(window) if self.rho_mode == "fitted" else 0.0
        # Retain sufficient history, including a small margin for the next fit.
        self.history = [r for r in self.history if (day-r[0]).days <= self.window_days]

    def _rates(self, home, away):
        return (min(5.0, max(.12, self.base_home * self.attack.get(home, 1.) * self.defence.get(away, 1.))),
                min(5.0, max(.12, self.base_away * self.attack.get(away, 1.) * self.defence.get(home, 1.))))

    def _fit_rho(self, window):
        terms = []
        lo, hi = -.18, .12
        for h, a, hg, ag, w, _ in window:
            lh, la = self._rates(h, a)
            lo = max(lo, -1/lh + 1e-8, -1/la + 1e-8)
            hi = min(hi, 1/(lh*la) - 1e-8)
            if hg == 0 and ag == 0: terms.append((-lh*la, w))
            elif hg == 0 and ag == 1: terms.append((lh, w))
            elif hg == 1 and ag == 0: terms.append((la, w))
            elif hg == 1 and ag == 1: terms.append((-1., w))
        rho = 0.0
        if not terms or lo >= hi:
            return rho
        # Gaussian penalty precision 30 reduces unstable low-score estimates.
        for _ in range(8):
            g = sum(w * a/(1+a*rho) for a, w in terms) - 30*rho
            curvature = sum(w*a*a/(1+a*rho)**2 for a, w in terms) + 30
            step = g/curvature
            candidate = min(hi, max(lo, rho+step))
            if abs(candidate-rho) < 1e-8: break
            rho = candidate
        return rho

    def predict(self, home, away, date, neutral=False):
        day = _day(date)
        if not home or not away or home == away:
            raise ValueError("Participantes inválidos")
        if self.last_batch_date is not None and day <= self.last_batch_date:
            raise ValueError("Una predicción sólo puede usar resultados de fechas anteriores")
        if self.as_of is not None and day < self.as_of:
            raise ValueError("No se puede retroceder el reloj del modelo")
        self.as_of = day
        stale_fit_with_new_results = (self.fit_training_max_date is not None
                                     and (day-self.fit_training_max_date).days > 45
                                     and self.last_result_date > self.fit_training_max_date)
        if self.last_fit_date is None or (day-self.last_fit_date).days >= self.refit_days or stale_fit_with_new_results:
            self._fit(day)
        lh, la = self._rates(home, away)
        result = score_grid(lh, la, self.rho)
        # Effective counts decay between fits; the model never gains evidence
        # merely because the next fixture has a later date.
        decay = 2 ** (-(day-self.last_fit_date).days/self.half_life_days) if self.last_fit_date else 1.
        n = min(self.counts.get(home, 0), self.counts.get(away, 0))
        effective = min(self.effective_counts.get(home, 0), self.effective_counts.get(away, 0)) * decay
        age = (day-self.fit_training_max_date).days if self.fit_training_max_date else None
        neutral = str(neutral).lower() in ("true", "1", "yes")
        reasons = []
        if self.fit_history_size < 120 or n < 8 or effective < 6:
            reasons.append("Historial previo insuficiente de la liga o participantes")
        if age is None or age > 45:
            reasons.append("Historial desactualizado para una decisión actual")
        if neutral:
            reasons.append("Cancha neutral sin modelo específico validado")
        result.update({"model": "opponent_adjusted_poisson_dc_v2" if self.rho_mode == "fitted" else "opponent_adjusted_poisson_v2",
                       "sample_size": n, "effective_sample_size": effective,
                       "league_sample_size": self.fit_history_size, "eligible": not reasons,
                       "training_max_date": self.fit_training_max_date.isoformat() if self.fit_training_max_date else None,
                       "training_as_of": self.fit_training_max_date.isoformat() if self.fit_training_max_date else None,
                       "observed_results_max_date": self.last_result_date.isoformat() if self.last_result_date else None,
                       "parameter_fit_date": self.last_fit_date.isoformat() if self.last_fit_date else None,
                       "model_age_days": age, "neutral_venue_unsupported": neutral,
                       "reasons": reasons, "ready_for_live": False})
        return result

    def update_batch(self, rows):
        if not rows:
            return
        days = {_day(r["date"]) for r in rows}
        if len(days) != 1:
            raise ValueError("El lote debe contener una sola fecha")
        day = next(iter(days))
        if self.last_batch_date is not None and day <= self.last_batch_date:
            raise ValueError("Los resultados deben llegar en fechas estrictamente crecientes")
        if self.as_of is not None and day < self.as_of:
            raise ValueError("No se pueden actualizar resultados después de mirar una fecha posterior")
        accepted = []
        for row in rows:
            if str(row.get("neutral_venue", "false")).lower() in ("true", "1", "yes"):
                continue
            h, a = row["home_team"], row["away_team"]
            hs, aws = float(row["home_score"]), float(row["away_score"])
            if h == a or not h or not a or any(not math.isfinite(v) or v < 0 or int(v) != v for v in (hs, aws)):
                raise ValueError("Partido o marcador inválido")
            accepted.append((day, h, a, int(hs), int(aws)))
        self.history.extend(accepted)
        self.last_batch_date = day
        if accepted:
            self.last_result_date = day
        self.as_of = day


def replay_predictions(rows, config=None, include_grid=False):
    """Yield prior-only predictions per id, with separate state for every league.

    Input order does not change the result. Each complete date is predicted
    before any result for that date is assimilated. The default avoids keeping
    millions of redundant grid cells in a research cache.
    """
    ordered = sorted((r for r in rows if r.get("sport", "football") in ("football", "soccer")),
                     key=lambda r: (str(r["date"])[:10], r.get("league", ""), str(r.get("id", ""))))
    models = {}
    for day, day_rows in groupby(ordered, lambda r: str(r["date"])[:10]):
        group = list(day_rows)
        league_rows = defaultdict(list)
        for row in group:
            league = row.get("league", "")
            if league not in models:
                models[league] = OnlineGoalsV2(**(config or {}))
            model = models[league]
            prediction = model.predict(row["home_team"], row["away_team"], day, row.get("neutral_venue", False))
            if not include_grid:
                prediction.pop("grid", None)
            yield {"id": row.get("id"), "date": day, "league": league, "prediction": prediction}
            league_rows[league].append(row)
        for league, entries in league_rows.items():
            models[league].update_batch(entries)
