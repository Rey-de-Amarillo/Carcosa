# Valor esperado de resultados 1X2

La fórmula por cada peso apostado es `EV = probabilidad × cuota decimal − 1`.
Se prueba una apuesta por partido, la de mayor EV estimado, con cuotas Bet365 de 1,20 a 5,00.

Se reconstruyeron Elo, forma de puntos y goles, localía, rival, descanso y tasas de liga con fechas anteriores. Archivo: 238,854 partidos con resultado; 226,815 con cuotas e historial mínimo.

Calidad de cuotas: se excluyen grupos 1X2 cuyo margen implícito sea negativo o supere 25%; sus marcadores sí actualizan el historial posterior. Se apartaron 10 grupos del archivo, antes de estimar los modelos.

Entrenamiento 2000–2017; elección por logloss 2018–2021; reentrenamiento hasta 2021; evaluación final 2022–2026. No se seleccionó el modelo por rentabilidad.

| Modelo | Logloss validación |
|---|---:|
| market_no_vig | 1.002881 |
| price_calibration | 1.002358 |
| odds_prior_team_weak_penalty | 1.002847 |
| odds_prior_team_strong_penalty | 1.002567 |

Modelo seleccionado: **price_calibration**.

| Umbral EV estimado | Apuestas | Beneficio por 100 apostados | Intervalo 95% por meses |
|---|---:|---:|---:|
| 0% | 571 | -0.30 | [-5.30, 5.03] |
| 3% | 0 | — | — |
| 5% | 0 | — | — |

Aceptando cualquier EV estimado positivo: 571 apuestas, EV predicho promedio 0.48%, retorno real -0.30%. Con cuotas 1% inferiores: -1.30%.
Probabilidad predicha media 73.82%; acierto observado 72.85%; umbral de equilibrio medio 73.46%.

**Conclusión:** estas variables no sostuvieron una ventaja positiva en la política principal.

Los coeficientes, predicciones seleccionadas, calibración y auditoría están en `data/analysis/research_result_ev.json` y `research_result_ev_trades.jsonl`. El código puede recalcularlo todo.
