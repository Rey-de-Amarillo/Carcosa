# Una apuesta: ambos equipos marcan, Sí

**La prueba no mostró una ventaja rentable.**

| Simulación de una unidad por partido | Partidos | Aciertos | Resultado por cada 100 apostados |
|---|---:|---:|---:|
| Muestra completa | 2945 | 1728 (58.68%) | -5.90 |
| Fechas posteriores desde 2026-08-20 | 983 | 584 (59.41%) | -7.37 |

Importe simulado: 2945 unidades. Devuelto: 2771.11. Pérdida: 173.89.
Fórmula exacta: `suma(acierto × cuota individual − 1)`; acierto exige que ambos marcadores finales sean mayores que cero.

La calibración ajustada sólo con los partidos anteriores seleccionó **0** apuestas posteriores con `p × cuota − 1 > 0`.
Cobertura de Sí y No: 0 sumas inversas menores que 1 entre 3059 pares registrados, incluidos pendientes.

Son precios históricos de [SGodds](https://sgodds.com/football/data), no operaciones ejecutadas. No se optimizaron equipos, ligas o rangos de cuota.
La comparación cronológica es retrospectiva; no descarta otras reglas. Se conserva esta prueba negativa junto con la anterior en [METRICAS_PROBADAS.md](METRICAS_PROBADAS.md).

Código: `scripts/analyze_btts_yes.py`; protocolo: `config/metric_experiments.json`.
Datos, predicciones, intervalos por fecha y hashes: `data/analysis/btts_yes_backtest.json`.
Reproducir: `python3 scripts/analyze_btts_yes.py`.
