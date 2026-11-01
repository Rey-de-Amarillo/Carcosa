#!/usr/bin/env python3
"""Publish a dated, price-only football audit without changing the frozen model."""
from __future__ import annotations
import collections
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.market_audit import audit_event
from engine.quote_costs import summarize_costs
from engine.markets import settle_score, net_return
from scripts.build_sport_comparison import build_comparison

ALIASES = {'h2h':'1x2','h2h_3_way':'1x2','spreads':'asian_handicap','alternate_spreads':'asian_handicap','alternate_totals':'totals','alternate_team_totals':'team_totals','draw_no_bet':'dnb'}
SUPPORTED = {'1x2','asian_handicap','totals','team_totals','dnb','double_chance','btts','correct_score','odd_even'}

def normalize_quote(row, index):
    if row.get('sport') != 'football':
        return None, 'other_sport'
    if row.get('exchange') or row.get('dfs') or row.get('market_key','').endswith('_lay'):
        return None, 'exchange_or_dfs_costs_unverified'
    key = row.get('market_key','')
    # Only regulation goal-score contracts, with separately disclosed assumed rules.
    if re.search(r'_(h[12]|q\d|p\d|s\d|ot|ex_ot|rt)$', key):
        return None, 'period_specific_requires_separate_audit'
    market = ALIASES.get(key,key)
    if market not in SUPPORTED:
        return None, 'unsupported_goal_contract'
    home,away = row['home_team'],row['away_team']
    raw = row.get('selection','')
    selection = {home:'home',away:'away','Draw':'draw','Over':'over','Under':'under','Yes':'yes','No':'no','Odd':'odd','Even':'even'}.get(raw)
    if market == 'double_chance':
        selection = {f'{home} or Draw':'home_draw',f'{away} or Draw':'draw_away',f'{home} or {away}':'home_away',f'{away} or {home}':'home_away'}.get(raw)
    score = None
    if market == 'correct_score':
        pattern = re.fullmatch(re.escape(home)+r':(\d+)\|'+re.escape(away)+r':(\d+)', raw)
        if not pattern:
            return None, 'unknown_correct_score_tail_or_syntax'
        score = [int(pattern[1]),int(pattern[2])]
        if max(score)>6:
            return None, 'score_search_bound'
        selection = 'score'
    if selection is None:
        return None, 'unknown_selection'
    line = row.get('line')
    if market in ('totals','team_totals') and (line is None or not 0<=float(line)<=6):
        return None, 'goal_line_search_bound'
    if market == 'asian_handicap' and (line is None or abs(float(line))>3):
        return None, 'handicap_search_bound'
    team = None
    if market == 'team_totals':
        team = {home:'home',away:'away'}.get(row.get('description'))
        if team is None:
            return None, 'unknown_team_participant'
    return {'quote_id':str(index),'event_id':row['event_id'],'market':market,'selection':selection,
            'line':line,'score':score,'team':team,'odds':row['odds'],'bookmaker':row['bookmaker'],
            'last_update':row['last_update'],'period':'regulation_90m_assumed',
            'statistic':'goals','settlement_basis':'whole_period_score',
            'settlement_rules':'ASSUMED_common_regulation_goals_NOT_VERIFIED',
            'verified_rules':False,'available_limit':None,'source':row}, None


def build():
    sample_path=ROOT/'data/analysis/football_audit_sample.json'
    sample=json.loads(sample_path.read_text())
    sample_sha=hashlib.sha256(sample_path.read_bytes()).hexdigest()
    inventory=json.loads((ROOT/'config/football_market_inventory.json').read_text())
    rows=sample['fresh_quotes']
    costs=summarize_costs(rows)
    costs['regions_observed']=sorted(set(row['region'] for row in rows))
    costs['region_policy']='Muestra multirregión EU/UK/US; cada contrato conserva la captura completa más reciente. Este agregado no es una comparación restringida a EU. El panel balanceado filtra EU antes de construir los mercados completos.'
    grouped=collections.defaultdict(list)
    excluded=collections.Counter()
    for i,row in enumerate(rows):
        q,reason=normalize_quote(row,i)
        if reason:
            excluded[reason]+=1
        else:
            grouped[(row['event_id'],row['region'])].append(q)
    output={'summary':{},'candidates':[],'relations':[],'rejected':[],'coverage':[],'event_summaries':[]}
    summed=collections.Counter()
    capped=False
    event_names={r['event_id']:r['event'] for r in rows}
    for (event,region),quotes in sorted(grouped.items()):
        result=audit_event(quotes,now=sample['meta']['generated_at'],max_cross_quotes=18,max_relation_quotes=48)
        summary=result['summary']
        output['event_summaries'].append({'event_id':event,'event':event_names[event],'region':region,**summary})
        for key in ('input_quotes','accepted_quotes','retained_best_prices','collapsed_duplicate_prices','theoretical_price_candidates','synchronized_positive_contract_candidates','relations','searched_pairs','searched_triples'):
            summed[key]+=summary.get(key,0)
        capped |= summary['cross_search_capped'] or summary['relation_search_capped']
        for key in ('candidates','relations','rejected','coverage'):
            output[key].extend([{**item,'event':event_names[event],'region':region} for item in result.get(key,[])])
        print(f"{event_names[event]} [{region}]: {summary['accepted_quotes']} quotes, {summary['theoretical_price_candidates']} candidates",flush=True)
    output['candidates'].sort(key=lambda c:(not c['relation_only'],c['minimum_net_return_per_capital']),reverse=True)
    for candidate in output['candidates']:
        # An adverse-price scenario, holding the original capital fractions fixed.
        # Use the same certified representative state space as the original audit.
        bound=candidate['state_space']['max_representative_score']
        candidate['minimum_return_after_1pct_odds_haircut']=min(
            sum(leg['capital_fraction']*net_return(settle_score(h,a,leg['market'],leg['selection'],
                line=leg.get('line'),score=leg.get('score'),team=leg.get('team')),leg['odds']*.99)
                for leg in candidate['legs'])
            for h in range(bound+1) for a in range(bound+1))
        candidate['minimum_return_after_0_5pct_capital_cost']=candidate['minimum_net_return_per_capital']-.005
    output['summary']={**summed,'event_region_groups':len(grouped),'verified_arbitrages':0,'executable':False,
                       'search_exhaustive':False,'cross_search_capped':capped,'maximum_cross_market_legs':3,
                       'excluded_rows_by_reason':dict(excluded),'audit_clock':sample['meta']['generated_at'],
                       'assumed_rules_only':True,'external_void_states_included':False}
    output['summary']['candidate_events']=len(set(c['event_id'] for c in output['candidates']))
    output['summary']['positive_after_1pct_odds_haircut']=sum(c['minimum_return_after_1pct_odds_haircut']>1e-9 for c in output['candidates'])
    output['summary']['positive_after_0_5pct_capital_cost']=sum(c['minimum_return_after_0_5pct_capital_cost']>1e-9 for c in output['candidates'])
    meta={**sample['meta'],'built_at':datetime.now(timezone.utc).isoformat(),
          'source_sha256':sample_sha,
          **{k:inventory['meta'][k] for k in ('market_count','family_count','source_count','brand_count')},
          'quotes':len(rows),'football_quotes':sum(r['sport']=='football' for r in rows),
          'board_count':len(costs['boards']),'football_board_count':sum(b['sport']=='football' for b in costs['boards']),
          'sports_count':len(costs['by_sport']),'available_provider_keys':len(set(k for d in sample['discoveries'] for k in d['available_keys'])),
          'executed_bets':0,'provider_quota_at_capture':sample['provider_status'].get('provider_quota',{}),
          'sample_is_current_execution_quote':False}
    conclusions=[
        'No se demuestra una ventaja rentable inherente a un deporte ni a una familia de apuesta. Se necesitan precios, reglas, costes y probabilidades del contrato concreto.',
        'El margen de una casa y la pérdida proporcional de referencia describen precios; no son ROI realizado ni beneficio esperado demostrado.',
        f"Las {len(output['candidates'])} carteras candidatas corresponden a {output['summary']['candidate_events']} partidos de la captura; pueden compartir exposición. Conservan retorno mínimo positivo {output['summary']['positive_after_0_5pct_capital_cost']} con coste fijo del 0,5% del capital y {output['summary']['positive_after_1pct_odds_haircut']} con un recorte adverso del 1% en las cuotas, sin reajustar importes. Son escenarios separados, no costes reales estimados.",
        'La comparación entre deportes se limita a mercados de ganador de partido, región EU y casas comunes. Cambian ligas, eventos, cantidad de resultados y reglas de prórroga; la muestra no establece una superioridad causal.',
        'La auditoría de pagos usa una captura fechada y asume reglas comunes de goles reglamentarios sin verificarlas por casa. Cualquier cobertura es teórica: límites, disponibilidad simultánea, anulaciones, impuestos y contratación no están comprobados.',
        'La búsqueda compara particiones completas y carteras de hasta tres patas con poda explícita. No agota todas las combinaciones, líneas, períodos, promociones ni ofertas regionales.',
        'Props de jugadores, tarjetas, córners y primer gol necesitan datos y modelos propios; no se derivan automáticamente del marcador final ni de probabilidades independientes.',
        f"El inventario abarca {inventory['meta']['brand_count']} marcas; {inventory['meta']['status_counts'].get('verified_rules_not_live_price',0)} entradas tienen reglas verificadas y {len(inventory['markets'])-inventory['meta']['status_counts'].get('verified_rules_not_live_price',0)} requieren confirmar vigencia u oferta. No prueba disponibilidad para una cuenta argentina.",
        'Se mantiene el modelo v2 registrado y su validación prospectiva. Esta auditoría de precios no retoca parámetros ni convierte la revisión retrospectiva ya observada en validación nueva.'
    ]
    report={'schema_version':1,'meta':meta,'inventory':inventory,'costs':costs,'price_audit':output,
            'discoveries':sample['discoveries'],'conclusions':conclusions,
            'sports_framework':json.loads((ROOT/'config/sport_advantage_framework.json').read_text())}
    report['sport_comparison']=build_comparison(sample,region='eu',horizon_days=7,
        source_path='data/analysis/football_audit_sample.json',source_sha256=sample_sha)
    (ROOT/'data/analysis/football_sport_comparison.json').write_text(
        json.dumps(report['sport_comparison'],ensure_ascii=False,indent=2)+'\n')
    for path in (ROOT/'data/analysis/football_audit.json',ROOT/'app/data/football_audit.json'):
        path.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({'meta':meta,'summary':output['summary']},ensure_ascii=False,indent=2))

if __name__=='__main__':
    build()
