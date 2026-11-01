#!/usr/bin/env python3
"""Export football entities from verified provider snapshots, never scorer guesses.

Current roster membership is a point-in-time observation. It is deliberately not
converted into a historical membership interval. FPL retains departed players:
can_select=False/status=u/removed entries are excluded. ESPN roster entries whose
defaultTeam disagrees with the roster's team are quarantined rather than guessed.

Run: python3 scripts/export_football_entities.py
"""
from __future__ import annotations
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
FPL_ROOT=ROOT/'data/raw/fpl/player_numbers/20261030T161701561613Z'
ESPN_ROOT=ROOT/'data/raw/espn/arg_fixture_20261030/20261030T164057498386Z'
VERIFICATION_ROOT=ROOT/'data/raw/football_entities_verification'
LOAN_VERIFICATION_URL='https://www.chelseafc.com/en/news/article/shumaira-mheuka-signs-new-chelsea-contract-and-joins-celtic-on-loan'
COUNTRIES={'E0':'eng','E1':'eng','B1':'bel','D1':'ger','F1':'fra','I1':'ita','N1':'ned','P1':'por','SC0':'sco','SP1':'esp','T1':'tur','ARG1':'arg','SGP_AUS':'aus','SGP_JPN':'jpn','SGP_KOR':'kor','SGP_SWE':'swe','SGP_USA':'usa'}
ESPN_LEAGUES={'eng.1':'E0','eng.2':'E1','esp.1':'SP1','ita.1':'I1','ger.1':'D1','fra.1':'F1','ned.1':'N1','por.1':'P1','tur.1':'T1','bel.1':'B1','sco.1':'SC0','arg.1':'ARG1'}
SG_LEAGUES={'English Premier':'E0','English League Champ':'E1','Dutch League':'N1','French League':'F1','German League':'D1','Italian League':'I1','Spanish League':'SP1','A League':'SGP_AUS','J League':'SGP_JPN','K League':'SGP_KOR','Swedish League':'SGP_SWE','US Soccer League':'SGP_USA'}
# Explicit club-identity aliases, scoped to their football country. No fuzzy
# substring/initial matching and no player-name inference is performed.
ALIAS_GROUPS={
 'eng':[
  ['Arsenal'],['Aston Villa'],['Bournemouth','AFC Bournemouth'],['Brentford'],['Brighton','Brighton & Hove Albion'],['Chelsea'],
  ['Coventry','Coventry City'],['Crystal Palace'],['Everton'],['Fulham'],['Hull','Hull City'],['Ipswich','Ipswich Town'],['Leeds','Leeds United'],
  ['Liverpool'],['Man City','Manchester City'],['Man United','Man Utd','Manchester Utd','Manchester United'],['Newcastle','Newcastle United'],
  ["Nott'm Forest",'Nottingham','Nottingham Forest'],['Tottenham','Spurs','Tottenham Hotspur'],['Sunderland'],['Wolves','Wolverhampton','Wolverhampton Wanderers'],
  ['Norwich','Norwich City'],['Lincoln','Lincoln City'],['Oxford','Oxford United'],['Sheffield United','Sheffield Utd'],['Sheffield Weds','Sheffield Wed','Sheffield Wednesday'],
  ['Stoke','Stoke City'],['West Brom','West Bromwich','West Bromwich Albion']],
 'ned':[['Groningen','FC Groningen'],['Utrecht','FC Utrecht'],['Nijmegen','NEC Nijmegen','NEC'],['Zwolle','PEC Zwolle'],['Den Haag','ADO Den Haag'],['AZ Alkmaar','Alkmaar'],['For Sittard','Fortuna Sittard'],['PSV Eindhoven','PSV'],['Twente','Twente Enschede','FC Twente']],
 'fra':[['Le Havre','Le Havre AC'],['Paris SG','Paris Saint-Germain','PSG'],['Angers','Angers SCO']],
 'ger':[['FC Koln','Cologne','1. FC Köln'],['Ein Frankfurt','E Frankfurt','Eintracht Frankfurt'],['St Pauli','FC St Pauli'],["M'gladbach",'Monchengladbach','Borussia Mönchengladbach']],
 'ita':[['Roma','AS Roma'],['Inter','Internazionale','Inter Milan'],['Monza','AC Monza']],
 'esp':[['Ath Bilbao','Athletic Bilbao','Athletic Club','Athletic'],['Ath Madrid','Atletico Madrid','Atlético Madrid'],['Celta','Celta de Vigo','Celta Vigo'],['Vallecano','Rayo Vallecano','Rayo'],['Sociedad','Real Sociedad'],['La Coruna','Deportivo','Deportivo La Coruña'],['Espanol','Espanyol'],['Santander','Racing','Racing Santander'],['Betis','Real Betis']],
 'por':[['Academico Viseu','Académico de Viseu','Académico'],['Sp Braga','Braga'],['Famalicao','FC Famalicao'],['Porto','FC Porto'],['Sp Lisbon','Sporting CP','Sporting'],['Guimaraes','Vitória de Guimaraes']],
 'tur':[['Amedspor','Amed SFK'],['Rizespor','Caykur Rizespor'],['Goztep','Goztepe'],['Buyuksehyr','Istanbul Basaksehir','Istanbul BB'],['Corum','Çorum FK']],
 'bel':[['Gent','KAA Gent'],['Kortrijk','KV Kortrijk'],['Mechelen','KV Mechelen'],['Charleroi','Royal Charleroi SC','Royal Charleroi'],['St Truiden','Sint-Truidense'],['St. Gilloise','Union St.-Gilloise','Union SG'],['Waregem','Zulte-Waregem'],['Standard','Standard Liège','Standard Liege']],
 'arg':[['Estudiantes de Río Cuarto','Estudiantes Rio Cuarto','Estudiantes Río Cuarto','Estudiantes RC','Estudiantes R.C.'],['Gimnasia La Plata','Gimnasia LP','Gimnasia L.P.','Gimnasia y Esgrima La Plata']],
}


def normalized(value):
 return ''.join(c for c in unicodedata.normalize('NFD',str(value)).casefold() if c.isalnum())

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 manifest=json.loads((ROOT/'app/data/workspace.json').read_text())
 source_manifest=json.loads((FPL_ROOT/'manifest.json').read_text())
 espn_manifest=json.loads((ESPN_ROOT/'manifest.json').read_text())
 sources=[];teams={};players=[];excluded=[];lookup={};alias_groups={};verification=[];loan_exclusions={}
 verification_marker=VERIFICATION_ROOT/'latest.json'
 if verification_marker.is_file():
  verification_manifest=json.loads((ROOT/json.loads(verification_marker.read_text())['manifest']).read_text())
  verification=verification_manifest.get('sources',[])
  for meta in verification:
   source_path=ROOT/meta['path']
   if digest(source_path)!=meta['sha256']:raise AssertionError('Verification source changed: '+meta['path'])
   if meta['url']==LOAN_VERIFICATION_URL:
    body=source_path.read_text()
    if not all(token in body for token in ['Mheuka','Celtic','2026/27']):raise AssertionError('Official loan evidence does not identify player/club/season')
    loan_exclusions[567119]={'reason':'official_current_loan_to_other_club','url':meta['url'],'source':meta,'team':'Celtic','season':'2026/27'}
 for country,groups in ALIAS_GROUPS.items():
  for group in groups:
   for alias in group:alias_groups[(country,normalized(alias))]=group
 leagues={x['code']:{'id':x['code'],'name':x['name']} for x in manifest['leagues']}
 leagues['ARG1']={'id':'ARG1','name':'Argentina · Liga Profesional'}
 for name,league in SG_LEAGUES.items():leagues.setdefault(league,{'id':league,'name':name})
 def source(source_id,path,metadata):
  if source_id in {s['id'] for s in sources}:return source_id
  if metadata.get('sha256') and digest(path)!=metadata['sha256']:raise AssertionError(f'Source hash mismatch: {path.name}')
  sources.append({'id':source_id,'url':metadata.get('url'),'asOf':metadata.get('retrieved_at') or metadata.get('captured_at'),'sha256':digest(path),'path':path.relative_to(ROOT).as_posix()})
  return source_id
 def team(name,league,*,team_id=None,aliases=()):
  country=COUNTRIES.get(league,league.lower());group=alias_groups.get((country,normalized(name)),[name]);all_aliases=list(dict.fromkeys([name,*group,*aliases]))
  found={lookup[(country,normalized(a))] for a in all_aliases if (country,normalized(a)) in lookup}
  if len(found)>1:raise AssertionError(f'Ambiguous alias group: {name}: {found}')
  key=next(iter(found)) if found else team_id or f'team:fd:{country}:{normalized(group[0])}'
  if team_id and found and key!=team_id:
   # Roster providers are initialized first; a later source cannot change identity.
   raise AssertionError(f'Canonical team id already set for {name}')
  if key not in teams:
   teams[key]={'id':key,'name':name,'aliases':[],'leagueIds':[],'playerIds':[],'playersCoverage':{'status':'unavailable','asOf':None,'source':None,'season':None}}
  record=teams[key]
  for a in all_aliases:
   if a not in record['aliases']:record['aliases'].append(a)
   lookup[(country,normalized(a))]=key
  if league not in record['leagueIds']:record['leagueIds'].append(league)
  return record
 # Official FPL snapshot: team.code and player.code remain stable across season IDs.
 fpl_meta=next(s for s in source_manifest['sources'] if s['url'].endswith('bootstrap-static/'))
 fpl_source=source('fpl:20261030',FPL_ROOT/'bootstrap-static.json',fpl_meta)
 fpl=json.loads((FPL_ROOT/'bootstrap-static.json').read_text());fpl_by_id={}
 as_of=fpl_meta['retrieved_at'];season='2026/27'
 for row in fpl['teams']:
  record=team(row['name'],'E0',team_id=f"team:fpl:{row['code']}")
  record['currentLeagueIds']=['E0']
  record['providers']={'fpl':{'teamId':row['id'],'code':row['code'],'season':season}}
  record['playersCoverage']={'status':'verified_snapshot','asOf':as_of,'source':fpl_source,'season':season,'membershipScope':'snapshot_only','completeRoster':False,'selection':'FPL selectable players; excludes departed/unavailable retained entries'}
  fpl_by_id[row['id']]=record
 position_labels={1:'Portero',2:'Defensa',3:'Mediocampista',4:'Delantero'}
 for row in fpl['elements']:
  if row['code'] in loan_exclusions:
   entry=loan_exclusions[row['code']];excluded.append({'source':fpl_source,'providerPlayerId':str(row['id']),'name':(row['first_name']+' '+row['second_name']).strip(),'reason':entry['reason'],'evidence':entry['url']});continue
  if row.get('removed') or row.get('can_select') is not True or row.get('status')=='u':
   excluded.append({'source':fpl_source,'providerPlayerId':str(row['id']),'name':(row['first_name']+' '+row['second_name']).strip(),'reason':'not_selectable_or_departed_retained_by_fpl'});continue
  record=fpl_by_id[row['team']];pid=f"player:fpl:{row['code']}"
  item={'id':pid,'name':row.get('known_name') or (row['first_name']+' '+row['second_name']).strip(),'fullName':(row['first_name']+' '+row['second_name']).strip(),'shortName':row['web_name'],'teamId':record['id'],'position':position_labels.get(row['element_type'],''),'leagueId':'E0','source':fpl_source,'asOf':as_of,'season':season,'membershipScope':'snapshot_only','providerPlayerId':str(row['id']),'providerStatus':row.get('status'),'sourceJoinedAt':row.get('team_join_date')}
  players.append(item);record['playerIds'].append(pid)
 # Current ESPN roster membership must agree with athlete.defaultTeam when present.
 for filename in ['rc_roster.json','glp_roster.json']:
  path=ESPN_ROOT/filename;meta=next(s for s in espn_manifest['sources'] if Path(s['path']).name==filename)
  payload=json.loads(path.read_text());provider_team=str(payload['team']['id']);sid=source('espn:arg1:'+provider_team+':20261030',path,meta)
  record=team(payload['team']['displayName'],'ARG1',team_id='team:espn:'+provider_team)
  record['currentLeagueIds']=['ARG1']
  record['providers']={'espn':{'teamId':provider_team,'league':'arg.1','season':2026}}
  record['playersCoverage']={'status':'verified_snapshot','asOf':meta['retrieved_at'],'source':sid,'season':'2026','membershipScope':'snapshot_only','completeRoster':False,'selection':'Active roster entries with matching defaultTeam'}
  for athlete in payload['athletes']:
   default=(athlete.get('defaultTeam') or {}).get('$ref','');match=re.search(r'/teams/(\d+)',default)
   current_status=(athlete.get('status') or {}).get('type')
   if (match and match[1]!=provider_team) or current_status not in (None,'active'):
    excluded.append({'source':sid,'providerPlayerId':athlete['id'],'name':athlete['displayName'],'reason':'default_team_disagrees_with_roster' if match and match[1]!=provider_team else 'inactive_roster_entry'});continue
   pid='player:espn:'+str(athlete['id']);position=(athlete.get('position') or {}).get('name','')
   position={'Goalkeeper':'Portero','Defender':'Defensa','Midfielder':'Mediocampista','Forward':'Delantero'}.get(position,position)
   players.append({'id':pid,'name':athlete.get('fullName') or athlete['displayName'],'shortName':athlete.get('shortName') or athlete['displayName'],'teamId':record['id'],'position':position,'leagueId':'ARG1','source':sid,'asOf':meta['retrieved_at'],'season':'2026','membershipScope':'snapshot_only','providerPlayerId':str(athlete['id']),'providerStatus':current_status})
   record['playerIds'].append(pid)
 # Independently corroborate two clubs against current ESPN roster responses.
 # The player's provider-supplied full/known names must match exactly; absence
 # from a senior list is not treated as proof that a youth player left the club.
 for meta in verification:
  name=Path(meta['path']).name
  club_map={'chelsea-roster.json':('team:fpl:8','363'),'manutd-roster.json':('team:fpl:1','360')}
  if name not in club_map:continue
  tid,provider_team=club_map[name];payload=json.loads((ROOT/meta['path']).read_text())
  if str(payload.get('team',{}).get('id'))!=provider_team or payload.get('season',{}).get('year')!=2026:raise AssertionError('Wrong club/season verification payload')
  sid=source('espn:eng1:'+provider_team+':20261030',ROOT/meta['path'],meta)
  coverage=teams[tid]['playersCoverage'];coverage.setdefault('corroboration',[]).append({'source':sid,'asOf':payload.get('timestamp') or meta['retrieved_at'],'season':'2026/27','providerPlayers':len(payload.get('athletes',[]))})
  by_name={}
  for athlete in payload.get('athletes',[]):
   for field in ['displayName','fullName']:
    if athlete.get(field):by_name.setdefault(normalized(athlete[field]),set()).add(str(athlete['id']))
  for player in players:
   if player['teamId']!=tid:continue
   matches=set().union(*(by_name.get(normalized(player.get(key,'')),set()) for key in ['name','fullName']))
   if len(matches)==1:player['corroboratedBy']=[{'source':sid,'providerPlayerId':next(iter(matches)),'basis':'exact_normalized_provider_full_or_known_name','asOf':payload.get('timestamp') or meta['retrieved_at']}]
 for meta in verification:
  name=Path(meta['path']).name
  official_map={'chelsea-profiles.html':('team:fpl:8','club:chelsea:mens-profiles:20261030'),'manutd-2026-squad.html':('team:fpl:1','club:manutd:202627-squad:20261030')}
  if name not in official_map:continue
  tid,sid=official_map[name];sid=source(sid,ROOT/meta['path'],meta)
  teams[tid]['playersCoverage'].setdefault('officialReferences',[]).append({'source':sid,'asOf':meta['retrieved_at'],'season':'2026/27'})
  if name=='manutd-2026-squad.html' and 'Bendito Mantato' in (ROOT/meta['path']).read_text():
   for player in players:
    if player['id']=='player:fpl:576620':player['corroboratedBy']=[{'source':sid,'basis':'exact_provider_name_in_official_202627_squad_article','asOf':meta['retrieved_at']}]
 for entry in loan_exclusions.values():
  meta=entry['source'];sid=source('club:chelsea:mheuka-loan-20260902',ROOT/meta['path'],meta)
  teams['team:fpl:8']['playersCoverage'].setdefault('quarantined',[]).append({'provider':'fpl','providerPlayerCode':567119,'reason':entry['reason'],'source':sid,'playingClub':entry['team'],'season':entry['season']})
 # Preserve the archived football universe, including teams without roster data.
 event_path=ROOT/'app/data'/manifest['tables']['events']['path'];archive=json.loads(gzip.decompress(event_path.read_bytes()));col={key:i for i,key in enumerate(archive['columns'])}
 for row in archive['rows']:
  for field in ['home_team','away_team']:team(row[col[field]],row[col['league']])
 # Singapore Pools names are explicitly reconciled; extra league teams remain
 # names-only rather than receiving somebody else's squad by fuzzy matching.
 database=ROOT/'data/processed/free_football_history.sqlite'
 if database.is_file():
  db=sqlite3.connect(f'file:{database}?mode=ro',uri=True)
  for league_name,match_name in db.execute('SELECT DISTINCT league,match_name FROM sgodds_matches'):
   league=SG_LEAGUES.get(league_name)
   if league and ' vs ' in match_name:
    for name in match_name.split(' vs '):team(name.strip(),league)
  db.close()
 # Known fixture metadata gives both sides canonical identities without guessing.
 fixtures=[];fixture_path=ROOT/'data/processed/fixtures.csv'
 if fixture_path.is_file():
  for row in csv.DictReader(fixture_path.open(newline='')):
   if row.get('sport')!='football' or row.get('league_code') not in leagues:continue
   league=row['league_code'];home=team(row['home_team'],league);away=team(row['away_team'],league)
   def price(key):
    try:return float(row[key]) if float(row[key])>1 else None
    except (TypeError,ValueError,KeyError):return None
   fixtures.append({'id':row['id'],'leagueId':league,'date':row['date'],'homeTeamId':home['id'],'awayTeamId':away['id'],'home':row['home_team'],'away':row['away_team'],'odds':{'home':price('home_odds'),'draw':price('draw_odds'),'away':price('away_odds')},'oddsSource':row.get('odds_source'),'source':row.get('source'),'asOf':row.get('retrieved_at'),'kickoffReliable':row.get('kickoff_reliable')=='true','oddsTimestamp':row.get('odds_timestamp') or None})
 fixture=json.loads((ESPN_ROOT/'fixture_summary.json').read_text())['header'];competition=fixture['competitions'][0];sides={x['homeAway']:x for x in competition['competitors']}
 fixtures.append({'id':'espn:'+fixture['id'],'leagueId':'ARG1','date':competition['date'][:10],'kickoff':competition['date'],'homeTeamId':'team:espn:'+sides['home']['id'],'awayTeamId':'team:espn:'+sides['away']['id'],'home':sides['home']['team']['displayName'],'away':sides['away']['team']['displayName'],'source':'https://www.espn.com/soccer/match/_/gameId/'+fixture['id'],'asOf':espn_manifest['generated_at'],'kickoffReliable':True,'oddsTimestamp':None})
 # Per-event historical membership is concrete lineup evidence, not a current
 # roster backfilled into earlier years. Only known catalog players are linked.
 historical=[];current_ids={p['id'] for p in players};audit_path=ROOT/'data/analysis/arg_fixture_data_audit.json'
 if audit_path.is_file():
  audit=json.loads(audit_path.read_text())
  for game in audit.get('espn',{}).get('games',[]):
   for player in game.get('players',[]):
    pid='player:espn:'+str(player['id']);tid='team:espn:'+str(player['team_id'])
    if pid in current_ids and tid in teams:
     historical.append({'playerId':pid,'teamId':tid,'eventId':'espn:'+str(game['event_id']),'date':game['date_utc'][:10],'season':str((game.get('season') or {}).get('year','')),'source':'espn_event_lineup','asOf':audit.get('generated_at') or espn_manifest['generated_at']})
 # Current squads across the twelve requested leagues. Preserve canonical
 # identities from the original catalog and join FPL/ESPN players only with
 # exact provider names plus birth date, or exact first-name/DOB within a club.
 roster_failures=[];roster_issues=[];cross_provider_reused=0
 roster_marker=ROOT/'data/raw/football_entities_rosters/latest.json'
 if roster_marker.is_file():
  roster_manifest=json.loads((ROOT/json.loads(roster_marker.read_text())['manifest']).read_text())
  roster_failures=roster_manifest.get('failures',[])
  roster_sources=roster_manifest.get('sources',[])
  list_teams={}
  for meta in roster_sources:
   if meta.get('team_id') is not None:continue
   payload=json.loads((ROOT/meta['path']).read_text());league=ESPN_LEAGUES[meta['league']]
   for sport in payload.get('sports',[]):
    for league_data in sport.get('leagues',[]):
     for item in league_data.get('teams',[]):
      club=item.get('team',item);list_teams[(meta['league'],str(club['id']))]=club
  fpl_identity={};fpl_exact={};fpl_dob_first={}
  for row in fpl['elements']:
   pid='player:fpl:'+str(row['code']);fpl_identity[pid]=row;birth=row.get('birth_date')
   for name in [(row['first_name']+' '+row['second_name']).strip(),row.get('known_name')]:
    if name:fpl_exact.setdefault((normalized(name),birth),set()).add(pid)
   fpl_dob_first.setdefault((birth,normalized(row['first_name'])),set()).add(pid)
  player_map={p['id']:p for p in players}
  for meta in sorted((x for x in roster_sources if x.get('team_id') is not None),key=lambda x:(x['league'],str(x['team_id']))):
   league=ESPN_LEAGUES.get(meta['league']);provider_team=str(meta['team_id']);path=ROOT/meta['path']
   if not league:continue
   payload=json.loads(path.read_text());team_info=payload.get('team',{});season_info=payload.get('season',{})
   if str(team_info.get('id'))!=provider_team or season_info.get('year')!=2026:
    roster_issues.append({'teamId':provider_team,'league':meta['league'],'reason':'wrong_team_or_season'});continue
   listing=list_teams.get((meta['league'],provider_team),{})
   labels=[x for x in [team_info.get('displayName'),team_info.get('name'),team_info.get('location'),listing.get('displayName'),listing.get('shortDisplayName'),listing.get('name'),listing.get('location')] if x]
   country=COUNTRIES[league];found={lookup[(country,normalized(name))] for name in labels if (country,normalized(name)) in lookup}
   if len(found)>1:
    roster_issues.append({'teamId':provider_team,'league':meta['league'],'reason':'ambiguous_existing_team_alias','canonicalIds':sorted(found)});continue
   record=team(labels[0],league,team_id=None if found else 'team:espn:'+provider_team,aliases=labels[1:])
   record.setdefault('currentLeagueIds',[])
   if league not in record['currentLeagueIds']:record['currentLeagueIds'].append(league)
   record.setdefault('providers',{})['espn']={'teamId':provider_team,'league':meta['league'],'season':2026}
   sid=source('espn:roster:'+meta['league']+':'+provider_team+':20261030',path,meta)
   season_label='2026' if league=='ARG1' else '2026/27'
   coverage=record['playersCoverage']
   coverage.update({'status':'verified_snapshot','asOf':payload.get('timestamp') or meta['retrieved_at'],'source':sid,'season':season_label,'sourceSeasonName':str(season_info.get('displayName') or 2026),'membershipScope':'snapshot_only','completeRoster':False,'selection':'Current ESPN roster; conflicting defaultTeam excluded'})
   for athlete in payload.get('athletes',[]):
    aid=str(athlete.get('id',''));status=(athlete.get('status') or {}).get('type');default=(athlete.get('defaultTeam') or {}).get('$ref','');default_match=re.search(r'/teams/(\d+)',default)
    if not aid or (default_match and default_match[1]!=provider_team) or status not in (None,'active'):
     if aid:roster_issues.append({'teamId':provider_team,'playerId':aid,'league':meta['league'],'reason':'default_team_disagrees_with_roster' if default_match and default_match[1]!=provider_team else 'inactive_roster_entry'})
     continue
    espn_pid='player:espn:'+aid;dob=str(athlete.get('dateOfBirth') or '')[:10] or None
    matching=set()
    if dob:
     for name in [athlete.get('displayName'),athlete.get('fullName')]:
      if name:matching.update(fpl_exact.get((normalized(name),dob),set()))
     if not matching:
      for pid in fpl_dob_first.get((dob,normalized(athlete.get('firstName',''))),set()):
       original=fpl_identity[pid];original_club=fpl_by_id.get(original['team'])
       if original_club and original_club['id']==record['id']:matching.add(pid)
    if espn_pid=='player:espn:372013' and record['id']=='team:fd:sco:celtic' and dob=='2007-10-20' and 567119 in loan_exclusions:
     # Official Chelsea profile identifies Shumaira/\"Shim\" Mheuka and the Celtic loan; the exact DOB agrees.
     pid='player:fpl:567119';cross_provider_reused+=1
    elif espn_pid in player_map:pid=espn_pid
    elif len(matching)==1:pid=next(iter(matching));cross_provider_reused+=1
    elif len(matching)>1:
     roster_issues.append({'teamId':provider_team,'playerId':aid,'league':meta['league'],'reason':'ambiguous_cross_provider_identity'});continue
    else:pid=espn_pid
    proof={'source':sid,'providerPlayerId':aid,'basis':'provider_roster_and_default_team','asOf':payload.get('timestamp') or meta['retrieved_at']}
    if pid in player_map:
     existing=player_map[pid]
     if existing['teamId']!=record['id']:
      # A newer, explicit playing-club source supersedes an obsolete FPL team.
      old_team=teams[existing['teamId']];old_team['playerIds']=[x for x in old_team['playerIds'] if x!=pid]
      old_team['playersCoverage'].setdefault('quarantined',[]).append({'playerId':pid,'reason':'newer_verified_playing_club','source':sid,'playingTeamId':record['id']})
      existing.update({'previousTeamId':existing['teamId'],'teamId':record['id'],'leagueId':league,'source':sid,'asOf':proof['asOf'],'season':season_label,'sourceSeasonName':str(season_info.get('displayName') or 2026)})
     existing.setdefault('corroboratedBy',[])
     if not any(p.get('source')==sid for p in existing['corroboratedBy']):existing['corroboratedBy'].append(proof)
     existing.setdefault('providers',{})['espn']={'playerId':aid,'teamId':provider_team}
    else:
     position=(athlete.get('position') or {}).get('name','');position={'Goalkeeper':'Portero','Defender':'Defensa','Midfielder':'Mediocampista','Forward':'Delantero'}.get(position,position)
     item={'id':pid,'name':athlete.get('displayName') or athlete.get('fullName'),'fullName':athlete.get('fullName') or athlete.get('displayName'),'shortName':athlete.get('shortName') or athlete.get('displayName'),'teamId':record['id'],'position':position,'leagueId':league,'source':sid,'asOf':proof['asOf'],'season':season_label,'sourceSeasonName':str(season_info.get('displayName') or 2026),'membershipScope':'snapshot_only','providerPlayerId':aid,'providerStatus':status,'providers':{'espn':{'playerId':aid,'teamId':provider_team}}}
     if pid.startswith('player:fpl:'):item['providers']['fpl']={'playerId':str(fpl_identity[pid]['id']),'code':fpl_identity[pid]['code']}
     players.append(item);player_map[pid]=item
    if pid not in record['playerIds']:record['playerIds'].append(pid)
  # Recalculate known ids for historical membership facts; membership dates
  # remain event-scoped and are not inferred from the added current squads.
  for record in teams.values():
   if record['playersCoverage']['status']=='verified_snapshot' and not record['playerIds']:record['playersCoverage']['status']='unavailable'
 for record in teams.values():
  record['aliases'].sort(key=str.casefold);record['leagueIds'].sort();record['playerIds'].sort()
 player_ids={p['id'] for p in players};assert len(player_ids)==len(players),'Duplicate current player id'
 for player in players:assert player['teamId'] in teams and player['id'] in teams[player['teamId']]['playerIds']
 for record in teams.values():assert set(record['playerIds'])<=player_ids
 index={}
 for record in teams.values():
  for league in record['leagueIds']:
   for alias in record['aliases']:
    key=league+'|'+normalized(alias)
    if key in index and index[key]!=record['id']:raise AssertionError('Ambiguous league alias: '+key)
    index[key]=record['id']
 result={'schemaVersion':1,'asOf':max(s['asOf'] for s in sources),'rosterScope':'provider_snapshot_only','leagues':sorted(leagues.values(),key=lambda x:x['name']),'teams':sorted(teams.values(),key=lambda t:(t['name'].casefold(),t['id'])),'players':sorted(players,key=lambda p:(p['name'].casefold(),p['id'])),'fixtures':fixtures,'teamAliasIndex':index,'historicalMemberships':historical,'sources':sources,'exclusionSummary':{'count':len(excluded),'fplUnavailableOrDeparted':sum(x['reason']=='not_selectable_or_departed_retained_by_fpl' for x in excluded),'espnContradictoryOrInactive':sum(x['source'].startswith('espn:') for x in excluded),'officialLoanContradictions':sum(x['reason']=='official_current_loan_to_other_club' for x in excluded)},'coverage':{'teams':len(teams),'teamsWithVerifiedPlayers':sum(bool(t['playerIds']) for t in teams.values()),'players':len(players),'fixtures':len(fixtures),'historicalMemberships':len(historical),'currentMembershipIsHistorical':False,'rosterSources':sum(1 for x in sources if x['id'].startswith('espn:roster:')),'rosterDownloadFailures':len(roster_failures),'rosterSourceIssues':len(roster_issues),'crossProviderIdentitiesReused':cross_provider_reused},'rosterIssues':roster_issues,'rosterDownloadFailures':roster_failures}
 out=ROOT/'app/data/entities.json';temporary=out.with_suffix('.json.tmp');temporary.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n');temporary.replace(out)
 # Provider contradictions are counted above, never added as selectable players.
 print(json.dumps({'path':str(out.relative_to(ROOT)),'bytes':out.stat().st_size,**result['coverage'],'excluded':len(excluded)},ensure_ascii=False))


def refresh_roster_sources():
 from concurrent.futures import ThreadPoolExecutor,as_completed
 from datetime import datetime,timezone
 from urllib.request import Request,urlopen
 from urllib.error import HTTPError
 from pathlib import Path
 import json,hashlib,time
 ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'data/raw/football_entities_rosters'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');DEST.mkdir(parents=True,exist_ok=True)
 LEAGUES=['eng.1','eng.2','esp.1','ita.1','ger.1','fra.1','ned.1','por.1','tur.1','bel.1','sco.1','arg.1'];sources=[];failures=[]
 def fetch(task):
  league,tid=task;url=f'https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/teams'+(f'/{tid}/roster?season=2026' if tid else '?limit=1000&season=2026')
  for attempt in range(3):
   try:
    response=urlopen(Request(url,headers={'User-Agent':'WorKraken personal football research'}),timeout=18);raw=response.read();payload=json.loads(raw);p=DEST/league/(f'team-{tid}.json' if tid else 'teams.json');p.parent.mkdir(exist_ok=True);p.write_bytes(raw)
    return payload,{'path':p.relative_to(ROOT).as_posix(),'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'server_date':response.headers.get('Date'),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'league':league,'team_id':tid}
   except Exception as exc:
    if attempt==2:return None,{'league':league,'team_id':tid,'url':url,'error':type(exc).__name__+': '+str(exc)}
    if isinstance(exc,HTTPError) and exc.code not in [429,500,502,503,504]:return None,{'league':league,'team_id':tid,'url':url,'error':str(exc)}
    time.sleep(1.5*(attempt+1))
 tasks=[]
 with ThreadPoolExecutor(max_workers=6) as pool:
  for payload,meta in pool.map(fetch,[(league,None) for league in LEAGUES]):
   if payload is None:failures.append(meta);continue
   sources.append(meta)
   for sport in payload.get('sports',[]):
    for league in sport.get('leagues',[]):
     for item in league.get('teams',[]):
      team=item.get('team',item)
      if team.get('id'):tasks.append((meta['league'],str(team['id'])))
  print(json.dumps({'phase':'team_lists','lists':len(sources),'rosters_queued':len(tasks),'failures':failures}),flush=True)
  # Prominent clubs first; no more than250 current squads.
  priority={'83','86','5','16','363','360'}
  tasks=sorted(set(tasks),key=lambda t:(t[1] not in priority,t))[:250]
  done=0
  for future in as_completed([pool.submit(fetch,task) for task in tasks]):
   payload,meta=future.result();done+=1
   if payload is None:failures.append(meta)
   else:sources.append(meta)
   if done%40==0:print(json.dumps({'phase':'rosters','done':done,'total':len(tasks),'sources':len(sources),'failures':len(failures)}),flush=True)
 manifest={'generated_at':datetime.now(timezone.utc).isoformat(),'season':2026,'sources':sources,'failures':failures};mp=DEST/'manifest.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');(DEST.parent/'latest.json').write_text(json.dumps({'manifest':mp.relative_to(ROOT).as_posix()},indent=2)+'\n');print(json.dumps({'complete':True,'manifest':mp.relative_to(ROOT).as_posix(),'sources':len(sources),'failures':failures}),flush=True)

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--refresh-rosters',action='store_true');args=parser.parse_args()
 if args.refresh_rosters:refresh_roster_sources()
 main()
