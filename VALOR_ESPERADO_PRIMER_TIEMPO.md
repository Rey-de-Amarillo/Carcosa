# Valor esperado: gol en el primer tiempo

Modelo con 9,870 resultados EPL, 22 variables y cuotas reales. Entrenamiento hasta 2017; selección 2018–2021; calibración 2022–29/12/2025; prueba de precios SGodds: 280 partidos desde 30/12/2025 hasta octubre de 2026.

Se compara cero goles —el mejor precio entre 0–0, total cero, nadie marca primero y Under 0.5— contra un gol o más. También se construye un gol o más repartiendo la unidad entre local y visitante como primer equipo en marcar: cuota efectiva `1 / (1/cuota_local + 1/cuota_visitante)`. Las posiciones son excluyentes y cubren cualquier primer gol, sin multiplicar probabilidades.

| EV mínimo | Apuestas | Ganancia por 100 apostados | IC 95% por fecha | Cuotas 1% menores |
|---|---:|---:|---:|---:|
| 0% | 7 | -2.714 | [-60.571, +36.714] | -3.687 |
| 3% | 1 | +38.000 | — (una fecha) | +36.620 |
| 5% | 1 | +38.000 | — (una fecha) | +36.620 |

Ejemplo histórico: 2026-04-12, Crystal Palace–Newcastle, Htou_01 @ 1.3800. Probabilidad 76.588%; equilibrio 72.464%; `EV = p × cuota − 1 = +5.691%`.

Las variables usan goles del primer tiempo: ataque/defensa, rival, localía, forma de últimos cinco partidos y exponencial, descanso, promedio de liga y cuotas FT. Se predice toda la fecha antes de incorporar sus resultados. Los 280 marcadores HT y FT coinciden con Football-Data tras corregir únicamente cinco alias y la fecha de huso horario.

Código: `scripts/research_first_half_ev.py`. Auditoría y posiciones: `data/analysis/research_first_half_ev.json`; predicciones y contratos: `data/analysis/research_first_half_ev_predictions.jsonl`. La cohorte SGodds es retrospectiva y ya apareció en estudios anteriores; no es una prueba prospectiva.
