#!/usr/bin/env python3
"""Acquire the official historical Football-Data season archives for private use.

Only individual bookmaker prices are exported. Market min/max/average series
are not bookmaker prices. Opening/pre-closing and closing contracts stay apart.
No probability, quote capture time, execution eligibility or return is invented.
Standard library only; downloaded source containers remain ignored local files.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/expanded-football'
OUT = ROOT / 'app/data'
PROVIDER = 'Football-Data.co.uk'
SOURCE_URL = 'https://www.football-data.co.uk/data.php'
NOTES_URL = 'https://www.football-data.co.uk/notes.txt'
LEAGUES = {
    'E0': ('Premier League', 'Inglaterra'), 'E1': ('Championship', 'Inglaterra'),
    'E2': ('League One', 'Inglaterra'), 'E3': ('League Two', 'Inglaterra'),
    'EC': ('National League', 'Inglaterra'), 'SC0': ('Premiership', 'Escocia'),
    'SC1': ('Championship', 'Escocia'), 'SC2': ('League One', 'Escocia'),
    'SC3': ('League Two', 'Escocia'), 'D1': ('Bundesliga', 'Alemania'),
    'D2': ('2. Bundesliga', 'Alemania'), 'I1': ('Serie A', 'Italia'),
    'I2': ('Serie B', 'Italia'), 'SP1': ('La Liga', 'España'),
    'SP2': ('Segunda División', 'España'), 'F1': ('Ligue 1', 'Francia'),
    'F2': ('Ligue 2', 'Francia'), 'N1': ('Eredivisie', 'Países Bajos'),
    'B1': ('Pro League', 'Bélgica'), 'P1': ('Primeira Liga', 'Portugal'),
    'T1': ('Süper Lig', 'Turquía'), 'G1': ('Super League', 'Grecia'),
}
BOOKS = {
    'B365': 'Bet365', 'BW': 'bwin', 'IW': 'Interwetten', 'LB': 'Ladbrokes',
    'PS': 'Pinnacle', 'VC': 'BetVictor', 'WH': 'William Hill',
    'BF': 'Betfair Sportsbook', 'BFE': 'Betfair Exchange', 'BFD': 'Betfred',
    'BMGM': 'BetMGM', 'CL': 'Coral', 'PP': 'Paddy Power', 'SKB': 'Sky Bet',
    '1XB': '1xBet', 'BS': 'Blue Square', 'GB': 'Gamebookers',
    'SO': 'Sporting Odds', 'SB': 'Sportingbet', 'SJ': 'Stan James',
    'SY': 'Stanleybet',
}
# Historical column spellings map to a single bookmaker, while sourceColumn
# always records the spelling in the actual file.
PREFIXES = {
    'B365': 'B365', 'BW': 'BW', 'IW': 'IW', 'LB': 'LB', 'PS': 'PS', 'P': 'PS',
    'VC': 'VC', 'BV': 'VC', 'WH': 'WH', 'BF': 'BF', 'BFE': 'BFE',
    'BFD': 'BFD', 'BMGM': 'BMGM', 'CL': 'CL', 'PP': 'PP', 'SKB': 'SKB',
    'SK': 'SKB', '1XB': '1XB', 'BS': 'BS', 'GB': 'GB', 'SO': 'SO',
    'SB': 'SB', 'SJ': 'SJ', 'SY': 'SY',
}
EVENT_COLUMNS = [
    'id', 'date', 'home', 'away', 'league', 'season', 'home_score', 'away_score',
    'home_ht_score', 'away_ht_score', 'home_corners', 'away_corners',
    'home_shots', 'away_shots', 'home_shots_on_target', 'away_shots_on_target',
    'home_yellow', 'away_yellow', 'home_red', 'away_red', 'kickoff_time', 'sourceRow',
]
QUOTE_COLUMNS = [
    'event', 'book', 'market', 'period', 'selection', 'line', 'phase', 'odds',
    'sourceColumn', 'sourceRow', 'lineColumn',
]
STATS = ['FTHG', 'FTAG', 'HTHG', 'HTAG', 'HC', 'AC', 'HS', 'AS', 'HST', 'AST',
         'HY', 'AY', 'HR', 'AR']
MARKETS = [{'id': 'match_result', 'name': 'Resultado 1X2'},
           {'id': 'total_goals', 'name': 'Goles del partido · más/menos 2,5'},
           {'id': 'asian_handicap', 'name': 'Hándicap asiático'}]
PHASES = [{'id': 'pre_closing', 'name': 'Previa al cierre'},
          {'id': 'closing', 'name': 'Cierre'}]


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.part')
    temp.write_bytes(data)
    temp.replace(path)


def numeric(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def nonnegative_int(value):
    number = numeric(value)
    return int(number) if number is not None and number >= 0 and number.is_integer() else None


def match_date(value):
    for form in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime((value or '').strip(), form).date().isoformat()
        except ValueError:
            pass
    return None


def csv_text(payload):
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError('Source CSV has no supported encoding')


def source_headers(headers):
    """Map documented individual-book columns; never match Max/Avg/Bb fields."""
    definitions = []
    for column in headers:
        for prefix in sorted(PREFIXES, key=len, reverse=True):
            if not column.startswith(prefix):
                continue
            suffix = column[len(prefix):]
            phase = 'closing' if suffix.startswith('C') else 'pre_closing'
            code = suffix[1:] if phase == 'closing' else suffix
            if code in ('H', 'D', 'A'):
                definitions.append((column, PREFIXES[prefix], 'match_result',
                                    {'H': 'home', 'D': 'draw', 'A': 'away'}[code], None, phase, None, prefix))
            elif code in ('>2.5', '<2.5'):
                definitions.append((column, PREFIXES[prefix], 'total_goals',
                                    'over' if code[0] == '>' else 'under', 2.5, phase, None, prefix))
            elif code in ('AHH', 'AHA'):
                # Before AHh/AHCh the bookmaker-specific line is required.
                candidates = [prefix + ('CAH' if phase == 'closing' else 'AH'),
                              'AHCh' if phase == 'closing' else 'AHh']
                line_column = next((name for name in candidates if name in headers), None)
                if line_column:
                    definitions.append((column, PREFIXES[prefix], 'asian_handicap',
                                        'home' if code == 'AHH' else 'away', None, phase, line_column, prefix))
            break
    return definitions


def transform_csv(payload, league, season):
    reader = csv.DictReader(io.StringIO(csv_text(payload)))
    definitions = source_headers(reader.fieldnames or [])
    events, quotes, seen_events = [], [], set()
    report = Counter()
    for source_row, row in enumerate(reader, start=2):
        report['sourceRows'] += 1
        day = match_date(row.get('Date'))
        home, away = (row.get('HomeTeam') or '').strip(), (row.get('AwayTeam') or '').strip()
        if not day or not home or not away:
            report['invalidIdentityRows'] += 1
            continue
        digest = hashlib.sha256('|'.join([league, season, day, home, away]).encode()).hexdigest()[:16]
        event_id = f'fd:{league}:{season}:{day}:{digest}'
        if event_id in seen_events:
            report['duplicateIdentityRows'] += 1
            # Duplicate rows can contain conflicting prices. Do not manufacture
            # a best historical quote by combining or replacing observations.
            continue
        seen_events.add(event_id)
        index = len(events)
        events.append([event_id, day, home, away, league, season,
                       *[nonnegative_int(row.get(field)) for field in STATS],
                       (row.get('Time') or '').strip() or None, source_row])
        seen_quotes = {}
        for column, book, market, selection, line, phase, line_column, prefix in definitions:
            price = numeric(row.get(column))
            if price is None or price <= 1:
                if row.get(column) not in (None, ''):
                    report['invalidPriceCells'] += 1
                continue
            if line_column:
                line = numeric(row.get(line_column))
                if line is None or not math.isclose(line * 4, round(line * 4), abs_tol=1e-9):
                    report['missingOrInvalidHandicapLines'] += 1
                    continue
                if selection == 'away':
                    line = -line
                if line == 0:
                    line = 0.0
            identity = (book, market, selection, line, phase)
            if identity in seen_quotes:
                # Alias headers should agree. Keep the first official column
                # only if values agree; otherwise quarantine the whole price.
                old = seen_quotes[identity]
                if old is not None and quotes[old][7] != price:
                    quotes[old] = None
                    seen_quotes[identity] = None
                    report['conflictingAliasCells'] += 1
                continue
            seen_quotes[identity] = len(quotes)
            quotes.append([index, book, market, 'full', selection, line, phase,
                           price, column, source_row, line_column])
    quotes = [row for row in quotes if row is not None]
    return {'events': {'columns': EVENT_COLUMNS, 'rows': events},
            'quotes': {'columns': QUOTE_COLUMNS, 'rows': quotes}}, dict(report)


def acquire_season(year, refresh=False):
    season_code = f'{year % 100:02d}{(year + 1) % 100:02d}'
    url = f'https://www.football-data.co.uk/mmz4281/{season_code}/data.zip'
    path, meta_path = RAW / f'{season_code}.zip', RAW / f'{season_code}.json'
    if path.exists() and meta_path.exists() and not refresh:
        payload = path.read_bytes()
        meta = json.loads(meta_path.read_text())
        if hashlib.sha256(payload).hexdigest() == meta.get('sha256'):
            return year, payload, meta
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Personal-Football-Archive/1.0'}), timeout=90) as response:
                payload = response.read()
                modified = response.headers.get('Last-Modified')
            if not zipfile.is_zipfile(io.BytesIO(payload)):
                raise ValueError('Official source returned a non-ZIP response')
            meta = {'url': url, 'retrievedAt': utcnow(), 'sha256': hashlib.sha256(payload).hexdigest(),
                    'bytes': len(payload), 'lastModified': modified}
            atomic(path, payload)
            atomic(meta_path, (dumps(meta) + '\n').encode())
            return year, payload, meta
        except HTTPError as error:
            if error.code in (404, 410):
                return year, None, {'url': url, 'status': error.code}
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = max(3, int(error.headers.get('Retry-After', 0) or 0))
            time.sleep(min(delay, 60))
        except (TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError('Unreachable source acquisition state')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-year', type=int, default=2000)
    parser.add_argument('--end-year', type=int, default=2026)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    if not (1993 <= args.start_year <= args.end_year <= 2100):
        parser.error('Invalid archive year range')
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    partitions, unavailable, all_reports = [], [], Counter()
    book_counts, market_counts, phase_counts = Counter(), Counter(), Counter()
    source_count = 0
    with ThreadPoolExecutor(max_workers=max(1, min(4, args.workers))) as pool:
        futures = [pool.submit(acquire_season, year, args.refresh) for year in range(args.start_year, args.end_year + 1)]
        for future in futures:
            year, archive_bytes, archive_source = future.result()
            if archive_bytes is None:
                unavailable.append(archive_source)
                continue
            season, code = f'{year}/{year + 1}', f'{year % 100:02d}{(year + 1) % 100:02d}'
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
            names = {Path(name).stem.upper(): name for name in archive.namelist() if name.lower().endswith('.csv')}
            season_total = 0
            for league in LEAGUES:
                member = names.get(league)
                if not member:
                    continue
                payload = archive.read(member)
                result, report = transform_csv(payload, league, season)
                if not result['events']['rows']:
                    continue
                source_count += 1
                all_reports.update(report)
                partition_id = f'{code}-{league}'
                path = f'expanded-football-{partition_id}.json.gz'
                compressed = gzip.compress(dumps(result).encode(), compresslevel=9, mtime=0)
                if len(compressed) >= 25 * 1024 * 1024:
                    raise ValueError(f'Partition exceeds hosting limit: {partition_id}')
                atomic(OUT / path, compressed)
                quotes, events = result['quotes']['rows'], result['events']['rows']
                books = Counter(row[1] for row in quotes)
                markets = Counter(row[2] for row in quotes)
                phases = Counter(row[6] for row in quotes)
                book_counts.update(books); market_counts.update(markets); phase_counts.update(phases)
                days = [row[1] for row in events]
                partitions.append({'id': partition_id, 'path': path, 'season': season, 'league': league,
                                   'eventCount': len(events), 'quoteCount': len(quotes),
                                   'dateMin': min(days), 'dateMax': max(days), 'compressedBytes': len(compressed),
                                   'sha256': hashlib.sha256(compressed).hexdigest(),
                                   'books': sorted(books), 'markets': sorted(markets), 'phases': sorted(phases),
                                   'bookCounts': dict(sorted(books.items())), 'marketCounts': dict(sorted(markets.items())),
                                   'phaseCounts': dict(sorted(phases.items())), 'validation': report,
                                   'source': {'url': f'https://www.football-data.co.uk/mmz4281/{code}/{league}.csv',
                                              'archiveUrl': archive_source['url'], 'archiveMember': member,
                                              'retrievedAt': archive_source['retrievedAt'],
                                              'sha256': hashlib.sha256(payload).hexdigest(),
                                              'archiveSha256': archive_source['sha256'], 'bytes': len(payload),
                                              'lastModified': archive_source.get('lastModified')}})
                season_total += len(quotes)
            print(f'{season}: {season_total:,} individual-book quotes', flush=True)
    seasons = sorted({part['season'] for part in partitions})
    manifest = {'version': 1, 'provider': PROVIDER, 'sourceUrl': SOURCE_URL, 'notesUrl': NOTES_URL,
                'generatedAt': utcnow(), 'eventCount': sum(p['eventCount'] for p in partitions),
                'quoteCount': sum(p['quoteCount'] for p in partitions), 'sourceFileCount': source_count,
                'compressedBytes': sum(p['compressedBytes'] for p in partitions),
                'dateMin': min((p['dateMin'] for p in partitions), default=None),
                'dateMax': max((p['dateMax'] for p in partitions), default=None),
                'books': [{'code': code, 'name': BOOKS[code], 'quoteCount': count} for code, count in sorted(book_counts.items())],
                'leagues': [{'id': code, 'name': LEAGUES[code][0], 'country': LEAGUES[code][1],
                             'eventCount': sum(p['eventCount'] for p in partitions if p['league'] == code),
                             'quoteCount': sum(p['quoteCount'] for p in partitions if p['league'] == code)}
                            for code in LEAGUES if any(p['league'] == code for p in partitions)],
                'markets': [{**market, 'quoteCount': market_counts[market['id']]} for market in MARKETS],
                'phases': [{**phase, 'quoteCount': phase_counts[phase['id']]} for phase in PHASES],
                'seasons': seasons, 'partitions': partitions, 'unavailableArchives': unavailable,
                'validation': dict(all_reports),
                'method': {'individualBookmakersOnly': True, 'marketAggregatesExcluded': True,
                           'quoteCaptureTimestampAvailable': False, 'openingClosingMerged': False,
                           'existingWorkspaceEventDeduplication': False,
                           'pinnacleReliabilityNote': 'The provider reports unreliable/stale Pinnacle public API prices since 2025-07-23.',
                           'usage': 'Private personal research archive; source restrictions apply; not a commercial redistribution or training dataset.'}}
    atomic(OUT / 'expanded-football-manifest.json', (dumps(manifest) + '\n').encode())
    print(dumps({key: manifest[key] for key in ('eventCount', 'quoteCount', 'sourceFileCount', 'compressedBytes', 'dateMin', 'dateMax')}), flush=True)


if __name__ == '__main__':
    main()
