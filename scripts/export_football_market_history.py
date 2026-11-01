#!/usr/bin/env python3
"""Export actual Singapore Pools archived goal/score prices for alert research.

A separate universe avoids counting a fixture again in the multi-book sample.
Prices retain their source labels and period; no 1X2 quote becomes a score quote.
"""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
LEAGUES={'English Premier':'E0','English League Champ':'E1','Dutch League':'N1','French League':'F1','German League':'D1','Italian League':'I1','Spanish League':'SP1','A League':'SGP_AUS','J League':'SGP_JPN','K League':'SGP_KOR','Swedish League':'SGP_SWE','US Soccer League':'SGP_USA'}


def main():
    conn=sqlite3.connect('file:'+str(ROOT/'data/processed/free_football_history.sqlite')+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    by_id={}
    for raw in conn.execute('SELECT * FROM sgodds_matches ORDER BY start_time_source,match_row_id'):
        r=dict(raw)
        if ' vs ' not in r['match_name']:continue
        h,a=r['match_name'].split(' vs ',1)
        league=LEAGUES.get(r['league'],'SG:'+r['league'])
        by_id[r['match_row_id']]={'id':'sg:'+str(r['match_row_id']),'date':r['start_time_source'][:10], 'startTimeSource':r['start_time_source'],'league':league,'league_name':r['league'],'home':h,'away':a,'home_team':h,'away_team':a,'home_score':r['ft_home'],'away_score':r['ft_away'],'home_ht_score':r['ht_home'],'away_ht_score':r['ht_away'],'home_corners':None,'away_corners':None,'marketQuotes':[],'source':'SGodds / Singapore Pools','quotePhase':'archive_timestamp_unknown'}
    counts={}
    for raw in conn.execute('SELECT * FROM sgodds_prices ORDER BY match_row_id,source_field'):
        r=dict(raw);e=by_id.get(r['match_row_id'])
        if e is None:continue
        source=r['market'];period={'FT':'full','HT':'first_half'}.get(r['period'])
        if period is None:continue
        market={'ft_1x2':'match_result','ht_1x2':'match_result','ft_correct_score':'correct_score','ht_correct_score':'correct_score','ft_btts':'btts','ht_btts':'btts','ft_goal_total':'total_goals','ht_goal_total':'total_goals','ft_exact_total_goals':'total_goals','ht_exact_total_goals':'total_goals'}.get(source)
        if market is None:continue
        q={'book':'SGP','market':market,'period':period,'selection':r['selection'],'odds':r['decimal_odds'],'sourceField':r['source_field'],'source':'SGodds / Singapore Pools'}
        if market=='correct_score':
            if r['selection']=='other':continue
            try:q['homeGoals'],q['awayGoals']=map(int,r['selection'].split('-'))
            except ValueError:continue
        if market=='total_goals':
            if source.endswith('exact_total_goals'):
                if not str(r['selection']).isdigit():continue
                q['line']=int(r['selection']);q['selection']='exact'
                e['marketQuotes'].append(q);counts[market]=counts.get(market,0)+1;continue
            try:q['line']=float(r['line_source'])
            except (ValueError,TypeError):continue
        e['marketQuotes'].append(q);counts[market]=counts.get(market,0)+1
    events=[];offers=[];excluded=0;seen=set()
    for e in by_id.values():
        hda={q['selection']:q['odds'] for q in e['marketQuotes'] if q['market']=='match_result' and q['period']=='full'}
        if set(hda)!={'home','draw','away'}:excluded+=1;continue
        key=(e['date'],e['league'],e['home'],e['away'])
        if key in seen:raise AssertionError('Duplicate archived fixture')
        seen.add(key);index=len(events);events.append(e)
        for side,name in enumerate(('home','draw','away')):
            offers.append({'id':e['id'],'event':index,'date':e['date'],'league':e['league'],'home':e['home'],'away':e['away'],'book':'SGP','side':side,'odds':hda[name],'probability':None,'referenceMean':None,'referenceSd':None,'references':[],'ev':None,'won':None if e['home_score'] is None or e['away_score'] is None else side==(0 if e['home_score']>e['away_score'] else 1 if e['home_score']==e['away_score'] else 2),'market':'h2h'})
    payload={'schemaVersion':1,'source':{'name':'SGodds / Singapore Pools','url':'https://sgodds.com/football/data','audit':'data/analysis/sgodds_archive_audit.json','priceTiming':'archive_timestamp_unknown','historicalScope':'recorded_archive_not_confirmed_executable_quotes'},'events':events,'offers':offers,'counts':{'events':len(events),'contextOffers':len(offers),'marketQuotes':counts,'excludedMissingContext':excluded,'completed':sum(e['home_score'] is not None and e['away_score'] is not None for e in events),'pending':sum(e['home_score'] is None or e['away_score'] is None for e in events)},'leagues':sorted({(e['league'],e['league_name']) for e in events})}
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    out=ROOT/'app/data/football-market-history.json.gz';out.write_bytes(gzip.compress(encoded,mtime=0,compresslevel=9))
    info={'path':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'bytes':out.stat().st_size,'counts':payload['counts']}
    (ROOT/'app/data/football-market-history.json').write_text(json.dumps(info,indent=2)+'\n')
    # Reconcile every exported score price with its original database key.
    for e in events:
        assert len({(q['market'],q['period'],q.get('line'),q['selection']) for q in e['marketQuotes']})==len(e['marketQuotes'])
        assert all(q['odds']>1 for q in e['marketQuotes'])
        if all(e[k] is not None for k in ('home_ht_score','away_ht_score','home_score','away_score')):
            assert e['home_ht_score']<=e['home_score'] and e['away_ht_score']<=e['away_score']
    print(json.dumps(info))

if __name__=='__main__':main()
