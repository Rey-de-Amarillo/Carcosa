# Una apuesta: un gol o más en el primer tiempo

**No se encontró una ventaja rentable en esta prueba.**

| Simulación, una unidad por partido | Partidos | Aciertos | Resultado por cada 100 apostados |
|---|---:|---:|---:|
| Toda la muestra | 946 | 619 (65.43%) | -7.43 |
| Período posterior, desde 2026-05-17 | 324 | 205 (63.27%) | -10.65 |

Se usó la cuota registrada de cada partido: `beneficio = suma(acierto × cuota − 1)`.
Son cuotas y marcadores históricos de [SGodds](https://sgodds.com/football/data), sólo cuando su línea principal de primer tiempo era 0,5.
El importe simulado total es 946 unidades y la pérdida es 70.32 unidades.

El ajuste de probabilidades con los 622 partidos anteriores no seleccionó ninguna apuesta posterior con valor esperado positivo: 0 de 324.
Este modelo sencillo no descarta otras estrategias. La división es retrospectiva y no constituye una validación prospectiva.

Los precios históricos no se verificaron como ofertas ejecutables. No se realizaron apuestas.
Los resultados detallados, incertidumbre por fecha y procedencia están en `data/analysis/first_half_over05_backtest.json`.

Reproducir: `python3 scripts/analyze_first_half_over05.py`.
