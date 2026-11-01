#!/usr/bin/env python3
"""Distinct retrospective EV experiment: EPL first-half zero versus any goal.
Probability model is frozen before SGodds 2026 labels; historical experiment
was not prospectively registered and the SGodds cohort appeared in earlier audits.
"""
from __future__ import annotations
import csv,hashlib,json,math,sqlite3,sys
from collections import defaultdict,deque
from datetime import date,datetime
from itertools import groupby
from pathlib import Path
import research_goal_ev as g
np=g.np;expit=g.expit
ROOT=Path(__file__).resolve().parents[1]
ALIASES={'Manchester City':'Man City','Manchester Utd':'Man United','Nottingham':"Nott'm Forest",'Wolverhampton':'Wolves','Hull City':'Hull'}
OUT=ROOT/'data/analysis/research_first_half_ev.json'
PRED=ROOT/'data/analysis/research_first_half_ev_predictions.jsonl'
FEATURES=['intercept','ft_market_logit_ht_any','structural_minus_market_logit','log_league_ht_goals',
'home_attack','home_defense','away_attack','away_defense','home_venue_attack','home_venue_defense','away_venue_attack','away_venue_defense',
'home_ew_attack','home_ew_defense','away_ew_attack','away_ew_defense','rest_difference','rest_sum','home_last5_total','away_last5_total','ft_home_fair_probability','ft_draw_fair_probability']
PROTOCOL={'train':'<=2017','select_by_log_loss':'2018-2021','calibration':'2022-01-01 through 2025-12-29','final':'all 280 reconciled SGodds EPL; starts 2025-12-30',
'ridge_candidates':[10.,100.,1000.],'primary_ev_threshold':.03,'sensitivity_thresholds':[0.,.05],
'minimum_prior_team_matches':10,'maximum_contracts_per_event':1,'unit_stake':1.,'bootstrap':'date cluster 3000 seed 20261030',
'odds_price_stress':'original decimal odds times 0.99, fixed positions','reused_retrospective_final_cohort':True,
'feature_odds':'actual paired Bet365 FT 2.5 and 1X2 from reconciled Football-Data row; no current result features',
'features':FEATURES}

def logit(p): return math.log(max(1e-9,p)/max(1e-9,1-p))
def parse_day(s):
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d/%m/%y'):
        try:return datetime.strptime(s,fmt).date().isoformat()
        except ValueError:pass
    raise ValueError(s)
def parse_match(raw,original=False):
    keys=('Div','Date','HTHG','HTAG','FTHG','FTAG','B365H','B365D','B365A','B365>2.5','B365<2.5') if original else ('Division','MatchDate','HTHome','HTAway','FTHome','FTAway','OddHome','OddDraw','OddAway','Over25','Under25')
    vals={key:raw.get(key) for key in keys}
    if vals[keys[0]]!='E0':return None
    try:
        day=parse_day(vals[keys[1]]); ht=[g.number(vals[k]) for k in keys[2:4]]; ft=[g.number(vals[k]) for k in keys[4:6]]
        if None in ht+ft or any(v<0 or not v.is_integer() for v in ht+ft) or any(h>f for h,f in zip(ht,ft)):return None
        r={'date':day,'ordinal':date.fromisoformat(day).toordinal(),'division':'E0','home':raw['HomeTeam'],'away':raw['AwayTeam'],
           'hg':int(ht[0]),'ag':int(ht[1]),'ft_hg':int(ft[0]),'ft_ag':int(ft[1]),'y':int(sum(ht)>=1)}
        odds=[g.number(vals[k]) for k in keys[6:]]
        if all(o and o>1 for o in odds):
            h,d,a,o,u=odds;s=1/h+1/d+1/a
            r.update(over_odds=o,under_odds=u,market_p=u/(o+u),ft_home_p=(1/h)/s,ft_draw_p=(1/d)/s)
        return r
    except (ValueError,TypeError):return None

def load_history():
    merged={};sources=[];overwritten=0
    for path,original in [(g.SOURCE,False),*( (ROOT/f'data/raw/football/{season}_E0.csv',True) for season in ('2526','2627'))]:
        sources.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        with path.open(newline='',encoding='utf-8-sig') as f:
            for raw in csv.DictReader(f):
                r=parse_match(raw,original)
                if r is None or r['date']>'2026-10-30':continue
                key=(r['date'],r['home'],r['away'])
                if key in merged:
                    prior=merged[key]
                    assert [prior[k] for k in ('hg','ag','ft_hg','ft_ag')]==[r[k] for k in ('hg','ag','ft_hg','ft_ag')],key
                    overwritten+=1
                merged[key]=r
    return sorted(merged.values(),key=lambda r:(r['date'],r['home'],r['away'])),sources,overwritten

def ft_market_ht_any(over_p):
    lo,hi=.01,12.
    for _ in range(45):
        lam=(lo+hi)/2;p=1-math.exp(-lam)*(1+lam+lam*lam/2)
        if p<over_p:lo=lam
        else:hi=lam
    return 1-math.exp(-.44*(lo+hi)/2)

class HTFeatures:
    def __init__(self):
        self.teams=defaultdict(g.Team);self.league=[0,0.,0.];self.last5=defaultdict(lambda:deque(maxlen=5));self.last_day=None
    def features(self,r):
        a,b=[self.teams[r[k]] for k in ('home','away')];n,hg,ag=self.league
        lh=(hg+100*.65)/(n+100);la=(ag+100*.50)/(n+100);avg=(lh+la)/2
        def rate(total,n,prior,k=10):return(total+k*prior)/(n+k)
        ratios=[];venue=[];ew=[]
        for t in (a,b):ratios.extend([math.log(rate(t.gf,t.n,avg)/avg),math.log(rate(t.ga,t.n,avg)/avg)])
        for t,v,pgf,pga in ((a,'H',lh,la),(b,'A',la,lh)):
            c,gf,ga=t.venue[v];venue.extend([math.log(rate(gf,c,pgf)/pgf),math.log(rate(ga,c,pga)/pga)])
        for t in (a,b):ew.extend([math.log(rate(t.ew_gf,t.ew_n,avg,5)/avg),math.log(rate(t.ew_ga,t.ew_n,avg,5)/avg)])
        lamh=lh*math.exp(.5*(ratios[0]+ratios[3]+venue[0]+venue[3]));lama=la*math.exp(.5*(ratios[2]+ratios[1]+venue[2]+venue[1]))
        pstruct=1-math.exp(-min(10,lamh+lama));base=ft_market_ht_any(r['market_p']);offset=logit(base)
        rests=[min(30,max(0,r['ordinal']-t.last)) if t.last else 7 for t in (a,b)]
        forms=[(sum(self.last5[r[k]])+5*(lh+la))/(len(self.last5[r[k]])+5)-(lh+la) for k in ('home','away')]
        x=[1.,offset,logit(pstruct)-offset,math.log(lh+la),*ratios,*venue,*ew,(rests[0]-rests[1])/14,(sum(rests)-14)/28,*forms,r['ft_home_p'],r['ft_draw_p']]
        return x,offset,min(a.n,b.n),self.last_day
    def update_day(self,day,rows):
        for r in rows:
            self.teams[r['home']].update(r['hg'],r['ag'],r['ordinal'],'H');self.teams[r['away']].update(r['ag'],r['hg'],r['ordinal'],'A')
            self.league[0]+=1;self.league[1]+=r['hg'];self.league[2]+=r['ag']
            for k in ('home','away'):self.last5[r[k]].append(r['hg']+r['ag'])
        self.last_day=day

def build(history):
    state=HTFeatures();rows=[];xs=[];offsets=[]
    for day,group in groupby(history,key=lambda r:r['date']):
        batch=list(group)
        for r in batch:
            if 'market_p' not in r:continue
            x,offset,n,maxday=state.features(r);rows.append({**r,'prior_team_min':n,'training_max_date':maxday});xs.append(x);offsets.append(offset)
        state.update_day(day,batch)
    return rows,np.asarray(xs),np.asarray(offsets)

def contracts(raw):
    def price(k):return g.number(raw.get(k))
    zero=[{'name':k,'odds':price(k),'positions':[{'field':k,'stake':1.,'odds':price(k)}],'side':'zero'} for k in ('Htpts_00','Httg_00','Htt1g_03') if price(k) and price(k)>1]
    anygoal=[]
    if price('Htou_Hcap')==.5:
        for key,side,target in (('Htou_02','zero',zero),('Htou_01','any',anygoal)):
            if price(key) and price(key)>1:target.append({'name':key,'odds':price(key),'positions':[{'field':key,'stake':1.,'odds':price(key)}],'side':side})
    h,a=price('Htt1g_01'),price('Htt1g_02')
    if h and a and min(h,a)>1:
        q=1/(1/h+1/a)
        anygoal.append({'name':'synthetic_home_or_away_first_HT','odds':q,'side':'any','positions':[{'field':'Htt1g_01','stake':q/h,'odds':h},{'field':'Htt1g_02','stake':q/a,'odds':a}]})
    return ([max(zero,key=lambda c:c['odds'])] if zero else [])+([max(anygoal,key=lambda c:c['odds'])] if anygoal else [])

def reconcile(rows,p):
    c=sqlite3.connect(f'file:{ROOT}/data/processed/free_football_history.sqlite?mode=ro',uri=True);c.row_factory=sqlite3.Row
    bypair=defaultdict(list)
    for r,pr in zip(rows,p):bypair[(r['home'],r['away'])].append((r,float(pr)))
    results=[]
    for m in c.execute("select * from sgodds_matches where league='English Premier' and has_ht_ft_result=1 order by start_time_source,match_row_id"):
        h,a=[ALIASES.get(t,t) for t in m['match_name'].split(' vs ')]
        sd=date.fromisoformat(m['start_time_source'][:10])
        candidates=[(r,pr) for r,pr in bypair[(h,a)] if abs((date.fromisoformat(r['date'])-sd).days)<=1]
        if len(candidates)!=1:raise ValueError(f'Expected unique original match: {m["match_name"]}')
        r,pr=candidates[0]
        assert [r[k] for k in ('hg','ag','ft_hg','ft_ag')]==[m[k] for k in ('ht_home','ht_away','ft_home','ft_away')]
        assert r['date']>='2025-12-30' and r['training_max_date']<r['date']
        results.append({**r,'match_row_id':m['match_row_id'],'sg_start_time_source':m['start_time_source'],'p_any':pr,'p_zero':1-pr,'contracts':contracts(json.loads(m['raw_row_json']))})
    c.close();assert len(results)==280,len(results)
    return results

def select(rows,threshold):
    bets=[]
    for r in rows:
        if r['prior_team_min']<10:continue
        offers=[]
        for c in r['contracts']:
            p=r['p_any'] if c['side']=='any' else r['p_zero'];ev=p*c['odds']-1
            if ev>=threshold:offers.append({**c,'date':r['date'],'match_row_id':r['match_row_id'],'home':r['home'],'away':r['away'],'p':p,'estimated_ev':ev,'break_even_p':1/c['odds'],'win':bool(r['y'] if c['side']=='any' else 1-r['y'])})
        if offers:bets.append(max(offers,key=lambda c:c['estimated_ev']))
    return bets

def summarize(bets):
    if not bets:return {'bets':0,'roi':None,'profit_units':0}
    returns=np.array([b['win']*b['odds']-1 for b in bets]);dates=defaultdict(lambda:[0.,0])
    for b,r in zip(bets,returns):dates[b['date']][0]+=float(r);dates[b['date']][1]+=1
    blocks=np.array(list(dates.values()));rng=np.random.default_rng(20261030);ix=rng.integers(0,len(blocks),size=(3000,len(blocks)))
    ci=np.quantile(blocks[ix,0].sum(axis=1)/blocks[ix,1].sum(axis=1),[.025,.975]) if len(blocks)>1 else None
    return {'bets':len(bets),'wins':sum(b['win'] for b in bets),'roi':float(returns.mean()),'profit_units':float(returns.sum()),'date_cluster_95':list(map(float,ci)) if ci is not None else None,
'distinct_dates':len(blocks),'bootstrap_status':'computed' if ci is not None else 'not estimable: only one date cluster',
'roi_price_haircut_1pct_fixed_positions':float(np.mean([b['win']*b['odds']*.99-1 for b in bets])),
'mean_estimated_ev':float(np.mean([b['estimated_ev'] for b in bets])),
'by_side':{side:{'bets':len(s:=[b for b in bets if b['side']==side]),'roi':sum(b['win']*b['odds']-1 for b in s)/len(s)} for side in sorted({b['side'] for b in bets})}}

def main():
    history,sources,duplicates=load_history();rows,X,offset=build(history)
    dates=np.array([r['date'] for r in rows]);y=np.array([r['y'] for r in rows],float)
    train=dates<'2018';valid=(dates>='2018')&(dates<'2022');calib=(dates>='2022')&(dates<'2025-12-30')
    candidates=[];coefs=[]
    for ridge in PROTOCOL['ridge_candidates']:
        beta,fit=g.fit_offset(X[train],y[train],offset[train],ridge)
        candidates.append({'ridge':ridge,'validation':g.scores(y[valid],expit(offset[valid]+X[valid]@beta)),'fit':fit});coefs.append(beta)
    chosen=int(np.argmin([c['validation']['log_loss'] for c in candidates]));beta=coefs[chosen]
    rawp=expit(offset+X@beta);cal,fit=g.calibrate(y[calib],rawp[calib]);p=expit(cal[0]+cal[1]*np.log(rawp/(1-rawp)))
    final=reconcile(rows,p);strategies={str(t):summarize(select(final,t)) for t in (0.,.03,.05)}
    yf=np.array([r['y'] for r in final]);pf=np.array([r['p_any'] for r in final]);bf=np.array([ft_market_ht_any(r['market_p']) for r in final])
    result={'protocol':PROTOCOL,'sources':sources,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
'shared_model_helper_sha256':hashlib.sha256(Path(g.__file__).read_bytes()).hexdigest(),
'sgodds_source_audit_sha256':hashlib.sha256((ROOT/'data/analysis/sgodds_archive_audit.json').read_bytes()).hexdigest(),
'deduplicated_recent_overrides':duplicates,
'history_results':len(history),'paired_feature_odds_rows':len(rows),'split_counts':{'training':int(train.sum()),'validation':int(valid.sum()),'calibration':int(calib.sum()),'SG_final':len(final)},
'candidates':candidates,'chosen_ridge':candidates[chosen]['ridge'],'coefficients':dict(zip(FEATURES,map(float,beta))),
'calibration':{'intercept':float(cal[0]),'slope':float(cal[1])},'final_quality':{'model':g.scores(yf,pf),'ft_price_poisson_baseline':g.scores(yf,bf)},
'final_strategies':strategies,'primary_ledger':select(final,.03),'example':max(select(final,0.),key=lambda b:b['estimated_ev'],default=None)}
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    PRED.write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in final))
    lines=['# Valor esperado: gol en el primer tiempo','',f"Modelo con {len(history):,} resultados EPL, {len(FEATURES)} variables y cuotas reales. Entrenamiento hasta 2017; selección 2018–2021; calibración 2022–29/12/2025; prueba de precios SGodds: {len(final)} partidos desde 30/12/2025 hasta octubre de 2026.",'',
'Se compara cero goles —el mejor precio entre 0–0, total cero, nadie marca primero y Under 0.5— contra un gol o más. También se construye un gol o más repartiendo la unidad entre local y visitante como primer equipo en marcar: cuota efectiva `1 / (1/cuota_local + 1/cuota_visitante)`. Las posiciones son excluyentes y cubren cualquier primer gol, sin multiplicar probabilidades.','',
'| EV mínimo | Apuestas | Ganancia por 100 apostados | IC 95% por fecha | Cuotas 1% menores |','|---|---:|---:|---:|---:|']
    for t,s in strategies.items():
        if s['bets']:
            ci=s['date_cluster_95'];ci_text=f'[{ci[0]*100:+.3f}, {ci[1]*100:+.3f}]' if ci else '— (una fecha)'
            lines.append(f"| {float(t):.0%} | {s['bets']} | {s['roi']*100:+.3f} | {ci_text} | {s['roi_price_haircut_1pct_fixed_positions']*100:+.3f} |")
        else:lines.append(f'| {float(t):.0%} | 0 | — | — | — |')
    if result['example']:
        e=result['example'];lines+=['',f"Ejemplo histórico: {e['date']}, {e['home']}–{e['away']}, {e['name']} @ {e['odds']:.4f}. Probabilidad {e['p']:.3%}; equilibrio {e['break_even_p']:.3%}; `EV = p × cuota − 1 = {e['estimated_ev']:+.3%}`."]
    lines+=['','Las variables usan goles del primer tiempo: ataque/defensa, rival, localía, forma de últimos cinco partidos y exponencial, descanso, promedio de liga y cuotas FT. Se predice toda la fecha antes de incorporar sus resultados. Los 280 marcadores HT y FT coinciden con Football-Data tras corregir únicamente cinco alias y la fecha de huso horario.','',
'Código: `scripts/research_first_half_ev.py`. Auditoría y posiciones: `data/analysis/research_first_half_ev.json`; predicciones y contratos: `data/analysis/research_first_half_ev_predictions.jsonl`. La cohorte SGodds es retrospectiva y ya apareció en estudios anteriores; no es una prueba prospectiva.','']
    (ROOT/'VALOR_ESPERADO_PRIMER_TIEMPO.md').write_text('\n'.join(lines));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
