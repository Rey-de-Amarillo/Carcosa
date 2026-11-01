# Combinaciones entre cuotas: archivo de investigación Betcity

Filas revisadas: 422064; mercados de resultado/doble oportunidad, goles, goles por equipo, ambos marcan y hándicap.
Se optimiza la distribución del importe entre todas las selecciones compatibles de cada fila; no se asumen independientes apuestas correlacionadas.

Portafolios con mínimo retorno mayor que1: **55**, bajo reglas estándar de devolución asiática.
De ellos, filas con una cobertura positiva usando sólo resultados binarios sin devoluciones ambiguas: **4**.
Coberturas débiles (no perder en ningún marcador, ganar en alguno): **0** bajo devoluciones asiáticas; **0** usando sólo resultados binarios.

La columna Betcity `BOTH_TEAMS_TO_SCORE__YES` queda **en cuarentena**, sin intercambiarla por No: muestra orientación inversa a los resultados reales. Otras familias tienen orientación global coherente, lo que no verifica cada cuota individual. El diagnóstico anterior sin cuarentena se conserva como evidencia de calidad de datos, no como una ganancia válida.

357243 filas se descartan mediante certificados duales de probabilidad y 64821 mediante programación lineal.
El soporte de marcadores es completo para las funciones usadas: límites derivados de cada línea, con prueba de reducción de cualquier marcador entero no acotado. No se descartan marcadores altos.

Se excluyen 114 filas con etiquetas explícitas de simulación, variante o duración especial. El resto conserva formato sin verificar.
Los casos positivos son discrepancias matemáticas de un archivo histórico, **no ganancias ejecutables verificadas**. Los tiempos, reglas, liquidez y aceptación de apuestas necesitan verificación.

Datos, asignaciones, peores casos, costos y sensibilidad: `data/analysis/betcity_crossmarket_search.json`.
Reproducir: `python3 scripts/betcity_crossmarket_search.py --scipy-path /tmp/football-portfolio-scipy`.
