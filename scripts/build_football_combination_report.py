#!/usr/bin/env python3
"""Combine auditable portfolio searches; keep theoretical and executed profit distinct."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/analysis/football_combination_research.json'
REPORT = ROOT / 'COMBINACIONES_FUTBOL.md'


def check_team_under_match_over(under_line, over_line, q_under, q_over, stake_under, stake_over):
    """Complete-domain coverage proof: away goals <= total goals.

    Both lines must be the same half-integer. If team Under loses, that team
    alone exceeds the match Over line. No cap on football scores is imposed.
    """
    if under_line != over_line or Decimal(str(under_line)) % 1 != Decimal('.5'):
        raise ValueError('This proof requires identical half-goal lines')
    q1,q2,s1,s2 = map(lambda x:Decimal(str(x)), (q_under,q_over,stake_under,stake_over))
    if min(q1,q2)<=1 or min(s1,s2)<0:
        raise ValueError('Invalid odds or stake')
    budget=s1+s2
    payouts=[s1*q1,s2*q2,s1*q1+s2*q2]
    return {'budget':str(budget), 'team_under_only_return':str(payouts[0]),
            'match_over_only_return':str(payouts[1]), 'both_return':str(payouts[2]),
            'minimum_return':str(min(payouts)), 'minimum_profit':str(min(payouts)-budget),
            'inverse_sum':str(1/q1+1/q2),
            'unbounded_domain_proof':'Team goals never exceed match total: team under loses => match over wins; match over loses => team under wins.'}


def check_opposite_integer_handicap(home_line, away_line, q_home, q_away, stake_home, stake_away):
    if home_line != -away_line or float(home_line).is_integer() is False:
        raise ValueError('Opposite integer handicaps required')
    q1,q2,s1,s2=map(lambda x:Decimal(str(x)),(q_home,q_away,stake_home,stake_away))
    budget=s1+s2
    return {'budget':str(budget), 'home_side_wins_profit':str(s1*q1-budget),
            'away_side_wins_profit':str(s2*q2-budget), 'push_profit':'0',
            'minimum_profit':str(min(s1*q1-budget,s2*q2-budget,Decimal(0)))}


def main():
    config_path=ROOT/'config/football_portfolio_research.json'
    config=json.loads(config_path.read_text())
    data={}; hashes={}
    for spec in config['searches']:
        path=ROOT/spec['result']
        raw=path.read_bytes()
        data[path.stem]=json.loads(raw)
        hashes[spec['result']]=hashlib.sha256(raw).hexdigest()
    root=data['football_score_combinations']; sg=data['sgodds_portfolio_search']; bc=data['betcity_crossmarket_search']; op=data['oddspapi_temporal_arb']
    raw_example=next(x for x in bc['positive_portfolios_top100_strict_binary']
                     if {l['source_key'] for l in x['legs']}=={'P2__TOTALS__UNDER(2.5)','TOTALS__OVER(2.5)'})
    legs={x['source_key']:x for x in raw_example['legs']}
    a,b=legs['P2__TOTALS__UNDER(2.5)'],legs['TOTALS__OVER(2.5)']
    arithmetic=check_team_under_match_over(2.5,2.5,a['decimal_odds'],b['decimal_odds'],a['rounded_stake_per_100'],b['rounded_stake_per_100'])
    weak=[]; strict=[]
    for fresh in op['freshness_summary'].values():
        weak.extend(fresh.get('top_push_covers',[])); strict.extend(fresh.get('top',[]))
    best_weak=max(weak,key=lambda x:x.get('worst_nonpush_profit_on_100_rounded',-1)) if weak else None
    longest_weak=max(weak,key=lambda x:x.get('interval_seconds',0)) if weak else None
    strongest_strict=max(strict,key=lambda x:x.get('worst_profit_on_100_rounded',-1)) if strict else None
    result={
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'config_sha256':hashlib.sha256(config_path.read_bytes()).hexdigest(),
        'input_result_hashes':hashes,
        'quarantine':json.loads((ROOT/config['quarantine']).read_text()),
        'score_templates':{'match_rows':root['matches'],'complete_cover_evaluations':root['template_evaluations'],
                           'positive_covers':root['positive_complete_covers'],
                           'score_settleable_selections':len(root['all_score_settleable_field_backtests']),
                           'positive_aggregate_historical_roi_fields':root['positive_full_roi_fields']},
        'sgodds_all_market_lp':{'match_rows':sg['source_match_rows'],'quotes':sg['quoted_price_count'],
                               'market_families':len(sg['market_family_counts']),'statuses':sg['statuses'],
                               'without_mutable_line_statuses':sg['without_mutable_lines_statuses']},
        'betcity_lp':{'source_rows':bc['source_rows'],'counts':bc['counts'],
                      'btts_quarantined':bc['btts_label_quarantined']},
        'betcity_example':{'source_witness':raw_example,'independent_decimal_arithmetic':arithmetic,
                           'status':'historical conditional mathematical cover; original market labels and simultaneous executable quotes unverified'},
        'oddspapi':{'fixture_count':op['fixture_count'],'catalog_market_count':op['catalog_market_count'],
                    'source_market_ids_contributing':len(set(mid for f in op['fixtures'] for mid in f['supported_source_market_ids'])),
                    'complete_group_count':sum(f['group_count'] for f in op['fixtures']),
                    'freshness_counts':{k:{j:v for j,v in x.items() if j not in ('top','top_at_least_5s','top_push_covers','top_closest_nonpositive_partition')} for k,x in op['freshness_summary'].items()},
                    'best_weak_recorded_example':best_weak,'longest_weak_recorded_example':longest_weak,
                    'strongest_strict_recorded_example':strongest_strict,
                    'verified_executable_opportunities':op['verified_executable_opportunities']},
        'overall_verified_executed_or_executable_profit_opportunities':0,
        'scope_limits':config['scope_limits'],
    }
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    lines=['# Combinaciones de apuestas de fútbol','',
      '**Hay combinaciones matemáticamente positivas en registros históricos. Ninguna quedó confirmada como ejecutable actualmente.**','',
      '## Ejemplo de goles, sin estimar probabilidades','',
      'Registro atribuido a Betcity, Ruvu Stars/JKT–Simba, 05/05/2025. Se excluyó el mercado BTTS por una etiqueta sospechosa; este ejemplo no lo usa.','',
      '| Apuesta separada | Cuota registrada | Importe sobre 100 |','|---|---:|---:|',
      f"| Visitante: menos de 2,5 goles | {a['decimal_odds']} | {a['rounded_stake_per_100']} |",
      f"| Partido: más de 2,5 goles | {b['decimal_odds']} | {b['rounded_stake_per_100']} |",'',
      f"Si el visitante marca 0, 1 o 2, la primera devuelve {arithmetic['team_under_only_return']}. Si marca 3 o más, necesariamente el total supera 2,5 y la segunda devuelve {arithmetic['match_over_only_return']}. Pueden ganar ambas, devolviendo {arithmetic['both_return']}.",
      f"**Mínimo matemático: {arithmetic['minimum_return']} por 100; beneficio mínimo {arithmetic['minimum_profit']}.** La desigualdad cubre cualquier marcador, sin cortar la cola de goles.",'',
      '**Condición pendiente:** que esas etiquetas, líneas y cuotas fueran correctas y aceptables al mismo tiempo. El archivo no demuestra esa disponibilidad; no es una recomendación actual.','',
      '## Contraste con precios históricos fechados de dos casas','',
      'En Manchester City–Ipswich del 17/10/2026 aparece Manchester City −1 al descanso, DraftKings 2,20, frente a Ipswich +1, Pinnacle 1,892. Repartiendo 46,24 y 53,76: City gana el primer tiempo por 2+ => +1,728; empata/pierde => +1,71392; gana por exactamente 1 => devolución total.',
      'La mejor pareja dura 0,672 segundos en el registro. Un tramo de 49,507 segundos con cuota Pinnacle 1,854 conserva al menos +0,606 por 100 fuera de la devolución. DraftKings estaba marcado activo aunque su último cambio era anterior en diez minutos; el límite de esa casa es nulo en la fuente, no ilimitado.',
      'Existe además una cobertura estricta de unos +0,023 por 100 con resultado/doble oportunidad, vulnerable a costos y dependiente de una cotización anterior. Los detalles de ventanas, límites y precios están en el informe específico.','',
      '## Alcance examinado','',
      '| Búsqueda | Cobertura y resultado |','|---|---|',
      f"| Marcadores/goles/empates/HTFT explícitos | {root['template_evaluations']} coberturas en {root['matches']} filas; {root['positive_complete_covers']} positivas. Incluye otros marcadores y colas. |",
      f"| Liquidación histórica por marcador | {len(root['all_score_settleable_field_backtests'])} selecciones; {len(root['positive_full_roi_fields'])} ROI nominales positivos en toda la muestra. No se inventa el orden del primer gol. |",
      f"| SGodds, cartera general conjunta | {sg['source_match_rows']} filas, {sg['quoted_price_count']} precios, {len(sg['market_family_counts'])} familias; {sg['statuses'].get('recorded_price_positive_complete_payoff_verified',0)} positivos sólo al admitir líneas variables no verificadas. Sin ellas, certificados negativos en todas las filas. |",
      f"| Betcity, cartera general | {bc['counts']['eligible_rows_scanned']} filas, {bc['counts']['positive_under_assumed_asian_refund_rules']} positivos con devoluciones supuestas y {bc['counts']['positive_using_only_strict_binary_markets']} con mercados binarios. Todos históricos y condicionales; BTTS en cuarentena. |",
      f"| OddsPapi, comparación temporal | {result['oddspapi']['complete_group_count']} grupos, {result['oddspapi']['source_market_ids_contributing']}/{op['catalog_market_count']} IDs, 5 partidos. Cero positivos con ambas cuotas de hasta 60 o 300 segundos; aparecen cruces con cotizaciones anteriores aún marcadas activas. |",'',
      'Las carteras usan apuestas separadas, con pesos elegidos para el peor resultado. No se multiplican probabilidades de sucesos correlacionados ni se inventan pagos BetBuilder. Las apuestas de jugadores, córners, tarjetas, goles, períodos, resultados y conteos se comparan sólo cuando los contratos forman coberturas completas reconocidas.',
      'El LP admite cualquier número de posiciones de compra dentro de las selecciones disponibles. Los certificados negativos y la verificación de colas están documentados por fuente. No equivale a probar todos los mercados de todas las casas del mundo.','',
      '## Datos excluidos o condicionados','',
      '- Betcity `BOTH_TEAMS_TO_SCORE__YES`: orientación inversa frente a resultados; cuarentena predeterminada, sin cambiarlo silenciosamente a NO.',
      '- SGodds: sus 82 positivos dependen de líneas modificables; la propia fuente advierte posibles desacoples entre línea y precio histórico.',
      '- Cotización antigua no significa automáticamente retirada, pero un estado activo del proveedor tampoco demuestra aceptación simultánea en cada casa.',
      '- No se trataron listas superpuestas de goleadores como resultados excluyentes. Una cola de marcadores sin cubrir invalida la cobertura.',
      '- La muestra Betfair contiene último precio negociado, no una oferta disponible; el pequeño snapshot SharpAPI no se mezcló como si fuera un tablero temporal único.',
      '- Las reglas de anulación, participación del jugador, prórroga, límites y comisiones deben coincidir antes de convertir un cálculo en una operación.',
      '', '## Código y reproducción','']
    for spec in config['searches']:
        lines.append(f"- [{spec['script']}]({spec['script']}) → [{spec['report']}]({spec['report']}).")
    lines.extend(['','Protocolo: `config/football_portfolio_research.json`. Cuarentena: `config/football_market_quarantine.json`.',
                  'Dependencias para LP: `requirements-research.txt` (NumPy/SciPy). Los scripts también aceptan `--scipy-path`; en esta ejecución se usó `/tmp/football-portfolio-scipy`.',
                  'Auditoría integrada, ejemplos, conteos y hashes: `data/analysis/football_combination_research.json`.',
                  'Regenerar este resumen: `python3 scripts/build_football_combination_report.py`.','',
                  'Fuentes de reglas: [Singapore Pools](https://www.singaporepools.com.sg/en/rules/Pages/pdf/football-betting-game-rules.pdf), [SGodds](https://sgodds.com/help), [DraftKings](https://sportsbook.draftkings.com/help/how-to-bet/soccer-betting-guide), [Pinnacle](https://www.pinnacle.com/en/future/betting-rules).'])
    REPORT.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'report':str(REPORT),'score_cover_count':root['template_evaluations'],
                      'betcity_strict_candidates':bc['counts']['positive_using_only_strict_binary_markets'],
                      'independent_example_check':arithmetic,'verified_executable':0},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
