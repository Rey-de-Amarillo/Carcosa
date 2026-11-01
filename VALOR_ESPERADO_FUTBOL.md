# Valor esperado positivo en fútbol

**Objetivo: ganar en promedio al repetir, aceptando apuestas perdidas.**

`EV = p × cuota − 1`. No hace falta ganar la mayoría: con p=30% y cuota3,50, el EV es +5% aunque se pierda el70% de las apuestas.

## Regla candidata: ventaja incluso con la referencia más conservadora

1. Quitar el margen de cada casa de referencia con el método power.
2. Excluir la casa donde se haría la apuesta y exigir al menos tres casas distintas.
3. Para ese resultado, tomar la menor probabilidad estimada entre las referencias.
4. Aceptar sólo `p_conservadora × cuota_ofrecida − 1 ≥ 0,03`, cuotas1,20–5,00 y una selección por partido.

| Período | Apuestas | Beneficio por100 apostados | EV estimado medio |
|---|---:|---:|---:|
| 2018–2021 | 219 | 10.22 | 5.91 |
| 2022–2026 | 76 | 16.82 | 6.34 |

Aciertos posteriores: 39/76; cuota1% inferior, mismas selecciones: ROI 15.65%.
El intervalo mensual95% del ROI posterior es [-10.57%, 43.07%]. Año2025: -37.76%. Se conserva la incertidumbre y el año negativo junto con la señal positiva.

La menor probabilidad entre casas es una envolvente conservadora de modelos; no es un límite inferior estadístico de la probabilidad real. La hipótesis para repetir es que esas estimaciones sigan calibradas.

## Ejemplo seleccionado por EV mediano, sin elegirlo por su resultado

St Johnstone–Aberdeen (2022-05-11), resultado 0 (0=local,1=empate,2=visitante), casa PS: cuota 3.71, p de referencia más conservadora 28.17821%.
`0.28178205 × 3.71 − 1 = +4.54114%`. Ese es el EV estimado por apuesta, no la ganancia garantizada de cada intento.

## Más variables probadas

- Modelo de goles: 22 variables previas de equipo/rival, ataque/defensa, localía, forma exponencial, descanso, liga y cuotas; 34470 partidos finales. EV mínimo3%: 9 apuestas, ROI -57.11%.
- Modelo1X2: Elo propio, forma5/10, goles, localía, rival, descanso, liga y precios; 46805 partidos finales. No superó3% de EV; aceptando cualquier EV estimado positivo: 571 apuestas, ROI -0.30%.
- Primer tiempo: historial causal y cuotas, cero goles frente a cualquier gol (también compra sintética por primeras anotaciones excluyentes), 280 partidos. EV mínimo3%: una selección; no se considera una estimación estable por sí sola.
- Referencias: comparación de media, mínimo y media menos una desviación; todas se publican, también Bet365 fija y los resultados negativos. No se seleccionaron equipos, casas o años tras ver cuál ganaba.

## Repetición y crecimiento

Con p y cuota constantes, `E[beneficio de n apuestas]=n×importe×EV`. Con cuotas/estimaciones variables se suman los EV individuales. La fórmula es condicional a las probabilidades declaradas, no una demostración de que el modelo conozca las probabilidades verdaderas.
La correlación modifica la variación del dinero; no crea esperanza positiva al mezclar apuestas que individualmente tienen esperanza negativa. Cada BetBuilder con precio propio exige calcular su probabilidad conjunta.
Para una fracción f del capital, `g=p·log(1+f·(cuota−1))+(1−p)·log(1−f)`. Apostar de más puede dar crecimiento logarítmico negativo incluso con EV positivo. Se conserva un diagnóstico matemático, sin activar apuestas automáticas.

## Código y trazabilidad

- [scripts/research_goal_ev.py](scripts/research_goal_ev.py) → [VALOR_ESPERADO_GOLES.md](VALOR_ESPERADO_GOLES.md).
- [scripts/research_result_ev.py](scripts/research_result_ev.py) → [VALOR_ESPERADO_RESULTADOS.md](VALOR_ESPERADO_RESULTADOS.md).
- [scripts/research_first_half_ev.py](scripts/research_first_half_ev.py) → [VALOR_ESPERADO_PRIMER_TIEMPO.md](VALOR_ESPERADO_PRIMER_TIEMPO.md).
- [scripts/research_market_reference_ev.py](scripts/research_market_reference_ev.py) → [VALOR_ESPERADO_CUOTAS.md](VALOR_ESPERADO_CUOTAS.md).
- [scripts/research_robust_reference_ev.py](scripts/research_robust_reference_ev.py) → [VALOR_ESPERADO_REFERENCIAS_ROBUSTAS.md](VALOR_ESPERADO_REFERENCIAS_ROBUSTAS.md).

Regla congelada para investigación: `config/football_ev_research.json`.
Fórmulas de EV, repetición, carteras correlacionadas y crecimiento: `scripts/long_run_ev.py`.
Auditoría integrada: `data/analysis/football_expected_value_research.json`. Todas las decisiones se conservan en los ledgers por experimento.
La regla robusta es una hipótesis exploratoria posterior al análisis de la media; no se presenta como una validación prospectiva nueva.

Referencia matemática de crecimiento: [Kelly1956](https://onlinelibrary.wiley.com/doi/abs/10.1002/j.1538-7305.1956.tb03809.x).
