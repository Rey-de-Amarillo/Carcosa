#!/usr/bin/env python3
"""Causal football goals value research. No current-match statistics enter features.

Protocol declared before evaluation: train <=2017, validation 2018..2021,
final 2022..2026; pick ridge by validation log loss, never by financial ROI.
Fixed 3% primary EV threshold, 0% and 5% sensitivities; one side per match.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from itertools import groupby
from pathlib import Path
sys.path.insert(0, '/tmp/football-portfolio-scipy')
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'data/raw/club_football_match_data/Matches.csv'
OUT = ROOT/'data/analysis/research_goal_ev.json'
PREDICTIONS = ROOT/'data/analysis/research_goal_ev_predictions.jsonl'
FEATURE_NAMES = ['intercept','market_logit','structural_minus_market_logit',
    'log_league_total','home_attack','home_defense','away_attack','away_defense',
    'home_venue_attack','home_venue_defense','away_venue_attack','away_venue_defense',
    'home_ew_attack','home_ew_defense','away_ew_attack','away_ew_defense',
    'rest_difference','rest_sum','home_recent_over','away_recent_over',
    'log_home_history','log_away_history']
PROTOCOL = {'training':'2000-2017','validation':'2018-2021','final':'2022-2026',
    'candidates':[{'ridge':10.0},{'ridge':100.0},{'ridge':1000.0}],
    'choice':'minimum validation log loss; no ROI tuning',
    'primary_ev_threshold':0.03,'sensitivity_ev_thresholds':[0.0,0.05],
    'odds_range':[1.2,5.0],'minimum_prior_team_matches':10,
    'same_day_updates':'all predictions before all result updates',
    'stake':'flat one unit; maximum one side per match',
    'price_stress':'multiply original decimal odds by 0.99; selections fixed',
    'bootstrap':'calendar-month cluster, 3000 replicates, seed 20261030',
    'features':FEATURE_NAMES,'ignored_source_columns':['HomeElo','AwayElo','Form3Home','Form5Home','Form3Away','Form5Away','C_*','current-match shots/cards/corners']}

@dataclass
class Team:
    n: int=0
    gf: float=0.
    ga: float=0.
    ew_n: float=0.
    ew_gf: float=0.
    ew_ga: float=0.
    ew_over: float=0.
    last: int|None=None
    venue: dict=field(default_factory=lambda:{'H':[0,0.,0.], 'A':[0,0.,0.]})
    def update(self, gf, ga, ordinal, venue):
        self.n+=1; self.gf+=gf; self.ga+=ga
        self.ew_n=self.ew_n*.90+1
        self.ew_gf=self.ew_gf*.90+gf
        self.ew_ga=self.ew_ga*.90+ga
        self.ew_over=self.ew_over*.90+int(gf+ga>2)
        self.last=ordinal
        v=self.venue[venue]; v[0]+=1; v[1]+=gf; v[2]+=ga

class CausalFeatures:
    def __init__(self):
        self.teams=defaultdict(Team)
        self.leagues=defaultdict(lambda:[0,0.,0.])
        self.last_updated_day=None
    def features(self,r):
        division=r['division']; t1=self.teams[(division,r['home'])]; t2=self.teams[(division,r['away'])]
        n,hg,ag=self.leagues[division]
        lh=(hg+100*1.45)/(n+100); la=(ag+100*1.15)/(n+100); avg=(lh+la)/2
        def shrink(total,n,prior,k=10): return (total+k*prior)/(n+k)
        ratios=[]
        for t in (t1,t2):
            ratios.extend([math.log(shrink(t.gf,t.n,avg)/avg),math.log(shrink(t.ga,t.n,avg)/avg)])
        venue=[]
        for t,v,pgf,pga in ((t1,'H',lh,la),(t2,'A',la,lh)):
            count,gf,ga=t.venue[v]
            venue.extend([math.log(shrink(gf,count,pgf)/pgf), math.log(shrink(ga,count,pga)/pga)])
        ew=[]
        for t in (t1,t2):
            ew.extend([math.log(shrink(t.ew_gf,t.ew_n,avg,5)/avg),math.log(shrink(t.ew_ga,t.ew_n,avg,5)/avg)])
        lam_h=lh*math.exp(.5*(ratios[0]+ratios[3]+venue[0]+venue[3]))
        lam_a=la*math.exp(.5*(ratios[2]+ratios[1]+venue[2]+venue[1]))
        lam=min(10,max(.1,lam_h+lam_a))
        pp=1-math.exp(-lam)*(1+lam+lam*lam/2)
        market=r.get('market_p',.5)
        ml=math.log(market/(1-market))
        structural=math.log(pp/(1-pp))
        rests=[min(30,max(0,r['ordinal']-t.last)) if t.last else 7 for t in (t1,t2)]
        over=[(t.ew_over+5*.5)/(t.ew_n+5)-.5 for t in (t1,t2)]
        x=[1., ml, structural-ml, math.log(lh+la),*ratios,*venue,*ew,
           (rests[0]-rests[1])/14,(rests[0]+rests[1]-14)/28,*over,
           math.log1p(t1.n)/5,math.log1p(t2.n)/5]
        return x, min(t1.n,t2.n), {'poisson_p':pp,'lambda_home':lam_h,'lambda_away':lam_a,'training_max_date':self.last_updated_day}
    def update_day(self,day,rows):
        for r in rows:
            self.teams[(r['division'],r['home'])].update(r['hg'],r['ag'],r['ordinal'],'H')
            self.teams[(r['division'],r['away'])].update(r['ag'],r['hg'],r['ordinal'],'A')
            v=self.leagues[r['division']]; v[0]+=1;v[1]+=r['hg'];v[2]+=r['ag']
        self.last_updated_day=day

def number(v):
    try:
        f=float(v)
        return f if math.isfinite(f) else None
    except (ValueError,TypeError): return None

def load_rows(source=SOURCE):
    rows=[]; seen=set(); excluded=defaultdict(int)
    with Path(source).open(newline='',encoding='utf-8-sig') as f:
        for line,r in enumerate(csv.DictReader(f),2):
            try: d=date.fromisoformat(r['MatchDate'])
            except (ValueError,TypeError): excluded['invalid_date']+=1;continue
            if d>date(2026,10,30): excluded['future']+=1;continue
            hg,ag=number(r['FTHome']),number(r['FTAway'])
            if hg is None or ag is None or min(hg,ag)<0 or not hg.is_integer() or not ag.is_integer():
                excluded['invalid_score']+=1;continue
            if r['FTResult']!=('H' if hg>ag else 'A' if ag>hg else 'D'):
                excluded['inconsistent_result']+=1;continue
            key=(r['Division'],r['MatchDate'],r['HomeTeam'],r['AwayTeam'])
            if key in seen: raise ValueError(f'Duplicate identity: {key}')
            seen.add(key)
            row={'row_id':line,'date':d.isoformat(),'ordinal':d.toordinal(),'division':r['Division'],
                 'home':r['HomeTeam'],'away':r['AwayTeam'],'hg':int(hg),'ag':int(ag),'y':int(hg+ag>2)}
            o,u=number(r['Over25']),number(r['Under25'])
            if o is not None and u is not None and min(o,u)>1:
                row.update(over_odds=o,under_odds=u,market_p=u/(o+u))
            rows.append(row)
    rows.sort(key=lambda r:(r['date'],r['row_id']))
    return rows,dict(excluded)

def build_features(rows):
    state=CausalFeatures(); paired=[]; features=[]
    for day,group in groupby(rows,key=lambda r:r['date']):
        batch=list(group)
        for row in batch:
            if 'market_p' not in row: continue
            x,count,details=state.features(row)
            paired.append({**row,'prior_team_min':count,**details});features.append(x)
        state.update_day(day,batch)
    return paired,np.asarray(features,dtype=float)

def fit_offset(X,y,offset,ridge):
    # The market logit is an offset; coefficients describe conditional corrections.
    scale=np.std(X,axis=0);scale[scale<1e-9]=1
    z=X/scale
    penalty=np.full(X.shape[1],ridge);penalty[0]=0
    def fun(beta):
        logits=offset+z@beta
        loss=np.logaddexp(0,logits).sum()-y@logits+.5*np.dot(penalty*beta,beta)
        grad=z.T@(expit(logits)-y)+penalty*beta
        return loss,grad
    fit=minimize(fun,np.zeros(X.shape[1]),jac=True,method='L-BFGS-B',options={'maxiter':300,'ftol':1e-11,'gtol':1e-5})
    if not fit.success and fit.nit>=300: raise RuntimeError(fit.message)
    return fit.x/scale, {'success':bool(fit.success),'iterations':fit.nit,'objective':float(fit.fun)}

def scores(y,p):
    p=np.clip(p,1e-9,1-1e-9)
    return {'n':len(y),'log_loss':float(np.mean(np.logaddexp(0,np.log(p/(1-p)))-y*np.log(p/(1-p)))),
            'brier':float(np.mean((p-y)**2)), 'mean_probability':float(np.mean(p)), 'event_rate':float(np.mean(y))}

def calibrate(y,p):
    # Only validation outcomes are used; final results never enter calibration.
    logits=np.log(np.clip(p,1e-9,1-1e-9)/(1-np.clip(p,1e-9,1-1e-9)))
    x=np.column_stack([np.ones(len(y)),logits])
    beta,detail=fit_offset(x,y,np.zeros(len(y)),10.)
    return beta,detail

def select_bets(rows,p,threshold):
    selected=[]
    for r,prob in zip(rows,p):
        if r['prior_team_min']<10: continue
        choices=[]
        for side,pr,odds in (('over',float(prob),r['over_odds']),('under',1-float(prob),r['under_odds'])):
            ev=pr*odds-1
            if 1.2<=odds<=5 and ev>=threshold:
                choices.append({'row_id':r['row_id'],'date':r['date'],'division':r['division'],
                    'home':r['home'],'away':r['away'],'side':side,'p':pr,'odds':odds,
                    'break_even_p':1/odds,'estimated_ev':ev,'win':bool(r['y'] if side=='over' else 1-r['y'])})
        if choices: selected.append(max(choices,key=lambda c:c['estimated_ev']))
    return selected

def summarize(bets,bootstrap=3000):
    if not bets: return {'bets':0,'roi':None,'profit_units':0,'month_bootstrap_95':None}
    returns=np.array([b['odds']*b['win']-1 for b in bets])
    stress=np.array([b['odds']*.99*b['win']-1 for b in bets])
    months=defaultdict(lambda:[0.,0])
    for b,r in zip(bets,returns): months[b['date'][:7]][0]+=float(r);months[b['date'][:7]][1]+=1
    sums=np.asarray(list(months.values()))
    rng=np.random.default_rng(20261030);ix=rng.integers(0,len(sums),size=(bootstrap,len(sums)))
    ratios=sums[ix,0].sum(axis=1)/sums[ix,1].sum(axis=1)
    years={}
    for year in sorted({b['date'][:4] for b in bets}):
        yy=[b for b in bets if b['date'].startswith(year)]
        years[year]={'bets':len(yy),'roi':float(np.mean([b['odds']*b['win']-1 for b in yy]))}
    return {'bets':len(bets),'wins':sum(b['win'] for b in bets),'hit_rate':float(np.mean([b['win'] for b in bets])),
      'profit_units':float(returns.sum()),'roi':float(returns.mean()),
      'mean_estimated_ev':float(np.mean([b['estimated_ev'] for b in bets])),
      'month_bootstrap_95':[float(v) for v in np.quantile(ratios,[.025,.975])],
      'roi_price_haircut_1pct_fixed_selections':float(stress.mean()),'years':years,
      'example':max(bets,key=lambda b:b['estimated_ev'])}

def paired_loss_comparison(rows,y,model_p,market_p):
    """Paired scoring advantage, clustered by calendar month, before looking at ROI."""
    def losses(p):
        p=np.clip(p,1e-9,1-1e-9)
        return -(y*np.log(p)+(1-y)*np.log(1-p))
    differences=losses(market_p)-losses(model_p)
    months=defaultdict(lambda:[0.,0])
    for row,value in zip(rows,differences):
        months[row['date'][:7]][0]+=float(value)
        months[row['date'][:7]][1]+=1
    sums=np.asarray(list(months.values()))
    rng=np.random.default_rng(20261030)
    ix=rng.integers(0,len(sums),size=(3000,len(sums)))
    samples=sums[ix,0].sum(axis=1)/sums[ix,1].sum(axis=1)
    return {'market_loss_minus_model_loss':float(np.mean(differences)),
            'month_cluster_95':[float(v) for v in np.quantile(samples,[.025,.975])],
            'positive_means':'model has lower predictive log loss'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,default=SOURCE);args=parser.parse_args()
    rows,excluded=load_rows(args.source);paired,X=build_features(rows)
    dates=np.array([r['date'] for r in paired]);y=np.array([r['y'] for r in paired],float)
    market=np.array([r['market_p'] for r in paired]);offset=np.log(market/(1-market))
    train=dates<'2018';valid=(dates>='2018')&(dates<'2022');test=dates>='2022'
    candidates=[];fitted=[]
    for spec in PROTOCOL['candidates']:
        beta,detail=fit_offset(X[train],y[train],offset[train],spec['ridge'])
        pv=expit(offset[valid]+X[valid]@beta)
        candidates.append({**spec,'validation':scores(y[valid],pv),'optimizer':detail})
        fitted.append(beta)
    chosen=int(np.argmin([c['validation']['log_loss'] for c in candidates]));beta=fitted[chosen]
    uncal=expit(offset+X@beta)
    cal,caldetail=calibrate(y[valid],uncal[valid]);p=expit(cal[0]+cal[1]*np.log(uncal/(1-uncal)))
    testrows=[r for r,keep in zip(paired,test) if keep];pt=p[test]
    thresholds={str(t):summarize(select_bets(testrows,pt,t)) for t in (0.,.03,.05)}
    bins=[]
    for lo,hi in zip(np.arange(0,1,.1),np.arange(.1,1.1,.1)):
        take=(pt>=lo)&(pt<hi)
        if take.any(): bins.append({'lo':float(lo),'hi':float(hi),'n':int(take.sum()),'p':float(pt[take].mean()),'rate':float(y[test][take].mean())})
    year_quality={}
    for year in sorted({r['date'][:4] for r in testrows}):
        take=np.char.startswith(dates[test],year)
        year_quality[year]={'model':scores(y[test][take],pt[take]),
                            'market_no_vig':scores(y[test][take],market[test][take])}
    result={'protocol':PROTOCOL,'source':str(args.source.relative_to(ROOT)),'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
      'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'all_valid_score_rows':len(rows),
      'excluded':excluded,'paired_odds_rows':len(paired),'split_counts':{'train':int(train.sum()),'validation':int(valid.sum()),'final':int(test.sum())},
      'date_range':[min(dates),max(dates)],'candidate_validation':candidates,'chosen':candidates[chosen]['ridge'],
      'coefficients':dict(zip(FEATURE_NAMES,map(float,beta))),'calibration':{'intercept':float(cal[0]),'slope':float(cal[1]),'optimizer':caldetail},
      'final_probability_quality':{'model_calibrated':scores(y[test],pt),'model_uncalibrated':scores(y[test],uncal[test]),'market_no_vig':scores(y[test],market[test])},
      'paired_predictive_advantage':paired_loss_comparison(testrows,y[test],pt,market[test]),
      'final_year_probability_quality':year_quality,
      'calibration_bins':bins,'final_strategies':thresholds,
      'primary_bet_ledger':select_bets(testrows,pt,.03),
      'closing_price':'not supplied; no CLV calculated'}
    OUT.parent.mkdir(exist_ok=True,parents=True);OUT.write_text(json.dumps(result,indent=2)+'\n')
    with PREDICTIONS.open('w') as f:
        for r,pr in zip(testrows,pt):
            f.write(json.dumps({**r,'p_over':float(pr),'p_under':1-float(pr)},separators=(',',':'))+'\n')
    primary=thresholds['0.03']
    lines=['# Valor esperado condicional: goles 2.5','',
      '**Este modelo no identificó una ventaja monetaria en la prueba final.**','',
      'Se comparan Over y Under con sus cuotas Bet365 del mismo partido. Fórmula: `EV = p × cuota − 1`.',
      f"Historial: {len(rows):,} resultados; {len(paired):,} partidos con ambas cuotas. Entrenamiento: {int(train.sum()):,}; validación: {int(valid.sum()):,}; prueba final 2022–2026: {int(test.sum()):,}.",'',
      'Variables: ataque y defensa del equipo y rival, localía, promedio de liga, forma exponencial, goles de cada equipo, descanso, cantidad de partidos previos y cuota previa. Todos los partidos del mismo día se predicen antes de cargar sus resultados.',
      '',f"Modelo elegido por log loss de validación: ridge {candidates[chosen]['ridge']:g}. Calibración ajustada exclusivamente en 2018–2021. Umbral principal 3% de EV estimado; una apuesta por partido y una unidad fija.",'',
      '| EV mínimo | Apuestas | Ganancia por 100 apostados | IC 95% por mes | Con cuota 1% menor |',
      '|---|---:|---:|---:|---:|']
    for threshold,s in thresholds.items():
        if s['bets']:
            ci=s['month_bootstrap_95'];lines.append(f"| {float(threshold):.0%} | {s['bets']:,} | {s['roi']*100:+.3f} | [{ci[0]*100:+.3f}, {ci[1]*100:+.3f}] | {s['roi_price_haircut_1pct_fixed_selections']*100:+.3f} |")
        else: lines.append(f'| {float(threshold):.0%} | 0 | — | — | — |')
    lines+=['','## Calidad probabilística final','', '| Modelo | Log loss | Brier |','|---|---:|---:|']
    for label,s in result['final_probability_quality'].items():lines.append(f"| {label} | {s['log_loss']:.6f} | {s['brier']:.6f} |")
    advantage=result['paired_predictive_advantage']
    lines+=['',f"Mejora media de log loss frente al mercado: {advantage['market_loss_minus_model_loss']:+.8f}; IC 95% por mes [{advantage['month_cluster_95'][0]:+.8f}, {advantage['month_cluster_95'][1]:+.8f}]."]
    lines+=['','## Resultado por año del umbral principal','','| Año | Apuestas | ROI |','|---|---:|---:|']
    for year,s in primary.get('years',{}).items():lines.append(f"| {year} | {s['bets']} | {s['roi']:+.3%} |")
    lines+=['','## Ejemplo de cálculo histórico','']
    if primary.get('example'):
        e=primary['example'];lines.append(f"{e['date']}: {e['home']}–{e['away']}, {e['side']} 2.5 @ {e['odds']}. `p` estimada {e['p']:.3%}; equilibrio {e['break_even_p']:.3%}; EV estimado {e['estimated_ev']:+.3%}; resultado {'ganó' if e['win'] else 'perdió'}. Es un ejemplo mecánico, no una selección actual.")
    lines+=['','Código y predicciones completas quedan en `scripts/research_goal_ev.py` y `data/analysis/research_goal_ev_predictions.jsonl`. El JSON de auditoría registra fechas, coeficientes, protocolo y hashes. No se dispone de cuota de cierre identificada.','']
    (ROOT/'VALOR_ESPERADO_GOLES.md').write_text('\n'.join(lines))
    print(json.dumps({'counts':result['split_counts'],'chosen_ridge':result['chosen'],'final_quality':result['final_probability_quality'],'strategies':thresholds},indent=2))
if __name__=='__main__': main()
