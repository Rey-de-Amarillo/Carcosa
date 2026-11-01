# Valor esperado condicional: goles 2.5

**Este modelo no identificó una ventaja monetaria en la prueba final.**

Se comparan Over y Under con sus cuotas Bet365 del mismo partido. Fórmula: `EV = p × cuota − 1`.
Historial: 238,854 resultados; 156,684 partidos con ambas cuotas. Entrenamiento: 92,373; validación: 29,841; prueba final 2022–2026: 34,470.

Variables: ataque y defensa del equipo y rival, localía, promedio de liga, forma exponencial, goles de cada equipo, descanso, cantidad de partidos previos y cuota previa. Todos los partidos del mismo día se predicen antes de cargar sus resultados.

Modelo elegido por log loss de validación: ridge 1000. Calibración ajustada exclusivamente en 2018–2021. Umbral principal 3% de EV estimado; una apuesta por partido y una unidad fija.

| EV mínimo | Apuestas | Ganancia por 100 apostados | IC 95% por mes | Con cuota 1% menor |
|---|---:|---:|---:|---:|
| 0% | 441 | -9.166 | [-17.937, +0.123] | -10.074 |
| 3% | 9 | -57.111 | [-100.000, +5.333] | -57.540 |
| 5% | 0 | — | — | — |

## Calidad probabilística final

| Modelo | Log loss | Brier |
|---|---:|---:|
| model_calibrated | 0.676483 | 0.241817 |
| model_uncalibrated | 0.676431 | 0.241793 |
| market_no_vig | 0.676502 | 0.241823 |

Mejora media de log loss frente al mercado: +0.00001870; IC 95% por mes [-0.00026865, +0.00029367].

## Resultado por año del umbral principal

| Año | Apuestas | ROI |
|---|---:|---:|
| 2022 | 2 | -12.000% |
| 2023 | 2 | -100.000% |
| 2024 | 1 | -100.000% |
| 2025 | 1 | -100.000% |
| 2026 | 3 | -30.000% |

## Ejemplo de cálculo histórico

2026-02-28: Kelty Hearts–Inverness C, under 2.5 @ 2.1. `p` estimada 49.480%; equilibrio 47.619%; EV estimado +3.907%; resultado ganó. Es un ejemplo mecánico, no una selección actual.

Código y predicciones completas quedan en `scripts/research_goal_ev.py` y `data/analysis/research_goal_ev_predictions.jsonl`. El JSON de auditoría registra fechas, coeficientes, protocolo y hashes. No se dispone de cuota de cierre identificada.
