# Combinaciones de apuestas de fútbol

**Hay combinaciones matemáticamente positivas en registros históricos. Ninguna quedó confirmada como ejecutable actualmente.**

## Ejemplo de goles, sin estimar probabilidades

Registro atribuido a Betcity, Ruvu Stars/JKT–Simba, 05/05/2025. Se excluyó el mercado BTTS por una etiqueta sospechosa; este ejemplo no lo usa.

| Apuesta separada | Cuota registrada | Importe sobre 100 |
|---|---:|---:|
| Visitante: menos de 2,5 goles | 2.22 | 47.76 |
| Partido: más de 2,5 goles | 2.03 | 52.24 |

Si el visitante marca 0, 1 o 2, la primera devuelve 106.0272. Si marca 3 o más, necesariamente el total supera 2,5 y la segunda devuelve 106.0472. Pueden ganar ambas, devolviendo 212.0744.
**Mínimo matemático: 106.0272 por 100; beneficio mínimo 6.0272.** La desigualdad cubre cualquier marcador, sin cortar la cola de goles.

**Condición pendiente:** que esas etiquetas, líneas y cuotas fueran correctas y aceptables al mismo tiempo. El archivo no demuestra esa disponibilidad; no es una recomendación actual.

## Contraste con precios históricos fechados de dos casas

En Manchester City–Ipswich del 17/10/2026 aparece Manchester City −1 al descanso, DraftKings 2,20, frente a Ipswich +1, Pinnacle 1,892. Repartiendo 46,24 y 53,76: City gana el primer tiempo por 2+ => +1,728; empata/pierde => +1,71392; gana por exactamente 1 => devolución total.
La mejor pareja dura 0,672 segundos en el registro. Un tramo de 49,507 segundos con cuota Pinnacle 1,854 conserva al menos +0,606 por 100 fuera de la devolución. DraftKings estaba marcado activo aunque su último cambio era anterior en diez minutos; el límite de esa casa es nulo en la fuente, no ilimitado.
Existe además una cobertura estricta de unos +0,023 por 100 con resultado/doble oportunidad, vulnerable a costos y dependiente de una cotización anterior. Los detalles de ventanas, límites y precios están en el informe específico.

## Alcance examinado

| Búsqueda | Cobertura y resultado |
|---|---|
| Marcadores/goles/empates/HTFT explícitos | 100020 coberturas en 3257 filas; 0 positivas. Incluye otros marcadores y colas. |
| Liquidación histórica por marcador | 95 selecciones; 0 ROI nominales positivos en toda la muestra. No se inventa el orden del primer gol. |
| SGodds, cartera general conjunta | 3257 filas, 319975 precios, 18 familias; 82 positivos sólo al admitir líneas variables no verificadas. Sin ellas, certificados negativos en todas las filas. |
| Betcity, cartera general | 422064 filas, 55 positivos con devoluciones supuestas y 4 con mercados binarios. Todos históricos y condicionales; BTTS en cuarentena. |
| OddsPapi, comparación temporal | 1403 grupos, 331/358 IDs, 5 partidos. Cero positivos con ambas cuotas de hasta 60 o 300 segundos; aparecen cruces con cotizaciones anteriores aún marcadas activas. |

Las carteras usan apuestas separadas, con pesos elegidos para el peor resultado. No se multiplican probabilidades de sucesos correlacionados ni se inventan pagos BetBuilder. Las apuestas de jugadores, córners, tarjetas, goles, períodos, resultados y conteos se comparan sólo cuando los contratos forman coberturas completas reconocidas.
El LP admite cualquier número de posiciones de compra dentro de las selecciones disponibles. Los certificados negativos y la verificación de colas están documentados por fuente. No equivale a probar todos los mercados de todas las casas del mundo.

## Datos excluidos o condicionados

- Betcity `BOTH_TEAMS_TO_SCORE__YES`: orientación inversa frente a resultados; cuarentena predeterminada, sin cambiarlo silenciosamente a NO.
- SGodds: sus 82 positivos dependen de líneas modificables; la propia fuente advierte posibles desacoples entre línea y precio histórico.
- Cotización antigua no significa automáticamente retirada, pero un estado activo del proveedor tampoco demuestra aceptación simultánea en cada casa.
- No se trataron listas superpuestas de goleadores como resultados excluyentes. Una cola de marcadores sin cubrir invalida la cobertura.
- La muestra Betfair contiene último precio negociado, no una oferta disponible; el pequeño snapshot SharpAPI no se mezcló como si fuera un tablero temporal único.
- Las reglas de anulación, participación del jugador, prórroga, límites y comisiones deben coincidir antes de convertir un cálculo en una operación.

## Código y reproducción

- [scripts/football_score_combinations.py](scripts/football_score_combinations.py) → [COMBINACIONES_MARCADORES.md](COMBINACIONES_MARCADORES.md).
- [scripts/sgodds_portfolio_search.py](scripts/sgodds_portfolio_search.py) → [COMBINACIONES_SGODDS.md](COMBINACIONES_SGODDS.md).
- [scripts/betcity_crossmarket_search.py](scripts/betcity_crossmarket_search.py) → [COMBINACIONES_BETCITY.md](COMBINACIONES_BETCITY.md).
- [scripts/oddspapi_temporal_arb.py](scripts/oddspapi_temporal_arb.py) → [COMBINACIONES_ODDSPAPI.md](COMBINACIONES_ODDSPAPI.md).

Protocolo: `config/football_portfolio_research.json`. Cuarentena: `config/football_market_quarantine.json`.
Dependencias para LP: `requirements-research.txt` (NumPy/SciPy). Los scripts también aceptan `--scipy-path`; en esta ejecución se usó `/tmp/football-portfolio-scipy`.
Auditoría integrada, ejemplos, conteos y hashes: `data/analysis/football_combination_research.json`.
Regenerar este resumen: `python3 scripts/build_football_combination_report.py`.

Fuentes de reglas: [Singapore Pools](https://www.singaporepools.com.sg/en/rules/Pages/pdf/football-betting-game-rules.pdf), [SGodds](https://sgodds.com/help), [DraftKings](https://sportsbook.draftkings.com/help/how-to-bet/soccer-betting-guide), [Pinnacle](https://www.pinnacle.com/en/future/betting-rules).
