# Una apuesta: menos de 2,5 goles en el partido

**No se encontró ventaja rentable en esta prueba.**

| Simulación de una unidad por partido | Partidos | Aciertos | Resultado por cada 100 apostados |
|---|---:|---:|---:|
| Muestra completa | 2155 | 1019 (47.29%) | -10.90 |
| Posteriores desde 2026-08-02 | 719 | 322 (44.78%) | -14.02 |

Apostado: 2155 unidades. Devuelto: 1920.09. Resultado neto: -234.91.
Se gana con 0, 1 o 2 goles totales; con 3 o más se pierde. No hay devolución por total entero en la línea 2,5.
Fórmula: `suma(acierto × cuota individual − 1)`.

La calibración ajustada sólo con partidos anteriores seleccionó 0 apuestas posteriores con `p × cuota − 1 > 0`.
Se encontraron 0 coberturas directas con suma inversa menor que 1 entre 2215 pares Under/Over, incluidos pendientes.

Datos de [SGodds](https://sgodds.com/football/data), sólo cuando la línea principal registrada era 2,5. Son simulaciones a precios históricos, no apuestas ejecutadas.
La comparación cronológica es retrospectiva y no descarta otras estrategias. Se conserva esta prueba junto con las anteriores en [METRICAS_PROBADAS.md](METRICAS_PROBADAS.md).
La misma apuesta se contrasta también con la [base grande de Football-Data](NUMEROS_MENOS_25_BASE_GRANDE.md), por separado y sin sumar partidos como si fueran independientes.

Código: `scripts/analyze_under25.py`. Datos, predicciones, incertidumbre por fecha y hashes: `data/analysis/under25_backtest.json`.
Reproducir: `python3 scripts/analyze_under25.py`.
