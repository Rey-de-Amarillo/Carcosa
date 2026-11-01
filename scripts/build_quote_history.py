#!/usr/bin/env python3
"""Extract named-book historical snapshots for private research, without downloads.

Pre-closing and closing remain separate; Avg, Max and exchange prices are never
offered as a named bookmaker's executable price. Exact quote times are unknown.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.download_history import football_row, csv_text

BOOKS = ('B365', 'BW', 'IW', 'LB', 'VC', 'WH', '1XB', 'BF', 'BFD', 'BMGM', 'BV', 'CL', 'PP', 'SKB', 'PS')
BOOK_NAMES = {'B365': 'Bet365', 'BW': 'Bwin', 'IW': 'Interwetten', 'LB': 'Ladbrokes',
              'VC': 'BetVictor (legacy VC Bet)', 'WH': 'William Hill', '1XB': '1xBet',
              'BF': 'Betfair Sportsbook', 'BFD': 'Betfred', 'BMGM': 'BetMGM',
              'BV': 'BetVictor', 'CL': 'Coral', 'PP': 'Paddy Power',
              'SKB': 'Sky Bet', 'PS': 'Pinnacle', 'GB': 'Gamebookers'}
PS_UNRELIABLE_FROM = '2025-07-23'


def prices(row, names):
    try:
        values = [float(row[name]) for name in names]
        return values if all(math.isfinite(v) and v > 1 for v in values) else None
    except (ValueError, TypeError, KeyError):
        return None


def line_value(row, names):
    for name in names:
        try:
            value = float(row[name])
            if math.isfinite(value) and abs(value * 4 - round(value * 4)) < 1e-8:
                return value
        except (ValueError, KeyError, TypeError):
            pass
    return None


def build(root=ROOT, output=None):
    root = Path(root)
    output = Path(output or root / 'data/analysis/quote_history.jsonl')
    with (root / 'data/processed/matches.csv').open(encoding='utf-8-sig') as stream:
        canonical = {row['id']: row for row in csv.DictReader(stream) if row['sport'] == 'football'}
    manifest = json.loads((root / 'data/manifest.json').read_text())
    metadata = {row['path']: row for row in manifest.get('files', [])}
    results, rejected = {}, collections.Counter()
    for path in sorted((root / 'data/raw/football').glob('*.csv')):
        if path.name == 'fixtures.csv':
            continue
        stem = path.stem
        extra = stem in ('ARG', 'BRA', 'USA', 'MEX')
        if extra:
            code, season = stem, ''
        else:
            try:
                period, code = stem.split('_', 1)
                start = 2000 + int(period[:2])
                season = str(start) + '/' + str(start + 1)
            except (ValueError, TypeError):
                rejected['unknown_source_filename'] += 1; continue
        raw = path.read_bytes()
        relative = str(path.relative_to(root))
        source_meta = metadata.get(relative, {})
        provenance = {'file': relative, 'sha256': hashlib.sha256(raw).hexdigest(),
                      'url': source_meta.get('url'), 'retrieved_at': source_meta.get('retrieved_at'),
                      'price_timestamp': None}
        for raw_row in csv.DictReader(io.StringIO(csv_text(raw))):
            row = football_row(raw_row, code, season, extra=extra)
            if not row:
                rejected['invalid_or_unfinished_row'] += 1; continue
            if row['id'] not in canonical:
                rejected['not_in_canonical_matches'] += 1; continue
            original = canonical[row['id']]
            if (row['date'], row['home_team'], row['away_team']) != (original['date'], original['home_team'], original['away_team']):
                raise AssertionError('Normalized match identity mismatch')
            item = {'id': row['id'], 'date': row['date'], 'league_code': code, 'league': original['league'],
                    'season': original['season'], 'home_team': row['home_team'], 'away_team': row['away_team'],
                    'h2h': {'pre': {}, 'closing': {}}, 'totals25': {'pre': {}, 'closing': {}},
                    'asian_handicap': {'pre': {}, 'closing': {}},
                    'source': provenance, 'price_timestamp_verified': False,
                    'executable_verified': False}
            for snapshot, marker in (('pre', ''), ('closing', 'C')):
                for book in BOOKS:
                    if book == 'PS' and row['date'] >= PS_UNRELIABLE_FROM:
                        continue
                    triple = prices(raw_row, [book + marker + label for label in ('H', 'D', 'A')])
                    if triple:
                        item['h2h'][snapshot][book] = triple
                for prefix, book in [('B365', 'B365'), ('P', 'PS'), ('GB', 'GB')]:
                    if book == 'PS' and row['date'] >= PS_UNRELIABLE_FROM:
                        continue
                    pair = prices(raw_row, [prefix + marker + label for label in ('>2.5', '<2.5')])
                    if pair:
                        item['totals25'][snapshot][book] = pair
                for prefix, book in [('B365', 'B365'), ('P', 'PS')]:
                    if book == 'PS' and row['date'] >= PS_UNRELIABLE_FROM:
                        continue
                    pair = prices(raw_row, [prefix + marker + label for label in ('AHH', 'AHA')])
                    # For older files an explicit book-specific line is required.
                    # BbAHh is a market aggregate, not proof of this book's line.
                    names = ['AHCh'] if marker else [prefix + 'AH', 'AHh']
                    line = line_value(raw_row, names)
                    if pair and line is not None:
                        item['asian_handicap'][snapshot][book] = {'line': line, 'odds': pair,
                                                                  'home_odds': pair[0], 'away_odds': pair[1],
                                                                  'line_source_column': next(n for n in names if line_value(raw_row, [n]) is not None)}
            if row['id'] in results:
                raise AssertionError('Duplicate historical quote identity: ' + row['id'])
            results[row['id']] = item
    coverage = collections.Counter()
    for row in results.values():
        for market in ('h2h', 'totals25', 'asian_handicap'):
            for snapshot in ('pre', 'closing'):
                books = row[market][snapshot]
                coverage[f'{market}:{snapshot}:with_named_book'] += bool(books)
                coverage[f'{market}:{snapshot}:two_or_more_books'] += len(books) >= 2
                coverage[f'{market}:{snapshot}:book_observations'] += len(books)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        for row in sorted(results.values(), key=lambda r: (r['date'], r['id'])):
            stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
    temporary.replace(output)
    summary = {'path': str(output), 'rows': len(results), 'canonical_football_matches': len(canonical),
               'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'coverage': dict(coverage),
               'rejected': dict(rejected), 'source_policy': 'private_research_only',
               'price_timestamp_verified': False, 'arbitrage_execution_proof': False, 'book_names': BOOK_NAMES,
               'excluded': ['Avg', 'Max', 'BbAv', 'BbMx', 'BFE', 'Pinnacle from 2025-07-23']}
    output.with_suffix('.summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output')
    args = p.parse_args()
    print(json.dumps(build(output=args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
