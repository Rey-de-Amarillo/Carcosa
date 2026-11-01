"""Exact SGodds fixture provenance, without invented times or source attribution."""
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from acquire_additional_market_history import export_legacy_provenance


class MarketSourceProvenanceTest(unittest.TestCase):
    def fixture(self,folder,url='https://sgodds.com/downloads/example.csv'):
        db=folder/'source.sqlite'
        with sqlite3.connect(db) as conn:
            conn.executescript('''CREATE TABLE source_files(file_id INTEGER PRIMARY KEY,source_id TEXT,url TEXT,retrieved_at TEXT,sha256 TEXT);
                CREATE TABLE sgodds_matches(match_row_id INTEGER PRIMARY KEY,source_file_id INTEGER,source_row_number INTEGER,source_match_id TEXT);''')
            conn.executemany('INSERT INTO source_files VALUES(?,?,?,?,?)',[(7,'sgodds',url,'2026-10-30T18:39:20+00:00','a'*64),(8,'sgodds',None,None,'b'*64)])
            conn.executemany('INSERT INTO sgodds_matches VALUES(?,?,?,?)',[(1,7,29,'0032'),(2,8,None,None),(3,7,31,'0034')])
        archive=folder/'archive.json.gz';archive.write_bytes(gzip.compress(json.dumps({'events':[{'id':'sg:1'},{'id':'sg:2'}]}).encode(),mtime=0))
        return db,archive,folder/'provenance.json'

    def test_exact_stored_join_and_missing_values(self):
        with tempfile.TemporaryDirectory() as temp:
            db,archive,out=self.fixture(Path(temp));result=export_legacy_provenance(db,archive,out)
            self.assertEqual(result['eventCount'],2);self.assertEqual(result['sourceCount'],2)
            self.assertEqual(result['events']['sg:1'],{'sourceId':'sgodds-file-7','sourceRow':29,'sourceEventId':'0032'})
            self.assertEqual(result['events']['sg:2'],{'sourceId':'sgodds-file-8'})
            self.assertNotIn('sg:3',result['events'],'database rows outside the published archive are excluded')
            sources={s['id']:s for s in result['sources']};self.assertIsNone(sources['sgodds-file-8']['url']);self.assertIsNone(sources['sgodds-file-8']['retrievedAt'])
            for source in result['sources']:
                self.assertEqual(source['provider'],'SGodds');self.assertEqual(source['book'],'SGP');self.assertEqual(source['bookmaker'],'Singapore Pools');self.assertNotIn('capturedAt',source)
            before=out.read_bytes();export_legacy_provenance(db,archive,out);self.assertEqual(out.read_bytes(),before,'provenance replay never invents current retrieval times')

    def test_missing_mapping_does_not_write_inferred_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            db,archive,out=self.fixture(Path(temp))
            with sqlite3.connect(db) as conn:conn.execute('DELETE FROM sgodds_matches WHERE match_row_id=2')
            with self.assertRaisesRegex(ValueError,'incomplete'):export_legacy_provenance(db,archive,out)
            self.assertFalse(out.exists())

    def test_query_or_credentials_are_not_exported(self):
        for url in ['https://sgodds.com/downloads/example.csv?api_key=EXAMPLE','https://user:password@sgodds.com/downloads/example.csv','https://other.example/data.csv']:
            with self.subTest(url=url),tempfile.TemporaryDirectory() as temp:
                db,archive,out=self.fixture(Path(temp),url)
                with self.assertRaisesRegex(ValueError,'credential-free'):export_legacy_provenance(db,archive,out)
                self.assertFalse(out.exists())

    def test_published_lookup_covers_every_existing_fixture(self):
        payload=json.loads((ROOT/'app/data/legacy-sgodds-provenance.json').read_text())
        archive_bytes=(ROOT/'app/data/football-market-history.json.gz').read_bytes();archive=json.loads(gzip.decompress(archive_bytes))
        self.assertEqual(payload['sourceArchiveSha256'],hashlib.sha256(archive_bytes).hexdigest())
        self.assertEqual(set(payload['events']),{e['id'] for e in archive['events']});self.assertEqual(payload['eventCount'],3257);self.assertEqual(payload['sourceCount'],12)
        sources={s['id']:s for s in payload['sources']}
        for row in payload['events'].values():self.assertIn(row['sourceId'],sources);self.assertGreaterEqual(row['sourceRow'],2)
        for source in sources.values():
            parsed=urlsplit(source['url']);self.assertEqual(parsed.netloc,'sgodds.com');self.assertFalse(parsed.query);self.assertIsNone(parsed.username);self.assertEqual(len(source['sha256']),64)
        audit_path=ROOT/'data/analysis/sgodds_archive_audit.json'
        if not audit_path.exists():return
        audit=json.loads(audit_path.read_text());files={f['sha256']:f for f in audit['files']};rows={}
        for source in sources.values():
            record=files[source['sha256']];path=ROOT/record['path']
            if not path.exists():return
            raw=path.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),source['sha256']);self.assertEqual(source['url'],record['url']);self.assertEqual(source['retrievedAt'],record['retrieved_at'])
            rows[source['id']]=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
        for event in archive['events']:
            provenance=payload['events'][event['id']];raw=rows[provenance['sourceId']][provenance['sourceRow']-2]
            self.assertEqual(provenance['sourceEventId'],raw['ID']);self.assertEqual(event['home']+' vs '+event['away'],raw['Match']);self.assertEqual(event['date'],raw['Start Time'][:10])
            for quote in event['marketQuotes']:self.assertEqual(quote['odds'],float(raw[quote['sourceField']]))

    def test_additional_manifest_provenance_has_no_embedded_credentials(self):
        manifest=json.loads((ROOT/'app/data/additional-market-manifest.json').read_text())
        for source in [*manifest['sources'],*manifest['documents'],*[p['source'] for p in manifest['partitions']]]:
            parsed=urlsplit(source['url']);self.assertEqual(parsed.netloc,'sgodds.com');self.assertFalse(parsed.query);self.assertIsNone(parsed.username);self.assertIsNone(parsed.password);self.assertEqual(len(source['sha256']),64)


if __name__=='__main__':unittest.main()
