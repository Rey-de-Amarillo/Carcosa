# Combinaciones de pagos: SGodds

Se analizaron **3257 filas de partidos**, **319975 cuotas** y **18 familias de mercados**, conjuntamente.
Resultado por estado: `{'no_guaranteed_profit_exact_dual': 3172, 'recorded_price_positive_complete_payoff_verified': 82, 'dual_rounding_unresolved': 3}`.

**82 combinaciones dan beneficio matemático con los números registrados**, verificando también marcadores fuera de la grilla. Esto NO demuestra que esas líneas/cuotas hayan estado disponibles juntas: las oportunidades usan líneas variables cuya asociación con la cuota de apertura está cuestionada por la propia documentación de SGodds.
Al retirar totales con línea, hándicaps asiáticos y el 1/2 Goal, la comprobación queda: `{'implied_by_full_market_certificate': 3172, 'no_guaranteed_profit_exact_dual': 85}`.

La optimización reparte una unidad entre cualquier cantidad de apuestas simples. Incluye marcador exacto (también «otro»), resultado, goles exactos, over/under, ambos marcan, par/impar, hándicap, primer equipo en marcar, primer tiempo y descanso/final.
Los marcadores y el primer equipo en marcar se tratan como eventos relacionados, nunca como probabilidades independientes.

Para cada fila certificada, una distribución racional sobre resultados válidos limita a 1 la devolución esperada de **cada** contrato. Esto demuestra que ninguna mezcla de esos contratos puede devolver más de 1 en todos los resultados: si pudiera, su expectativa también excedería 1.
No hace falta truncar el universo de marcadores para esta prueba negativa. Un resultado positivo en una grilla finita sí necesitaría comprobar todas las colas; no se declara como arbitraje automáticamente.

Mejor cota superior global certificada de devolución por unidad: 0.9997732218002268.
Las cuotas históricas no se verificaron como ofertas simultáneas ejecutables. No se realizaron apuestas.

En los casos numéricos de devolución mínima 1 se comprueba además beneficio en algún resultado sin perder en otros (arbitraje débil). Si esa comprobación sólo cubre una grilla de estados, no se afirma ausencia global de arbitraje débil.

Código: `scripts/sgodds_portfolio_search.py`; auditoría con certificados enteros por fila: `data/analysis/sgodds_portfolio_search.json`.
Reglas del operador: [Singapore Pools](https://www.singaporepools.com.sg/en/rules/Pages/pdf/football-betting-game-rules.pdf).
