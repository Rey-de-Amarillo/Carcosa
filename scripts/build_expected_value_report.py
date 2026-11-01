#!/usr/bin/env python3
"""Integrated EV research: conditional estimates, causal variables and repeats."""
from datetime import datetime,timezone
from decimal import Decimal
import hashlib,json,math
from pathlib import Path
try:
    from .long_run_ev import expected_log_growth,expected_unit_profit,kelly_fraction
except ImportError:
    from long_run_ev import expected_log_growth,expected_unit_profit,kelly_fraction

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/analysis/football_expected_value_research.json'
REPORT=ROOT/'VALOR_ESPERADO_FUTBOL.md'


def main():
    config_path=ROOT/'config/football_ev_research.json';config=json.loads(config_path.read_text())
    inputs={};hashes={}
    for spec in config['models']:
        p=ROOT/spec['result'];raw=p.read_bytes();inputs[spec['id']]=json.loads(raw)
        hashes[spec['result']]=hashlib.sha256(raw).hexdigest()
    robust=inputs['robust_market_reference'];r=robust['results']
    trades_path=ROOT/'data/analysis/research_robust_reference_ev.trades.jsonl'
    ledgers={'validation_all_books_minimum':[],'test_all_books_minimum':[]}
    for line in trades_path.open():
        t=json.loads(line)
        if t['scenario'] in ledgers:ledgers[t['scenario']].append(t)
    direct={}
    for name,rows in ledgers.items():
        if len({t['id'] for t in rows})!=len(rows):raise ValueError('Repeated event stake')
        for t in rows:
            if len(t['references'])<3 or t['book'] in t['references']:raise ValueError('Invalid reference set')
            if abs(t['ev']-expected_unit_profit(t['probability'],t['odds']))>1e-12:raise ArithmeticError('Incorrect EV')
            if t['ev']<.03-1e-12:raise ValueError('Policy threshold violated')
        returned=sum((Decimal(str(t['odds'])) for t in rows if t['won']),Decimal(0))
        profit=returned-len(rows)
        if abs(float(profit)-r[name]['profit_units'])>1e-8:raise ArithmeticError('Ledger P&L mismatch')
        direct[name]={'n':len(rows),'returned_units':str(returned),'profit_units':str(profit)}
    final=sorted(ledgers['test_all_books_minimum'],key=lambda t:(t['ev'],t['date'],t['id']))
    example=final[len(final)//2] # median estimated EV, not a winning-result filter
    f=config['long_run_math']['diagnostic_fraction_of_bankroll']
    log_diagnostic={
        'fraction':f,
        'mean_expected_log_growth_per_bet_under_reference_probabilities':sum(expected_log_growth(t['probability'],t['odds'],f) for t in final)/len(final),
        'mean_realized_log_return_in_sample':sum(math.log1p(f*(t['odds']*t['won']-1)) for t in final)/len(final),
        'scope':'Single-bet mathematical diagnostic at fixed fraction; not a funded simultaneous-trade simulation.'}
    result={'generated_at':datetime.now(timezone.utc).isoformat(),
            'config':config,'input_sha256':hashes,'config_sha256':hashlib.sha256(config_path.read_bytes()).hexdigest(),
            'ledger_sha256':hashlib.sha256(trades_path.read_bytes()).hexdigest(),
            'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'candidate_validation':r['validation_all_books_minimum'],'candidate_later_period':r['test_all_books_minimum'],
            'candidate_money_crosscheck':direct,'representative_example_by_median_estimated_ev':example,
            'single_bet_log_growth_diagnostic':log_diagnostic,
            'all_reference_policies':r,
            'other_models':{'goals':inputs['conditional_goals']['final_strategies'],
                            '1x2':inputs['conditional_1x2']['final_thresholds'],
                            'first_half':inputs['conditional_first_half']['final_strategies']},
            'interpretation':{'objective':'Positive expected profit under repetition, not winning every bet.',
                              'mathematical_condition':'E[net per unit]=p*odds-1 >0; repeated expected profit sums the individual expected profits.',
                              'model_condition':'Reference probability envelope is a set of estimates, not an established true lower probability.',
                              'research_status':'Exploratory candidate; robustness policy added after earlier mean-reference results were inspected.',
                              'no_claim_of_proven_infinite_real_profit':True}}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    val,test=result['candidate_validation'],result['candidate_later_period']
    goals=inputs['conditional_goals'];outcomes=inputs['conditional_1x2'];ht=inputs['conditional_first_half']
    lines=['# Valor esperado positivo en fútbol','',
      '**Objetivo: ganar en promedio al repetir, aceptando apuestas perdidas.**','',
      '`EV = p × cuota − 1`. No hace falta ganar la mayoría: con p=30% y cuota3,50, el EV es +5% aunque se pierda el70% de las apuestas.','',
      '## Regla candidata: ventaja incluso con la referencia más conservadora','',
      '1. Quitar el margen de cada casa de referencia con el método power.',
      '2. Excluir la casa donde se haría la apuesta y exigir al menos tres casas distintas.',
      '3. Para ese resultado, tomar la menor probabilidad estimada entre las referencias.',
      '4. Aceptar sólo `p_conservadora × cuota_ofrecida − 1 ≥ 0,03`, cuotas1,20–5,00 y una selección por partido.','',
      '| Período | Apuestas | Beneficio por100 apostados | EV estimado medio |','|---|---:|---:|---:|',
      f"| 2018–2021 | {val['n']} | {100*val['roi']:.2f} | {100*val['predicted_ev']:.2f} |",
      f"| 2022–2026 | {test['n']} | {100*test['roi']:.2f} | {100*test['predicted_ev']:.2f} |",'',
      f"Aciertos posteriores: {test['wins']}/{test['n']}; cuota1% inferior, mismas selecciones: ROI {100*test['roi_price_haircut_1pct']:.2f}%.",
      f"El intervalo mensual95% del ROI posterior es [{100*test['monthly_block_bootstrap_roi_95'][0]:.2f}%, {100*test['monthly_block_bootstrap_roi_95'][1]:.2f}%]. Año2025: {100*test['by_year']['2025']['roi']:.2f}%. Se conserva la incertidumbre y el año negativo junto con la señal positiva.",
      '', 'La menor probabilidad entre casas es una envolvente conservadora de modelos; no es un límite inferior estadístico de la probabilidad real. La hipótesis para repetir es que esas estimaciones sigan calibradas.','',
      '## Ejemplo seleccionado por EV mediano, sin elegirlo por su resultado','',
      f"{example['home_team']}–{example['away_team']} ({example['date']}), resultado {example['side']} (0=local,1=empate,2=visitante), casa {example['book']}: cuota {example['odds']}, p de referencia más conservadora {100*example['probability']:.5f}%.",
      f"`{example['probability']:.8f} × {example['odds']} − 1 = +{100*example['ev']:.5f}%`. Ese es el EV estimado por apuesta, no la ganancia garantizada de cada intento.",
      '', '## Más variables probadas','',
      f"- Modelo de goles: {len(goals['protocol']['features'])} variables previas de equipo/rival, ataque/defensa, localía, forma exponencial, descanso, liga y cuotas; {goals['split_counts']['final']} partidos finales. EV mínimo3%: {goals['final_strategies']['0.03']['bets']} apuestas, ROI {100*goals['final_strategies']['0.03']['roi']:.2f}%.",
      f"- Modelo1X2: Elo propio, forma5/10, goles, localía, rival, descanso, liga y precios; {outcomes['split_counts']['test']} partidos finales. No superó3% de EV; aceptando cualquier EV estimado positivo: {outcomes['final_thresholds']['0.0']['bets']} apuestas, ROI {100*outcomes['final_thresholds']['0.0']['roi']:.2f}%.",
      f"- Primer tiempo: historial causal y cuotas, cero goles frente a cualquier gol (también compra sintética por primeras anotaciones excluyentes), {ht['split_counts']['SG_final']} partidos. EV mínimo3%: una selección; no se considera una estimación estable por sí sola.",
      '- Referencias: comparación de media, mínimo y media menos una desviación; todas se publican, también Bet365 fija y los resultados negativos. No se seleccionaron equipos, casas o años tras ver cuál ganaba.','',
      '## Repetición y crecimiento','',
      'Con p y cuota constantes, `E[beneficio de n apuestas]=n×importe×EV`. Con cuotas/estimaciones variables se suman los EV individuales. La fórmula es condicional a las probabilidades declaradas, no una demostración de que el modelo conozca las probabilidades verdaderas.',
      'La correlación modifica la variación del dinero; no crea esperanza positiva al mezclar apuestas que individualmente tienen esperanza negativa. Cada BetBuilder con precio propio exige calcular su probabilidad conjunta.',
      'Para una fracción f del capital, `g=p·log(1+f·(cuota−1))+(1−p)·log(1−f)`. Apostar de más puede dar crecimiento logarítmico negativo incluso con EV positivo. Se conserva un diagnóstico matemático, sin activar apuestas automáticas.','',
      '## Código y trazabilidad','']
    for spec in config['models']:lines.append(f"- [{spec['script']}]({spec['script']}) → [{spec['report']}]({spec['report']}).")
    lines.extend(['', 'Regla congelada para investigación: `config/football_ev_research.json`.',
      'Fórmulas de EV, repetición, carteras correlacionadas y crecimiento: `scripts/long_run_ev.py`.',
      'Auditoría integrada: `data/analysis/football_expected_value_research.json`. Todas las decisiones se conservan en los ledgers por experimento.',
      'La regla robusta es una hipótesis exploratoria posterior al análisis de la media; no se presenta como una validación prospectiva nueva.','',
      'Referencia matemática de crecimiento: [Kelly1956](https://onlinelibrary.wiley.com/doi/abs/10.1002/j.1538-7305.1956.tb03809.x).'])
    REPORT.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'report':str(REPORT),'validation':direct['validation_all_books_minimum'],
                      'later':direct['test_all_books_minimum'],'model_mean_ev':test['predicted_ev'],
                      'median_ev_example':example,'log_growth':log_diagnostic},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
