#!/usr/bin/env python3
"""Acquire SGodds' public CSV archive and export only previously absent quotes.

SGodds is the archive website. Singapore Pools is the attributed bookmaker;
retrieval time is never treated as the time a quoted price was available.
No API keys, authenticated sessions, or paid services are used.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
import acquire_sgodds_archive as sg

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/additional-markets-sgodds'
OUT = ROOT / 'app/data'
PAGE = 'https://sgodds.com/football/data'
MANIFEST = OUT / 'additional-market-manifest.json'
LEAGUES = {'English Premier':'E0','English League Champ':'E1','Dutch League':'N1','French League':'F1','German League':'D1','Italian League':'I1','Spanish League':'SP1','A League':'SGP_AUS','J League':'SGP_JPN','K League':'SGP_KOR','Swedish League':'SGP_SWE','US Soccer League':'SGP_USA'}
LABELS = {'match_result':'Resultado (1X2)','asian_handicap':'Hándicap asiático','half_time_full_time':'Descanso / Final','correct_score':'Marcador exacto','total_goals':'Total de goles','first_team_to_score':'Primer equipo en marcar','odd_even':'Goles: impar / par','btts':'Ambos equipos marcarán','sgp_correct_score_other':'Marcador: cualquier otro resultado','sgp_half_goal_handicap':'Hándicap «1/2 Goal» original SGP'}
LIMITS = [
    'Public CSV archive advertises opening prices for twelve leagues in 2026; older years are not advertised on this page.',
    'Source Start Time is retained as supplied; source timezone is not independently verified.',
    'Exact quote timestamps and simultaneous availability are not provided: retrievedAt is a file download time, not capturedAt.',
    'SGodds documents possible historical handicap/total line and price mismatches when Singapore Pools changes a line.',
    'First-goal markets cannot generally be settled from HT/FT scores alone; no goal sequence is supplied.',
    'The original 1/2 Goal and Any Other Score selections remain explicitly source-specific where the app has no equivalent settlement contract.',
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(content):
    return hashlib.sha256(content).hexdigest()


def fetch(url, folder):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'sgodds.com' or parsed.query or parsed.username or parsed.password:
        raise ValueError('Only discovered, credential-free SGodds public URLs are accepted')
    name = parsed.path.rsplit('/', 1)[-1] or 'index.html'
    if '.' not in name:
        name += '.html'
    with urlopen(Request(url, headers={'User-Agent':'PersonalFootballResearch/1.0'}), timeout=40) as response:
        content = response.read(15_000_001)
        if len(content) > 15_000_000:
            raise ValueError('Download exceeds 15 MB limit')
        resolved = response.url
        if urlsplit(resolved).query:
            raise ValueError('Unexpected query-bearing redirect')
        modified = response.headers.get('Last-Modified')
    path = folder / name
    path.write_bytes(content)
    return {'path':str(path.relative_to(ROOT)), 'url':url, 'resolvedUrl':resolved, 'retrievedAt':now(), 'lastModified':modified, 'bytes':len(content), 'sha256':digest(content)}


def original_record(record):
    return {'path':record['path'], 'url':record['url'], 'resolvedUrl':record.get('resolved_url',record['url']), 'retrievedAt':record['retrieved_at'], 'lastModified':record.get('last_modified'), 'bytes':record['bytes'], 'sha256':record['sha256']}


def records(refresh):
    prior_path = ROOT / 'data/analysis/sgodds_archive_audit.json'
    prior = json.loads(prior_path.read_text()) if prior_path.exists() else {'files':[]}
    historical = [original_record(record) for record in prior['files'] if (ROOT / record['path']).is_file()]
    cache = RAW / 'latest.json'
    if not refresh and cache.exists():
        current = json.loads(cache.read_text())
    else:
        folder = RAW / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        folder.mkdir(parents=True, exist_ok=True)
        source_page = fetch(PAGE, folder)
        html = (ROOT / source_page['path']).read_text()
        links = sorted({urljoin(PAGE,h) for h in re.findall(r'href=["\']([^"\']+\.csv)["\']', html)})
        if not links:
            raise ValueError('No actual public CSV links found')
        with ThreadPoolExecutor(max_workers=2) as pool:
            files = list(pool.map(lambda url: fetch(url,folder), links))
        docs = [source_page, fetch('https://sgodds.com/help',folder)]
        current = {'provider':'SGodds', 'files':files, 'documents':docs}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(current,indent=2)+'\n')
    # Historical rows which disappeared from today's rolling CSVs are retained.
    return historical, current


def read_rows(record):
    content = (ROOT / record['path']).read_bytes()
    if digest(content) != record['sha256']:
        raise ValueError('Source hash mismatch: '+record['path'])
    reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
    if not sg.META <= set(reader.fieldnames or []):
        raise ValueError('Unexpected source schema')
    return list(reader)


def identity(league, date, home, away):
    return (league, date[:10], home.strip(), away.strip())


def contract(field, row):
    source = sg.field_contract(field,row)
    if source is None:
        return None
    family, period, selection = source['market'], source['period'], source['selection']
    q = {'period':{'FT':'full','HT':'first_half','HT+FT':'full'}[period], 'selection':selection}
    if family in ('ft_1x2','ht_1x2'):
        q['market'] = 'match_result'
    elif family in ('ft_asian_handicap','ht_asian_handicap','ft_half_goal_handicap_source_label'):
        q.update(market='sgp_half_goal_handicap' if family=='ft_half_goal_handicap_source_label' else 'asian_handicap',line=float(source['line_source']),team=selection)
    elif family=='ht_ft_result':
        q.update(market='half_time_full_time',selection=selection.replace('/','_'))
    elif family in ('ft_correct_score','ht_correct_score'):
        if selection=='other':
            q['market']='sgp_correct_score_other'
        else:
            home,away=map(int,selection.split('-'));q.update(market='correct_score',homeGoals=home,awayGoals=away)
    elif family in ('ft_exact_total_goals','ht_exact_total_goals'):
        q.update(market='total_goals',team='total',selection='at_least' if selection.endswith('+') else 'exact',line=int(selection.rstrip('+')))
    elif family in ('ft_first_team_to_score','ht_first_team_to_score'):
        q.update(market='first_team_to_score',selection='none' if selection=='no_goal' else selection)
    elif family in ('ft_odd_even','ht_odd_even'):
        q.update(market='odd_even',team='total')
    elif family in ('ft_goal_total','ht_goal_total'):
        q.update(market='total_goals',line=float(source['line_source']),team='total')
    elif family in ('ft_btts','ht_btts'):
        q['market']='btts'
    else:
        raise ValueError('Unmapped actual source family '+family)
    q['sourceMarket']=family
    q['lineSource']=source['line_source']
    q['settlementSupported']=q['market'] not in ('sgp_correct_score_other','sgp_half_goal_handicap') and family not in ('ft_first_team_to_score','ht_first_team_to_score')
    if q['market']=='asian_handicap' and q['line']*2 != int(q['line']*2):
        q['settlementSupported']=False
    return q


def export_legacy_provenance(db_path=None, archive_path=None, out_path=None):
    """Map every existing sg:<row> fixture to its stored source-file evidence."""
    db_path = Path(db_path or ROOT / 'data/processed/free_football_history.sqlite')
    archive_path = Path(archive_path or OUT / 'football-market-history.json.gz')
    out_path = Path(out_path or OUT / 'legacy-sgodds-provenance.json')
    archive_bytes = archive_path.read_bytes()
    archive = json.loads(gzip.decompress(archive_bytes))
    wanted = {event['id'] for event in archive['events']}
    sources, events = {}, {}
    with sqlite3.connect('file:'+str(db_path.resolve())+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        rows=conn.execute('''SELECT m.match_row_id,m.source_row_number,m.source_match_id,
            f.file_id,f.url,f.retrieved_at,f.sha256 FROM sgodds_matches m
            JOIN source_files f ON f.file_id=m.source_file_id
            WHERE f.source_id='sgodds' ORDER BY m.match_row_id''')
        for row in rows:
            event_id='sg:'+str(row['match_row_id'])
            if event_id not in wanted:
                continue
            url=row['url']
            if url is not None:
                parsed=urlsplit(url)
                if parsed.scheme!='https' or parsed.netloc!='sgodds.com' or parsed.query or parsed.username or parsed.password:
                    raise ValueError('Legacy source URL is not a credential-free public SGodds URL')
            source_id='sgodds-file-'+str(row['file_id'])
            sources[source_id]={'id':source_id,'provider':'SGodds','book':'SGP','bookmaker':'Singapore Pools','url':url,'retrievedAt':row['retrieved_at'],'sha256':row['sha256']}
            entry={'sourceId':source_id}
            if row['source_row_number'] is not None:
                entry['sourceRow']=row['source_row_number']
            if row['source_match_id'] is not None:
                entry['sourceEventId']=row['source_match_id']
            events[event_id]=entry
    if set(events)!=wanted:
        raise ValueError('Legacy fixture provenance is incomplete; no mapping was invented')
    payload={'schemaVersion':1,'provider':'SGodds','book':'SGP','bookmaker':'Singapore Pools','sourceArchiveSha256':digest(archive_bytes),'sources':list(sources.values()),'events':events,'eventCount':len(events),'sourceCount':len(sources)}
    out_path.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true',help='Download the currently advertised public CSVs')
    parser.add_argument('--legacy-provenance-only',action='store_true',help='Export exact existing fixture-to-CSV provenance from the local audit database')
    args=parser.parse_args()
    if args.legacy_provenance_only:
        payload=export_legacy_provenance()
        print(json.dumps({'eventCount':payload['eventCount'],'sourceCount':payload['sourceCount'],'output':'app/data/legacy-sgodds-provenance.json'}))
        return
    historical,current=records(args.refresh)
    existing=json.loads(gzip.decompress((OUT/'football-market-history.json.gz').read_bytes()))
    prior_events={identity(e['league_name'],e['date'],e['home'],e['away']):e for e in existing['events']}
    existing_fields={(key,q['sourceField']):q['odds'] for key,e in prior_events.items() for q in e['marketQuotes']}
    rows={};raw_rows=0
    for record in [*historical,*current['files']]:
        for row in read_rows(record):
            raw_rows+=1
            if ' vs ' not in row['Match']:
                continue
            home,away=row['Match'].split(' vs ',1)
            key=identity(row['League'],row['Start Time'],home,away)
            rows[key]=(row,record)
    partitions=defaultdict(list);market_counts=Counter();family_counts=Counter();excluded=Counter();all_new_events=set();all_events=set();added=0;sourcefiles={}
    for key,(row,record) in sorted(rows.items()):
        original=prior_events.get(key)
        event_id=original['id'] if original else 'sgodds:'+digest(json.dumps(key).encode())[:20]
        match=sg.RESULT.fullmatch(row['Result'].strip())
        hh,ha,fh,fa=map(int,match.groups()) if match else (None,None,None,None)
        event={'id':event_id,'date':key[1],'league':LEAGUES.get(key[0],'SG:'+key[0]),'league_name':key[0],'home':key[2],'away':key[3],'home_team':key[2],'away_team':key[3],'home_score':fh,'away_score':fa,'home_ht_score':hh,'away_ht_score':ha,'sourceProvider':'SGodds','sourceEventId':row['ID'],'sourceStartTime':row['Start Time'],'sourceTimezoneVerified':False,'marketQuotes':[]}
        if original:
            event['existingEventId']=original['id']
        else:
            all_new_events.add(event_id)
        for field,raw in row.items():
            odds=sg.valid_odds(raw)
            if odds is None:
                continue
            try:
                q=contract(field,row)
            except (ValueError,TypeError) as error:
                excluded['unparseable_contract']+=1
                continue
            if q is None:
                continue
            if (key,field) in existing_fields:
                excluded['already_exported_quotes']+=1
                if existing_fields[(key,field)] != odds:
                    excluded['changed_existing_opening_quotes_not_added']+=1
                continue
            q.update(book='SGP',bookmaker='Singapore Pools',odds=odds,sourceProvider='SGodds',sourceUrl=record['url'],sourceSha256=record['sha256'],retrievedAt=record['retrievedAt'],sourceField=field,quoteId='sgodds:'+digest(json.dumps([key,field]).encode())[:24],quotePhase='opening_archive_timestamp_unknown',capturedAt=None,rulesId=None,canEvaluateFromScores=q.pop('settlementSupported'))
            event['marketQuotes'].append(q);market_counts[q['market']]+=1;family_counts[q['sourceMarket']]+=1;added+=1
        if event['marketQuotes']:
            all_events.add(event_id);partkey=(event['league'],record['sha256']);partitions[partkey].append(event);sourcefiles[record['sha256']]=record
    parts=[]
    for (league,sourcehash),events in sorted(partitions.items()):
        record=sourcefiles[sourcehash];part_id=re.sub(r'[^a-z0-9]+','-',league.lower()).strip('-')+'-'+sourcehash[:10]
        path='additional-market-'+part_id+'.json.gz'
        data={'schemaVersion':1,'provider':'SGodds','bookmaker':'Singapore Pools','source':{'url':record['url'],'retrievedAt':record['retrievedAt'],'sha256':sourcehash},'events':events}
        encoded=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode();compressed=gzip.compress(encoded,compresslevel=9,mtime=0)
        if len(compressed)>=25*1024*1024:
            raise ValueError('Partition exceeds static hosting limit')
        (OUT/path).write_bytes(compressed)
        quotes=sum(len(e['marketQuotes']) for e in events)
        parts.append({'id':part_id,'path':path,'source':data['source'],'sha256':digest(compressed),'bytes':len(compressed),'eventCount':len(events),'newEventCount':sum('existingEventId' not in e for e in events),'quoteCount':quotes,'dateMin':min(e['date'] for e in events),'dateMax':max(e['date'] for e in events),'league':league,'season':None})
    retained={p['path'] for p in parts}
    for stale in OUT.glob('additional-market-*.json.gz'):
        if stale.name not in retained:
            stale.unlink()
    source_events={e['id']:e for events in partitions.values() for e in events}
    manifest={'schemaVersion':1,'provider':'SGodds','bookmaker':'Singapore Pools','providerUrl':PAGE,'retrievedAt':max(r['retrievedAt'] for r in current['files']),'books':[{'code':'SGP','name':'Singapore Pools','provider':'SGodds'}],'markets':[{'id':k,'name':LABELS[k],'quoteCount':v} for k,v in sorted(market_counts.items())],'leagues':[{'id':k,'name':next(e['league_name'] for e in source_events.values() if e['league']==k)} for k in sorted({e['league'] for e in source_events.values()})],'partitions':parts,'eventCount':len(all_events),'newEventCount':len(all_new_events & all_events),'existingEventCount':len(all_events)-len(all_new_events & all_events),'quoteCount':added,'dateMin':min(e['date'] for e in source_events.values()),'dateMax':max(e['date'] for e in source_events.values()),'sourceMarketQuoteCounts':dict(family_counts),'excluded':dict(excluded),'rawRowsRead':raw_rows,'uniqueSourceRows':len(rows),'existingArchive':{'path':'football-market-history.json.gz','eventCount':len(existing['events']),'quoteCount':sum(len(e['marketQuotes']) for e in existing['events']),'sha256':digest((OUT/'football-market-history.json.gz').read_bytes())},'sources':[sourcefiles[k] for k in sorted(sourcefiles)],'documents':current['documents'],'limitations':LIMITS}
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('provider','eventCount','newEventCount','existingEventCount','quoteCount','dateMin','dateMax','sourceMarketQuoteCounts','excluded')},ensure_ascii=False,indent=2))
    print('Partitions:',len(parts),'max compressed bytes:',max(p['bytes'] for p in parts))


if __name__=='__main__':
    main()
