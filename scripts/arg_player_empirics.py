#!/usr/bin/env python3
"""Empirical player and joint-event counts from the archived ARG audit only.

No network, rates-per90, promotion valuation, independence assumption or EV.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import math
import unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ALIASES={
 'Agustin Auzmendi':('334165','9','Agustín Auzmendi'),
 'Agustin Quiroga':('361259','19685','Agustin Quiroga'),
 'Benjamin Moyano':('421206','19685','Benjamin Moyano'),
 'Gabriel Alanis':('206678','19685','Gabriel Alanís'),
 'Ibrahim Hesar':('287691','19685','Ibrahim Hesar'),
 'Ignacio Fernandez':('106583','9','Ignacio Fernández'),
 'Javier Ferreira':('188914','19685','Javier Ferreira'),
 'Lucas Gonzalez':('276229','19685','Lucas González'),
 'Marcelo Torres':('85513','9','Marcelo Torres'),
 'Martín Garnerone':('288428','19685','Martín Garnerone'),
 'Maximiliano Zalazar':('307925','9','Maximiliano Zalazar'),
 'Nicolas Barros Schelotto':('366024','9','Nicolas Schelotto')}
STAT_KEYS={'goals':'totalGoals','assists':'goalAssists','shots_on_target':'shotsOnTarget','shots':'totalShots'}


def wilson(k,n):
    if not n:return None
    z=1.959963984540054;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [0. if k==0 else max(0.,c-r),1. if k==n else min(1.,c+r)]


def summary(observations):
    n=len(observations);k=sum(bool(x['success']) for x in observations)
    return {'n':n,'successes':k,'frequency':k/n if n else None,'wilson_95':wilson(k,n),'date_min':min((x['date_utc'] for x in observations),default=None),'date_max':max((x['date_utc'] for x in observations),default=None),'success_event_ids':[x['event_id'] for x in observations if x['success']],'eligible_event_ids':[x['event_id'] for x in observations],'interpretation':'Historical conditional frequency; Wilson95 is binomial/descriptive, not calibrated upcoming-match probability.'}


def in_window(game,window):
    return window=='season_2026' or (str((game.get('season') or {}).get('year'))=='2026' and 'clausura' in str((game.get('season') or {}).get('name','')).lower())


def active_record(game,player_name):
    pid,tid,_=ALIASES[player_name]
    rows=[p for p in game['players'] if p['id']==pid and p['team_id']==tid and (p['statistics'].get('appearances') or 0)>0]
    if len(rows)>1:raise ValueError('Duplicate active player in one match: '+player_name)
    return rows[0] if rows else None


def side_for_team(game,tid):
    return 'home' if game['home_id']==tid else 'away' if game['away_id']==tid else None


def event_value(player,stat):
    values=player['statistics']
    if stat=='goal_or_assist':
        if values.get('totalGoals') is None or values.get('goalAssists') is None:return None
        return int(values['totalGoals']>0 or values['goalAssists']>0)
    return values.get(STAT_KEYS[stat])


def player_metrics(sample):
    metrics={}
    for stat,thresholds in [('goals',[1]),('assists',[1]),('goal_or_assist',[1]),('shots_on_target',[1,2,3]),('shots',[1,2,3,4,5,6])]:
        for threshold in thresholds:
            observations=[]
            for game,p in sample:
                value=event_value(p,stat)
                if value is None:continue
                observations.append({'event_id':game['event_id'],'date_utc':game['date_utc'],'success':value>=threshold})
            metrics[f'{stat}_ge_{threshold}']={**summary(observations),'missing_stat_games':len(sample)-len(observations)}
    return metrics


def all_participants(quote):
    return [row['participant'] for row in [quote]+quote.get('legs',[]) if row.get('participant')]


def joint_observations(games,legs,cohort):
    observations=[];no_participation=0;missing=0
    player_names=[leg['participant'] for leg in legs if leg.get('participant')]
    team_ids={ALIASES[name][1] for name in player_names}
    if not team_ids:team_ids={'9'}
    candidates=[g for g in games if team_ids<={g['home_id'],g['away_id']}]
    for game in candidates:
        players={name:active_record(game,name) for name in player_names}
        if any(p is None for p in players.values()) or (cohort=='both_starters' and any(p.get('starter') is not True for p in players.values())):
            no_participation+=1;continue
        outcomes=[]
        for leg in legs:
            market=leg['market'];p=players.get(leg.get('participant'))
            if market in ['player_count','player_goal','player_assist','player_goal_or_assist']:
                stat=leg.get('statistic') if market=='player_count' else {'player_goal':'goals','player_assist':'assists','player_goal_or_assist':'goal_or_assist'}[market]
                value=event_value(p,stat)
                if value is None:outcomes.append(None);continue
                outcomes.append(value>float(leg['line']) if market=='player_count' else value>=1)
            elif market in ['1x2','most_corners']:
                # In the selected fixture "away" means Gimnasia, regardless of
                # whether Gimnasia was home or away in the historical fixture.
                target='9' if leg.get('selection')=='away' else '19685'
                side=side_for_team(game,target)
                if not side:outcomes.append(None);continue
                other='away' if side=='home' else 'home';field='score' if market=='1x2' else 'corners'
                a,b=game.get(side+'_'+field),game.get(other+'_'+field)
                outcomes.append(a>b if a is not None and b is not None else None)
            elif market=='totals':
                a,b=game.get('home_score'),game.get('away_score');outcomes.append(a+b>float(leg['line']) if a is not None and b is not None else None)
            elif market=='btts':outcomes.append(game['home_score']>0 and game['away_score']>0)
            else:raise ValueError('Unsupported joint market '+market)
        if None in outcomes:missing+=1;continue
        observations.append({'event_id':game['event_id'],'date_utc':game['date_utc'],'success':all(outcomes),'leg_outcomes':outcomes,'gimnasia_away':game['away_id']=='9','home_score':game['home_score'],'away_score':game['away_score'],'home_corners':game['home_corners'],'away_corners':game['away_corners']})
    return observations,{'candidate_same_fixture_games':len(candidates),'nonappearance_or_not_both_starting_excluded':no_participation,'missing_stat_excluded':missing}


def normalized_exact(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD',str(value)) if not unicodedata.combining(c)).casefold().split())


def resolve_current_roster_names(audit,names):
    # FullName and displayName are provider fields. Do not construct names by
    # deleting tokens or use fuzzy/substring/initial matching.
    root=ROOT/Path(audit['espn']['snapshot_manifest']).parent
    candidates={}
    for filename,tid in [('rc_roster.json','19685'),('glp_roster.json','9')]:
        data=json.loads((root/filename).read_text())
        for athlete in data.get('athletes',[]):
            candidate=(athlete['id'],tid,athlete['displayName'])
            for field in ['displayName','fullName']:
                if athlete.get(field):candidates.setdefault(normalized_exact(athlete[field]),set()).add(candidate)
    mappings={};unresolved={}
    for name in names:
        if name in ALIASES:mappings[name]={'basis':'explicit_previously_verified_alias','value':ALIASES[name]};continue
        options=candidates.get(normalized_exact(name),set())
        identities={(row[0],row[1]) for row in options}
        if len(identities)==1:
            value=sorted(options)[0];ALIASES[name]=value;mappings[name]={'basis':'unique_normalized_exact_provider_display_or_full_name','value':value}
        else:unresolved[name]={'reason':'no_exact_provider_name' if not options else 'ambiguous_exact_provider_name','candidate_ids':[list(x) for x in sorted(identities)]}
    return mappings,unresolved


def quote_metric_key(quote):
    if quote['market']=='player_count':return f"{quote['statistic']}_ge_{int(math.floor(quote['line'])+1)}"
    return {'player_goal':'goals_ge_1','player_assist':'assists_ge_1','player_goal_or_assist':'goal_or_assist_ge_1'}.get(quote['market'])


def attach_quote_sensitivities(profile,name,quotes):
    linked=[]
    for quote in quotes['quotes']:
        if quote.get('participant')!=name:continue
        key=quote_metric_key(quote);scenarios={}
        for window,w in profile['windows'].items():
            scenarios[window]={}
            for cohort in ['appearance_metrics','starter_metrics']:
                metric=(w.get(cohort) or {}).get(key) if key else None
                n=metric['n'] if metric else None;p=metric['frequency'] if metric else None;ci=metric['wilson_95'] if metric else None
                selection=str(quote.get('selection','yes')).lower()
                valid_period=quote.get('period')=='full_time'
                if quote['market']=='player_count' and not math.isclose(float(quote['line'])%1,.5,abs_tol=1e-10):valid_period=False
                if not valid_period:p=None;ci=None
                elif selection in ['no','under'] and p is not None:p=1-p;ci=[1-ci[1],1-ci[0]]
                scenarios[window][cohort]={'n':n,'historical_conditional_frequency':p,'wilson_95':ci,
                    'ev_per_100_stationary_personal_only':100*(p*quote['odds']-1) if p is not None else None,
                    'ev_per_100_wilson_stationary_personal_only':[100*(bound*quote['odds']-1) for bound in ci] if ci else None,
                    'interpretation':'Descriptive personal-event sensitivity under stationarity/identical payout; not future calibration, real ROI or full Suplente+ valuation.'}
        linked.append({'quote_id':quote['id'],'market':quote['market'],'statistic':quote.get('statistic'),'selection':quote.get('selection'),'line':quote.get('line'),'odds':quote['odds'],'period':quote['period'],'substitute_plus':quote.get('substitute_plus'),'empirical_metric_key':key,'bet365_last_matches_displayed':quote.get('last_matches_displayed'),'break_even_probability':1/quote['odds'],'descriptive_scenarios':scenarios,'full_promotion_probability':None,'executable':False})
    profile['quoted_markets']=linked


def main():
    audit_path=ROOT/'data/analysis/arg_fixture_data_audit.json';quotes_path=ROOT/'data/analysis/bet365_arg_quotes.json'
    audit_raw=audit_path.read_bytes();quotes_raw=quotes_path.read_bytes();audit=json.loads(audit_raw);quotes=json.loads(quotes_raw);games=audit['espn']['games']
    windows=['season_2026','clausura_2026'];participants=sorted({name for quote in quotes['quotes'] for name in all_participants(quote)})
    resolved,unresolved=resolve_current_roster_names(audit,participants)
    profiles=[]
    for name in participants:
        if name in unresolved:
            profile={'quote_name':name,'espn_id':None,'team_id':None,'identity_status':'unresolved','identity_reason':unresolved[name],'confirmed_starting_lineup':False,'windows':{window:{'appearances':None,'starts':None,'appearance_metrics':None,'starter_metrics':None,'mean_minutes':None,'goals_per90':None,'xg_per90':None} for window in windows},'appearance_rows':[]}
            attach_quote_sensitivities(profile,name,quotes);profiles.append(profile);continue
        pid,tid,source_name=ALIASES[name];appearances=[]
        for game in games:
            p=active_record(game,name)
            if p:appearances.append((game,p))
        profile={'quote_name':name,'espn_id':pid,'espn_name':source_name,'team_id':tid,'team':audit['espn']['espn_id_to_local_alias'][tid],'identity_status':'resolved','identity_basis':resolved[name]['basis'],'confirmed_starting_lineup':False,'windows':{},'appearance_rows':[{'event_id':g['event_id'],'date_utc':g['date_utc'],'starter':p.get('starter'),'statistics':p['statistics']} for g,p in appearances]}
        for window in windows:
            selected=[(g,p) for g,p in appearances if in_window(g,window)];starts=[(g,p) for g,p in selected if p.get('starter') is True]
            profile['windows'][window]={'appearances':len(selected),'starts':len(starts),'appearance_metrics':player_metrics(selected),'starter_metrics':player_metrics(starts),'mean_minutes':None,'goals_per90':None,'xg_per90':None}
        attach_quote_sensitivities(profile,name,quotes)
        profiles.append(profile)
    joint=[]
    for qid in ['q0170','q0171','q0172','q0173','q0174']:
        quote=next((q for q in quotes['quotes'] if q['id']==qid),None)
        if not quote:continue
        item={'quote_id':qid,'label':quote['label'],'odds':quote['odds'],'legs':quote['legs'],'rule_equivalence_verified':False,'substitute_plus_priced':False,'windows':{},'executable':False}
        for window in windows:
            selected=[g for g in games if in_window(g,window)]
            item['windows'][window]={}
            for cohort in ['both_appearances','both_starters']:
                observations,excluded=joint_observations(selected,quote['legs'],cohort)
                item['windows'][window][cohort]={'all_venues':{**summary(observations),**excluded,'observations':observations},'gimnasia_away':summary([o for o in observations if o['gimnasia_away']])}
        if qid=='q0171':item['interpretation']='Win AND strictly more team corners AND at least3 total goals, observed in the same match. Strict interpretation of Over2Goals; integer Asian2 push and BetBuilder rule not verified.'
        if qid=='q0172':item['interpretation']='Opposing-club players: requires a real RC–Gimnasia fixture with both players appearing. Other separate team matches are not combined.'
        joint.append(item)
    result={'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'fixture':audit['fixture'],'source_audit':{'path':str(audit_path.relative_to(ROOT)),'sha256':hashlib.sha256(audit_raw).hexdigest(),'snapshot':audit['espn']['snapshot_manifest']},'source_quotes':{'path':str(quotes_path.relative_to(ROOT)),'sha256':hashlib.sha256(quotes_raw).hexdigest(),'count':len(quotes['quotes']),'meta':quotes['meta']},'players':profiles,'identity_counts':{'quoted_names':len(participants),'resolved':len(resolved),'unresolved':len(unresolved)},'unresolved_players':unresolved,'joint_combos':joint,'methodology':['No download: uses only the61 archived2026 completed match summaries.','Appearances require provider appearances>0. Unused substitutes, non-squad players and missing stat fields are excluded, not coded as0.','Starter cohort additionally requires starter=true in that exact match. No minute exposure inferred.','Player records are restricted to the quoted player current club ID; previous transfers/opponent rows are excluded.','Clausura scope follows the provider season name/year, not a manually chosen date.','Each threshold denominator excludes missing values of that statistic; full n and success/eligible fixture IDs are retained.','All combined frequencies are calculated as a conjunction on the same event ID. No multiplication of player or team marginals.','Wilson95 intervals describe small historical conditional samples and assume binomial trials; dependency, opponent mix and fixture uncertainty are not included.','Suplente+ replacement chains and bookmaker stat definitions are not verified/priced by individual-player occurrence counts.','Personal-only descriptive EV sensitivities use100*(historical conditional frequency*odds-1), with Wilson bounds transformed linearly under stationarity. They do not value Suplente+, predict the upcoming fixture or establish ROI.','Unresolved or ambiguous exact names retain null sample/probability/EV; no fuzzy match, token deletion or false zero exposure.'], 'execution_enabled':False,'network_requests':0}
    output=ROOT/'data/analysis/arg_player_empirics.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(output.relative_to(ROOT)),'players':len(profiles),'quoted_player_rows':sum(len(p['quoted_markets']) for p in profiles),'joint_combos':len(joint),'source_quotes':len(quotes['quotes'])},ensure_ascii=False))
    for item in joint:
        v=item['windows']['season_2026']['both_appearances'];print(item['quote_id'],item['label'],'ALL',v['all_venues']['successes'],v['all_venues']['n'],v['all_venues']['wilson_95'],'AWAY',v['gimnasia_away']['successes'],v['gimnasia_away']['n'],v['gimnasia_away']['wilson_95'])


if __name__=='__main__':main()
