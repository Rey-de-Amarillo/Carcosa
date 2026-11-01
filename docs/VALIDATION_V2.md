# Verificación v2 — 30/10/2026

La revisión mejora el modelo estructural y la evaluación financiera, pero
todavía **no acredita una estrategia rentable en una prueba prospectiva**.
Este documento corresponde a investigación y unidades simuladas. El informe
de v1 se conserva en [VALIDATION.md](VALIDATION.md) y en
`data/analysis/baseline_v1`.

## Protocolo y fuentes

Se fijó desarrollo hasta 2021, selección de especificación en 2022–2023 y
auditoría de 2024 a 30/10/2026. La auditoría ya había sido inspeccionada en la
versión anterior; no se presenta como un test intacto. La selección usa log
loss, no ROI. El seguimiento prospectivo comienza el 31/10/2026 y registra
cero eventos al crear esta versión.

La base conserva 109.780 partidos y tres deportes. La nueva extracción de
precios contiene 65.810 identidades de partidos de fútbol y conserva las casas
reales de cada snapshot. Hay 42.610 partidos con dos o más casas pre-closing;
el procedimiento financiero requiere tres referencias además de la casa
objetivo, por lo que ese dato de cobertura no equivale al número de apuestas.

Los precios pre-closing y closing nunca se mezclan. Se excluyen promedios,
máximos, exchange sin comisiones modeladas y Pinnacle desde el corte de
desactualización comunicado por la fuente. Los CSV no confirman el instante
individual ni la aceptación de una cuota. Los archivos multicasa originales
permanecen en el área privada local.

## Mejora predictiva sobre la misma muestra

| Pronóstico | Partidos emparejados | Log loss | Brier multiclase |
| --- | ---: | ---: | ---: |
| Poisson v1 | 9.992 | 0,999166 | 0,596113 |
| Poisson ajustado + Dixon–Coles v2 | 9.992 | 0,991979 | 0,591700 |
| Consenso proporcional | 9.992 | 0,971770 | 0,578254 |
| Consenso power | 9.992 | 0,970791 | 0,577808 |

Menor error es mejor. La mejora estructural de log loss es 0,007187, con
intervalo bootstrap por fecha aproximado de 0,004964 a 0,009239. Es una mejora
del baseline sobre esta auditoría, no una afirmación de superioridad frente
al consenso de precios.

La selección de 2022–2023 comparó seis especificaciones sobre 7.325 partidos.
Ganó **consenso power, peso estructural cero**, con log loss 0,965787. Su
pronóstico usa las casas; la comparación contra ese mismo consenso es
idéntica, no evidencia de información predictiva independiente adicional.

La métrica de los 9.992 partidos emparejados y la auditoría financiera de
15.011 registros elegibles tienen filtros distintos. No se atribuye una
comparación pareada a esos conjuntos completos por el solo hecho de compartir
fechas.

## Investigación financiera

La política se fijó antes de recorrer estos resultados: EV mínimo 3 %, cuota
1,20–5,00, tres casas de referencia excluyendo la casa del precio, una selección
por evento, 10 % de Kelly, hasta 0,25 % por evento y 2 % por fecha. No fue
elegida por el ROI del período auditado. Fue diseñada tras diagnosticar v1;
ese hecho impide interpretar la auditoría como validación independiente.

| Política / período | Apuestas | ROI simulado | Intervalo de ROI | ROI con precio 1 % peor |
| --- | ---: | ---: | --- | ---: |
| Mejor precio, selección 2022–2023 | 159 | +1,12 % | −17,78 % a +20,77 % | +0,11 % |
| Bet365 fijo, selección 2022–2023 | 15 | −59,20 % | −100,00 % a +2,60 % | −59,61 % |
| Mejor precio, auditoría 2024–2026 | 137 | +16,81 % | −8,17 % a +43,38 % | +15,64 % |
| Bet365 fijo, auditoría 2024–2026 | 23 | −12,06 % | −66,00 % a +49,54 % | −12,94 % |

El portfolio principal acumula 247,03 unidades apostadas y +41,53 de beneficio
hipotético: pasa de 1.000 a 1.041,53 unidades, con caída máxima de 1,97 %.
El ROI +16,81 % divide por el volumen apostado; el retorno del capital inicial
es +4,15 %. No son cantidades intercambiables.

Los intervalos contienen resultados negativos. El stress mantiene exactamente
las mismas selecciones y los mismos importes del portfolio base; sólo empeora
la cotización al liquidarlos. La diferencia entre mejor precio y Bet365 fijo
no aísla un efecto causal de buscar casas: las políticas generan diferentes
eventos y selecciones. Tampoco confirma simultaneidad, límites o acceso a esas
ofertas históricas.

OU2.5 y hándicap respetaron el mismo mínimo de referencias. No hubo posiciones
que lo cumplieran; su ROI permanece ausente (`null`). No se informa 0 % como
si la abstención demostrara una mejora rentable.

## Cobertura de tipos de apuesta

El catálogo tiene **53 entradas de mercados**, agrupadas por deporte y
contrato. No son 53 modelos entrenados. Doce familias tienen liquidación
matemática implementada. La corrida incluye **16 evaluaciones numéricas**:

- Siete sucesos derivados de goles: más de 0,5/1,5/2,5/3,5, ambos marcan y dos
  dobles oportunidades.
- Cuatro sucesos del primer tiempo, con estado propio de goles al descanso.
- Tres líneas de córners, con modelo de conteos separado.
- Dos líneas de amarillas, con modelo separado de las rojas y de los puntos
  por tarjetas.

Primer tiempo usa Poisson regularizado. Córners y amarillas permiten
sobredispersión mediante binomial negativa. Se comparan contra frecuencias
previas de liga y se entrenan sólo con resultados anteriores al evento.
Faltan precios históricos equivalentes para esas familias; por eso se evalúa
precisión, sin fabricar EV, importe o ROI.

Primer goleador, sets, innings, props, carreras, futuros y otros contratos
mantienen requisitos explícitos en el catálogo. La existencia de una fórmula
de liquidación o una API no significa disponer de un predictor validado.

## Auditoría independiente del pipeline

Se revisaron `scripts/research_v2.py`, `engine/ensemble.py`, el portfolio y la
integración. Se verificó:

- 137 liquidaciones reconciliadas con selección, marcador y cuota.
- Ninguna casa objetivo dentro de su referencia y ningún trade con menos de
  tres referencias.
- Ninguna fecha máxima de entrenamiento igual o posterior al evento.
- La selección de especificación no cambia al modificar resultados o precios
  de 2024 en adelante.
- Las ramas con una sola fuente de probabilidad validan valores finitos,
  límites y suma uno.
- La remoción de margen, el consenso y los ensambles conservan una
  distribución válida.

La revisión detectó y se corrigieron tres problemas de interpretación o
persistencia:

1. Una fuente de consenso ausente podía sustituirse silenciosamente por el
   modelo estructural, aun con peso estructural cero. Ahora esa probabilidad
   queda ausente y se conserva la identidad de la especificación elegida.
2. OU2.5 podía mostrar el Brier estructural de todos los partidos junto al del
   mercado de una submuestra. La comparación actual usa la misma muestra y
   mantiene aparte los eventos sin cuotas.
3. Repetir la investigación podía resetear el registro prospectivo y cambiar
   el hash por el timestamp. La identidad del protocolo ahora es estable y
   preserva el registro existente.

## Pruebas y reproducción

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_quote_history.py
python3 scripts/research_v2.py
python3 scripts/build_report.py --reuse-research
```

Las pruebas específicas de consenso/selección (`test_ensemble.py`, siete) y
portfolios (`test_research_backtest.py`, trece) pasaron durante la revisión.
Cubren pool probabilístico, datos inválidos, independencia del período futuro,
referencia excluyendo objetivo, capital congelado por fecha, límites,
snapshot correcto, haircut con portfolio fijo, bootstrap reproducible y
liquidaciones parciales asiáticas. La suite completa también incorpora modelos,
estadísticas, backend y bot con bases temporales y proveedores simulados.

`build_report.py` ejecuta el pipeline v2 de forma predeterminada.
`--reuse-research` sirve para integrar una investigación existente coherente
con sus entradas; `--legacy` reproduce el baseline. La exportación vigente
identifica su número de decisiones en `history_export.count`: no se reutiliza
el recuento de v1 como si fuera la nueva historia.

## Estado operativo

Se mantiene `research_only`, sin ejecución de apuestas y con importes actuales
en cero. El bot observador conserva el plan gratuito, intervalo mínimo de 24
horas y hasta doce consultas diarias; los originales y las claves permanecen
locales. El panel privado distribuye una captura de resultados derivados.

Los siguientes requisitos siguen pendientes: muestra prospectiva suficiente,
intervalos positivos bajo costos, reglas y timestamps verificables y
evidencia que permita distinguir una oportunidad persistente de ruido o un
precio histórico desactualizado. Las cifras positivas de esta revisión no
suprimen esos requisitos.

## Comprobación final de integración

- 112 pruebas aprobadas con `python3 -m unittest discover -s tests -v`.
- Historial vigente: 23.813 decisiones; la referencia v1 permanece en `data/analysis/baseline_v1/`.
- Una ejecución real v2 del bot terminó sin errores, preservó exactamente el backtest y no consumió créditos adicionales.
- Tras una consulta fresca de EPL (un crédito gratuito), quedaron congelados 20 pronósticos para eventos posteriores al comienzo registrado del 31/10/2026: veinte pendientes, cero resultados comprobados y ninguna selección de simulación prospectiva aceptada.
- Las capturas preservan el vector global coherente para puntuación y el vector de referencia que excluye la casa del precio para evaluar cada oferta.
- Las fuentes del motor, del scanner y del registro prospectivo, junto con la selección y el protocolo, se archivan por SHA-256.
- El historial web usa un nombre que contiene su hash, para que una actualización no mezcle el informe anterior con un archivo parcialmente reemplazado.

La restauración por fallo también verifica los artefactos v2 completos; preserva los registros prospectivos por hash y la auditoría inmutable en SQLite.
