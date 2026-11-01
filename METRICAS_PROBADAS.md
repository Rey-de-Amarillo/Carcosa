# Métricas probadas

Se conservan todas las pruebas, incluidos los resultados negativos. Cada fila usa una unidad por partido a su cuota histórica registrada.

| Métrica | Partidos | ROI total | Partidos posteriores | ROI posterior | Código |
|---|---:|---:|---:|---:|---|
| [Al menos un gol en el primer tiempo](NUMEROS_PRIMER_TIEMPO.md) | 946 | -7.43% | 324 | -10.65% | [scripts/analyze_first_half_over05.py](scripts/analyze_first_half_over05.py) |
| [Ambos equipos marcan: Sí](NUMEROS_AMBOS_MARCAN.md) | 2945 | -5.90% | 983 | -7.37% | [scripts/analyze_btts_yes.py](scripts/analyze_btts_yes.py) |
| [Menos de 2,5 goles en el partido](NUMEROS_MENOS_25_GOLES.md) | 2155 | -10.90% | 719 | -14.02% | [scripts/analyze_under25.py](scripts/analyze_under25.py) |

Comprobación adicional de **Menos de 2,5 goles en el partido**, Club Football Match Data / Football-Data, cuotas Bet365: 156684 partidos, ROI total -6.20%; tramo posterior 52272 partidos, ROI -6.16%. [Datos y código](NUMEROS_MENOS_25_BASE_GRANDE.md). No se suman las fuentes como partidos independientes.

Protocolo: primeros dos tercios cronológicos para ajustar y fechas posteriores para comparar; la fecha de corte nunca se reparte entre ambos grupos. No se optimizan equipos o ligas.

La calibración usa ambas cuotas del mercado y resultados anteriores; sólo selecciona si `p × cuota − 1 > 0`. Una muestra retrospectiva y los precios no verificados como ejecutables no demuestran ganancias futuras.

Cada métrica nueva cuenta como otra hipótesis exploratoria: no se descartan pérdidas ni se declara una estrategia validada por encontrar un resultado positivo entre muchas pruebas.

Registro de protocolos y rutas: `config/metric_experiments.json`. Resultados detallados: `data/analysis/*_backtest.json`.
