#!/usr/bin/env python3
"""Temporal 1X2 expected-value research; actual Bet365 columns, prior-date data only.

Run: OPENBLAS_NUM_THREADS=1 python3 scripts/research_result_ev.py
The four candidates and thresholds below are fixed before the 2022+ evaluation.
No current-match statistics, supplied Elo/form fields, maximum prices or ROI tuning.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date
from itertools import groupby
from pathlib import Path

if Path('/tmp/football-portfolio-scipy').is_dir():
    sys.path.insert(0, '/tmp/football-portfolio-scipy')
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'data/raw/club_football_match_data/Matches.csv'
OUT = ROOT / 'data/analysis/research_result_ev.json'
TRADES = ROOT / 'data/analysis/research_result_ev_trades.jsonl'
MIN_HISTORY = 8
THRESHOLDS = (0.0, 0.03, 0.05)
CANDIDATES = (
    ('market_no_vig', 'baseline', 0.0),
    ('price_calibration', 'price', 0.001),
    ('odds_prior_team_weak_penalty', 'conditional', 0.001),
    ('odds_prior_team_strong_penalty', 'conditional', 0.01),
)
FEATURE_NAMES = [
    'log_p_home_over_away', 'log_p_draw_over_away',
    'log_p_home_over_away_squared', 'log_p_draw_over_away_squared', 'overround',
    'own_online_elo_difference', 'form5_points_difference', 'form10_points_difference',
    'form5_goal_difference_difference', 'form10_goals_scored_difference',
    'form10_goals_conceded_difference', 'venue_points_difference',
    'venue_goals_scored_difference', 'venue_goals_conceded_difference',
    'home_attack_vs_away_defense', 'away_attack_vs_home_defense',
    'log_rest_difference', 'home_log_rest', 'away_log_rest',
    'home_log_prior_count', 'away_log_prior_count',
    'league_home_goals', 'league_away_goals', 'league_home_win_rate', 'league_draw_rate',
]


@dataclass
class Match:
    day: date
    division: str
    home: str
    away: str
    hg: int
    ag: int
    odds: tuple[float, float, float] | None
    source_row: int

    @property
    def target(self):
        return 0 if self.hg > self.ag else 1 if self.hg == self.ag else 2


@dataclass
class Team:
    elo: float = 1500.0
    history: deque = field(default_factory=lambda: deque(maxlen=10))
    home_history: deque = field(default_factory=lambda: deque(maxlen=10))
    away_history: deque = field(default_factory=lambda: deque(maxlen=10))
    n: int = 0
    last_day: date | None = None


@dataclass
class League:
    n: int = 0
    hg: int = 0
    ag: int = 0
    home_wins: int = 0
    draws: int = 0


def read_matches(path=INPUT):
    matches, rejected, seen = [], defaultdict(int), set()
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        for source_row, row in enumerate(csv.DictReader(f), 2):
            try:
                day = date.fromisoformat(row['MatchDate'])
                hg, ag = float(row['FTHome']), float(row['FTAway'])
                if not (hg.is_integer() and ag.is_integer() and hg >= 0 and ag >= 0):
                    raise ValueError('invalid score')
                key = (day, row['Division'], row['HomeTeam'], row['AwayTeam'])
                if key in seen:
                    rejected['duplicate_fixture'] += 1
                    continue
                seen.add(key)
                target = 'H' if hg > ag else 'D' if hg == ag else 'A'
                if row['FTResult'] != target:
                    rejected['inconsistent_result'] += 1
                    continue
                odds = None
                try:
                    value = tuple(float(row[k]) for k in ('OddHome', 'OddDraw', 'OddAway'))
                    if all(math.isfinite(v) and v > 1 for v in value):
                        margin = sum(1 / v for v in value) - 1
                        if 0 <= margin <= .25:
                            odds = value
                        else:
                            rejected['quote_group_outside_zero_to_25pct_margin'] += 1
                except ValueError:
                    pass
                matches.append(Match(day, row['Division'], row['HomeTeam'], row['AwayTeam'], int(hg), int(ag), odds, source_row))
            except (ValueError, TypeError, KeyError):
                rejected['missing_or_invalid_outcome'] += 1
    return sorted(matches, key=lambda x: (x.day, x.division, x.home, x.away)), dict(rejected)


def prior_mean(history, col, prior, length=10, strength=4.0):
    items = list(history)[-length:]
    return (sum(x[col] for x in items) + strength * prior) / (len(items) + strength)


def match_features(match, home, away, league):
    """Only the caller's state enters features; the current result is never read."""
    odds = np.asarray(match.odds, dtype=float)
    implied = 1 / odds
    market = implied / implied.sum()
    lh, ld = np.log(market[:2] / market[2])
    lg_h = (league.hg + 100 * 1.5) / (league.n + 100)
    lg_a = (league.ag + 100 * 1.15) / (league.n + 100)
    avg_g = (lg_h + lg_a) / 2
    hp5 = prior_mean(home.history, 0, 1.35, 5)
    ap5 = prior_mean(away.history, 0, 1.35, 5)
    hp10 = prior_mean(home.history, 0, 1.35)
    ap10 = prior_mean(away.history, 0, 1.35)
    hgf = prior_mean(home.history, 1, avg_g)
    agf = prior_mean(away.history, 1, avg_g)
    hga = prior_mean(home.history, 2, avg_g)
    aga = prior_mean(away.history, 2, avg_g)
    hvgf = prior_mean(home.home_history, 1, lg_h)
    avgf = prior_mean(away.away_history, 1, lg_a)
    hvga = prior_mean(home.home_history, 2, lg_a)
    avga = prior_mean(away.away_history, 2, lg_h)
    hrest = math.log(min(60, max(1, (match.day - home.last_day).days)) if home.last_day else 7)
    arest = math.log(min(60, max(1, (match.day - away.last_day).days)) if away.last_day else 7)
    hg5 = prior_mean(home.history, 1, avg_g, 5) - prior_mean(home.history, 2, avg_g, 5)
    ag5 = prior_mean(away.history, 1, avg_g, 5) - prior_mean(away.history, 2, avg_g, 5)
    features = [
        lh, ld, lh * lh, ld * ld, implied.sum() - 1,
        (home.elo - away.elo + 65) / 400,
        hp5 - ap5, hp10 - ap10, hg5 - ag5, hgf - agf, hga - aga,
        prior_mean(home.home_history, 0, 1.6) - prior_mean(away.away_history, 0, 1.1),
        hvgf - avgf, hvga - avga, hvgf - avga, avgf - hvga,
        hrest - arest, hrest, arest, math.log1p(home.n), math.log1p(away.n),
        lg_h, lg_a, (league.home_wins + 45) / (league.n + 100),
        (league.draws + 27) / (league.n + 100),
    ]
    return features, market


def build_dataset(matches):
    teams, leagues = defaultdict(Team), defaultdict(League)
    xs, ps, ys, os, meta = [], [], [], [], []
    divisions = sorted({m.division for m in matches})
    div_index = {d: i for i, d in enumerate(divisions)}
    for day, group in groupby(matches, key=lambda m: m.day):
        batch = list(group)
        # Whole date is predicted before ANY result from this date enters state.
        for m in batch:
            h, a = teams[(m.division, m.home)], teams[(m.division, m.away)]
            if m.odds is not None and min(h.n, a.n) >= MIN_HISTORY:
                features, p = match_features(m, h, a, leagues[m.division])
                indicator = [0.] * len(divisions)
                indicator[div_index[m.division]] = 1.
                xs.append(features + indicator)
                ps.append(p)
                ys.append(m.target)
                os.append(m.odds)
                meta.append({'date': day.isoformat(), 'division': m.division, 'home': m.home, 'away': m.away,
                             'home_prior_matches': h.n, 'away_prior_matches': a.n, 'source_row': m.source_row})
        elo_changes = defaultdict(float)
        for m in batch:
            h, a = teams[(m.division, m.home)], teams[(m.division, m.away)]
            expected_home = 1 / (1 + 10 ** ((a.elo - h.elo - 65) / 400))
            actual_home = 1. if m.hg > m.ag else .5 if m.hg == m.ag else 0.
            change = 20 * (actual_home - expected_home)
            elo_changes[(m.division, m.home)] += change
            elo_changes[(m.division, m.away)] -= change
        for m in batch:
            h, a = teams[(m.division, m.home)], teams[(m.division, m.away)]
            hp = 3 if m.hg > m.ag else 1 if m.hg == m.ag else 0
            ap = 3 if m.ag > m.hg else 1 if m.hg == m.ag else 0
            h.history.append((hp, m.hg, m.ag)); h.home_history.append((hp, m.hg, m.ag))
            a.history.append((ap, m.ag, m.hg)); a.away_history.append((ap, m.ag, m.hg))
            h.n += 1; a.n += 1
            h.last_day = a.last_day = day
            league = leagues[m.division]
            league.n += 1; league.hg += m.hg; league.ag += m.ag
            league.home_wins += m.hg > m.ag; league.draws += m.hg == m.ag
        for key, change in elo_changes.items():
            teams[key].elo += change
    return np.asarray(xs), np.asarray(ps), np.asarray(ys), np.asarray(os), meta, FEATURE_NAMES + ['league_' + d for d in divisions]


def fit_model(x, market, y, mode, penalty):
    if mode == 'baseline':
        return {'mode': mode}
    indices = list(range(5)) if mode == 'price' else list(range(x.shape[1]))
    raw = x[:, indices]
    mean, scale = raw.mean(axis=0), raw.std(axis=0)
    scale[scale < 1e-8] = 1
    design = np.column_stack((np.ones(len(raw)), (raw - mean) / scale))
    offset = np.log(market)
    n, k = design.shape
    target = np.eye(3)[y]
    def objective(flat):
        weight = flat.reshape(k, 2)
        logits = offset.copy()
        logits[:, :2] += design @ weight
        normalizer = logsumexp(logits, axis=1)
        loss = (normalizer - logits[np.arange(n), y]).mean() + .5 * penalty * (weight[1:] ** 2).sum()
        probabilities = np.exp(logits - normalizer[:, None])
        grad = design.T @ (probabilities[:, :2] - target[:, :2]) / n
        grad[1:] += penalty * weight[1:]
        return float(loss), grad.ravel()
    fit = minimize(objective, np.zeros(k * 2), method='L-BFGS-B', jac=True,
                   options={'maxiter': 180, 'ftol': 1e-10, 'gtol': 1e-7})
    return {'mode': mode, 'penalty': penalty, 'indices': indices, 'mean': mean.tolist(), 'scale': scale.tolist(),
            'weights': fit.x.reshape(k, 2).tolist(), 'converged': bool(fit.success), 'optimizer': str(fit.message),
            'iterations': int(fit.nit)}


def predict(model, x, market):
    if model['mode'] == 'baseline':
        return market.copy()
    raw = x[:, model['indices']]
    design = np.column_stack((np.ones(len(x)), (raw - model['mean']) / model['scale']))
    logits = np.log(market)
    logits[:, :2] += design @ np.asarray(model['weights'])
    return np.exp(logits - logsumexp(logits, axis=1)[:, None])


def scores(p, y):
    return {'matches': len(y), 'logloss': float(-np.log(p[np.arange(len(y)), y]).mean()),
            'brier_multiclass': float(np.square(p - np.eye(3)[y]).sum(axis=1).mean())}


def choose_bets(p, odds, y, meta, threshold):
    ev = p * odds - 1
    allowed = (odds >= 1.2) & (odds <= 5)
    # An underround triplet cannot establish a conditional forecasting edge.
    # Quarantine malformed/special-price groups, rather than claim their anomaly
    # as model skill (the archive contains River 2.39 / draw 5.72 / Arsenal 10.84).
    margin = (1 / odds).sum(axis=1) - 1
    allowed &= ((margin >= 0) & (margin <= .25))[:, None]
    ev = np.where(allowed, ev, -np.inf)
    chosen = ev.argmax(axis=1)
    rows = np.arange(len(p))
    use = ev[rows, chosen] >= threshold - 1e-12
    trades = []
    for i in np.flatnonzero(use):
        k = int(chosen[i])
        won = int(y[i] == k)
        price = float(odds[i, k])
        probability = float(p[i, k])
        trades.append({**meta[i], 'selection': ('H', 'D', 'A')[k], 'odds': price,
                       'model_probability': probability, 'break_even_probability': 1 / price,
                       'expected_profit_per_unit': probability * price - 1,
                       'won': won, 'profit': price * won - 1,
                       # Haircut changes the payout, not selected trades or probabilities.
                       'profit_after_1pct_odds_haircut': price * .99 * won - 1})
    return trades


def trade_summary(trades, bootstrap=4000):
    if not trades:
        return {'bets': 0, 'profit_units': 0., 'roi': None, 'positive_expected_value_supported': False}
    profit = np.asarray([t['profit'] for t in trades])
    by_month = defaultdict(lambda: [0., 0])
    by_year = defaultdict(list)
    for t in trades:
        by_month[t['date'][:7]][0] += t['profit']
        by_month[t['date'][:7]][1] += 1
        by_year[t['date'][:4]].append(t)
    blocks = np.asarray(list(by_month.values()))
    rng = np.random.default_rng(20261030)
    sampled = rng.integers(0, len(blocks), size=(bootstrap, len(blocks)))
    aggregate = blocks[sampled].sum(axis=1)
    enough_blocks = len(blocks) >= 12
    ci = np.quantile(aggregate[:, 0] / aggregate[:, 1], [.025, .975]).tolist() if enough_blocks else None
    calibration = []
    for lo, hi in zip(np.arange(0, 1, .1), np.arange(.1, 1.01, .1)):
        group = [t for t in trades if lo <= t['model_probability'] < hi + (1e-12 if hi > .99 else 0)]
        if group:
            calibration.append({'probability_bin': [float(lo), float(hi)], 'bets': len(group),
                                'mean_model_probability': sum(t['model_probability'] for t in group) / len(group),
                                'observed_win_rate': sum(t['won'] for t in group) / len(group)})
    result = {'bets': len(trades), 'wins': sum(t['won'] for t in trades),
              'hit_rate': sum(t['won'] for t in trades) / len(trades),
              'mean_break_even_probability': sum(t['break_even_probability'] for t in trades) / len(trades),
              'mean_predicted_probability': sum(t['model_probability'] for t in trades) / len(trades),
              'mean_odds': sum(t['odds'] for t in trades) / len(trades),
              'predicted_ev': sum(t['expected_profit_per_unit'] for t in trades) / len(trades),
              'profit_units': float(profit.sum()), 'roi': float(profit.mean()),
              'roi_month_cluster_bootstrap95': ci,
              'active_month_clusters': len(blocks),
              'roi_after_1pct_odds_haircut': sum(t['profit_after_1pct_odds_haircut'] for t in trades) / len(trades),
              'positive_expected_value_supported': bool(ci is not None and ci[0] > 0 and len(trades) >= 100 and len(by_year) >= 2),
              'by_year': {y: {'bets': len(ts), 'profit_units': sum(t['profit'] for t in ts),
                              'roi': sum(t['profit'] for t in ts) / len(ts)} for y, ts in sorted(by_year.items())},
              'selected_bet_calibration': calibration}
    return result


def run():
    matches, rejected = read_matches()
    x, market, y, odds, meta, names = build_dataset(matches)
    dates = np.asarray([m['date'] for m in meta])
    train = dates < '2018-01-01'
    val = (dates >= '2018-01-01') & (dates < '2022-01-01')
    test = dates >= '2022-01-01'
    candidates, models = {}, {}
    print(json.dumps({'stage': 'features_built', 'matches': len(matches), 'eligible': len(y),
                      'train': int(train.sum()), 'validation': int(val.sum()), 'test': int(test.sum())}), flush=True)
    for name, mode, penalty in CANDIDATES:
        model = fit_model(x[train], market[train], y[train], mode, penalty)
        pred = predict(model, x[val], market[val])
        candidates[name] = {'validation': scores(pred, y[val]), 'model': model}
        models[name] = model
        print(json.dumps({'stage': 'candidate', 'name': name, **candidates[name]['validation']}), flush=True)
    selected = min(candidates, key=lambda key: candidates[key]['validation']['logloss'])
    specification = next(c for c in CANDIDATES if c[0] == selected)
    final = fit_model(x[train | val], market[train | val], y[train | val], specification[1], specification[2])
    p = predict(final, x[test], market[test])
    test_meta = [m for m, use in zip(meta, test) if use]
    thresholds, trades = {}, {}
    for threshold in THRESHOLDS:
        selected_trades = choose_bets(p, odds[test], y[test], test_meta, threshold)
        thresholds[str(threshold)] = trade_summary(selected_trades)
        trades[threshold] = selected_trades
    primary = trades[.03]
    # Coefficients in this file make every final test prediction reproducible.
    report = {
        'schema': 'football-conditional-result-ev-v1',
        'source': {'file': str(INPUT.relative_to(ROOT)), 'sha256': hashlib.sha256(INPUT.read_bytes()).hexdigest(),
                   'odds_columns': ['OddHome', 'OddDraw', 'OddAway'], 'bookmaker': 'Bet365 (archive label)',
                   'scored_matches': len(matches), 'rejected': rejected},
        'protocol': {'train': ['2000-01-01', '2017-12-31'], 'validation': ['2018-01-01', '2021-12-31'],
                     'final_test': ['2022-01-01', max(m['date'] for m in test_meta)],
                     'selection_metric': 'validation multiclass logloss, never profit',
                     'refit': 'selected specification refitted through 2021-12-31; fixed coefficients throughout final test',
                     'feature_updates': 'only scores from dates strictly before prediction; state updates after whole-date batch',
                     'min_prior_matches_each_team': MIN_HISTORY, 'elo_k': 20, 'elo_home_advantage_points': 65,
                     'primary_ev': .03, 'ev_sensitivities': list(THRESHOLDS), 'odds_range': [1.2, 5.],
                     'quote_group_quality': 'exclude whole 1X2 group if overround outside [0,0.25]; still use its final score for later team state',
                     'positive_evidence_rule': 'month-cluster bootstrap lower bound >0, at least100 bets,12 active months,2 years',
                     'flat_stake': 1., 'bets_per_match_max': 1, 'bootstrap': '4000 resamples of active calendar-month clusters, seed20261030',
                     'not_used': ['HomeElo', 'AwayElo', 'Form3Home', 'Form5Home', 'Form3Away', 'Form5Away',
                                  'post-match shots/cards/corners', 'C_*', 'MaxHome', 'MaxDraw', 'MaxAway']},
        'eligible_matches': len(y), 'split_counts': {'train': int(train.sum()), 'validation': int(val.sum()), 'test': int(test.sum())},
        'feature_names': names, 'candidates': candidates, 'selected_model': selected, 'final_model': final,
        'final_probability_scores': {'model': scores(p, y[test]), 'market_no_vig': scores(market[test], y[test])},
        'final_thresholds': thresholds,
        'examples_highest_expected_value': sorted(trades[0.0], key=lambda t: t['expected_profit_per_unit'], reverse=True)[:5],
        'conclusion': 'positive EV supported by held-out returns' if thresholds['0.03']['positive_expected_value_supported'] else 'no supported positive EV for frozen primary policy',
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    with TRADES.open('w') as f:
        for threshold, selected_trades in trades.items():
            for t in selected_trades:
                f.write(json.dumps({'ev_threshold': threshold, **t}, ensure_ascii=False, allow_nan=False) + '\n')
    write_markdown(report)
    print(json.dumps({'selected': selected, 'final_scores': report['final_probability_scores'],
                      'primary': thresholds['0.03'], 'report': str(OUT)}, ensure_ascii=False), flush=True)
    return report


def write_markdown(r):
    p = r['final_thresholds']['0.03']
    lines = ['# Valor esperado de resultados 1X2', '',
             'La fórmula por cada peso apostado es `EV = probabilidad × cuota decimal − 1`.',
             'Se prueba una apuesta por partido, la de mayor EV estimado, con cuotas Bet365 de 1,20 a 5,00.', '',
             f"Se reconstruyeron Elo, forma de puntos y goles, localía, rival, descanso y tasas de liga con fechas anteriores. Archivo: {r['source']['scored_matches']:,} partidos con resultado; {r['eligible_matches']:,} con cuotas e historial mínimo.", '',
             'Calidad de cuotas: se excluyen grupos 1X2 cuyo margen implícito sea negativo o supere 25%; sus marcadores sí actualizan el historial posterior. Se apartaron 10 grupos del archivo, antes de estimar los modelos.', '',
             'Entrenamiento 2000–2017; elección por logloss 2018–2021; reentrenamiento hasta 2021; evaluación final 2022–2026. No se seleccionó el modelo por rentabilidad.', '',
             '| Modelo | Logloss validación |', '|---|---:|']
    for name, candidate in r['candidates'].items():
        lines.append(f"| {name} | {candidate['validation']['logloss']:.6f} |")
    lines += ['', f"Modelo seleccionado: **{r['selected_model']}**.", '',
              '| Umbral EV estimado | Apuestas | Beneficio por 100 apostados | Intervalo 95% por meses |', '|---|---:|---:|---:|']
    for threshold, v in r['final_thresholds'].items():
        ci = v.get('roi_month_cluster_bootstrap95')
        lines.append(f"| {float(threshold):.0%} | {v['bets']:,} | {v['roi'] * 100:.2f} | [{ci[0] * 100:.2f}, {ci[1] * 100:.2f}] |" if ci else f"| {float(threshold):.0%} | 0 | — | — |")
    if p['bets']:
        lines += ['', f"Política principal: EV ≥ 3%; retorno real {p['roi']:.2%}; EV predicho promedio {p['predicted_ev']:.2%}; tasa de acierto {p['hit_rate']:.2%}; probabilidad predicha media {p['mean_predicted_probability']:.2%}.",
                  f"Mismas selecciones con todas las cuotas 1% inferiores: retorno {p['roi_after_1pct_odds_haircut']:.2%}.", '',
                  '| Año final | Apuestas | Beneficio por 100 |', '|---|---:|---:|']
        for year, v in p['by_year'].items():
            lines.append(f"| {year} | {v['bets']:,} | {v['roi'] * 100:.2f} |")
    loose = r['final_thresholds']['0.0']
    if loose['bets']:
        lines += ['', f"Aceptando cualquier EV estimado positivo: {loose['bets']} apuestas, EV predicho promedio {loose['predicted_ev']:.2%}, retorno real {loose['roi']:.2%}. Con cuotas 1% inferiores: {loose['roi_after_1pct_odds_haircut']:.2%}.",
                  f"Probabilidad predicha media {loose['mean_predicted_probability']:.2%}; acierto observado {loose['hit_rate']:.2%}; umbral de equilibrio medio {loose['mean_break_even_probability']:.2%}."]
    lines += ['', '**Conclusión:** ' + ('hay evidencia de valor esperado positivo en la política principal.' if p['positive_expected_value_supported'] else 'estas variables no sostuvieron una ventaja positiva en la política principal.'), '',
              'Los coeficientes, predicciones seleccionadas, calibración y auditoría están en `data/analysis/research_result_ev.json` y `research_result_ev_trades.jsonl`. El código puede recalcularlo todo.', '']
    (ROOT / 'VALOR_ESPERADO_RESULTADOS.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    run()
