# Números de fútbol · Bet365 · 30/10/2026

Chelsea–Manchester United, 31/10/2026. Cuotas leídas directamente en Bet365 Argentina: jugadores a las 13:09:59 y primer tiempo a las 13:11:29, hora de Salta. Estadísticas individuales: API oficial FPL, ocho fechas de la temporada actual y temporada anterior como referencia.

## La cuenta de una apuesta simple

Para probabilidad p, cuota decimal c e importe A: **beneficio esperado = A × (p × c − 1)**. Equilibrio: **p = 1/c** o **c = 1/p**. Las dos cuotas de un Sí/No permiten medir el margen de precios, pero la probabilidad real requiere una estimación contrastada.

## Jugadores · gol en cualquier momento

Probabilidad condicionada a 75–90 minutos, mediante Gamma–Poisson regularizado con la temporada anterior. Los extremos son escenarios de minutos, no un intervalo de confianza. El modelo aún no ajusta rival, posición actual ni la cadena de Suplente+.

| Jugador | Gol en partidos de titular esta temporada | Cuota real | Acierto mínimo para equilibrio | p con 75–90 min | EV base por $100 |
|---|---:|---:|---:|---:|---:|
| Cole Palmer | 2/8 | 2,37 | 42,19% | 26,14%–30,37% | $-38,05 a $-28,03 |
| Pedro Neto | 2/7 | 3,60 | 27,78% | 20,64%–24,13% | $-25,68 a $-13,13 |
| Bryan Mbeumo | 4/8 | 3,40 | 29,41% | 29,72%–34,38% | $1,03 a $16,89 |
| Bruno Fernandes | 1/7 | 4,00 | 25,00% | 23,67%–27,57% | $-5,34 a $10,27 |
| Morgan Rogers | 4/8 | 3,00 | 33,33% | 26,58%–30,86% | $-20,27 a $-7,42 |

Mbeumo: 4 goles en 720 minutos actuales; 11 en 2.611 minutos de la temporada anterior. Previo fijo de 900 minutos. α = 4 + 900 × 11/2611 = 7.791651; β = 720 + 900 = 1620. Probabilidad predictiva para m minutos: **p = 1 − (β/(β+m))^α**. A 90 minutos: p = 34,38%; EV = p × 3,40 − 1 = 16,89%.

El intervalo del modelo para su probabilidad a 90 minutos es 16,77%–54,35%; incluye el equilibrio de 29,41%. Es un candidato numérico, con rentabilidad pendiente de demostrar. Las cuotas muestran Suplente+: el EV de la tasa personal no valora la oferta completa.

## Primer tiempo · apuestas concretas

El modelo usa goles reales del primer tiempo, con datos anteriores a cada partido. Para el evento binario de que haya algún gol, el calibrador se ajustó sólo en 2022–23 y se congeló antes de evaluar 2024+.

| Selección | Cuota Bet365 | p del modelo | EV por $100 |
|---|---:|---:|---:|
| Chelsea gana al descanso | 2,30 | 36,31% | $-16,48 |
| Empate al descanso | 2,40 | 40,76% | $-2,17 |
| Man United gana al descanso | 4,33 | 22,92% | $-0,74 |
| Ambos marcan en primer tiempo · Sí | 3,75 | 20,76% | $-22,16 |
| Ambos marcan en primer tiempo · No | 1,25 | 79,24% | $-0,95 |
| Man United marca en primer tiempo · Sí | 2,25 | 40,16% | $-9,63 |
| Man United marca en primer tiempo · No | 1,57 | 59,84% | $-6,06 |
| 0–0 al descanso · modelo original | 3,50 | 28,91% | $1,19 |
| 0–0 al descanso · recalibrado | 3,50 | 28,05% | $-1,84 |

Algún gol antes del descanso: p recalibrada = 71,95%; cuota de equilibrio = 1,39. La cuota Bet365 para Sí no pudo leerse; no se sustituye con otra casa. El 0–0 a 3,50 queda por debajo de su cuota de equilibrio recalibrada, 3,5655.

## Ganancia histórica usando cuotas Bet365 registradas

Partidos entre 01/01/2024 y 29/10/2026, una unidad constante por apuesta. Son liquidaciones retrospectivas con columnas B365 anteriores al cierre; falta hora exacta del precio. Este tramo ya había sido inspeccionado.

| Apuesta fija | n | Acierto | ROI histórico |
|---|---:|---:|---:|
| Local 1X2 | 9986 | 43,19% | -9,60% |
| Empate 1X2 | 9986 | 25,53% | -3,40% |
| Visitante 1X2 | 9986 | 31,28% | -11,11% |
| Más de 2,5 goles | 9986 | 53,99% | -3,49% |
| Menos de 2,5 goles | 9986 | 46,01% | -7,21% |
| Local al hándicap asiático B365 de cada partido | 9962 | 45,16% | -5,22% |

Política de modelo: elegir el lado de Más/Menos 2,5 con mayor EV estimado, sólo cuando EV ≥3%; una unidad por posición. Calibrador ajustado sólo en 2022–23 mediante log loss.

| Método | Apuestas | Acierto de selecciones | ROI histórico | IC95% ROI |
|---|---:|---:|---:|---:|
| Modelo original | 4664 | 45,54% | -5,73% | -8,92% a -2,63% |
| Modelo recalibrado | 4354 | 41,66% | -7,00% | -10,50% a -3,65% |

El original estimaba EV medio +10,85%, pero realizó −5,73%. La recalibración mejora Brier/log loss en los mismos partidos, y la política termina con −7,00% de ROI sobre una selección distinta. No identifica todavía una estrategia rentable.

Fuentes: [cuotas Bet365 Argentina](https://www.bet365.bet.ar/?#/AC/B1/C1/D8/E202201732/F3/G40/), [estadísticas oficiales FPL](https://fantasy.premierleague.com/api/bootstrap-static/), CSV Football-Data.co.uk conservados localmente. Entradas y cálculos completos: data/analysis/player_numbers.json, first_half_numbers.json y bet365_numbers.json.

Reproducción: `python3 scripts/player_numbers.py --offline`; `python3 scripts/first_half_numbers.py --as-of-date 2026-10-30`; `python3 scripts/bet365_numbers.py`. La app y el modelo v2 operativo no se cambiaron en este análisis.
