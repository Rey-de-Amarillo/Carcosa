#!/usr/bin/env python3
"""Frozen chronological research of value in football bookmaker disagreement.

References exclude the target book. Primary: Bet365, pre-closing 1X2 and
O/U2.5; best EV per event, EV >= .03. Thresholds 0/.05 and other books are
declared sensitivities, never selected by final-period ROI.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if Path('/tmp/football-portfolio-scipy').is_dir():
    sys.path.insert(0, '/tmp/football-portfolio-scipy')
import numpy as np
from scipy.optimize import minimize
from engine.ensemble import devig
from engine.research_backtest import _actual_book

TEST_START = '2022-01-01'
MARKETS = ('h2h', 'totals25')
CONFIG = dict(primary_target='B365', primary_ev=.03, sensitivity_evs=[0., .05],
              min_odds=1.2, max_odds=5., max_overround=.15,
              h2h_min_reference_books=3, totals_reference='PS',
              one_bet_per_event=True, stake_per_bet=1., test_start=TEST_START,
              snapshot='pre', price_haircut=.01, bootstrap_month_blocks=2000,
              calibration_selection='validation log loss; no ROI selection',
              h2h_train_end='2018-12-31', h2h_validation_start='2019-01-01',
              totals25_train_end='2020-12-31', totals25_validation_start='2021-01-01')


def valid_books(row, market):
    """Only actual complete pre-closing vectors; never closing/Max/Avg/BFE."""
    result = {}
    size = 3 if market == 'h2h' else 2
    for name, prices in row.get(market, {}).get('pre', {}).items():
        if not _actual_book(name, row['date']):
            continue
        try:
            q = [float(o) for o in prices]
            if len(q) != size:
                continue
            fitted = devig(q, 'power')
            if not -.02 <= fitted['overround'] <= CONFIG['max_overround']:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        result[name] = dict(odds=q, p=fitted['probabilities'],
                            overround=fitted['overround'])
    return result


def reference(books, target, market):
    if target not in books:
        return None
    if market == 'totals25':
        # Only two genuine books are in this archive's O/U snapshot.
        other = 'PS' if target != 'PS' else 'B365'
        names = [other] if other in books else []
    else:
        names = [b for b in books if b != target]
        if len(names) < CONFIG['h2h_min_reference_books']:
            return None
    if not names:
        return None
    vectors = np.asarray([books[b]['p'] for b in names])
    p = vectors.mean(axis=0)
    return dict(p=p.tolist(), books=names, dispersion=vectors.std(axis=0).tolist())


def outcome(score, market):
    h, a = score
    return (0 if h > a else 1 if h == a else 2) if market == 'h2h' else (0 if h+a > 2.5 else 1)


def probabilities(p, target_p, spec):
    p, target_p = np.asarray(p, dtype=float), np.asarray(target_p, dtype=float)
    if spec['kind'] == 'raw':
        return p
    if spec['kind'] == 'blend':
        return spec['reference_weight'] * p + (1-spec['reference_weight']) * target_p
    logits = np.log(np.clip(p, 1e-12, 1)) * spec['temperature']
    logits += np.asarray(spec['intercepts'])
    logits -= logits.max(axis=-1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=-1, keepdims=True)


def fit_specs(rows, size):
    if len(rows) < 100:
        return [dict(kind='raw')]
    p = np.asarray([r['p'] for r in rows]); target = np.asarray([r['target_p'] for r in rows])
    y = np.asarray([r['outcome'] for r in rows]); positions = np.arange(len(y))

    def loss_temp(x):
        spec = dict(kind='temperature', temperature=float(x[0]), intercepts=[*x[1:], 0.])
        q = probabilities(p, target, spec)
        return -np.log(q[positions, y]).mean() + .001*np.dot(x[1:], x[1:])

    fitted = minimize(loss_temp, np.r_[1., np.zeros(size-1)], method='L-BFGS-B',
                      bounds=[(.5, 2.)] + [(-1., 1.)]*(size-1))

    def loss_blend(x):
        q = x[0]*p + (1-x[0])*target
        return -np.log(q[positions, y]).mean()

    blend = minimize(loss_blend, [.8], bounds=[(0., 1.)], method='L-BFGS-B')
    return [dict(kind='raw'),
            dict(kind='temperature', temperature=float(fitted.x[0]), intercepts=[*map(float, fitted.x[1:]), 0.]),
            dict(kind='blend', reference_weight=float(blend.x[0]))]


def probability_metrics(rows, spec):
    if not rows:
        return dict(n=0)
    p = probabilities([r['p'] for r in rows], [r['target_p'] for r in rows], spec)
    y = np.asarray([r['outcome'] for r in rows]); truth = np.eye(p.shape[1])[y]
    return dict(n=len(rows), log_loss=float(-np.log(p[np.arange(len(y)), y]).mean()),
                multiclass_brier=float(((p-truth)**2).sum(axis=1).mean()))


def choose_spec(rows, market):
    end = CONFIG[market+'_train_end']
    train = [r for r in rows if r['date'] <= end]
    val = [r for r in rows if end < r['date'] < TEST_START]
    specs = fit_specs(train, 3 if market == 'h2h' else 2)
    table = [dict(spec=s, training=probability_metrics(train, s),
                  validation=probability_metrics(val, s)) for s in specs]
    selected = min(table, key=lambda r: (r['validation'].get('log_loss', float('inf')),
                                       0 if r['spec']['kind'] == 'raw' else 1))
    # Refit the selected model family on all pre-test observations. No test labels.
    if selected['spec']['kind'] == 'raw':
        final = selected['spec']
    else:
        all_prior = [r for r in rows if r['date'] < TEST_START]
        final = next(s for s in fit_specs(all_prior, 3 if market == 'h2h' else 2)
                     if s['kind'] == selected['spec']['kind'])
    return dict(selected=final, candidates=table,
                test=probability_metrics([r for r in rows if r['date'] >= TEST_START], final),
                test_raw_reference=probability_metrics([r for r in rows if r['date'] >= TEST_START], dict(kind='raw')))


def pick_candidates(row, scores, calibrators):
    result = []
    for market in MARKETS:
        books = valid_books(row, market)
        for target, own in books.items():
            ref = reference(books, target, market)
            if ref is None:
                continue
            p = probabilities(ref['p'], own['p'], calibrators[market]['selected'])
            for side, price in enumerate(own['odds']):
                if not CONFIG['min_odds'] <= price <= CONFIG['max_odds']:
                    continue
                result.append(dict(id=row['id'], date=row['date'], league=row['league_code'],
                    home_team=row['home_team'], away_team=row['away_team'], market=market,
                    book=target, side=side, odds=price, probability=float(p[side]),
                    raw_reference_probability=ref['p'][side], ev=float(p[side]*price-1),
                    won=outcome(scores[row['id']], market) == side,
                    references=ref['books'], reference_dispersion=ref['dispersion'][side],
                    reference_max_overround=max(books[b]['overround'] for b in ref['books']),
                    pinnacle_reference_overround=(books['PS']['overround'] if 'PS' in ref['books'] else None),
                    bookmaker_overround=own['overround']))
    return result


def select_event(candidates, threshold=.03, book='B365'):
    eligible = [r for r in candidates if r['ev'] >= threshold and (book is None or r['book'] == book)]
    return max(eligible, key=lambda r: (r['ev'], r['book'], r['market'], -r['side'])) if eligible else None


def settled_return(trade, haircut=0.):
    return (max(1., trade['odds']*(1-haircut)) if trade['won'] else 0.) - 1.


def bootstrap_ci(trades, grouping='month', replicates=2000):
    grouped = collections.defaultdict(list)
    for r in trades:
        grouped[r['date'][:7] if grouping == 'month' else r['date']].append(settled_return(r))
    blocks = [(len(v), sum(v)) for v in grouped.values()]
    if len(blocks) < 2:
        return None
    rng = random.Random(20261030)
    draws = []
    for _ in range(replicates):
        sampled = [rng.choice(blocks) for _ in blocks]
        draws.append(sum(x[1] for x in sampled)/sum(x[0] for x in sampled))
    draws.sort()
    return [draws[int(.025*replicates)], draws[min(replicates-1, int(.975*replicates))]]


def summarize(trades, detailed=True):
    n = len(trades)
    if not n:
        return dict(n=0)
    profit = sum(settled_return(r) for r in trades)
    p = np.asarray([r['probability'] for r in trades]); y = np.asarray([r['won'] for r in trades], float)
    result = dict(n=n, wins=int(y.sum()), win_rate=float(y.mean()), profit_units=profit,
                  stake_units=n, roi=profit/n, average_odds=sum(r['odds'] for r in trades)/n,
                  first_date=min(r['date'] for r in trades), last_date=max(r['date'] for r in trades),
                  predicted_ev=sum(r['ev'] for r in trades)/n,
                  average_predicted_probability=float(p.mean()), calibration_gap=float(y.mean()-p.mean()),
                  binary_brier=float(((p-y)**2).mean()),
                  binary_log_loss=float(-(y*np.log(np.clip(p, 1e-12, 1))+(1-y)*np.log(np.clip(1-p, 1e-12, 1))).mean()),
                  roi_price_haircut_1pct=sum(settled_return(r, .01) for r in trades)/n,
                  books=dict(collections.Counter(r['book'] for r in trades)),
                  markets=dict(collections.Counter(r['market'] for r in trades)))
    if detailed:
        result['monthly_block_bootstrap_roi_95'] = bootstrap_ci(trades, 'month')
        result['date_block_bootstrap_roi_95'] = bootstrap_ci(trades, 'date', 1000)
        result['by_year'] = {year: summarize([r for r in trades if r['date'].startswith(year)], False)
                             for year in sorted({r['date'][:4] for r in trades})}
        result['by_market'] = {m:summarize([r for r in trades if r['market']==m], False) for m in MARKETS}
        result['by_book'] = {m:summarize([r for r in trades if r['book']==m], False)
                             for m in sorted({r['book'] for r in trades})}
        result['by_league'] = {m:summarize([r for r in trades if r['league']==m], False)
                               for m in sorted({r['league'] for r in trades})}
        result['calibration_bins'] = []
        for lo, hi in [(0,.3),(.3,.4),(.4,.5),(.5,.6),(.6,.7),(.7,1.00001)]:
            subset = [r for r in trades if lo <= r['probability'] < hi]
            if subset:
                result['calibration_bins'].append(dict(lower=lo, upper=min(hi,1.), **summarize(subset, False)))
    return result


def read_scores():
    scores = {}
    with (ROOT/'data/processed/matches.csv').open() as handle:
        for r in csv.DictReader(handle):
            if r['sport'] != 'football':
                continue
            try:
                h,a = float(r['home_score']),float(r['away_score'])
                if h >= 0 and a >= 0 and h.is_integer() and a.is_integer():
                    scores[r['id']] = (int(h),int(a))
            except (TypeError, ValueError):
                pass
    return scores


def run():
    path = ROOT/'data/analysis/quote_history.jsonl'
    scores = read_scores(); rows = {m:[] for m in MARKETS}
    with path.open() as handle:
        for line in handle:
            r = json.loads(line)
            if r['id'] not in scores:
                continue
            for market in MARKETS:
                b = valid_books(r, market); ref = reference(b, 'B365', market)
                if ref is not None:
                    rows[market].append(dict(date=r['date'], p=ref['p'], target_p=b['B365']['p'],
                                             outcome=outcome(scores[r['id']], market)))
    calibrators = {m:choose_spec(rows[m],m) for m in MARKETS}
    scenario_trades = {f'{book or "all_books"}_ev_{threshold:.2f}': []
                       for book in ['B365',None] for threshold in [0.,.03,.05]}
    quality_diagnostic = {'B365':[], 'all_books':[]}
    raw_primary = []
    with path.open() as handle:
        for line in handle:
            r = json.loads(line)
            if r['id'] not in scores or r['date'] < TEST_START:
                continue
            choices = pick_candidates(r, scores, calibrators)
            # Outcome-blind price-quality diagnostic introduced after the first run.
            # Explicitly exploratory; does not replace or tune the primary rule.
            clean = [q for q in choices if q['pinnacle_reference_overround'] is None
                     or q['pinnacle_reference_overround'] <= .05]
            for book in ['B365',None]:
                chosen = select_event(clean,.03,book)
                if chosen:
                    quality_diagnostic[book or 'all_books'].append(chosen)
            for book in ['B365',None]:
                for threshold in [0.,.03,.05]:
                    chosen = select_event(choices,threshold,book)
                    if chosen:
                        scenario_trades[f'{book or "all_books"}_ev_{threshold:.2f}'].append(chosen)
            # Raw reference is a separately declared baseline, not ROI-selected.
            raw_choices = [{**q,'probability':q['raw_reference_probability'],
                            'ev':q['raw_reference_probability']*q['odds']-1} for q in choices]
            chosen = select_event(raw_choices,.03,'B365')
            if chosen:
                raw_primary.append(chosen)
    result = dict(config=CONFIG, source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  calibration=calibrators, scenarios={k:summarize(v) for k,v in scenario_trades.items()},
                  raw_reference_B365_ev_003=summarize(raw_primary),
                  exploratory_reference_quality_diagnostic=dict(
                      rule='If Pinnacle is a reference, its overround must be <=5%.',
                      specified_after_first_test_run=True,
                      results={k:summarize(v) for k,v in quality_diagnostic.items()}),
                  metadata=dict(price_timestamp_verified=False, executable_verified=False,
                                timestamps='Pre-closing archive columns; exact observation time absent.',
                                no_closing_prices_used=True, no_postmatch_features_used=True,
                                no_final_period_model_or_threshold_selection=True,
                                pinnacles_stale_feed_excluded_from='2025-07-23',
                                probabilities_are='Calibrated reference estimates; test ROI determines observed evidence.',
                                returns='One unit per event, decimal payout including stake, no bankroll reinvestment.'))
    out=ROOT/'data/analysis/research_market_reference_ev.json'
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    trades = scenario_trades['B365_ev_0.03']
    (ROOT/'data/analysis/research_market_reference_ev.trades.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in trades))
    (ROOT/'data/analysis/research_market_reference_ev.scenarios.jsonl').write_text(
        ''.join(json.dumps(dict(scenario=scenario, **r),ensure_ascii=False)+'\n'
                for scenario, trades_in_scenario in scenario_trades.items() for r in trades_in_scenario))
    print(json.dumps(dict(calibration={m:v['selected'] for m,v in calibrators.items()},
                         scenarios={k:{f:v.get(f) for f in ['n','roi','predicted_ev','monthly_block_bootstrap_roi_95','roi_price_haircut_1pct']}
                                    for k,v in result['scenarios'].items()}, raw=result['raw_reference_B365_ev_003']),ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    run()
