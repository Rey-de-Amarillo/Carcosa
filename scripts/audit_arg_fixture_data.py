#!/usr/bin/env python3
"""Audit only Estudiantes Rio Cuarto–Gimnasia LP before 2026-10-30 kick-off.

Read-only toward model inputs. ESPN public responses are archived locally;
no odds-provider request, credentials, purchase or wager is used.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE='https://site.api.espn.com/apis/site/v2/sports/soccer/arg.1/'
TARGET_IDS={'19685':'Estudiantes Rio Cuarto','9':'Gimnasia L.P.'}
KICKOFF='2026-10-30T22:00:00+00:00'
FIELDS={'ft':('home_score','away_score'),'ht':('home_ht_score','away_ht_score'),'corners':('home_corners','away_corners'),'yellow_cards':('home_yellow','away_yellow'),'shots':('home_shots','away_shots'),'shots_on_target':('home_shots_on_target','away_shots_on_target'),'red_cards':('home_red','away_red')}


def num(value):
    if value in (None,''):return None
    try:return float(value)
    except (TypeError,ValueError):return None


def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


def fetch(url,path):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (personal sports research)'}),timeout=25) as response:
        raw=response.read();data=json.loads(raw);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        info={'url':url,'path':str(path.relative_to(ROOT)),'retrieved_at':datetime.now(timezone.utc).isoformat(),'server_date':response.headers.get('Date'),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        return data,info


def local_audit():
    paths=['data/processed/matches.csv','data/raw/football/ARG.csv']
    metadata=[]
    with (ROOT/paths[0]).open(newline='') as h:reader=csv.DictReader(h);columns=reader.fieldnames;rows=list(reader)
    arg=[r for r in rows if r.get('league_code')=='ARG' and r['date']<'2026-10-30']
    for path in paths:
        raw=(ROOT/path).read_bytes()
        with (ROOT/path).open(newline='',encoding='utf-8-sig') as h:reader=csv.DictReader(h);cols=reader.fieldnames;source_rows=list(reader)
        metadata.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(source_rows),'columns':cols})
    teams={}
    for team in TARGET_IDS.values():
        sample=[r for r in arg if team in (r['home_team'],r['away_team'])]
        teams[team]={'n':len(sample),'home':sum(r['home_team']==team for r in sample),'away':sum(r['away_team']==team for r in sample),'date_min':min(r['date'] for r in sample),'date_max':max(r['date'] for r in sample),'by_season':dict(Counter(r['season'] for r in sample)),'coverage':{key:sum(all(num(r.get(k)) is not None for k in cols) for r in sample) for key,cols in FIELDS.items()},'player_stat_rows':0,'opponents':sorted({r['away_team'] if r['home_team']==team else r['home_team'] for r in sample}),'last_5':[{k:r[k] for k in ['date','home_team','away_team','home_score','away_score','odds_snapshot']} for r in sorted(sample,key=lambda x:x['date'])[-5:]]}
    return {'sources':metadata,'arg_matches':len(arg),'date_min':min(r['date'] for r in arg),'date_max':max(r['date'] for r in arg),'teams':teams},arg


def normalize_game(data):
    header=data['header'];comp=header['competitions'][0]
    sides={x['homeAway']:x for x in comp['competitors']}
    hs,aws=sides['home'],sides['away']
    hscores,ascores=hs.get('linescores',[]),aws.get('linescores',[])
    hg,ag=num(hs.get('score')),num(aws.get('score'))
    hperiod=[num(x.get('displayValue')) for x in hscores];aperiod=[num(x.get('displayValue')) for x in ascores]
    two_halves=(len(hperiod)==len(aperiod)==2 and None not in hperiod+aperiod and abs(sum(hperiod)-hg)<1e-8 and abs(sum(aperiod)-ag)<1e-8) if hg is not None and ag is not None else False
    stats={x['team']['id']:{s['name']:num(s.get('displayValue',s.get('value'))) for s in x.get('statistics',[])} for x in data.get('boxscore',{}).get('teams',[])}
    row={'event_id':header['id'],'date_utc':comp['date'],'season':header.get('season'),'status':comp['status']['type'],'home_id':hs['id'],'away_id':aws['id'],'home_team':TARGET_IDS.get(hs['id'],hs['team']['displayName']),'away_team':TARGET_IDS.get(aws['id'],aws['team']['displayName']),'home_score':hg,'away_score':ag,'home_ht_score':hperiod[0] if two_halves else None,'away_ht_score':aperiod[0] if two_halves else None,'two_half_sum_matches_final':two_halves,'players':[]}
    for side,competitor in [('home',hs),('away',aws)]:
        for field,key in [('corners','wonCorners'),('yellow','yellowCards'),('red','redCards'),('shots','totalShots'),('shots_on_target','shotsOnTarget')]:row[f'{side}_{field}']=stats.get(competitor['id'],{}).get(key)
    for team in data.get('rosters',[]):
        for player in team.get('roster',[]):
            values={s['name']:num(s.get('value',s.get('displayValue'))) for s in player.get('stats',[])}
            if not values:continue
            row['players'].append({'id':player['athlete']['id'],'name':player['athlete']['displayName'],'team_id':team['team']['id'],'starter':player.get('starter'),'statistics':values,'minutes':values.get('minutesPlayed'),'xg':values.get('expectedGoals')})
    row['joint_ft_ht_corners_complete']=two_halves and all(row[f'{side}_corners'] is not None for side in ['home','away'])
    return row


def roster_profiles(data):
    players=[]
    for row in data.get('athletes',[]):
        stats={s['name']:num(s.get('value',s.get('displayValue'))) for c in row.get('statistics',{}).get('splits',{}).get('categories',[]) for s in c.get('stats',[])}
        players.append({'id':row['id'],'name':row['displayName'],'position':row.get('position',{}).get('name'),'jersey':row.get('jersey'),'stats':stats,'minutes':stats.get('minutesPlayed'),'xg':stats.get('expectedGoals')})
    return {'season_scope':data.get('season'),'provider_timestamp':data.get('timestamp'),'listed_players':len(players),'players_with_statistics':sum(bool(p['stats']) for p in players),'players_with_minutes':sum(p['minutes'] is not None for p in players),'players_with_xg':sum(p['xg'] is not None for p in players),'players':players}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--offline',action='store_true');parser.add_argument('--snapshot',type=Path);args=parser.parse_args()
    generated=datetime.now(timezone.utc).isoformat();cutoff=stamp(generated)
    base=ROOT/'data/raw/espn/arg_fixture_20261030'
    directory=args.snapshot or (Path(json.loads((base/'latest.json').read_text())['snapshot_directory']) if args.offline else base/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    if not directory.is_absolute():directory=ROOT/directory
    sources=[];failures=[];named={}
    if args.offline:
        manifest=json.loads((directory/'manifest.json').read_text());generated=manifest['generated_at'];cutoff=stamp(generated);failures=manifest.get('failures',[])
        for info in manifest['sources']:
            raw=(ROOT/info['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==info['sha256'];sources.append(info);named[info['name']]=json.loads(raw)
    else:
        endpoints={'scoreboard':'scoreboard?dates=20261030&limit=1000','fixture_summary':'summary?event=401841655','rc_schedule':'teams/19685/schedule?season=2026','glp_schedule':'teams/9/schedule?season=2026','rc_roster':'teams/19685/roster?season=2026','glp_roster':'teams/9/roster?season=2026'}
        for name,endpoint in endpoints.items():
            named[name],info=fetch(BASE+endpoint,directory/(name+'.json'));info['name']=name;sources.append(info)
        events={}
        for name in ['rc_schedule','glp_schedule']:
            for row in named[name]['events']:
                comp=row['competitions'][0];status=comp['status']['type']
                if status.get('completed') and stamp(comp['date'])<cutoff:events[row['id']]=row
        def download(eid):
            name='event_'+eid;data,info=fetch(BASE+'summary?event='+eid,directory/(name+'.json'));info['name']=name;return name,data,info
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(download,eid):eid for eid in events}
            for future in as_completed(futures):
                try:name,data,info=future.result();named[name]=data;sources.append(info)
                except Exception as error:failures.append({'event_id':futures[future],'error':str(error)})
        directory.mkdir(parents=True,exist_ok=True)
        (directory/'manifest.json').write_text(json.dumps({'generated_at':generated,'sources':sources,'failures':failures},ensure_ascii=False,indent=2)+'\n')
    (base/'latest.json').write_text(json.dumps({'snapshot_directory':str(directory.relative_to(ROOT))})+'\n')
    local,arg=local_audit();games=[]
    for name,data in named.items():
        if name.startswith('event_'):
            row=normalize_game(data)
            if row['status'].get('completed') and stamp(row['date_utc'])<cutoff:games.append(row)
    games.sort(key=lambda row:(row['date_utc'],row['event_id']))
    teams={}
    for tid,alias in TARGET_IDS.items():
        sample=[r for r in games if tid in [r['home_id'],r['away_id']]]
        counters={key:sum(all(r.get(k) is not None for k in cols) for r in sample) for key,cols in FIELDS.items()}
        counters['ht_corners']=0
        counters['joint_ht_goals_ht_corners']=0
        counters['joint_ft_ht_corners']=sum(r['joint_ft_ht_corners_complete'] for r in sample)
        counters['games_with_player_statistics']=sum(any(p['team_id']==tid for p in r['players']) for r in sample)
        counters['player_rows_with_minutes']=sum(p['minutes'] is not None for r in sample for p in r['players'] if p['team_id']==tid)
        counters['player_rows_with_xg']=sum(p['xg'] is not None for r in sample for p in r['players'] if p['team_id']==tid)
        roster=roster_profiles(named['rc_roster' if tid=='19685' else 'glp_roster'])
        teams[alias]={'espn_id':tid,'completed_games_2026':len(sample),'home':sum(r['home_id']==tid for r in sample),'away':sum(r['away_id']==tid for r in sample),'coverage':counters,'last_5':[{k:r[k] for k in ['event_id','date_utc','home_team','away_team','home_score','away_score','home_ht_score','away_ht_score','home_corners','away_corners']} for r in sample[-5:]],'roster_snapshot':roster}
    fixture=named['fixture_summary']['header']['competitions'][0]
    lineup_counts={team['team']['id']:len(team.get('roster',[])) for team in named['fixture_summary'].get('rosters',[])}
    comparison=[]
    alias_map={tid:alias for tid,alias in TARGET_IDS.items()}
    known_csv_date_exceptions={'401841511':'2026-08-22','401841622':'2026-10-16'}
    for tid,alias in TARGET_IDS.items():
        for row in games:
            if tid not in [row['home_id'],row['away_id']]:continue
            own_home=row['home_id']==tid
            source_day=row['date_utc'][:10]
            csv_day=known_csv_date_exceptions.get(row['event_id'],source_day)
            matches=[r for r in arg if r['date']==csv_day and r['home_team' if own_home else 'away_team']==alias]
            same_scores=len(matches)==1 and num(matches[0]['home_score'])==row['home_score'] and num(matches[0]['away_score'])==row['away_score']
            if same_scores:
                for side in ['home','away']:
                    team_id=row[side+'_id'];canonical=matches[0][side+'_team']
                    if team_id in alias_map and alias_map[team_id]!=canonical:raise ValueError('Inconsistent explicit team identity '+team_id)
                    alias_map[team_id]=canonical
            comparison.append({'team':alias,'event_id':row['event_id'],'espn_day_utc':source_day,'csv_day':csv_day,'explicit_date_exception':source_day!=csv_day,'local_match_count':len(matches),'ft_scores_match':same_scores,'date_note':'ESPN23:00UTC; raw ARG.csv00:00 on following date. CSV timezone unverified; source date preserved, no silent rewrite.' if source_day!=csv_day else None})
    for row in games:
        for side in ['home','away']:
            row['source_'+side+'_team']=row[side+'_team']
            row[side+'_team']=alias_map.get(row[side+'_id'],row[side+'_team'])
    result={'schema_version':1,'generated_at':generated,'fixture':{'home':'Estudiantes Rio Cuarto','away':'Gimnasia L.P.','date_local':'2026-10-30','kickoff_local':'2026-10-30T19:00:00-03:00','kickoff_utc':KICKOFF,'espn_event_id':'401841655','espn_date':fixture['date'],'bet365_url':'https://www.bet365.bet.ar/#/AC/B1/C1/D8/E202426204/F3/I1/','espn_url':'https://www.espn.com/soccer/match/_/gameId/401841655/gimnasia-la-plata-estudiantes-de-rio-cuarto','status':fixture['status']['type'],'lineup_rows':lineup_counts,'confirmed_lineups_available':all(lineup_counts.get(tid,0)>=11 for tid in TARGET_IDS)},
      'aliases':{'Estudiantes Rio Cuarto':{'espn_id':'19685','verified_labels':['Estudiantes de Río Cuarto','Estudiantes RC','Estudiantes (RC)','Estudiantes (Rio Cuarto)'],'explicitly_not':['Estudiantes L.P.','Estudiantes de La Plata']},'Gimnasia L.P.':{'espn_id':'9','verified_labels':['Gimnasia La Plata','Gimnasia LP','Gimnasia y Esgrima La Plata'],'explicitly_not':['Gimnasia Mendoza','Gimnasia de Jujuy']}},
      'cutoff_policy':'Historical local date-only records strictly before2026-10-30. ESPN requires completed=true and kickoff strictly before generated_at; current event has no outcome data consumed.',
      'local':local,'espn':{'teams':teams,'unique_completed_games_2026':len(games),'games':games,'espn_id_to_local_alias':alias_map,'explicit_date_exceptions':known_csv_date_exceptions,'local_ft_reconciliation':comparison,'local_ft_reconciliation_all_match':all(r['ft_scores_match'] for r in comparison),'failures':failures,'sources':sources,'snapshot_manifest':str((directory/'manifest.json').relative_to(ROOT))},
      'primary_metadata_sources':[{'url':'https://www.aaestudiantesriocuarto.com/','checked_at':'2026-10-30','fact':'Official club announces Friday30October19:00 at Antonio Candini; current squad names, no statistical minutes history.'},{'url':'https://www.gimnasia.org.ar/futbol/futbol-profesional/','checked_at':'2026-10-30','fact':'Official club squad and preparation for Estudiantes Rio Cuarto; career counters are not a season exposure table.'}],
      'modelling_quality':{'ft':'Local full-time results available, but RC has only30 top-division games; validate solely ARG chronological history.','ht':'ESPN first-period linescores accepted only when exactly two half scores sum to final score for each team. Missing/nonstandard period rows remain null.','corners':'ESPN wonCorners is full-game match statistic; period-specific corners not supplied here. Requires its own count/joint model and sportsbook definition check.','joint_ft_ht_corners':'Same-event FT, HT and corners observations permit studying dependence; small two-team2026 sample alone does not validate a multidimensional predictive model.','players':'Official rosters give current Clausura appearances/goals/shots, and historical summaries provide match statistics. Minutes and xG absent in inspected payloads; cannot state goals/xG per90 or calibrated scorer probabilities.','lineups':'Roster listing is not confirmation of starters for the selected fixture.','source_limit':'Two23:00UTC fixtures have date-only CSV records on following day; explicit IDs and score matching are recorded without changing either source. Public ESPN endpoint is undocumented; archive raw bodies. Stats are current corrections retrieved today, not verified historical as-of-publication snapshots.'},'execution_enabled':False,'api_credits_used':0}
    path=ROOT/'data/analysis/arg_fixture_data_audit.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(path.relative_to(ROOT)),'unique_games':len(games),'teams':{k:{'n':v['completed_games_2026'],'coverage':v['coverage']} for k,v in teams.items()},'local_ft_reconciled':result['espn']['local_ft_reconciliation_all_match'],'failures':failures,'snapshot':result['espn']['snapshot_manifest']},ensure_ascii=False))


if __name__=='__main__':main()
