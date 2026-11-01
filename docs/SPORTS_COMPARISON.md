# Ventajas matemáticas por mercado y deporte

Revisión: **30/10/2026**. Investigación privada, fuentes gratuitas. Este documento compara mecanismos verificables; no asigna rentabilidad a un deporte por su nombre. El inventario de contratos de fútbol está en [FOOTBALL_MARKETS_AUDIT.md](FOOTBALL_MARKETS_AUDIT.md) y las pruebas de cobertura de precios en [MATHEMATICAL_EDGES.md](MATHEMATICAL_EDGES.md).

## Conclusión que permite la evidencia

**No hay evidencia local suficiente para afirmar que fútbol, tenis, NBA, MLB, NHL o NFL sea más rentable.** La rentabilidad depende del contrato concreto, del precio disponible, de la probabilidad estimada y de los costos. Un deporte más predecible puede tener precios más ajustados. Más partidos dan más observaciones potenciales, pero también repiten equipos, jornadas y factores comunes.

La base local tiene 65.810 partidos de fútbol, 31.822 de NBA y 12.148 de MLB. NBA termina en 2015 y MLB cubre 2021–2025; ambos archivos carecen de cuotas históricas comparables. Permiten estudiar predicción, **no calcular ROI observado ni ordenar los deportes por beneficio**. Las coberturas se documentan en [DATA_SOURCES.md](DATA_SOURCES.md).

En fútbol, el consenso Power obtuvo en la auditoría retrospectiva 137 selecciones, ROI simulado +16,81 % e intervalo bootstrap por fecha de −8,17 % a +43,38 %. El período ya había sido inspeccionado. Las cuotas no acreditan aceptación o simultaneidad. Por tanto, sigue siendo una hipótesis, y no una ventaja independiente demostrada. Las 23 selecciones de Bet365 fijo son otra cohorte; comparar directamente sus ROI no mide causalmente el beneficio de buscar mejores precios. [Protocolo y resultados locales](VALIDATION_V2.md).

## Qué significan beneficio, margen y facilidad predictiva

Para un contrato simple sin devolución, con cuota decimal `O` y probabilidad real `p`, el beneficio esperado por unidad es `EV = p × O − 1`. Acertar 70 % a cuota 1,30 produce `−9 %`; acertar 40 % a cuota 2,60 produce `+4 %`. Son ejemplos algebraicos, no pronósticos del bot. Una mayor tasa de aciertos por sí sola no mejora el ROI.

Si los resultados de un mercado son **mutuamente excluyentes y exhaustivos**, sin pagos parciales, `S = Σ(1/Oᵢ)` y `overround = S − 1`. El overround no identifica la pérdida esperada de cada selección. Bajo el supuesto adicional de margen proporcional, `pᵢ = (1/Oᵢ)/S` y la pérdida esperada es `1 − 1/S`. Con margen desigual hace falta estimar cada `pᵢ`.

**Dos resultados no garantizan menor margen que tres.** Dos cuotas 1,90/1,90 y tres cuotas 2,85/2,85/2,85 tienen el mismo `S = 1,05263` y la misma pérdida proporcional teórica del 5 %. Dos resultados simplifican la cobertura, pero el precio puede absorber esa ventaja operativa. En mercados con devolución, medias ganancias o medias pérdidas, se usa el vector completo de pagos, no esta simplificación.

No se suman inversas de precios de “marca en cualquier momento” para obtener overround: pueden marcar varios jugadores. Las tres dobles oportunidades se solapan. Un listado de resultados exactos sin “cualquier otro marcador” puede estar incompleto. Primer goleador requiere todos los jugadores elegibles y la situación sin goleador según las reglas. Ninguno de esos conjuntos se interpreta automáticamente como 1X2.

En **draw no bet (DNB)** pueden resumirse las dos cuotas del mismo evento, casa, período y captura como índice **condicionado a que no haya empate**. Si empatan se devuelve el importe. `1 − 1/Σ(1/O)` es sólo el proxy proporcional condicionado: no es margen incondicional del partido, porque falta la probabilidad de empate. Una suma de inversas menor que uno tampoco prueba por sí sola un beneficio garantizado: en el estado empate ambas posiciones se devuelven. Se necesita el vector completo de pagos y las reglas para evaluar cualquier cobertura.

Quitar margen crea una referencia probabilística, no una probabilidad verdadera. Clarke, Kovalchik e Ingram compararon métodos en tres conjuntos deportivos y encontraron mejor desempeño de Power que de normalización proporcional en sus muestras. Eso justifica probar ambos; no demuestra beneficio futuro. El bot selecciona el método por log loss previo, excluyendo del consenso la casa cuyo precio se evalúa. [Artículo original, 2017](https://www.sciencepg.com/article/10.11648/j.ajss.20170506.12).

## Comparación por familias de fútbol

La columna “oportunidad a comprobar” es una hipótesis. No equivale a una señal aceptada. Los márgenes actuales sólo pueden provenir de snapshots reales completos; no se asignan porcentajes supuestos a props o combinadas.

| Familia | Oportunidad a comprobar | Qué debe verificarse | Evidencia local que falta |
| --- | --- | --- | --- |
| 1X2, ganador 90 minutos | Diferencias multicasa; coherencia de precios y consenso sin casa objetivo | Tres resultados, mismo evento/período/reglas, tiempos de actualización y acceso a cada precio | Validación prospectiva suficiente; ejecución simultánea |
| Hándicap asiático, DNB, doble oportunidad | Misma exposición obtenida a mejor precio por contratos equivalentes | Push, cuartos, mitad de pérdida/ganancia; doble oportunidad no es una partición | Más casas históricas por línea; referencia mínima no cumplida en el backtest asiático |
| Totales de goles, goles por equipo, BTTS | Consistencia entre líneas, team totals, ambos marcan y distribución de marcadores | Línea, período y pagos enteros/medios; dependencia entre sucesos | Histórico multicasa suficiente de esos contratos; OU2.5 no generó posiciones válidas |
| Marcador exacto, margen de victoria, descanso/final | Incoherencias entre contratos derivados del mismo estado | Cola “otros”, dependencia entre tiempos; no tratar derivados como observaciones independientes | Cuotas históricas equivalentes y modelo conjunto contrastado |
| Primer tiempo, intervalos, próximo gol, minuto del gol | Precios incompatibles con el estado de partido o entre intervalos | Reloj, descanso añadido, sin gol, suspensión, VAR y actualización | Secuencias y ticks sincronizados; el resultado HT no contiene el orden de goles |
| Córners | Mejor precio/consistencia de líneas; conteos con sobredispersión | Córner concedido o ejecutado, repeticiones, período, fuente estadística | Cuotas históricas y estadísticas con definición equivalente; modelo de conteo no valida EV |
| Tarjetas, booking points, rojas | Diferencias de precios para una misma definición disciplinaria | Amarilla/segunda amarilla/roja, puntos, banca/cuerpo técnico, período | Histórico de sanciones y reglas compatibles; amarillas no equivalen a puntos |
| Jugadores: goleador, primer/último gol, tiros, asistencias, faltas, tackles, offsides | Precio frente a distribución condicionada a minutos y rol | Alineaciones, suplencia, no participante, minutos, autogol, proveedor, revisiones | Historia individual previa, minutos esperados, todas las selecciones y odds. Los 64 partidos StatsBomb no bastan |
| Futuros, campeón, clasificación, goleador de torneo | Incoherencias entre escenarios de temporada y torneo | Plantel, transferencias, calendario, reglas de empate, retiro y dead heat | Cuotas por fecha y simulación de escenarios; capital comprometido y cobertura de “otros” |
| Combinadas, sistemas, Bet Builder | Incoherencia entre precio final y pago conjunto de sus componentes | Dependencia, legs void/push, límite de pago; precio del ticket final | Precios históricos finales de combinadas y un modelo conjunto validado |
| Live, cash out, back/lay | Cobertura o precio de salida mejor que una réplica disponible | Latencia, suspensión, disponibilidad, profundidad y comisión por mercado | Ticks ejecutables y reglas idénticas; un snapshot diario no demuestra una operación live |
| Boosts, free bets, seguros, pagos anticipados | Valor del contrato completo bajo sus condiciones | Stake devuelto o no, rollover, cuota mínima, vencimiento, límites y condiciones de retiro | Oferta concreta elegible y pagos por cada escenario; no es una propiedad del deporte |

Hegarty y Whelan comparan 1X2 y hándicap asiático sobre los mismos partidos europeos: encuentran diferencias de sesgo favorito–no favorito relacionadas con estructura de mercado. Es evidencia de que **importa la familia de contrato y la competencia entre casas**, y no una prueba de que apostar al favorito o al asiático produzca ROI positivo hoy. [Trabajo original de los autores, revisión de marzo de 2025](https://www.karlwhelan.com/Papers/Monopoly.pdf).

## Comparación con otros deportes

| Deporte / contrato | Facilidad matemática potencial | Principal dificultad de precio o datos | Estado del proyecto |
| --- | --- | --- | --- |
| Fútbol 1X2 | Tres estados bien definidos y amplia historia disponible | Empate, bajas tasas de gol, margen desigual, precios de distintas horas | Comparación retrospectiva con cuotas; ventaja aún no validada |
| Fútbol asiático / goles | Dos lados y pagos reproducibles; equivalencias auditables | Push/cuarto; precio eficiente puede eliminar el valor | Sin posiciones históricas que cumplan referencias |
| Tenis ganador / sets / games | Ganador de dos resultados; estructura punto–juego–set | Retiros, superficie, nivel rival, fecha exacta por ronda, servicio, reglas de tie-break | Sin historia local autorizada y consistente para comparación financiera |
| NBA ganador / spread / total | Muchos eventos de anotación y estados por posesión/tiempo | Lesiones, descansos, minutos, cambios de rol, OT, dependencia entre props | Resultados antiguos sin odds; sin ROI comparable |
| MLB ganador / run line / total | Estructura por entrada y bateador; partidos repetidos | Pitcher, bullpen, orden al bate, clima/estadio, juegos dobles, entradas extra | 2021–2025 sin odds; sin ROI comparable |
| NHL ganador / 60 minutos / puck line | Puede separar regulación, OT y shootout | Portero, empty net, cambios de línea, pocos goles; 2-way y 3-way son contratos distintos | Sin histórico local suficiente ni permiso bulk verificado |
| NFL ganador / spread / total / props | Estado por jugada y posesión; modelación situacional | Menor muestra por equipo/temporada, números clave, lesiones, clima, empate/OT y cambios de reglas | Sin histórico local de odds y jugadas para evaluación |
| Cricket, rugby, voleibol, béisbol no MLB, MMA y otros | Estructura específica permite modelos especializados | Formatos, duración, reglas, nivel de liga y datos heterogéneos | Catálogo y algunas cuotas observadas no equivalen a modelos validados |

Las reglas importan incluso dentro de un deporte. Pinnacle incluye OT en mercados de partido y segunda mitad de básquet; su dinero-línea de tenis puede tener acción tras un set completado aunque otros contratos se anulen. Betfair documenta contratos NHL que incluyen OT/shootout y otros de regulación. Estas diferencias invalidan comparar sólo el nombre “ganador”. [Pinnacle: reglas](https://www.pinnacle.com/en/future/betting-rules), [Pinnacle: retiro en tenis](https://support.pinnacle.com/hc/en-us/articles/46732813299601-How-does-Pinnacle-grade-tennis-matches-in-the-event-of-retirement-or-disqualification), [Betfair: hockey](https://support.betfair.com/app/answers/detail/ice-hockey-rules/).

La investigación original de Levitt sobre NFL encuentra que las casas pueden explotar preferencias de los apostadores sin equilibrar necesariamente los importes a ambos lados. Encontrar un sesgo de demanda no implica que alcance para superar el costo. Es un estudio de un contexto histórico concreto, no una clasificación actual de rentabilidad entre ligas. [NBER, trabajo original](https://www.nber.org/papers/w9422).

## Combinadas, costos y liquidez

Para sucesos independientes y cuotas multiplicadas, el retorno bruto esperado conjunto es `Π(pᵢ Oᵢ)`. Si cada leg tiene factor 0,95, dos legs dejan `0,95² − 1 = −9,75 %` y cinco `0,95⁵ − 1 = −22,62 %`. Es un ejemplo derivado bajo independencia; no es un margen observado de ninguna casa.

En un mismo partido hace falta `P(A∩B)`, no `P(A)P(B)`. Algunas combinaciones son redundantes o imposibles. La correlación por sí sola no crea beneficio si la cuota final ya la refleja. Pinnacle restringe combinadas correlacionadas; Betfair ofrece Bet Builder y especifica condiciones por deporte. Debe archivarse el precio final aceptable, además de las cuotas individuales. [Pinnacle: restricciones](https://support.pinnacle.com/hc/en-us/articles/45299381622673-What-bet-types-are-not-available-for-Multiple-bets), [Betfair: Bet Builder](https://support.betfair.com/app/answers/detail/a_id/6653/).

En exchange, una cuota back aislada con comisión `c` sobre ganancia neta tiene cuota efectiva `1+(O−1)(1−c)`. Con varias posiciones la comisión se calcula sobre el resultado neto del mercado; no se descuenta de cada leg de forma independiente. Tampoco alcanza el mejor precio de pantalla sin cantidad disponible. [Betfair: comisión](https://support.betfair.com/app/answers/detail/a_id/413/).

Para live o coberturas multicasa son necesarios datos de estado y precio sincronizados, además de aceptación y profundidad. La documentación oficial de Betfair indica que su clave Delayed entrega snapshots con demora variable de 1 a 180 segundos y usa producción, no dinero virtual. Una discrepancia hallada con esos datos no acredita una cobertura realizable. [Betfair Developer: Delayed/Live](https://support.developer.betfair.com/hc/en-us/articles/360009638032-When-should-I-use-the-Delayed-or-Live-Application-Key).

## Cuánta evidencia hace falta

El retorno simulado y la precisión se evalúan por separado: log loss/Brier y calibración; ROI, intervalo por bloques de fechas/eventos, volumen y drawdown. No se comparan log loss o Brier crudos entre objetivos de distinta cantidad de resultados sin su baseline/normalización. Ganar 1X2 y estimar un total binario tienen dificultades y entropías distintas.

Como ejemplo algebraico, una apuesta justa a cuota 2 tiene desviación estándar 1 unidad por unidad apostada. Con independencia y tamaños iguales, el ancho aproximado de un intervalo del promedio al 95 % es ±`1,96/√n`: con 100 apuestas, ±19,6 puntos de ROI; con 1.000, ±6,2; con 10.000, ±1,96. Dependencias, cambios de mercado y selección de la mejor estrategia pueden ampliar la incertidumbre. Cientos de props del mismo partido no son cientos de partidos independientes.

El protocolo debe fijar modelo, reglas, fuentes, selección y costos antes del período nuevo; registrar cada abstención y cada oferta; mantener un conjunto prospectivo sin reutilizarlo para elegir especificaciones. Las múltiples familias probadas se declaran para no confundir al mejor resultado entre muchas pruebas con un hallazgo robusto. Kelly reduce/importa exposición según probabilidades; **no convierte EV negativo ni probabilidades mal calibradas en ventaja**.

## Presupuesto gratuito y próximos datos

El dominio usado es **the-odds-api.com**, con guiones. Su plan Starter publica 500 créditos por mes, todos los mercados según cobertura y sin cuotas históricas. El endpoint general factura por mercados y regiones solicitados; el de evento por mercados únicos devueltos y regiones. No es viable seguir todos los mercados de todos los deportes en live con esa cuota. No se confunde con proveedores de nombre parecido. [Plan oficial](https://the-odds-api.com/), [documentación v4](https://the-odds-api.com/liveapi/guides/v4/).

La prioridad de investigación se decide por evidencia accesible: capturar hacia adelante contratos completos y reglas identificadas; ampliar resultados que puedan liquidarlos; comprobar calibración sin fuga temporal; recién después estimar ROI neto por mercado y deporte con el mismo protocolo. Las licencias y atribuciones se conservan en [DATA_SOURCES.md](DATA_SOURCES.md). No se exportan las claves ni los archivos originales con permisos de uso privado.

El archivo [sport_advantage_framework.json](../config/sport_advantage_framework.json) contiene este marco en formato legible por la app. Sus campos de margen/costo observado permanecen separados de los snapshots: `null` expresa evidencia faltante o no atribuida al contrato concreto, no costo cero. El índice actual se reproduce con `engine.quote_costs.summarize_costs` y las cotizaciones del archivo local de auditoría.

## Comparación empírica del snapshot actual

Fuente local: `data/analysis/football_audit_sample.json`, generado **30/10/2026 a las 15:45:01 UTC**. Primero se filtraron las filas RAW de `fresh_quotes` por **`region == 'eu'`**, antes de construir boards o deduplicar aliases. Hay 7.199 cotizaciones EU; otras 3.555 filas no entran en esta comparación. Después se conservaron solamente boards completos de **h2h de partido completo**, sin exchange/DFS y deduplicando aliases de una misma exposición. Hay 1.189 boards EU de cinco deportes con esa definición antes del límite de siete días, y 871 dentro del horizonte. No se usa la mediana de todos los mercados juntos para comparar deportes: fútbol incluye muchos contratos especiales que el muestreo de otros deportes no contiene.

En el h2h completo EU sin restringir casas, las medianas de overround son fútbol 5,78 %, NBA 5,36 %, NFL 5,16 %, NHL 5,00 % y tenis 5,56 %. La composición cambia de 10 casas en NHL a 23 en fútbol, y el horizonte de fixtures llega al 26 de diciembre en NBA y al 22 de noviembre en EPL. Estas medianas no permiten atribuir la diferencia al deporte.

Se construyó un panel más comparable sobre esas filas **EU estrictas**: primero se limitó el inicio a **los próximos siete días** desde la captura (hasta 06/11/2026 a las 15:45 UTC), luego se eligieron **las mismas siete marcas en los cinco deportes** y, dentro de cada deporte, únicamente eventos que tienen cotización en las siete. Las marcas son BetAnySports, BetOnline, Betsson, NordicBet, Pinnacle, 888sport y William Hill. Cada evento aporta exactamente siete boards; no se rellena una cuota faltante. Una captura UK más nueva no puede reemplazar una cuota EU. Los porcentajes son `Σ(1/O) − 1`, no ROI. Resultados, método, región y hash de la entrada se conservan en `data/analysis/football_sport_comparison.json`. Se reproducen sin red mediante `python3 scripts/build_sport_comparison.py --region eu --horizon-days 7`.

| Deporte / muestra | Eventos | Boards | Mediana de overround | P25–P75 | Mínimo–máximo |
| --- | ---: | ---: | ---: | --- | --- |
| Fútbol, EPL | 10 | 70 | 5,13 % | 3,52–6,61 % | 3,25–8,73 % |
| Básquet, NBA | 9 | 63 | 5,30 % | 3,75–5,99 % | 2,53–7,94 % |
| Fútbol americano, NFL | 11 | 77 | 5,13 % | 3,84–5,36 % | 2,85–5,79 % |
| Hockey, NHL | 3 | 21 | 4,71 % | 3,44–5,16 % | 2,33–5,81 % |
| Tenis, ATP Viena/Basilea | 4 | 28 | 5,49 % | 4,17–5,91 % | 2,21–6,33 % |

Las cotizaciones del panel tenían antigüedad de hasta 69 segundos al recuperarse. Los eventos de tenis eran del mismo día; NBA/NHL del 30–31 de octubre, EPL del 31 de octubre al 2 de noviembre y NFL del 1 al 3 de noviembre. Las reglas individuales no se han confirmado en cada ticket, ni la aceptación o capacidad de ejecución.

El panel muestra por qué **no corresponde anunciar que el fútbol es intrínsecamente más caro**: al controlar marcas y cobertura, su mediana queda prácticamente igual a NFL en esta captura. Tampoco corresponde declarar NHL “mejor”: sólo hay tres eventos y su contrato ganador suele incluir OT/shootout, frente a 90 minutos y empate en fútbol. El orden cambia con casa, selección y muestra.

La dispersión entre marcas también importa. En los diez partidos EPL del panel, la mediana por marca va de 3,46 % a 8,28 %. En nueve partidos NBA va de 2,82 % a 6,52 %. Una comparación de deportes que cambie la mezcla de casas puede reflejar esa composición. Algunas marcas muestran cuotas idénticas en muchos eventos: siete marcas no acreditan siete señales de formación de precios independientes. No se estima incertidumbre entre deportes tratando cada precio repetido como un partido independiente.

Este ejercicio mide el costo implícito observado de cotizar una partición. **No demuestra EV positivo en ningún deporte**. Para ello siguen faltando probabilidades independientes calibradas, resultados futuros y costos/reglas de las ofertas que realmente puedan tomarse.
