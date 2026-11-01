#!/usr/bin/env python3
"""Fixed exploratory EV policies that penalize reference-book disagreement.

Created after inspecting a prior mean-reference backtest. No final-period
optimization: mean, minimum, and mean-minus-one-SD are all reported at EV>=3%.
The minimum/SD scores are robustness heuristics, not confidence bounds on truth.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.research_market_reference_ev import (
    valid_books,read_scores,outcome,select_event,summarize,
)

POLICIES=('mean','minimum','mean_minus_one_sd')


def reference_scores(books,target):
    refs=[b for b in books if b!=target]
    if target not in books or len(refs)<3:
        return None
    p=[books[b]['p'] for b in refs]
    mean=[sum(v[s] for v in p)/len(p) for s in range(3)]
    sd=[(sum((v[s]-mean[s])**2 for v in p)/len(p))**.5 for s in range(3)]
    return dict(books=refs,mean=mean,minimum=[min(v[s] for v in p) for s in range(3)],
                mean_minus_one_sd=[max(0.,mean[s]-sd[s]) for s in range(3)],sd=sd)


def candidates(row,scores):
    books=valid_books(row,'h2h')
    result={p:[] for p in POLICIES}
    for book,own in books.items():
        refs=reference_scores(books,book)
        if refs is None:
            continue
        for side,odd in enumerate(own['odds']):
            if not 1.2<=odd<=5.:
                continue
            for policy in POLICIES:
                p=refs[policy][side]
                result[policy].append(dict(
                    id=row['id'],date=row['date'],league=row['league_code'],
                    home_team=row['home_team'],away_team=row['away_team'],
                    market='h2h',book=book,side=side,odds=odd,probability=p,
                    probability_interpretation='Reference-model robustness score; not a certified true probability.',
                    ev=p*odd-1,won=outcome(scores[row['id']],'h2h')==side,
                    references=refs['books'],reference_mean=refs['mean'][side],
                    reference_sd=refs['sd'][side],reference_minimum=refs['minimum'][side],
                    policy=policy))
    return result


def run():
    scores=read_scores(); path=ROOT/'data/analysis/quote_history.jsonl'
    trades={f'{period}_{book or "all_books"}_{policy}':[]
            for period in ('validation','test') for book in ('B365',None) for policy in POLICIES}
    eligible=0
    with path.open() as handle:
        for line in handle:
            r=json.loads(line)
            if r['id'] not in scores or r['date']<'2018-01-01':
                continue
            period='test' if r['date']>='2022-01-01' else 'validation'
            options=candidates(r,scores)
            if options['mean']:
                eligible+=1
            for book in ('B365',None):
                for policy in POLICIES:
                    chosen=select_event(options[policy],.03,book)
                    if chosen:
                        trades[f'{period}_{book or "all_books"}_{policy}'].append(chosen)
    result=dict(
        config=dict(markets=['1X2'],ev_threshold=.03,odds_range=[1.2,5.],
                    minimum_other_real_books=3,one_selection_per_event=True,
                    validation='2018-01-01 through 2021-12-31',test='2022-01-01 onward',
                    policies=list(POLICIES),stake_per_event=1.,price_haircut=.01,
                    introduced_after_prior_test_inspection=True,
                    selected_winner_by_final_roi=False,
                    uncertainty_note='Neither minimum nor mean-minus-SD is a statistical confidence bound.'),
        eligible_events=eligible,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        results={k:summarize(v) for k,v in trades.items()},
        timestamp_metadata=dict(snapshot='pre',exact_price_timestamp_verified=False,closing_not_used=True))
    (ROOT/'data/analysis/research_robust_reference_ev.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'data/analysis/research_robust_reference_ev.trades.jsonl').write_text(
        ''.join(json.dumps(dict(scenario=k,**r),ensure_ascii=False)+'\n' for k,v in trades.items() for r in v))
    print(json.dumps({k:{f:v.get(f) for f in ['n','roi','predicted_ev','roi_price_haircut_1pct','monthly_block_bootstrap_roi_95']}
                      for k,v in result['results'].items()},ensure_ascii=False))
    return result


if __name__=='__main__':
    run()
