#!/usr/bin/env python3
"""Reproducible, conditional player calculations from official FPL statistics.

This is a rate sensitivity exercise, not a calibrated fixture forecast or an
executable betting signal. No sportsbook/API account credentials are required.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE='https://fantasy.premierleague.com/api/'
BET365_URL='https://www.bet365.bet.ar/?#/AC/B1/C1/D8/E202201732/F3/G40/'
QUOTE_TIME='2026-10-30T16:09:59+00:00'
FIXTURE_TIME='2026-10-31T12:30:00+00:00'
PLAYERS=[(154,'Cole Palmer',2.37,1.66),(156,'Pedro Neto',3.60,2.20),(427,'Bryan Mbeumo',3.40,2.60),(426,'Bruno Fernandes',4.00,2.20),(40,'Morgan Rogers',3.00,1.90)]
PRIOR_MINUTES=900  # Fixed ten-full-match exposure; no tuning to price or EV.


def fetch_json(url,raw_path):
    request=urllib.request.Request(url,headers={'User-Agent':'KrakenEdge research, public official statistics'})
    with urllib.request.urlopen(request,timeout=30) as response:
        raw=response.read()
        parsed=json.loads(raw)
        raw_path.parent.mkdir(parents=True,exist_ok=True)
        raw_path.write_bytes(raw)
        return parsed,{'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'server_date':response.headers.get('Date'),'sha256':hashlib.sha256(raw).hexdigest(),'raw_path':str(raw_path.relative_to(ROOT)),'bytes':len(raw)}


def probability(rate_per_90,minutes):
    return -math.expm1(-rate_per_90*minutes/90)


def wilson(successes,n):
    if not n:return None
    z,p=1.959963984540054,successes/n
    denominator=1+z*z/n
    center=(p+z*z/(2*n))/denominator
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return [max(0.,center-half),min(1.,center+half)]


def quantify(p,odds):
    return {'p_score':p,'p_no_score':1-p,'fair_odds_score':1/p if p else None,
            'fair_odds_no_score':1/(1-p) if p<1 else None,'base_ev_per_stake':p*odds-1,
            'opposite_quote_observed':False,'opposite_ev':None}


def percentile(values,q):
    v=sorted(values);index=(len(v)-1)*q;lo=math.floor(index);hi=math.ceil(index)
    return v[lo]+(v[hi]-v[lo])*(index-lo)


def build(bootstrap,summaries,provenance,local_quotes):
    teams={row['id']:row['name'] for row in bootstrap['teams']}
    positions={row['id']:row['singular_name'] for row in bootstrap['element_types']}
    profiles=[]
    for player_id,name,odds,score_assist_odds in PLAYERS:
        p=next(row for row in bootstrap['elements'] if row['id']==player_id)
        summary=summaries[player_id]
        history=[row for row in summary['history'] if row.get('kickoff_time') and datetime.fromisoformat(row['kickoff_time'].replace('Z','+00:00'))<datetime.fromisoformat(FIXTURE_TIME)]
        # Raw season aggregates and fixture rows must refer to the same season.
        minutes=sum(row['minutes'] for row in history)
        goals=sum(row['goals_scored'] for row in history)
        xg=sum(float(row.get('expected_goals') or 0) for row in history)
        assert minutes==p['minutes'] and goals==p['goals_scored'],f'Aggregate mismatch for {name}'
        assert abs(xg-float(p.get('expected_goals') or 0))<.015,f'xG mismatch for {name}'
        started=[row for row in history if row.get('starts')==1]
        scored=sum(row['goals_scored']>0 for row in started)
        empirical=scored/len(started) if started else None
        empirical_ci=wilson(scored,len(started))
        past=[{key:row.get(key) for key in ['season_name','minutes','goals_scored','assists','expected_goals','expected_assists','starts']} for row in summary['history_past']]
        prior=next((row for row in reversed(past) if row.get('minutes',0)>0),None)
        rates={'goals_per_90':goals*90/minutes,'xg_per_90':xg*90/minutes}
        models={}
        for key,rate in rates.items():
            models['poisson_'+key]={'rate_per_90':rate,'minute_scenarios':{str(m):quantify(probability(rate,m),odds) for m in [60,75,90]}}
        if empirical is not None:
            models['empirical_starting_appearance']={**quantify(empirical,odds),'n_starts':len(started),'starts_with_goal':scored,'wilson_95':empirical_ci,'observed_mean_minutes_per_start':sum(r['minutes'] for r in started)/len(started),'interval_meaning':'Wilson interval for historical starting-appearance frequency; not a calibrated upcoming-fixture interval.'}
        if prior:
            prior_rate=prior['goals_scored']/prior['minutes']
            alpha=prior_rate*PRIOR_MINUTES+goals
            beta=PRIOR_MINUTES+minutes
            rng=random.Random(20261030+player_id)
            draws=[rng.gammavariate(alpha,1/beta) for _ in range(40000)]
            lo,hi=percentile(draws,.025),percentile(draws,.975)
            scenarios={}
            for m in [60,75,90]:
                # Exact Gamma-Poisson posterior predictive probability of >=1.
                predictive=1-(beta/(beta+m))**alpha
                scenarios[str(m)]={**quantify(predictive,odds),'rate_model_credible_95':[1-math.exp(-lo*m),1-math.exp(-hi*m)]}
            models['historical_prior_gamma_poisson']={'prior_season':prior['season_name'],'prior_goals':prior['goals_scored'],'prior_minutes':prior['minutes'],'fixed_prior_strength_minutes':PRIOR_MINUTES,'prior_mean_goals_per_90':prior_rate*90,'posterior_shape':alpha,'posterior_rate_minutes':beta,'posterior_mean_goals_per_90':alpha/beta*90,'minute_scenarios':scenarios,'interval_meaning':'95% credible interval for latent rate under this fixed Gamma-Poisson model; excludes opponent, lineup and transfer uncertainty. Monte Carlo seed fixed.'}
            prev_xg=float(prior.get('expected_goals') or 0)
            pool_minutes=prior['minutes']+minutes
            models['pooled_previous_current_xg']={'seasons':[prior['season_name'],'2026/27'],'minutes':pool_minutes,'xg':prev_xg+xg,'rate_per_90':(prev_xg+xg)*90/pool_minutes,'minute_scenarios':{str(m):quantify(probability((prev_xg+xg)*90/pool_minutes,m),odds) for m in [60,75,90]},'meaning':'Exposure-weighted previous completed season plus current season; separate sensitivity reference, not selected for best EV.'}
        game_rows=[{**{key:row.get(key) for key in ['fixture','kickoff_time','minutes','starts','goals_scored','assists','expected_goals','expected_assists','was_home']},'opponent':teams.get(row.get('opponent_team'))} for row in history]
        quotes=[{key:q.get(key) for key in ['event','description','market_key','selection','odds','bookmaker','bookmaker_title','last_update','retrieved_at','region','verified_rules']} for q in local_quotes if q.get('description')==name and q.get('market_key')=='player_goal_scorer_anytime' and q.get('event')=='Chelsea — Manchester United']
        profiles.append({'name':name,'fpl_id':player_id,'team':teams[p['team']],'fpl_position':positions[p['element_type']],
          'source_url':BASE+f'element-summary/{player_id}/','statistics_scope':'Premier League 2026/27, before Chelsea-Manchester United fixture',
          'current_season':{'minutes':minutes,'goals':goals,'xg':xg,'assists':p.get('assists'),'xa':float(p.get('expected_assists') or 0),'fixtures_in_history':len(history),'appearances':sum(r['minutes']>0 for r in history),'starts':len(started),'starting_appearances_with_goal':scored,'goals_per_90':rates['goals_per_90'],'xg_per_90':rates['xg_per_90'],'last_match':game_rows[-1] if game_rows else None},
          'availability':{key:p.get(key) for key in ['status','news','chance_of_playing_next_round','chance_of_playing_this_round','news_added']},
          'confirmed_starting_lineup':False,'availability_interpretation':'FPL status a means available; chance_of_playing is not probability of starting or predicted minutes.',
          'next_fixture':next((row for row in summary['fixtures'] if row.get('kickoff_time') and row['kickoff_time'].startswith('2026-10-31')),None),
          'history':game_rows,'history_past':past,
          'bet365_quote':{'market':'Anytime goalscorer','odds':odds,'score_or_assist_odds':score_assist_odds,'bookmaker':'bet365 Argentina','source_url':BET365_URL,'observed_at':QUOTE_TIME,'provenance':'Direct browser UI observation by parent agent; quote table rows matched to players, no bet placed.','substitute_plus_displayed':True,'base_model_prices_full_promotion':False,'no_score_quote':None,'break_even_probability':1/odds},
          'other_book_quotes':quotes,'models':models,'actionable':False})
    return {'schema_version':1,'generated_at':provenance[0]['retrieved_at'],
      'fixture':{'event':'Chelsea — Manchester United','kickoff':FIXTURE_TIME,'bet365_event_url':BET365_URL},
      'sources':provenance,'players':profiles,'methodology':[
       'All statistics are fetched from the official public Fantasy Premier League API, without key or paid request.',
       'Poisson rate models: p(at least one goal | fixed minutes m)=1-exp(-rate_per_90*m/90). This is a conditional transformation of historical rate, not a validated fixture probability.',
       'Empirical model counts historical starts with >=1 goal, not goals divided by starts. Wilson95 interval reports small-sample frequency uncertainty.',
       'Historical Gamma-Poisson prior uses last completed season goal rate and fixed900-minute exposure. All estimators remain separate; none chosen for highest EV.',
       'EV base = p*quoted_odds-1. For Suplente+, personal scoring is only part of the full offer. No replacement-chain value is estimated.',
       'No-score fair odds are mathematical thresholds. A tradable No/lay price was not observed; no opposite EV can be calculated.',
       'FPL assists and expected assists do not verify Bet365 assist settlement. Score-or-assist odds are recorded without fitting a probability from scoring alone.'
      ],'limitations':[
       'Current season has only8 fixtures per team. Finishing, xG and empirical estimates diverge markedly.',
       'No adjustment for this opponent, venue, current penalty-taker, tactics, transfer role, fitness or dependence with teammates.',
       'Starting lineups unconfirmed; 60/75/90 are conditional scenarios, not promised playing time. Bruno last match minutes0 is retained.',
       'Credible/frequency intervals quantify only the specified historical-rate model; they are not calibrated coverage intervals for this match.',
       'Bet365 quote timestamp16:09:59UTC differs from API retrieval; both are dated observations, not execution prices.',
       'Suplente+ changes the covered participant and may retain accumulated events; personal-only EV does not price the actual whole promotion.',
       'No bets were placed and no bookmaker account was created.'
      ],'executed_bets':0,'execution_enabled':False}


def _read_verified(entry,path_key='raw_path'):
    path=ROOT/entry[path_key]
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
        raise ValueError('Snapshot hash mismatch: '+str(path))
    return json.loads(raw)


def capture_snapshot():
    captured=datetime.now(timezone.utc)
    directory=ROOT/'data/raw/fpl/player_numbers'/captured.strftime('%Y%m%dT%H%M%S%fZ')
    bootstrap,info=fetch_json(BASE+'bootstrap-static/',directory/'bootstrap-static.json')
    summaries,provenance={},[info]
    for player_id,_,_,_ in PLAYERS:
        summaries[player_id],info=fetch_json(BASE+f'element-summary/{player_id}/',directory/f'element-summary-{player_id}.json')
        provenance.append(info)
    original=ROOT/'data/analysis/football_audit_sample.json'
    raw=original.read_bytes()
    source=json.loads(raw)
    names={name for _,name,_,_ in PLAYERS}
    # Freeze only the exact quote inputs used by build(), with provenance of
    # their parent capture. This avoids depending on a future mutable report.
    rows=[q for q in source['quotes'] if q.get('description') in names and q.get('market_key')=='player_goal_scorer_anytime' and q.get('event')=='Chelsea — Manchester United']
    frozen=json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()
    quote_path=directory/'other-book-quotes.json'
    quote_path.write_bytes(frozen)
    manifest={'schema_version':1,'captured_at':captured.isoformat(),'sources':provenance,
              'players':PLAYERS,'quote_input':{'raw_path':str(quote_path.relative_to(ROOT)),'sha256':hashlib.sha256(frozen).hexdigest(),'source_path':str(original.relative_to(ROOT)),'source_sha256':hashlib.sha256(raw).hexdigest()},
              'note':'Six exact official FPL response bodies plus a frozen subset of already captured quote inputs. No paid API request.'}
    manifest_path=directory/'manifest.json'
    serialized=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    manifest_path.write_text(serialized)
    (directory.parent/'latest.json').write_text(serialized)
    return bootstrap,summaries,provenance,rows,manifest_path


def load_snapshot(path):
    path=path.resolve()
    if path.is_dir():path=path/'manifest.json'
    manifest=json.loads(path.read_text())
    by_url={entry['url']:entry for entry in manifest['sources']}
    expected=[BASE+'bootstrap-static/']+[BASE+f'element-summary/{player_id}/' for player_id,_,_,_ in PLAYERS]
    if sorted(by_url)!=sorted(expected) or len(manifest['sources'])!=6:
        raise ValueError('Snapshot must contain exactly the six expected official FPL responses.')
    if [list(row) for row in manifest['players']]!=[list(row) for row in PLAYERS]:
        raise ValueError('Snapshot player/price specifications differ from this pinned analysis.')
    bootstrap=_read_verified(by_url[expected[0]])
    summaries={player_id:_read_verified(by_url[BASE+f'element-summary/{player_id}/']) for player_id,_,_,_ in PLAYERS}
    rows=_read_verified(manifest['quote_input'])
    # Normalize latest.json to the immutable source manifest, not the pointer.
    immutable=ROOT/manifest['sources'][0]['raw_path']
    return bootstrap,summaries,manifest['sources'],rows,immutable.parent/'manifest.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'data/analysis/player_numbers.json')
    parser.add_argument('--offline',action='store_true',help='Never access the network; use --reuse-snapshot or the latest archived snapshot.')
    parser.add_argument('--reuse-snapshot',type=Path,help='Archived manifest.json or its directory; implies offline mode.')
    args=parser.parse_args()
    if args.offline or args.reuse_snapshot:
        snapshot=args.reuse_snapshot or ROOT/'data/raw/fpl/player_numbers/latest.json'
        bootstrap,summaries,provenance,rows,manifest_path=load_snapshot(snapshot)
    else:
        bootstrap,summaries,provenance,rows,manifest_path=capture_snapshot()
    result=build(bootstrap,summaries,provenance,rows)
    result['input_snapshot']={'manifest_path':str(manifest_path.relative_to(ROOT)),'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'offline_reproduction_supported':True,'raw_fpl_response_count':6}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for player in result['players']:
        models=player['models'];season=player['current_season'];q=player['bet365_quote']
        print(json.dumps({'name':player['name'],'minutes':season['minutes'],'goals':season['goals'],'xg':season['xg'],'starts_with_goal':f"{season['starting_appearances_with_goal']}/{season['starts']}",'bet365_odds':q['odds'],'p_goals90':models['poisson_goals_per_90']['minute_scenarios']['90']['p_score'],'p_xg90':models['poisson_xg_per_90']['minute_scenarios']['90']['p_score'],'p_prior75':models['historical_prior_gamma_poisson']['minute_scenarios']['75']['p_score'],'p_prior90':models['historical_prior_gamma_poisson']['minute_scenarios']['90']['p_score']},ensure_ascii=False))


if __name__=='__main__':main()
