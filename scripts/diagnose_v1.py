#!/usr/bin/env python3
"""Descriptive post-mortem of the fixed v1 football strategy.

No threshold, league or strategy is selected here. The old test period was
already inspected and must never be relabelled as an untouched holdout.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ('B365', 'BW', 'IW', 'LB', 'VC', 'WH', '1XB', 'BF', 'BFD', 'BMGM', 'BV', 'CL', 'PP', 'SKB', 'PS')
PS_UNRELIABLE_FROM = '2025-07-23'


def finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def outcome(row):
    h, a = int(row['home_score']), int(row['away_score'])
    return (h > a if row['selection_label'] == 'Local' else
            h == a if row['selection_label'] == 'Empate' else h < a)


def summarize(rows):
    if not rows:
        return {'n': 0}
    stake = sum(r['stake'] for r in rows)
    pnl = sum(r['profit'] for r in rows)
    flat_returns = [(r['odds'] - 1) if outcome(r) else -1 for r in rows]
    probs = [r['probability'] for r in rows]
    market = [r['market_probability'] for r in rows if r.get('market_probability') is not None]
    return {'n': len(rows), 'stake': stake, 'pnl': pnl,
            'kelly_roi': pnl / stake if stake else None,
            'flat_profit': sum(flat_returns), 'flat_roi': statistics.mean(flat_returns),
            'win_rate': sum(outcome(r) for r in rows) / len(rows),
            'model_probability_mean': statistics.mean(probs),
            'market_probability_mean': statistics.mean(market) if market else None,
            'mean_model_ev': statistics.mean(r['ev'] for r in rows),
            'stake_weighted_model_ev': sum(r['ev'] * r['stake'] for r in rows) / stake if stake else None,
            'probability_optimism': statistics.mean(probs) - sum(outcome(r) for r in rows) / len(rows),
            'stake_share': None}


def grouped(rows, key):
    groups = collections.defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    total_stake = sum(r['stake'] for r in rows)
    result = {}
    for label, members in sorted(groups.items()):
        item = summarize(members)
        item['stake_share'] = item['stake'] / total_stake if total_stake else None
        result[label] = item
    return result


def odds_bin(o):
    return '<2' if o < 2 else '2–3' if o < 3 else '3–5' if o < 5 else '5–10' if o < 10 else '10+'


def probability_bin(p):
    lower = min(9, int(p * 10)) * 10
    return f'{lower:02d}–{lower+10:02d}%'


def ev_bin(ev):
    return '5–10%' if ev < .10 else '10–20%' if ev < .20 else '20–50%' if ev < .50 else '50%+'


def date_iso(value):
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except (ValueError, TypeError):
            pass
    return None


def raw_market_coverage(directory):
    totals = collections.Counter()
    books = collections.Counter()
    by_file = []
    for path in sorted(Path(directory).glob('*.csv')):
        if path.name == 'fixtures.csv':
            continue
        raw = path.read_bytes()
        text = None
        for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                text = raw.decode(encoding); break
            except UnicodeDecodeError:
                pass
        counts = collections.Counter()
        for row in csv.DictReader(io.StringIO(text or '')):
            if finite(row.get('FTHG', row.get('HG'))) is None or finite(row.get('FTAG', row.get('AG'))) is None:
                continue
            day = date_iso(row.get('Date'))
            if day is None:
                continue
            counts['results'] += 1
            for snapshot, marker in (('pre_closing', ''), ('closing', 'C')):
                complete = []
                for book in BOOKS:
                    if book == 'PS' and day >= PS_UNRELIABLE_FROM:
                        continue
                    prices = [finite(row.get(book + marker + label)) for label in ('H', 'D', 'A')]
                    if all(value is not None and value > 1 for value in prices):
                        complete.append(book)
                        books[f'{snapshot}:{book}'] += 1
                counts[f'{snapshot}_at_least_one_book'] += bool(complete)
                counts[f'{snapshot}_at_least_two_books'] += len(complete) >= 2
                counts[f'{snapshot}_at_least_three_books'] += len(complete) >= 3
                totals[f'{snapshot}_named_book_markets'] += len(complete)
                if all((finite(row.get('B365' + marker + x)) or 0) > 1 for x in ('>2.5', '<2.5')):
                    counts[f'{snapshot}_b365_over_under25'] += 1
                if all((finite(row.get('B365' + marker + x)) or 0) > 1 for x in ('AHH', 'AHA')):
                    line_key = 'AHCh' if marker else 'AHh'
                    line = finite(row.get(line_key, row.get('B365AH')))
                    counts[f'{snapshot}_b365_asian_handicap_with_line'] += line is not None
            for field, label in [('HTHG', 'halftime'), ('HC', 'corners'), ('HY', 'yellow_cards'), ('HR', 'red_cards')]:
                counterpart = {'HTHG':'HTAG', 'HC':'AC', 'HY':'AY', 'HR':'AR'}[field]
                counts[f'paired_{label}_results'] += finite(row.get(field)) is not None and finite(row.get(counterpart)) is not None
        if counts:
            by_file.append({'file': path.name, **dict(counts)})
            totals.update(counts)
    return {'totals': dict(totals), 'named_books': dict(books), 'files': by_file,
            'excluded_from_book_prices': ['Avg', 'Max', 'BbAv', 'BbMx', 'BFE exchange without commission model'],
            'pinnacle_excluded_from': PS_UNRELIABLE_FROM,
            'notes': ['Counts are stored snapshots, not timestamp-verified executable offers.',
                      'Pre-closing and closing form separate cohorts; never mix them into simultaneous arbitrage.',
                      'Named bookmaker max prices can be investigated, but the historical CSV has no per-price clock.',
                      'Corners/cards/half-time results are not equivalent to historical market prices.']}


def diagnose(history_path, matches_path, raw_dir):
    source = Path(history_path)
    decisions = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    football = [row for row in decisions if row.get('sport') == 'football']
    bets = [row for row in football if row.get('stake', 0) > 0]
    matches = {row['id']: row for row in csv.DictReader(Path(matches_path).open()) if row['sport'] == 'football'}
    settlement_mismatches = []
    for row in bets:
        expected = row['stake'] * (row['odds'] - 1) if outcome(row) else -row['stake']
        if not math.isclose(row['profit'], expected, abs_tol=1e-10):
            settlement_mismatches.append(row['id'])
    def favorite_rank(row):
        raw = matches[row['id']]
        prices = [float(raw[x]) for x in ('home_odds', 'draw_odds', 'away_odds')]
        index = {'Local':0, 'Empate':1, 'Visitante':2}[row['selection_label']]
        return 1 + sum(o < prices[index] for o in prices)
    summary = summarize(bets)
    summary['fraction_of_test_events_bet'] = len(bets) / len(football)
    summary['model_expected_profit'] = sum(r['ev'] * r['stake'] for r in bets)
    summary['market_reference_expected_profit'] = sum((r['market_probability'] * r['odds'] - 1) * r['stake'] for r in bets)
    summary['model_vs_actual_profit_gap'] = summary['model_expected_profit'] - summary['pnl']
    by = {'odds': grouped(bets, lambda r: odds_bin(r['odds'])),
          'probability': grouped(bets, lambda r: probability_bin(r['probability'])),
          'selection': grouped(bets, lambda r: r['selection_label']),
          'market_favorite_rank': grouped(bets, favorite_rank),
          'league': grouped(bets, lambda r: r['league']),
          'year': grouped(bets, lambda r: r['date'][:4]),
          'snapshot': grouped(bets, lambda r: r.get('odds_snapshot', 'unknown')),
          'ev': grouped(bets, lambda r: ev_bin(r['ev']))}
    for groups in by.values():
        assert sum(item['n'] for item in groups.values()) == len(bets)
        assert math.isclose(sum(item['stake'] for item in groups.values()), summary['stake'], abs_tol=1e-7)
        assert math.isclose(sum(item['pnl'] for item in groups.values()), summary['pnl'], abs_tol=1e-7)
    assert not settlement_mismatches
    return {'model_version': '0.1.0', 'generated_at': datetime.now(timezone.utc).isoformat(),
            'kind': 'descriptive_postmortem_not_strategy_selection',
            'test_already_inspected': True, 'selection_allowed_on_this_report': False,
            'history_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'football_decisions': len(football), 'summary': summary, 'groups': by,
            'integrity': {'settlement_mismatches': settlement_mismatches,
                          'training_date_violations': [r['id'] for r in football if r.get('training_as_of') and r['training_as_of'] >= r['date']],
                          'average_price_bets': sum(':Avg:' in r.get('odds_source', '') for r in bets),
                          'group_reconciliation_passed': True},
            'raw_market_coverage': raw_market_coverage(raw_dir)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', default=str(ROOT / 'data/processed/decisions.jsonl'))
    parser.add_argument('--matches', default=str(ROOT / 'data/processed/matches.csv'))
    parser.add_argument('--raw-dir', default=str(ROOT / 'data/raw/football'))
    parser.add_argument('--output', default=str(ROOT / 'data/analysis/v1_diagnosis.json'))
    args = parser.parse_args()
    result = diagnose(args.history, args.matches, args.raw_dir)
    target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    print(json.dumps({'output': str(target), 'summary': result['summary'], 'integrity': result['integrity'],
                      'market_coverage': result['raw_market_coverage']['totals']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
