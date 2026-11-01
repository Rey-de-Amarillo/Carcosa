"""Overlay the validated research protocol on the app, preserving the v1 baseline."""
import gzip
import hashlib
import json
from pathlib import Path

VERSION='0.2.0'


def integrate_report(base,root,history_output):
    root=Path(root)
    research=json.loads((root/'data/analysis/research_v2.json').read_text())
    portfolio=json.loads((root/'data/analysis/portfolio_v2.json').read_text())
    spec=research['selection']['selected']
    with (root/'data/analysis/integration_v2.jsonl').open() as f:records=list(map(json.loads,f))
    decisions=[]
    for r in records:
        trade=r.get('trade');probabilities=r.get('probabilities');raw=r['prediction']
        index=trade['selection_index'] if trade else max(range(3),key=probabilities.__getitem__) if probabilities else max(range(3),key=lambda i:[raw['home'],raw['draw'],raw['away']][i])
        p=trade['model_probability'] if trade else probabilities[index] if probabilities else None
        ref=trade.get('reference_p') if trade else r['reference'][index] if r.get('reference') else None
        odds=trade['odds'] if trade else None
        reasons=['Revisión retrospectiva ya inspeccionada; no es validación independiente ni una orden actual.',
                 'Selección de modelo por log loss en 2022–2023; no se eligió por el ROI de esta revisión.']
        if trade:
            reasons.extend(['Precio histórico de una casa identificada; referencia excluye esa casa.',
                            'Sin timestamp individual ni simultaneidad comprobada; beneficio hipotético.'])
        elif probabilities is None:reasons.append('Falta referencia multicasa para aplicar el modelo seleccionado. El cálculo estructural se conserva aparte.')
        else:reasons.append('La selección no cumplió EV mínimo, rango de precio o número de referencias de la política fija.')
        selection=r['home_team'] if index==0 else 'Empate' if index==1 else r['away_team']
        outcome='won' if trade and trade.get('won') else 'lost' if trade else 'no_bet'
        source=trade.get('source') if trade else None
        source_url=source.get('url') if isinstance(source,dict) else source
        decisions.append({'id':r['id'],'event_id':r['id'],'model_version':VERSION,'sport':'football',
                          'event':r['home_team']+' — '+r['away_team'],'date':r['date'],'league':r['league'],
                          'home_team':r['home_team'],'away_team':r['away_team'],'home_score':r['home_score'],'away_score':r['away_score'],
                          'market':'1X2','selection':selection,'selection_index':index,'probability':p,'model_probability':p,
                          'structural_probability':[raw['home'],raw['draw'],raw['away']][index],
                          'market_probability':ref,'odds':odds,'ev':p*odds-1 if p is not None and odds else None,
                          'edge':p-ref if p is not None and ref is not None else None,
                          'stake':trade['stake'] if trade else 0,'profit':trade['pnl'] if trade else 0,'pnl':trade['pnl'] if trade else 0,
                          'outcome':outcome,'status':'paper_settled' if trade else 'abstain','reasons':reasons,
                          'settlement_target':'regulation_time_1x2','model':'Consenso multicasa power (aporte estructural 0%)' if spec['structural_weight']==0 else 'Ensamble v2',
                          'sample_size':raw.get('sample_size'),'effective_sample_size':raw.get('effective_sample_size'),
                          'training_as_of':raw.get('training_max_date'),'reference_books':trade.get('reference_books',[]) if trade else [],
                          'probability_source':'leave_book_out_market_consensus' if trade and spec['structural_weight']==0 else 'multibook_consensus' if probabilities is not None else 'unavailable',
                          'structural_weight':spec['structural_weight'],'odds_source':trade.get('book') if trade else None,
                          'bookmaker':trade.get('book') if trade else None,'source':source_url,'odds_snapshot':'pre' if trade else None,
                          'quote_timestamp':None,'is_simulation':True,'is_live':False,'mode':'historical_research','execution_enabled':False,
                          'explanation':{'probability':'Referencia de precios multicasa sin margen; no probabilidad verdadera conocida.',
                                         'summary':'La validación eligió consenso puro para 1X2. El modelo estructural mejora pero no agrega precisión suficiente frente a este consenso.' if spec['structural_weight']==0 else 'Mezcla probabilística seleccionada sólo en el período de validación.',
                                         'ev_formula':f'{p:.6f} × {odds:.4f} − 1 = {p*odds-1:.6f}' if p is not None and odds else None}})
    # Keep the unaffected NBA/MLB historical analyses, with their original version.
    baseline_history=root/'data/analysis/baseline_v1/decisions.jsonl'
    if baseline_history.exists():
        with baseline_history.open() as f:
            decisions.extend(r for r in map(json.loads,f) if r.get('sport')!='football')
    decisions.sort(key=lambda r:(r['date'],r['id']),reverse=True)
    destination=Path(history_output);destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.tmp')
    with temporary.open('w') as f:
        for row in decisions:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    temporary.replace(destination)
    selected_metric=next(x for x in research['comparison'] if x['id']=='selected' and x['period']=='audit')
    market_metric=next(x for x in research['comparison'] if x['id']=='consensus_power' and x['period']=='audit')
    baseline_report=root/'data/analysis/baseline_v1/report.json'
    old=json.loads(baseline_report.read_text()) if baseline_report.exists() else base
    base['baseline_v1']={'overview':old['overview'],'backtest':{k:old['backtest'].get(k) for k in ['bets','roi','profit','max_drawdown','initial_bankroll','final_bankroll']},
                         'note':'Referencia anterior conservada. Cambiaron fuente de precios, población, política y modelo; los ROI no aíslan una sola causa.'}
    base['meta'].update({'version':VERSION,'model_version':VERSION,'generated_at':research['meta']['generated_at'],
                         'model_selection':spec['id'],'structural_weight':spec['structural_weight']})
    base['overview'].update({'paper_bets':portfolio['bets'],'paper_profit':portfolio['profit'],'paper_roi':portfolio['roi'],
                            'bankroll':portfolio['final_bankroll'],'max_drawdown':portfolio['max_drawdown'],
                            'evaluated_matches':len(records),'decisions':len(decisions),'abstentions':sum(r['stake']==0 for r in decisions),
                            'brier':selected_metric['brier'],'log_loss':selected_metric['log_loss'],'market_brier':market_metric['brier'],
                            'ready_for_live':False,'model_status':'prospective_validation_pending'})
    base['backtest']={k:v for k,v in portfolio.items() if k!='trades'}
    base['backtest'].update({'bankroll':portfolio['final_bankroll'],'net_profit':portfolio['profit'],
                             'metrics':selected_metric,'model_metrics':selected_metric,'market_metrics':market_metric,'baseline':market_metric,
                             'paired_comparison':research['improvement']['selected_vs_market'],
                             'sample':len(records),'sample_size':len(records),'period':{'test_start':'2024-01-01','test_end':'2026-10-30'},
                             'strategy':'Referencia multicasa excluye la casa objetivo; EV ≥3%, precio1,2–5, Kelly10%, tope0,25%evento/2%fecha.',
                             'status':'retrospective_previously_inspected','validated_edge':False,
                             'gate_reason':research['recommendation']['reason'],
                             'stressed_roi':next(x['stressed_roi'] for x in research['strategies'] if x['id']=='consensus_best' and x['period']=='audit'),
                             'calibration':_calibration(records),'other_markets':research['market_evaluations'],
                             'selection_period_result':next(x for x in research['strategies'] if x['id']=='consensus_best' and x['period']=='selection')})
    base['decisions']=decisions[:240]
    traded=[r for r in decisions if r['stake']>0]
    present={r['id'] for r in base['decisions']}
    base['decisions'].extend(r for r in traded[:40] if r['id'] not in present)
    base['decision_history']={'total':len(decisions),'displayed':len(base['decisions']),'exported':True,'format':'JSONL'}
    base['calibration']=base['backtest']['calibration']
    base['model'].update({'version':VERSION,'name':'Consenso multicasa power' if spec['structural_weight']==0 else 'Ensamble v2',
                          'ready_for_live':False,'structural_weight':spec['structural_weight'],'live_block_reason':research['recommendation']['reason']})
    for sport in base['sports']:
        if sport['sport']=='football':
            sport.update({'model':'V2: consenso power; modelo de goles ajustado por adversario separado',
                          'metrics':selected_metric,'market_metrics':market_metric,'calibration':base['calibration'],
                          'period':{'train_start':'2012-01-01','validation_start':'2022-01-01','test_start':'2024-01-01','test_end':'2026-10-30'}})
    base['research']={'url':'/data/research.json','version':VERSION,'prospective':research['prospective'],
                      'catalog_markets':len(research['catalog']['markets']),'market_evaluations':len(research['market_evaluations'])}
    base['predictions']=[]
    for r in sorted(records,key=lambda x:(x['date'],x['id']),reverse=True)[:8]:
        p=r['prediction'];selected=r.get('probabilities')
        markets=[]
        markets.append({'market':'1X2 · consenso v2','status':'research','actionable':False,
                        'selections':[{'selection':label,'probability':selected[i] if selected else None} for i,label in enumerate(['Local','Empate','Visitante'])]})
        for name,options in [('1X2 · estructural v2',[('Local','home'),('Empate','draw'),('Visitante','away')]),
                             ('Total 2,5 goles',[('Más de 2,5','over25'),('Menos de 2,5','under25')]),
                             ('Ambos marcan',[('Sí','btts_yes'),('No','btts_no')])]:
            markets.append({'market':name,'status':'research','actionable':False,'selections':[{'selection':label,'probability':p[key]} for label,key in options]})
        base['predictions'].append({'id':r['id'],'event':r['home_team']+' — '+r['away_team'],'date':r['date'],
                                    'league':r['league'],'sport':'football','historical':True,'is_live':False,
                                    'model':'Modelo estructural v2 y consenso como referencias distintas',
                                    'sample_size':p.get('sample_size'),'markets':markets})
    base['market_catalog']=research['catalog']
    base['alerts']=[{'type':'research','message':research['recommendation']['reason']}]
    return base


def _calibration(records):
    from collections import defaultdict
    buckets=defaultdict(list)
    for row in records:
        p=row.get('probabilities')
        if p is None:continue
        index=max(range(3),key=p.__getitem__)
        actual=0 if row['home_score']>row['away_score'] else 1 if row['home_score']==row['away_score'] else 2
        buckets[min(9,int(p[index]*10))].append((p[index],index==actual))
    return [{'count':len(v),'predicted':sum(x[0] for x in v)/len(v),'observed':sum(x[1] for x in v)/len(v)} for _,v in sorted(buckets.items())]
