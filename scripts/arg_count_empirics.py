#!/usr/bin/env python3
"""No-network descriptive counts/price sensitivities for the ARG fixture.

Historical hit frequencies and Wilson intervals are not future calibrated
probabilities or realized ROI. Integer two-way push contracts are rejected.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import math
import random
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
SUPPORTED_STATS={'corners','cards','yellow_cards','red_cards','shots','shots_on_target'}
SUPPORTED_MARKETS={'totals','team_totals','count_total_3way','goal_range','both_teams_count'}
STAT_FIELDS={'corners':'corners','yellow_cards':'yellow','red_cards':'red','shots':'shots','shots_on_target':'shots_on_target'}


def wilson(k,n):
    if not n:return None
    z=1.959963984540054;p=k/n;den=1+z*z/n;center=(p+z*z/(2*n))/den;rad=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [0. if k==0 else max(0.,center-rad),1. if k==n else min(1.,center+rad)]


def in_window(g,window):return window=='season_2026' or ('clausura' in str((g.get('season') or {}).get('name','')).lower() and str((g.get('season') or {}).get('year'))=='2026')


def cohorts(games):
    return {'rc_all_matches':[g for g in games if '19685' in [g['home_id'],g['away_id']]],
            'rc_home_matches':[g for g in games if g['home_id']=='19685'],
            'gimnasia_all_matches':[g for g in games if '9' in [g['home_id'],g['away_id']]],
            'gimnasia_away_matches':[g for g in games if g['away_id']=='9'],
            'pooled_unique_all_matches':list(games),
            'pooled_unique_matching_venue':[g for g in games if g['home_id']=='19685' or g['away_id']=='9']}


def count_value(g,side,stat,card_rule):
    if stat!='cards':return g.get(side+'_'+STAT_FIELDS[stat])
    yellow,red=g.get(side+'_yellow'),g.get(side+'_red')
    if yellow is None or red is None:return None
    return yellow if card_rule=='yellow_only' else yellow+red if card_rule=='yellow_plus_red' else yellow+2*red


def evaluate(q,g,card_rule):
    values={side:count_value(g,side,q['statistic'],card_rule) for side in ['home','away']}
    if any(v is None for v in values.values()):return None
    usage='match_total'
    if q['market']=='team_totals':
        # Future home=RC, away=Gimnasia. When that team is not in a historical
        # fixture, retain an explicitly labelled opponent proxy, not its own
        # opponent's total silently mistaken for this specific team's history.
        target='19685' if q.get('team')=='home' else '9'
        counterpart='9' if target=='19685' else '19685'
        if target in [g['home_id'],g['away_id']]:side='home' if g['home_id']==target else 'away';usage='direct_target_team'
        elif counterpart in [g['home_id'],g['away_id']]:side='away' if g['home_id']==counterpart else 'home';usage='opponents_of_other_fixture_team_proxy'
        else:return None
        value=values[side]
    elif q['market']=='both_teams_count':
        yes=all(v>=float(q['min_count']) for v in values.values())
        return {'success':yes if q['selection']=='yes' else not yes,'value':min(values.values()),'usage':'both_teams_joint','home_count':values['home'],'away_count':values['away']}
    else:value=sum(values.values())
    if q['market']=='goal_range':
        lo=float(q.get('min_goals',q.get('min_count',0)));hi=q.get('max_goals',q.get('max_count'))
        hit=value>=lo and (hi is None or value<=float(hi))
        selection=str(q.get('selection','yes')).lower()
        if selection=='no':hit=not hit
        elif selection!='yes':raise ValueError('Range selection must be yes or no')
    elif q['selection']=='over':hit=value>float(q['line'])
    elif q['selection']=='under':hit=value<float(q['line'])
    elif q['selection']=='exact':hit=value==float(q['line'])
    else:raise ValueError('Unsupported selection '+q['selection'])
    return {'success':hit,'value':value,'usage':usage,'home_count':values['home'],'away_count':values['away']}


def empirical(q,rows,card_rule):
    observations=[]
    for g in rows:
        ev=evaluate(q,g,card_rule)
        if ev is not None:observations.append({'event_id':g['event_id'],'date_utc':g['date_utc'],**ev})
    n=len(observations);k=sum(r['success'] for r in observations);p=k/n if n else None;ci=wilson(k,n);odds=q['odds']
    return {'n':n,'successes':k,'historical_hit_frequency':p,'wilson_95_frequency':ci,'break_even_probability':1/odds,
            'ev_per_100_stationary_sensitivity':100*(p*odds-1) if p is not None else None,
            'ev_per_100_wilson_stationary_sensitivity':[100*(bound*odds-1) for bound in ci] if ci else None,
            'historical_sample_return_if_same_price_each_game':None,
            'missing_stat_excluded':len(rows)-n,'direct_target_team_games':sum(r['usage']=='direct_target_team' for r in observations),
            'opponent_proxy_games':sum(r['usage']=='opponents_of_other_fixture_team_proxy' for r in observations),
            'observed_count_mean':sum(r['value'] for r in observations)/n if n else None,
            'date_min':min((r['date_utc'] for r in observations),default=None),'date_max':max((r['date_utc'] for r in observations),default=None),
            'success_event_ids':[r['event_id'] for r in observations if r['success']],'eligible_event_ids':[r['event_id'] for r in observations],
            'interpretation':'Descriptive sensitivity only: assumes the historical conditional frequency is stationary and this exact binary payout applies. Wilson interval is marginal binomial, not fixture calibration, accepted price or real ROI.'}


def audit_cards(audit):
    root=ROOT/Path(audit['espn']['snapshot_manifest']).parent;units=0;second=0;fail=[]
    for g in audit['espn']['games']:
        data=json.loads((root/('event_'+g['event_id']+'.json')).read_text())
        events=data.get('keyEvents',[])
        for side in ['home','away']:
            tid=g[side+'_id'];ce=[e for e in events if e.get('team',{}).get('id')==tid]
            y=sum(e.get('type',{}).get('type')=='yellow-card' for e in ce);r=sum(e.get('type',{}).get('type')=='red-card' for e in ce)
            sy=sum(e.get('type',{}).get('type')=='red-card' and 'second yellow' in str(e.get('text','')).lower() for e in ce)
            units+=1;second+=sy
            if y-sy!=g[side+'_yellow'] or r!=g[side+'_red']:fail.append({'event_id':g['event_id'],'side':side,'yellow_events':y,'second_yellow_red_events':sy,'yellow_box':g[side+'_yellow'],'red_events':r,'red_box':g[side+'_red']})
    return {'game_team_units_checked':units,'second_yellow_red_events':second,'all_box_yellows_exclude_second_yellows':not fail,'exceptions':fail,
            'primary_assumption':'Sensitivity only: yellow_box + 2*red_box follows a documented bet365 GB/AU convention, not verified Argentina settlement. ESPN box yellow counts exclude the second yellow preceding red in122 inspected team-game units.',
            'bookmaker_equivalence_verified':False,'remaining_scope_risks':['Argentina license card weights and maximum3 after double yellow plus red unverified','Players on field versus bench/staff','Cards between periods/after final whistle','Bookmaker exact regional card definition'],
            'sensitivity_rules':['yellow_only','yellow_plus_red','yellow_plus_2red']}


def count_moments(values):
    n=len(values)
    if not n:return {'n':0,'mean':None,'sample_variance':None,'alpha_raw':None,'alpha_clipped':None}
    mean=math.fsum(values)/n
    variance=math.fsum((v-mean)**2 for v in values)/(n-1) if n>1 else 0.
    raw=(variance-mean)/mean**2 if mean else 0.
    return {'n':n,'mean':mean,'sample_variance':variance,'alpha_raw':raw,'alpha_clipped':max(0.,raw)}


def poisson_cdf5(mean):
    if mean<0:raise ValueError('Negative Poisson mean')
    term=math.exp(-mean);total=term
    for k in range(1,6):term*=mean/k;total+=term
    return min(1.,max(0.,total))


def nb_cdf5(mean,alpha):
    if mean<0 or alpha<0:raise ValueError('Negative mean or dispersion')
    if alpha<1e-10:return poisson_cdf5(mean)
    shape=1/alpha;ratio=mean/(shape+mean)
    term=math.exp(-shape*math.log1p(mean/shape));total=term
    for k in range(1,6):term*=(k-1+shape)/k*ratio;total+=term
    return min(1.,max(0.,total))


def common_alpha(a,b):
    denominator=a['mean']**2+b['mean']**2
    return max(0.,(a['sample_variance']-a['mean']+b['sample_variance']-b['mean'])/denominator) if denominator else 0.


def quantile(values,fraction):
    ordered=sorted(values);position=(len(ordered)-1)*fraction;lo=math.floor(position);hi=math.ceil(position)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(position-lo)


def corner_hypothesis(audit,quotes,repetitions=20000):
    quote=next(q for q in quotes['quotes'] if q['id']=='q0333')
    if not (quote['market']=='team_totals' and quote['statistic']=='corners' and quote['team']=='away' and quote['selection']=='under' and quote['line']==5.5):raise ValueError('Gimnasia corner quote identity changed')
    odds=quote['odds'];games=audit['espn']['games'];windows={}
    for window in ['season_2026','clausura_2026']:
        selected=[g for g in games if in_window(g,window)]
        gim=[g for g in selected if g['away_id']=='9' and g.get('away_corners') is not None]
        rc=[g for g in selected if g['home_id']=='19685' and g.get('away_corners') is not None]
        va=[g['away_corners'] for g in gim];vb=[g['away_corners'] for g in rc]
        if not va or not vb:continue
        a,b=count_moments(va),count_moments(vb);rate=(a['mean']+b['mean'])/2;alpha=common_alpha(a,b)
        pp=poisson_cdf5(rate);pn=nb_cdf5(rate,alpha)
        rng=random.Random(20261030 if window=='season_2026' else 20261031)
        draws=[]
        for _ in range(repetitions):
            aa=count_moments([va[rng.randrange(len(va))] for _ in va]);bb=count_moments([vb[rng.randrange(len(vb))] for _ in vb])
            lam=(aa['mean']+bb['mean'])/2;dispersion=common_alpha(aa,bb)
            draws.append((lam,poisson_cdf5(lam),nb_cdf5(lam,dispersion),dispersion))
        intervals={name:[quantile([r[i] for r in draws],.025),quantile([r[i] for r in draws],.975)] for i,name in enumerate(['lambda','poisson_probability_under','nb_probability_under','nb_alpha'])}
        for model in ['poisson','nb']:
            intervals[model+'_ev_per_100']=[100*(p*odds-1) for p in intervals[model+'_probability_under']]
        def sample(rows,values,moments,label):
            return {**moments,'meaning':label,'under_5_5_count':sum(v<=5 for v in values),'observed_under_frequency':sum(v<=5 for v in values)/len(values),'values_chronological':values,'event_ids':[g['event_id'] for g in rows],
                    'latest_10':[{'event_id':g['event_id'],'date_utc':g['date_utc'],'date_local_salta':datetime.fromisoformat(g['date_utc'].replace('Z','+00:00')).astimezone(ZoneInfo('America/Argentina/Salta')).isoformat(),'home_team':g['home_team'],'away_team':g['away_team'],'corners':g['away_corners']} for g in rows[-10:]]}
        overlap=sorted({g['event_id'] for g in gim}&{g['event_id'] for g in rc})
        windows[window]={'gimnasia_away_for':sample(gim,va,a,'Corners taken by Gimnasia in its own17 away matches (n depends on window).'),
                         'rio_cuarto_home_against':sample(rc,vb,b,'Corners by visiting opponents against Rio Cuarto at home; these are NOT Gimnasia games.'),
                         'sample_overlap_event_ids':overlap,'not_32_gimnasia_matches':True,
                         'lambda_arithmetic_mean_of_two_means':rate,'group_weights':[.5,.5],
                         'nb_common_alpha_mom':alpha,'nb_variance_at_lambda':rate+alpha*rate**2,
                         'poisson':{'probability_under_5_5':pp,'ev_per_100':100*(pp*odds-1),'fair_decimal_odds':1/pp},
                         'negative_binomial':{'probability_under_5_5':pn,'ev_per_100':100*(pn*odds-1),'fair_decimal_odds':1/pn},
                         'bootstrap':{'repetitions':repetitions,'sampling':'Within each original cohort independently, resample matches with replacement using its original sample size; recompute both means and common NB alpha.','seed':20261030 if window=='season_2026' else 20261031,'intervals_95_percentile':intervals,'interval_meaning':'Uncertainty of this rate-based model under independent stationary resampling; not full fixture predictive uncertainty, calibrated interval, selection adjustment or realized ROI.'}}
    return {'quote_id':quote['id'],'odds':odds,'period':'full_time','market':'Gimnasia own corners under5.5','break_even_probability':1/odds,'captured_at':quote.get('captured_at'),'source_url':quote['source_url'],
            'specification':'Exploratory requested lambda=(mean Gimnasia away corners for + mean Rio Cuarto home corners against)/2. Equal cohort weights, no fitting to odds or ROI.',
            'nb_parameterization':'Var(Y)=mu+alpha*mu^2; common alpha=max(0,[(s2_G-mu_G)+(s2_RC-mu_RC)]/[mu_G^2+mu_RC^2]). Each sample variance uses n-1. Negative per-cohort excess variance is reported; common NB alpha cannot be negative.',
            'selection_context':'Candidate selected after examining many prices/counts; exploration, not an independent confirmatory test.',
            'windows':windows,'limitations':['Simple arithmetic means do not control opponent strength, competition phase, tactics or current lineup.','The32 observations are17 Gimnasia-away games and15 other games of visitors at Rio Cuarto; they are not32 Gimnasia appearances.','Bootstrap treats matches and cohorts as independent and stationary, ignores shared league/date shocks, model misspecification and market-selection multiplicity.','No out-of-sample calibration/backtest against these exact historical corner prices; model EV is not demonstrated return.','Bookmaker taken/awarded corners, retakes, abandonment and current price acceptance remain unverified.'],
            'verified_edge':False,'executable':False}


def main():
    ap=ROOT/'data/analysis/arg_fixture_data_audit.json';qp=ROOT/'data/analysis/bet365_arg_quotes.json';ar=ap.read_bytes();qr=qp.read_bytes();audit=json.loads(ar);quotes=json.loads(qr)
    games=audit['espn']['games'];assert len({g['event_id'] for g in games})==len(games)
    windows={w:cohorts([g for g in games if in_window(g,w)]) for w in ['season_2026','clausura_2026']};evaluations=[];rejected=[]
    for q in quotes['quotes']:
        if q.get('statistic') not in SUPPORTED_STATS:continue
        if q.get('market') not in SUPPORTED_MARKETS:rejected.append({'quote_id':q['id'],'reason':'player_counts_covered_by_arg_player_empirics' if q.get('market')=='player_count' else 'unsupported_count_contract'});continue
        if q.get('period')!='full_time':rejected.append({'quote_id':q['id'],'reason':'period_specific_counts_missing'});continue
        if q['market'] in ['totals','team_totals'] and not math.isclose(float(q['line'])%1,.5,abs_tol=1e-10):
            rejected.append({'quote_id':q['id'],'reason':'two_way_non_half_line_needs_push_or_partial_payoff'});continue
        entry={'quote_id':q['id'],'label':q['label'],'market':q['market'],'statistic':q['statistic'],'selection':q['selection'],'line':q.get('line'),'team':q.get('team'),'min_count':q.get('min_count'),'range':[q.get('min_goals'),q.get('max_goals')] if q['market']=='goal_range' else None,'odds':q['odds'],'break_even_probability':1/q['odds'],'period':q['period'],'captured_at':q.get('captured_at'),'source_url':q.get('source_url'),'exact_bookmaker_rules_verified':False,'windows':{},'executable':False}
        for window,groups in windows.items():entry['windows'][window]={name:empirical(q,rows,'yellow_plus_2red') for name,rows in groups.items()}
        if q['statistic']=='cards':entry['card_rule_sensitivity']={rule:{window:{name:empirical(q,rows,rule) for name,rows in groups.items()} for window,groups in windows.items()} for rule in ['yellow_only','yellow_plus_red']}
        evaluations.append(entry)
    result={'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'fixture':audit['fixture'],
      'sources':[{'path':str(ap.relative_to(ROOT)),'sha256':hashlib.sha256(ar).hexdigest()},{'path':str(qp.relative_to(ROOT)),'sha256':hashlib.sha256(qr).hexdigest()}],
      'raw_snapshot':audit['espn']['snapshot_manifest'],'input_quote_count':len(quotes['quotes']),'evaluated_count_quotes':len(evaluations),'quotes':evaluations,'rejected':rejected,
      'cohort_counts':{w:{name:len(rows) for name,rows in groups.items()} for w,groups in windows.items()},
      'cohort_meaning':{'rc_all_matches':'All2026 RC matches, whatever venue.','rc_home_matches':'RC historical home matches.','gimnasia_all_matches':'All2026 Gimnasia LP matches, whatever venue.','gimnasia_away_matches':'Gimnasia LP historical away matches.','pooled_unique_all_matches':'Union of both histories by event ID; shared head-to-head counted once. Descriptive opponent-mix pool, not a fitted matchup probability.','pooled_unique_matching_venue':'Union of RC home and Gimnasia away matches by event ID. Opponents and phase/competition context still differ.'},
      'card_count_audit':audit_cards(audit),'corner_hypothesis':corner_hypothesis(audit,quotes),
      'methodology':['No network. All observed counts come from the61 frozen completed ESPN matches before the selected fixture.','Every cohort is deduplicated by event ID. RC30 + Gimnasia32 has one shared match, so pooled n61, not62.','Three-way count under/exact/over are binary selections: count equal to line loses an under/over selection, not push. Under10 three-way equals Under9.5 two-way only with identical period/rules.','Range fields min_goals/max_goals are retained from the source quote schema but applied to the declared statistic, including corners.','Two-way integer/quarter total contracts are rejected from this binary EV calculation.','Team corner quote home maps to RC and away to Gimnasia. Direct team history and opponent-of-other-team proxy are separately counted and labelled; pooling them does not establish opponent adjustment.','Cards primary assumption uses yellow+2red; secondary-yellow treatment was checked against archived events. Regional bookmaker and player/bench scope still unverified.','Break-even=1/decimal_odds. Descriptive EV per100=100*(historical hit frequency*odds-1). The Wilson frequency bounds are transformed by the same formula.','These sensitivities assume stationarity and exact payout equivalence; no historical prices, real ROI, calibrated fixture probability or executable edge are established.','Comparing many lines/windows creates selection risk. Wilson intervals are individual, unadjusted and do not remove serial/opponent/phase dependence.','Clausura and whole2026 remain separate; their disagreement must not be hidden by selecting the most profitable window.'],
      'execution_enabled':False,'network_requests':0}
    output=ROOT/'data/analysis/arg_count_empirics.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(output.relative_to(ROOT)),'count_quotes':len(evaluations),'source_quotes':len(quotes['quotes']),'rejected':len(rejected),'cohorts':result['cohort_counts']},ensure_ascii=False))
    under=next((r for r in evaluations if r['statistic']=='corners' and r['market']=='totals' and r['selection']=='under' and r['line']==9.5),None)
    if under:
        for window,groups in under['windows'].items():
            for name,row in groups.items():print(window,name,row['successes'],row['n'],row['wilson_95_frequency'],row['ev_per_100_stationary_sensitivity'],row['ev_per_100_wilson_stationary_sensitivity'])


if __name__=='__main__':main()
