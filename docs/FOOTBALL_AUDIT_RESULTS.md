# Resultado de la auditoría de fútbol · 30 de octubre de 2026

Captura de precios: **15:45:01 UTC** (12:45:01 de Salta). No representa cuotas vigentes para contratar. Fuentes gratuitas; ninguna apuesta ejecutada.

Se documentaron **184 modalidades en 20 familias**, con 62 enlaces oficiales de 11 marcas. Son contratos y variantes documentados: 181 tienen reglas verificadas, dos provienen de cupones oficiales fechados y una requiere confirmar la vigencia del documento indexado. No es una afirmación de cobertura literal de cada línea, combinación, región o oferta de cada partido.

La descarga produjo 10.892 observaciones, de las cuales 10.754 cumplían el filtro temporal al finalizar la captura; 6.098 son de fútbol. Las claves ofertadas por la API suman 59 distintas entre regiones (55 en US). Las claves de API no equivalen a las 184 modalidades del inventario. La muestra es de Premier League para precios de fútbol; el menú detallado corresponde principalmente a Chelsea–Manchester United. No se infiere cobertura de precios de todas las ligas.

## Qué beneficio aparece en precios

El auditor procesó 2.902 cuotas de goles reglamentarios, agrupadas en 23 pares partido/región. Retuvo 512 mejores precios equivalentes y comparó particiones completas, 400 pares y 4.010 tríos de patas. La poda es explícita y no constituye una búsqueda exhaustiva. Rechaza cruces con jugadores, otros conteos, períodos o líneas no soportadas.

Aparecen **9 carteras en 6 partidos**, con retorno mínimo teórico de **0,0396% a 0,4806%** del capital. Varias carteras comparten partido y exposición, por lo que no son oportunidades independientes. La mayor combina 1X2 Tottenham–Crystal Palace a cuotas 1,63 / 4,65 / 6,00: suma inversa 0,99521736 y retorno bajo los supuestos de 0,480562%. Estos son precios observados en una captura fechada, no una instrucción de ejecución.

Todas mantienen `verified_arbitrage=false` y `executable=false`: las reglas comunes son un supuesto, no hay límites/llenados confirmados y faltan costes e impuestos aplicables. Una diferencia de reloj inferior a 120 segundos tampoco garantiza que las patas puedan contratarse simultáneamente. Las anulaciones externas al marcador no están cubiertas.

**Ninguna de las nueve mantiene retorno mínimo positivo** si se resta un coste total del 0,5% del capital o si todas las cuotas decimales se reducen un 1%, conservando las fracciones de capital originales. Son escenarios de sensibilidad, no tarifas efectivas ni predicciones de deslizamiento.

Se detectan además 194 relaciones de precios: 94 intervalos de middle, 36 réplicas DNB, 28 identidades de liquidación, 27 dominancias y 9 réplicas de doble oportunidad. Una mejor réplica o una dominancia no prueba EV positivo. Un middle puede perder fuera de su intervalo. Los tres resultados de doble oportunidad se solapan y no admiten el test de suma inversa de una partición.

## Comparación con otros deportes

Panel descriptivo: mismas siete marcas, próximos siete días y sólo eventos presentes en las siete dentro de cada deporte; 37 eventos y 259 mercados completos. Cada marca/evento aporta un mercado de ganador del partido. No son 259 observaciones independientes: las casas pueden compartir precios y los deportes tienen diferentes eventos/reglas de prórroga.

| Muestra | Eventos | Mediana de overround | Rango observado |
|---|---:|---:|---:|
| Premier League | 10 | 5,13% | 3,25–8,73% |
| NBA | 9 | 5,30% | 2,53–7,94% |
| NFL | 11 | 5,13% | 2,85–5,79% |
| NHL | 3 | 4,71% | 2,33–5,81% |
| Tenis | 4 | 5,49% | 2,21–6,33% |

El overround es `sum(1/cuota) - 1`, una propiedad del precio de una partición completa. **No es ROI ni pérdida esperada de un apostador particular.** El tamaño y la composición no permiten recomendar un deporte como intrínsecamente más rentable. En esta muestra la dispersión entre casas es material y la mediana de EPL y NFL prácticamente coincide.

## Qué sigue sin demostrarse

Los mercados de primer gol, goleador, tiros, tarjetas, córners y microeventos requieren estimar exposición y procesos propios; una cuadrícula del marcador final no los identifica. Bet Builders necesitan probabilidades conjuntas, promociones/cashout trayectorias y reglas de contrato; ninguno se valida multiplicando probabilidades marginales. Se mantienen estos requisitos y las fuentes por entrada en el catálogo.

La evidencia de sesgo favorito–no favorito o de diferente eficiencia en asiáticos/1X2 motiva pruebas específicas; no garantiza rentabilidad después de margen. El modelo v2 registrado y sus pronósticos prospectivos no fueron retocados con esta auditoría.

Reproducción local: `python3 scripts/football_audit_sample.py` descarga la muestra con límites de créditos y `python3 scripts/build_football_audit.py` genera el informe a partir del archivo guardado. No es necesario volver a consultar la API para reproducir los cálculos. Entradas privadas en `data/analysis/football_audit_sample.json`; informe derivado en `app/data/football_audit.json`, con SHA-256 y fecha de captura.

Documentos de apoyo: `FOOTBALL_MARKETS_AUDIT.md`, `MATHEMATICAL_EDGES.md` y `SPORTS_COMPARISON.md`. Las fuentes oficiales están enlazadas en el catálogo de la app.
