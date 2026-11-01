"""Auditable v2 development/selection and an explicitly previously-seen audit.

No query, account, price execution, or real-money action is performed here.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.report import read_matches
from engine.core import LeaguePoisson,proper_scores
from engine.models_v2 import replay_predictions,score_grid
from engine.ensemble import consensus,blend,select_candidate,multiclass_logloss


def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    tmp.replace(path)


def fingerprint():
    digest=hashlib.sha256()
    for name in ['data/processed/matches.csv','data/processed/baseball.csv','engine/models_v2.py']:
        p=ROOT/name
        if p.exists():digest.update(p.read_bytes())
    return digest.hexdigest()


def archive_quote_inputs():
    """Retain the exact multi-book inputs if future raw files are corrected."""
    source=ROOT/'data/analysis/quote_history.jsonl'
    if not source.exists():return None
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    target=ROOT/'data/runtime/reproducibility'/f'{digest}.quote_history.jsonl.gz'
    if not target.exists():
        import shutil
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_suffix('.gz.tmp')
        with source.open('rb') as inp,gzip.open(tmp,'wb',compresslevel=6) as out:
            shutil.copyfileobj(inp,out)
        tmp.replace(target)
    return {'sha256':digest,'archive':str(target.relative_to(ROOT))}


def old_predictions(rows):
    from itertools import groupby
    models={};result={}
    for day,group in groupby(rows,key=lambda r:r['date']):
        entries=list(group)
        for row in entries:
            model=models.setdefault(row['league'],LeaguePoisson())
            model.advance(row['_day'])
            p=model.predict(row['home_team'],row['away_team'])
            if p['eligible'] and str(row.get('neutral_venue','false')).lower()!='true':
                result[row['id']]=[p['home'],p['draw'],p['away']]
        for row in entries:
            if str(row.get('neutral_venue','false')).lower()!='true':
                models[row['league']].update(row['home_team'],row['away_team'],row['home_score'],row['away_score'])
    return result


def predictions(rows,force=False):
    path=ROOT/'data/analysis/v2_prediction_cache.jsonl'
    stamp=fingerprint()
    if path.exists() and not force:
        with path.open() as f:
            header=json.loads(next(f))
            if header.get('fingerprint')==stamp:
                return {r['id']:r['prediction'] for r in map(json.loads,f)}
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    result={}
    with tmp.open('w') as f:
        f.write(json.dumps({'fingerprint':stamp})+'\n')
        for item in replay_predictions(rows):
            f.write(json.dumps(item,ensure_ascii=False)+'\n')
            result[item['id']]=item['prediction']
    tmp.replace(path)
    return result


def metrics(rows,key,name,period):
    valid=[r for r in rows if r.get(key) is not None]
    if not valid:return {'id':key,'name':name,'period':period,'n':0,'log_loss':None,'brier':None,'accuracy':None,'ece':None}
    losses=[];briers=[];correct=0;bins=defaultdict(list)
    for r in valid:
        p=r[key];y=r['outcome'];best=max(range(len(p)),key=p.__getitem__)
        losses.append(multiclass_logloss(p,y))
        briers.append(sum((v-(i==y))**2 for i,v in enumerate(p)))
        correct+=best==y;bins[min(9,int(p[best]*10))].append((p[best],best==y))
    n=len(valid)
    ece=sum(abs(sum(v[0] for v in values)-sum(v[1] for v in values)) for values in bins.values())/n
    return {'id':key,'name':name,'period':period,'n':n,'log_loss':sum(losses)/n,
            'brier':sum(briers)/n,'accuracy':correct/n,'ece':ece,
            'from':min(r['date'] for r in valid),'to':max(r['date'] for r in valid)}


def paired_ci(rows,a,b):
    groups=defaultdict(list)
    for r in rows:
        if r.get(a) is not None and r.get(b) is not None:
            groups[r['date']].append(multiclass_logloss(r[a],r['outcome'])-multiclass_logloss(r[b],r['outcome']))
    values=list(groups.values());rng=random.Random(20261030);samples=[]
    for _ in range(400 if values else 0):
        chosen=[rng.choice(values) for _ in values]
        samples.append(sum(map(sum,chosen))/sum(map(len,chosen)))
    samples.sort()
    return {'n':sum(map(len,values)),'dates':len(values),'improvement':sum(map(sum,values))/sum(map(len,values)) if values else None,
            'low':samples[int(.025*len(samples))] if samples else None,
            'high':samples[min(len(samples)-1,int(.975*len(samples)))] if samples else None,
            'method':'Bootstrap por fecha, 400 réplicas. Auditoría retrospectiva ya inspeccionada; no confirmación prospectiva.'}


def calibration(rows,key):
    bins=defaultdict(list)
    for r in rows:
        if not r.get(key):continue
        p=r[key];i=max(range(len(p)),key=p.__getitem__)
        bins[min(9,int(p[i]*10))].append((p[i],i==r['outcome']))
    return [{'predicted':sum(x[0] for x in v)/len(v),'observed':sum(x[1] for x in v)/len(v),'count':len(v)} for _,v in sorted(bins.items())]


def market_evaluation(rows):
    """Score-derived events, each scored against the correct observed target."""
    targets={
      'over05':('Más de 0,5 goles',lambda h,a:h+a>.5,lambda p:1-math.exp(-p['home_rate']-p['away_rate'])*(1-p['home_rate']*p['away_rate']*p['rho_applied'])),
      'over15':('Más de 1,5 goles',lambda h,a:h+a>1.5,None),
      'over25':('Más de 2,5 goles',lambda h,a:h+a>2.5,lambda p:p['over25']),
      'over35':('Más de 3,5 goles',lambda h,a:h+a>3.5,None),
      'btts':('Ambos equipos marcan',lambda h,a:h>0 and a>0,lambda p:p['btts_yes']),
      'double_home':('Doble oportunidad: local o empate',lambda h,a:h>=a,lambda p:p['home']+p['draw']),
      'double_away':('Doble oportunidad: empate o visitante',lambda h,a:h<=a,lambda p:p['draw']+p['away'])}
    accum={k:{'brier':0.,'log_loss':0.,'correct':0,'n':0,'market_brier_sum':0.,'market_n':0,
              'paired_brier_sum':0.,'paired_log_loss_sum':0.,'paired_correct':0} for k in targets}
    for r in rows:
        p=r['prediction'];h,a=r['home_score'],r['away_score']
        grid=None
        for key,(name,label,forecast) in targets.items():
            if forecast is not None:prob=forecast(p)
            else:
                if grid is None:grid=score_grid(p['home_rate'],p['away_rate'],p['rho_applied'])['grid']
                line=1.5 if key=='over15' else 3.5
                prob=sum(v for x,row in enumerate(grid) for y,v in enumerate(row) if x+y>line)
            prob=max(1e-12,min(1-1e-12,prob));actual=label(h,a);z=accum[key]
            z['n']+=1;z['brier']+=(prob-actual)**2;z['log_loss']+=-math.log(prob if actual else 1-prob);z['correct']+=(prob>=.5)==actual
            if key=='over25':
                q=r['quote'].get('totals25',{}).get('pre',{})
                ref=consensus(q,'power')
                if ref['probabilities']:
                    z['market_brier_sum']+=(ref['probabilities'][0]-actual)**2;z['market_n']+=1
                    z['paired_brier_sum']+=(prob-actual)**2
                    z['paired_log_loss_sum']+=-math.log(prob if actual else 1-prob)
                    z['paired_correct']+=(prob>=.5)==actual
    result=[]
    for key,(name,*_) in targets.items():
        z=accum[key];n=z['n']
        paired=key=='over25' and z['market_n']>0
        display_n=z['market_n'] if paired else n
        result.append({'id':key,'name':name,'n':display_n,'all_available_events':n,
                       'brier':z['paired_brier_sum']/display_n if paired else z['brier']/n if n else None,
                       'log_loss':z['paired_log_loss_sum']/display_n if paired else z['log_loss']/n if n else None,
                       'accuracy':z['paired_correct']/display_n if paired else z['correct']/n if n else None,
                       'market_brier':z['market_brier_sum']/z['market_n'] if z['market_n'] else None,
                       'odds_events':z['market_n'],'roi':None,'status':'research',
                       'note':'Métrica binaria (0–1); modelo estructural sin declarar rentabilidad por falta de precio equivalente.' if key!='over25' else 'Precios 2,5 disponibles; la comparación financiera se informa por separado.','model':'Poisson V2 ajustado por adversario y marcadores bajos'})
    return result


def prepare():
    rows,_=read_matches(ROOT/'data/processed')
    rows=[r for r in rows if r['sport']=='football']
    print('Generando predicciones cronológicas v2…',flush=True)
    pp=predictions(rows)
    print('Predicciones listas. Reproduciendo referencia v1…',flush=True)
    old=old_predictions(rows)
    with (ROOT/'data/analysis/quote_history.jsonl').open() as f:quotes={r['id']:r for r in map(json.loads,f)}
    records=[]
    for row in rows:
        p=pp.get(row['id'])
        if not p or not p.get('eligible'):continue
        quote=quotes.get(row['id'],{'h2h':{},'totals25':{},'asian_handicap':{}})
        record={k:v for k,v in row.items() if not k.startswith('_')}
        record.update({'prediction':p,'structural':[p['home'],p['draw'],p['away']],
                       'v1':old.get(row['id']),'quote':quote,
                       'outcome':0 if row['home_score']>row['away_score'] else 1 if row['home_score']==row['away_score'] else 2})
        for method in ['proportional','power']:
            ref=consensus(quote.get('h2h',{}).get('pre',{}),method)
            record['consensus_'+method]=ref['probabilities']
            if method=='power':record['reference_books']=ref['count']
        records.append(record)
    return rows,records


def main():
    cfg=json.loads((ROOT/'config/experiment_v2.json').read_text())
    quote_archive=archive_quote_inputs()
    rows,records=prepare()
    selection=select_candidate(records,cfg['ensemble_candidates'],cfg['selection_start'],cfg['selection_end'])
    if not selection['selected']:raise RuntimeError('No hay muestra de selección.')
    lock={**selection,'protocol':cfg,'registered_at':datetime.now(timezone.utc).isoformat(),
          'data_fingerprint':fingerprint(),'audit_status':'previously_inspected_not_independent_holdout'}
    lock['spec_sha256']=hashlib.sha256(json.dumps(lock,sort_keys=True).encode()).hexdigest()
    atomic(ROOT/'data/analysis/selection_v2.json',lock)
    selected_spec={k:selection['selected'][k] for k in ('id','devig','structural_weight')}
    selected_spec.update({'version':'0.2.0','selected_on':{'from':cfg['selection_start'],'to':cfg['selection_end']},
                         'criterion':'log_loss','live_enabled':False})
    atomic(ROOT/'config/selected_model_v2.json',selected_spec)
    print('Selección fijada sin leer ROI de auditoría: '+selection['selected']['id'],flush=True)
    spec=selection['selected']
    for record in records:
        record['selected']=blend(record['structural'],record['consensus_'+spec['devig']],spec['structural_weight'])
    audit=[r for r in records if cfg['retrospective_audit_start']<=r['date']<=cfg['retrospective_audit_end']]
    valid=[r for r in audit if r.get('v1') is not None and r['consensus_power'] is not None]
    valid_selection=[r for r in records if cfg['selection_start']<=r['date']<=cfg['selection_end'] and r.get('v1') is not None and r['consensus_power'] is not None]
    labels={'v1':'Poisson v1','structural':'Poisson ajustado + Dixon–Coles v2','consensus_proportional':'Consenso multicasa proporcional',
            'consensus_power':'Consenso multicasa power','selected':'Ensamble elegido en validación'}
    comparison=[]
    for name,group in [('selection',valid_selection),('audit',valid)]:
        for key,label in labels.items():comparison.append(metrics(group,key,label,name))
    from engine.research_backtest import simulate_h2h
    strategies=[];portfolios={}
    for period,group in [('selection',valid_selection),('audit',audit)]:
        for sid,name,target in [('consensus_best','Consenso y mejor precio entre casas',None),('consensus_b365','Consenso frente a Bet365','B365')]:
            result=simulate_h2h(group,spec,cfg['research_policy'],target_book=target)
            stress=simulate_h2h(group,spec,cfg['research_policy'],target_book=target,price_haircut=.01)
            portfolios[(sid,period)]=result
            strategies.append({**{k:v for k,v in result.items() if k not in ('trades','curve')},'id':sid,'name':name,'market':'1X2',
                               'snapshot':'pre','period':period,'stressed_roi':stress['roi'],
                               'note':'Regla fija; referencia excluye la casa del precio. Snapshot periódico sin simultaneidad verificada. Auditoría ya inspeccionada.'})
    try:
        from engine.research_backtest import simulate_score_market
        for market,label in [('totals25','Más / menos 2,5 goles'),('asian_handicap','Hándicap asiático')]:
            result=simulate_score_market(audit,market=market,policy=cfg['research_policy'])
            strategies.append({**{k:v for k,v in result.items() if k not in ('trades','curve')},'id':market,'name':label,'market':market,
                               'snapshot':'pre','period':'audit','stressed_roi':result.get('stressed_roi'),
                               'note':'Modelo estructural y liquidación específica; no se eligió el mercado por su ROI.'})
    except ImportError:pass
    market_scores=market_evaluation(audit)
    try:
        from engine.stat_markets import run_stat_market_evaluation
        market_scores.extend(run_stat_market_evaluation(rows,audit_start=cfg['retrospective_audit_start']))
    except ImportError:pass
    catalog=json.loads((ROOT/'config/market_catalog_v2.json').read_text())
    for item in catalog.get('markets',[]):
        if item['key'] in ('first_half','half_time_result','first_half_result','halftime_result','half_time_totals','half_time_btts'):
            item['model_status']='exploratory_period_specific_model'
            item['requirements']=list(item.get('requirements',[]))+['Modelo de primer tiempo disponible sólo para fútbol; otros deportes y períodos requieren su propio entrenamiento.']
        if item['key'] in ('corners_total','total_corners','corners_totals'):
            item['model_status']='exploratory_count_model'
        if item['key'] in ('cards_total','total_cards','cards_totals'):
            item['model_status']='exploratory_count_model'
            item['requirements']=list(item.get('requirements',[]))+['El modelo actual sólo usa amarillas; no equivale a puntos por tarjetas ni combina rojas.']
    diagnosis=json.loads((ROOT/'data/analysis/v1_diagnosis.json').read_text())
    generated=datetime.now(timezone.utc).isoformat()
    model_digest=hashlib.sha256(json.dumps({'spec':selected_spec,'policy':cfg},sort_keys=True).encode())
    for source_path in sorted((ROOT/'engine').glob('*.py'))+[p for p in [(ROOT/'backend/scanner.py'),(ROOT/'backend/providers.py'),(ROOT/'backend/prospective.py')] if p.exists()]:
        model_digest.update(source_path.read_bytes())
    model_hash=model_digest.hexdigest()
    registry_path=ROOT/'data/runtime/prospective'/f'{model_hash}.json'
    from datetime import date,timedelta
    from zoneinfo import ZoneInfo
    first_allowed=(datetime.now(timezone.utc).astimezone(ZoneInfo('America/Argentina/Salta')).date()+timedelta(days=1)).isoformat()
    prospective=json.loads(registry_path.read_text()) if registry_path.exists() else {'start':max(cfg['prospective_start'],first_allowed),'events':0,'registered_at':generated,'model_hash':model_hash}
    if not registry_path.exists():atomic(registry_path,prospective)
    research={'meta':{'version':'0.2.0','generated_at':generated,'data_fingerprint':fingerprint(),'quote_inputs':quote_archive},'protocol':cfg,
              'diagnosis':diagnosis,'selection':selection,'comparison':comparison,'strategies':strategies,
              'market_evaluations':market_scores,'catalog':catalog,
              'improvement':{'raw_v2_vs_v1':paired_ci(valid,'v1','structural'),'selected_vs_v1':paired_ci(valid,'v1','selected'),
                             'selected_vs_market':paired_ci(valid,'consensus_power','selected')},
              'recommendation':{'status':'research_only','live_enabled':False,
                                  'reason':'Auditoría retrospectiva ya inspeccionada; pendientes datos prospectivos, precio ejecutable y reglas verificadas.'},
              'prospective':prospective}
    availability=ROOT/'data/analysis/market_availability.json'
    if availability.exists():research['market_availability']=json.loads(availability.read_text())
    atomic(ROOT/'data/analysis/research_v2.json',research)
    atomic(ROOT/'app/data/research.json',research)
    # Export a compact integration bundle, keeping raw bookmaker history local.
    main_result=portfolios[('consensus_best','audit')]
    trades={t['id']:t for t in main_result.get('trades',[])}
    integration=[]
    for r in audit:
        p=r['prediction'];trade=trades.get(r['id'])
        integration.append({'id':r['id'],'date':r['date'],'sport':'football','league':r['league'],
                            'home_team':r['home_team'],'away_team':r['away_team'],'home_score':r['home_score'],'away_score':r['away_score'],
                            'prediction':p,'probabilities':r['selected'],'reference':r['consensus_power'],
                            'reference_books':r['reference_books'],'trade':trade,
                            'original_odds':[r.get('home_odds'),r.get('draw_odds'),r.get('away_odds')],
                            'original_odds_source':r.get('odds_source')})
    path=ROOT/'data/analysis/integration_v2.jsonl'
    with path.open('w') as f:
        for r in integration:f.write(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n')
    atomic(ROOT/'data/analysis/portfolio_v2.json',main_result)
    atomic(ROOT/'data/runtime/prospective_v2.json',research['prospective'])
    print(json.dumps({'selected':spec,'audit_matches':len(audit),'paired_matches':len(valid),'strategies':[{k:s.get(k) for k in ('id','period','bets','roi','profit','max_drawdown')} for s in strategies],
                      'market_evaluations':len(market_scores)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
