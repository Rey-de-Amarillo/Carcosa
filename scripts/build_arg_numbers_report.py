"""A concise numerical report plus a full table, from frozen offline analyses."""
from pathlib import Path
import hashlib
import json
from engine.stat_markets import count_over_probability
ROOT=Path(__file__).resolve().parents[1]

def main():
    load=lambda name:json.loads((ROOT/'data/analysis'/name).read_text())
    raw=load('bet365_arg_quotes.json'); bets=load('arg_betting_numbers.json'); counts=load('arg_count_empirics.json'); players=load('arg_player_empirics.json')
    sha=hashlib.sha256((ROOT/'data/analysis/bet365_arg_quotes.json').read_bytes()).hexdigest()
    assert sha in bets['source_sha256'].values()
    assert players['source_quotes']['sha256']==sha
    assert any(s['sha256']==sha for s in counts['sources'])
    fmt=lambda x,d=2:'—' if x is None else f'{x:.{d}f}'.replace('.',',')
    pct=lambda x:'—' if x is None else fmt(x*100)+'%'
    amount=lambda x:'—' if x is None else ('+' if x>0 else '−' if x<0 else '')+'$'+fmt(abs(x))
    h=counts['corner_hypothesis'];w=h['windows']['season_2026'];mu=w['lambda_arithmetic_mean_of_two_means'];alpha=w['nb_common_alpha_mom'];odds=h['odds']
    scenarios=[]
    for factor in [1,1.1,1.2,1.3,1.4,1.5]:
        row={'rate_factor':factor,'expected_corners':mu*factor}
        for label,a in [('poisson',0),('negative_binomial',alpha)]:
            prob=1-count_over_probability(mu*factor,5.5,a)
            row[label]={'probability_under':prob,'ev_per_100':100*(prob*odds-1)}
        scenarios.append(row)
    thresholds={}
    for label,a in [('poisson',0),('negative_binomial',alpha)]:
        lo,hi=0.,30.
        for _ in range(100):
            mid=(lo+hi)/2
            if 1-count_over_probability(mid,5.5,a)>1/odds:lo=mid
            else:hi=mid
        thresholds[label]={'break_even_mean':(lo+hi)/2,'relative_increase_from_base':(lo+hi)/(2*mu)-1}
    stress={'source_quote_sha256':sha,'source_count_analysis_sha256':hashlib.sha256((ROOT/'data/analysis/arg_count_empirics.json').read_bytes()).hexdigest(),'hypothesis':'Gimnasia LP under5.5 own full-time corners','odds':odds,'assumption':'Sensitivity to an externally shifted mean. NB alpha held fixed; this does not estimate the probability of that shift.','scenarios':scenarios,'break_even_mean':thresholds,'executed_bets':0}
    (ROOT/'data/analysis/arg_corner_stress.json').write_text(json.dumps(stress,ensure_ascii=False,indent=2)+'\n')
    lines=['# Estudiantes Río Cuarto–Gimnasia LP · números de Bet365','',
        'Partido:30/10/2026,19:00 de Salta. Captura13:36:46–14:08:24:12 secciones inspeccionadas,485 lecturas de precios y467 selecciones sintácticas distintas. Hay repeticiones/equivalencias; no son485 oportunidades independientes. Algunas secciones abiertas mostraron etiquetas sin precios.','',
        '## Candidato principal: Gimnasia menos de5,5 córners a1,80','',
        '| Referencia | Partidos | Media de córners | Cumplió menos de6 |','|---|---:|---:|---:|',
        f"| Gimnasia visitante, córners propios | {w['gimnasia_away_for']['n']} | {fmt(w['gimnasia_away_for']['mean'],3)} | 14/17 |",
        f"| Visitantes contra Río Cuarto local | {w['rio_cuarto_home_against']['n']} | {fmt(w['rio_cuarto_home_against']['mean'],3)} | 10/15 |",'',
        f'No se cuentan esos15 partidos como partidos de Gimnasia. La media del modelo es λ=({fmt(w["gimnasia_away_for"]["mean"],4)}+{fmt(w["rio_cuarto_home_against"]["mean"],4)})/2={fmt(mu,4)}. La ponderación50/50 es un supuesto exploratorio.','',
        '| Modelo | p(0–5 córners) | Cuota de equilibrio | EV por $100 a1,80 |','|---|---:|---:|---:|']
    for key,label in [('poisson','Poisson'),('negative_binomial','Binomial negativa')]:
        z=w[key];lines.append(f"| {label} | {pct(z['probability_under_5_5'])} | {fmt(z['fair_decimal_odds'],4)} | {amount(z['ev_per_100'])} |")
    lines+=['',f"**EV=$100×(p×1,80−1).** Con p={pct(w['negative_binomial']['probability_under_5_5'])}, el modelo da {amount(w['negative_binomial']['ev_per_100'])} esperados por100. Una apuesta individual devuelve beneficio+80 si acierta o−100 si falla.",'',
        'Poisson usa P(C≤5)=exp(−λ)×Σ(k=0..5)λ^k/k!. Binomial negativa admite varianza μ+αμ²; α='+fmt(alpha,6)+'.', '',
        'El remuestreo de20.000 muestras, separado por las dos cohortes, da EV binomial-negativo de '+amount(w['bootstrap']['intervals_95_percentile']['nb_ev_per_100'][0])+' a '+amount(w['bootstrap']['intervals_95_percentile']['nb_ev_per_100'][1])+' por100. Es incertidumbre del modelo bajo estacionariedad; no cubre cambios tácticos, alineación, selección entre muchas cuotas ni demuestra rentabilidad futura.','',
        '| Cambio de media | Córners esperados | EV Poisson por100 | EV binomial negativa por100 |','|---|---:|---:|---:|']
    for row in scenarios:lines.append(f"| +{fmt((row['rate_factor']-1)*100,0)}% | {fmt(row['expected_corners'])} | {amount(row['poisson']['ev_per_100'])} | {amount(row['negative_binomial']['ev_per_100'])} |")
    lines+=['',f"El equilibrio Poisson se alcanza en λ={fmt(thresholds['poisson']['break_even_mean'],4)}: una subida de {pct(thresholds['poisson']['relative_increase_from_base'])} sobre la media estimada. El mercado exige p>55,56% a cuota1,80. La cuota se reconfirmó a las14:08:24 de Salta.",'',
        '## Goles y combinaciones concretas','',
        'Son EV de la distribución conjunta de goles, no ROI histórico observado. Se conservan las mismas políticas y dos ventanas históricas; no se multiplican marginales de selecciones correlacionadas.','',
        '| Selección | Cuota | EV central por100 | Peor ventana | Percentil2,5 de EV remuestreado |','|---|---:|---:|---:|---:|']
    selected=[]
    for market,selection,line in [('totals','under',2.25),('totals','under',2.5),('totals','under',3.5),('btts','no',None)]:
        selected.append(next(q for q in bets['quotes'] if q.get('status')=='modelled_final_score_contract' and q['contract']['market']==market and q['contract']['selection']==selection and q['contract'].get('line')==line))
    selected.append(next(q for q in bets['quotes'] if q['id']=='q0184'))
    labels=['Menos de2,25 asiático','Menos de2,5','Menos de3,5','Ambos marcan:No','Menos de2,5 + Ambos marcan:No']
    for label,q in zip(labels,selected):lines.append(f"| {label} | {fmt(q['odds'])} | {amount(q['ev_per_100_staked'])} | {amount(q['minimum_ev_across_methods_per_100'])} | {amount(q.get('parameter_bootstrap_sensitivity',{}).get('ev_per_100_p025'))} |")
    combo=selected[-1]
    lines+=['',f"Menos de2,5 + BTTSNo a2,00 gana con00,10,01,20o02. Su probabilidad es la suma de esas cinco celdas: {pct(combo['probability'])}. El EV central es {amount(combo['ev_per_100_staked'])} por100, pero cambia de signo con la otra ventana. Ninguna ofertaFT de goles conserva EV positivo en el percentil2,5 de los remuestreos.",'',
        'En Under2,25 a1,80, con100 apostados:0–1goles deja+80; exactamente2goles deja+40;3omás deja−100. Fórmula:EV=0,80P(G≤1)+0,40P(G=2)−P(G≥3). Su probabilidad de media ganancia no permite usar1/p como cuota justa.','',
        '## Boosts y diferencias de precio','',
        '- Gimnasia gana + mayoría estricta de córners +3omásgoles a7,00:se dio3/32 veces2026 (9,38%), frente a14,29% necesario. Sensibilidad usando esa frecuencia y precioactual:−34,38por100. Se interpreta Over2Goals como3omás, sin tratarlo como Asian2 conpush; la regla exacta de la combinación sigue sin verificar.',
        '- Auzmendi1+rematealarco + Torres1+rematealarco + Gimnasia gana a6,50:3/26 con ambos participantes;2/9 siendo ambos titulares. Cada condición requiere su propia muestra; faltan alineaciones y valoración de Suplente+.',
        '- Boost9,00:ambos equipos2+córners en cada mitad + BTTS. Las61 fichas no tienen córners por mitad:probabilidad/EV sin estimar.',
        '- Menos de0,5goles paga8,00;0–0paga7,50;empate+BTTSNo paga7,50. Bajo iguales reglas de período/liquidación,8,00 devuelve50másporcada100 si acierta que7,50. Es mejorprecio para igual marcador; no una cobertura de beneficio seguro.','',
        '## Alcance y procedencia','',
        'El motor de goles usa6.445 partidos argentinos. La validaciónFT tiene1.499 partidos; OU/BTTS no superan claramente la frecuencia base. Los datos ampliados son61 partidos únicos2026, con30 deRíoCuarto y32deGimnasia y un encuentro compartido. El test por mitades es exploratorio:41eventos.59de64jugadores se identificaron por coincidencias exactas/aliases explícitos; cinco quedan sin correspondencia.',
        'La auditoría de pagos no encontró coberturas positivas en su búsqueda acotada de hasta tres patas. No prueba ausencia universal de arbitraje. Capturas, reglas y límites no están confirmados como contratación simultánea; no se realizaron apuestas.',
        'Fuentes: [Bet365, partido y córners](https://www.bet365.bet.ar/#/AC/B1/C1/D8/E202426204/F3/I5/), [ESPN, ficha oficial del evento](https://site.api.espn.com/apis/site/v2/sports/soccer/arg.1/summary?event=401841655). Se conservaron las61 fichas históricas, CSV originales y hashes localmente.','',
        'Archivos completos: data/analysis/bet365_arg_quotes.json, arg_betting_numbers.json, arg_count_empirics.json, arg_player_empirics.json y arg_corner_stress.json. Hash de captura:'+sha+'.','',
        '## Tabla de todos los contratos con modelo de goles','',
        'p=retorno positivo, incluidas medias ganancias; EVpor100 neto. Mitades y combinaciones de mitades están marcadas como exploratorias. Los campos vacíos de otros contratos se conservan enJSON con motivo, sin inventar probabilidades.','',
        '| ID | Contrato | Cuota | p | EV por100 | Método/estado |','|---|---|---:|---:|---:|---|']
    for q in bets['quotes']:
        if q.get('probability') is None:continue
        contract=q['contract'];details=[q['label'],contract['selection'],contract.get('team'),('línea'+str(contract['line'])) if contract.get('line') is not None else None,('rango'+str(contract['min_goals'])+'–'+str(contract.get('max_goals'))) if contract.get('min_goals') is not None else None,str(contract.get('score')) if contract.get('score') is not None else None,contract['period']]
        label=' · '.join(str(v) for v in details if v is not None).replace('|','/')
        lines.append(f"| {q['id']} | {label} | {fmt(q['odds'])} | {pct(q['probability'])} | {amount(q['ev_per_100_staked'])} | {q['status']} |")
    target=ROOT/'NUMEROS_ESTUDIANTES_GIMNASIA.md';target.write_text('\n'.join(lines)+'\n');print(target)

if __name__=='__main__':main()
