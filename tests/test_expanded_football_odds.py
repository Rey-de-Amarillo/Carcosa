import importlib.util
import json
import csv
import gzip
import hashlib
import io
import math
import zipfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('expanded_acquire', ROOT / 'scripts/acquire_expanded_football_odds.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def rows(table):
    return [dict(zip(table['columns'], row)) for row in table['rows']]


class ExpandedOddsTests(unittest.TestCase):
    def test_real_book_headers_phases_and_aggregates(self):
        csv = ('Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,B365H,B365D,B365A,B365CH,B365CD,B365CA,BFH,BFDH,BFEH,MaxH,AvgH,BbMxH\n'
               'E0,31/10/2026,15:00,Alpha,Beta,2,1,2.1,3.2,4,2.2,3.3,4.1,2.05,2.08,2.12,9,9,9\n').encode()
        result, validation = mod.transform_csv(csv, 'E0', '2026/2027')
        events, quotes = rows(result['events']), rows(result['quotes'])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['date'], '2026-10-31')
        self.assertEqual(events[0]['kickoff_time'], '15:00')
        self.assertEqual(events[0]['sourceRow'], 2)
        self.assertEqual(events[0]['home_corners'], None)
        self.assertEqual(len(quotes), 9)
        self.assertEqual({q['book'] for q in quotes}, {'B365', 'BF', 'BFD', 'BFE'})
        self.assertEqual({q['sourceColumn'] for q in quotes}, {'B365H', 'B365D', 'B365A', 'B365CH', 'B365CD', 'B365CA', 'BFH', 'BFDH', 'BFEH'})
        self.assertEqual(next(q for q in quotes if q['sourceColumn'] == 'B365CH')['phase'], 'closing')
        self.assertEqual(next(q for q in quotes if q['sourceColumn'] == 'B365H')['phase'], 'pre_closing')
        self.assertTrue(all(q['sourceRow'] == 2 and q['period'] == 'full' for q in quotes))
        self.assertTrue(all('capturedAt' not in q and 'probability' not in q for q in quotes))
        self.assertEqual(validation['sourceRows'], 1)

    def test_total_and_asian_lines_preserve_side_and_phase(self):
        csv = ('Date,HomeTeam,AwayTeam,B365>2.5,B365<2.5,B365C>2.5,B365C<2.5,AHh,AHCh,B365AHH,B365AHA,B365CAHH,B365CAHA\n'
               '31/10/26,Alpha,Beta,1.8,2.1,1.7,2.2,-0.5,-0.75,1.9,2,1.95,1.95\n').encode()
        result, _ = mod.transform_csv(csv, 'E0', '2026/2027')
        quotes = rows(result['quotes'])
        self.assertEqual(len(quotes), 8)
        by_field = {q['sourceColumn']: q for q in quotes}
        self.assertEqual(by_field['B365>2.5']['line'], 2.5)
        self.assertEqual(by_field['B365<2.5']['selection'], 'under')
        self.assertEqual(by_field['B365AHH']['line'], -0.5)
        self.assertEqual(by_field['B365AHA']['line'], 0.5)
        self.assertEqual(by_field['B365CAHH']['line'], -0.75)
        self.assertEqual(by_field['B365CAHA']['line'], 0.75)
        self.assertEqual(by_field['B365CAHA']['lineColumn'], 'AHCh')

    def test_book_specific_handicap_not_inferred_from_aggregate(self):
        csv = ('Date,HomeTeam,AwayTeam,B365AH,GBAH,LBAH,BbAHh,B365AHH,B365AHA,GBAHH,GBAHA,LBAHH,LBAHA,PAHH,PAHA\n'
               '31/10/26,Alpha,Beta,-1,-0.25,0,-0.5,1.9,2,1.85,2.1,1.8,2.2,1.9,1.9\n').encode()
        result, _ = mod.transform_csv(csv, 'E0', '2026/2027')
        quotes = rows(result['quotes'])
        self.assertEqual(len(quotes), 6)
        self.assertEqual({q['book'] for q in quotes}, {'B365', 'GB', 'LB'})
        self.assertEqual(next(q for q in quotes if q['sourceColumn'] == 'GBAHH')['line'], -0.25)

    def test_invalid_odds_missing_identity_and_alias_conflicts(self):
        csv = ('Date,HomeTeam,AwayTeam,PSH,PH,B365D,B365A,B365H\n'
               '31/10/26,Alpha,Beta,2,2.2,NaN,1,0\n'
               'no date,Alpha,Beta,2,2,3,4,5\n').encode()
        result, validation = mod.transform_csv(csv, 'E0', '2026/2027')
        self.assertEqual(len(result['events']['rows']), 1)
        self.assertEqual(result['quotes']['rows'], [])
        self.assertEqual(validation['conflictingAliasCells'], 1)
        self.assertEqual(validation['invalidIdentityRows'], 1)
        self.assertEqual(validation['invalidPriceCells'], 3)

    def test_stable_event_identity_and_duplicate_rows(self):
        data = b'Date,HomeTeam,AwayTeam,B365H\n31/10/26,Alpha,Beta,2\n31/10/26,Alpha,Beta,3\n'
        result, validation = mod.transform_csv(data, 'E0', '2026/2027')
        self.assertEqual(len(result['events']['rows']), 1)
        self.assertEqual(len(result['quotes']['rows']), 1)
        self.assertEqual(result['quotes']['rows'][0][7], 2)
        self.assertEqual(validation['duplicateIdentityRows'], 1)
        again, _ = mod.transform_csv(data, 'E0', '2026/2027')
        self.assertEqual(result, again)
        self.assertNotEqual(result['events']['rows'][0][0], mod.transform_csv(data, 'E1', '2026/2027')[0]['events']['rows'][0][0])

    def test_generated_archive_provenance_and_counts(self):
        manifest_path = ROOT / 'app/data/expanded-football-manifest.json'
        if not manifest_path.exists():
            self.skipTest('Run acquisition to validate the generated archive')
        manifest = json.loads(manifest_path.read_text())
        events_total = quotes_total = 0
        identifiers = set()
        source_samples = 0
        for part in manifest['partitions']:
            compressed = (ROOT / 'app/data' / part['path']).read_bytes()
            self.assertEqual(hashlib.sha256(compressed).hexdigest(), part['sha256'])
            self.assertLess(len(compressed), 25 * 1024 * 1024)
            payload = json.loads(gzip.decompress(compressed))
            events, quotes = payload['events']['rows'], payload['quotes']['rows']
            self.assertEqual(payload['events']['columns'], mod.EVENT_COLUMNS)
            self.assertEqual(payload['quotes']['columns'], mod.QUOTE_COLUMNS)
            self.assertEqual(len(events), part['eventCount'])
            self.assertEqual(len(quotes), part['quoteCount'])
            self.assertEqual(min(row[1] for row in events), part['dateMin'])
            self.assertEqual(max(row[1] for row in events), part['dateMax'])
            for event in events:
                self.assertNotIn(event[0], identifiers)
                identifiers.add(event[0])
                self.assertEqual(len(event), len(mod.EVENT_COLUMNS))
            archive_code = part['id'].split('-')[0]
            archive_path = mod.RAW / f'{archive_code}.zip'
            source_rows = None
            if archive_path.exists():
                with zipfile.ZipFile(archive_path) as archive:
                    raw = archive.read(part['source']['archiveMember'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), part['source']['sha256'])
                source_rows = list(csv.DictReader(io.StringIO(mod.csv_text(raw))))
            quote_ids = set()
            for index, quote in enumerate(quotes):
                self.assertEqual(len(quote), len(mod.QUOTE_COLUMNS))
                event, book, market, period, selection, line, phase, price, column, source_row, line_column = quote
                self.assertTrue(0 <= event < len(events))
                self.assertIn(book, mod.BOOKS)
                self.assertIn(phase, ['pre_closing', 'closing'])
                self.assertEqual(period, 'full')
                self.assertTrue(math.isfinite(price) and price > 1)
                self.assertFalse(column.startswith(('Avg', 'Max', 'Bb')))
                self.assertEqual(source_row, events[event][-1])
                identity = (event, book, market, selection, line, phase)
                self.assertNotIn(identity, quote_ids)
                quote_ids.add(identity)
                if source_rows is not None and index % 257 == 0:
                    original = source_rows[source_row - 2]
                    self.assertEqual(price, float(original[column]))
                    if line_column:
                        home_line = float(original[line_column])
                        self.assertEqual(line, home_line if selection == 'home' else -home_line)
                    source_samples += 1
            events_total += len(events)
            quotes_total += len(quotes)
        self.assertEqual(events_total, manifest['eventCount'])
        self.assertEqual(quotes_total, manifest['quoteCount'])
        self.assertGreater(quotes_total, 6_000_000)
        self.assertGreaterEqual(len(manifest['leagues']), 22)
        self.assertGreaterEqual(len(manifest['seasons']), 27)
        self.assertGreater(source_samples, 10000)


if __name__ == '__main__':
    unittest.main()
