# Cómo calcula y se evalúa Kraken Edge v2

Versión de investigación: **0.2.0**. Los resultados deportivos son reales; las probabilidades son estimaciones y los importes son unidades simuladas. Una salida del modelo no es una probabilidad verdadera conocida.

La versión anterior y su diagnóstico se conservan en `data/analysis/baseline_v1` y [DIAGNOSIS_V1.md](DIAGNOSIS_V1.md). La verificación actual está en [VALIDATION_V2.md](VALIDATION_V2.md).

## Qué cambió después del ROI negativo

El baseline v1 elegía el mayor EV estimado con un Poisson de promedios regularizados. Entre sus apuestas estimaba 32,20 % de acierto y se observó 22,46 %. El importe fijo también perdía: no era sólo un problema de Kelly. Elegir el mayor EV seleccionaba errores optimistas, particularmente en cuotas altas.

V2 separa dos caminos:

1. **Modelo deportivo estructural:** ajusta simultáneamente ataque, defensa, localía, calendario de adversarios y marcadores bajos.
2. **Referencia de precios:** remueve el margen de cada casa y combina probabilidades. Al evaluar una oferta, excluye del consenso la casa que ofrece ese precio.

La selección eligió consenso power con peso estructural **cero**. Se utiliza información de cuotas; no se afirma que el pronóstico deportivo independiente haya superado a los mercados. La mejora estructural se mide por separado.

## Protocolo temporal

| Etapa | Fechas | Uso |
| --- | --- | --- |
| Desarrollo | Hasta 31/12/2021 | Diseño del modelo y parámetros regularizados. |
| Selección | 01/01/2022–31/12/2023 | Comparar seis especificaciones mediante log loss, sin elegir por ROI. |
| Auditoría retrospectiva | 01/01/2024–30/10/2026 | Informar precisión y resultados de reglas fijas. Este período ya fue inspeccionado. |
| Seguimiento prospectivo | Desde 31/10/2026 | Registrar decisiones antes del resultado; cero eventos al registrar esta versión. |

Todos los partidos de una fecha se predicen antes de incorporar cualquiera de sus resultados. Aprender de fechas anteriores dentro de validación o auditoría reproduce un sistema online; no permite ajustar hiperparámetros usando el resultado futuro. Cada liga tiene estado separado.

El período 2024–2026 **no se renombra como un holdout intacto**. Sirve para comparar el código y diagnosticar fallos, pero no confirma por sí solo una ventaja futura. Las reglas v2 se diseñaron después de observar el fallo v1. Probar filtros sobre esos mismos resultados y conservar el ganador introduciría selección retrospectiva.

El seguimiento prospectivo usa un hash estable de especificación, política y fuentes relevantes. El timestamp no identifica al modelo. Repetir el informe con la misma especificación conserva el seguimiento; cambiar el protocolo produce otra identidad.

## Modelo de goles ajustado por adversario

```text
λ_local = base_local × ataque_local × defensa_visitante
λ_visitante = base_visitante × ataque_visitante × defensa_local
```

Las fuerzas se ajustan conjuntamente mediante actualizaciones condicionales Poisson con regularización hacia uno. Se utilizan partidos de ambas localías. Un promedio bruto alto no es la misma evidencia si se obtuvo contra defensas fuertes o débiles.

La implementación fija una ventana de 1.095 días, semivida de 365 días, ajuste cada 14 días, regularización de fuerza 12 y doce iteraciones condicionales. Normalizar geométricamente ataque y defensa resuelve su escala sin cambiar las intensidades. Las tasas se limitan al dominio previsto; una extrapolación extrema no se interpreta como ventaja.

Se exige historial previo suficiente: 120 partidos de liga, ocho por participante y seis partidos equivalentes tras el decaimiento. La última fecha de resultados usada es anterior al encuentro. Cancha neutral e historial desactualizado activan abstención; no se traslada automáticamente la ventaja local a una final neutral.

### Corrección Dixon–Coles

La base es el producto de dos Poisson. Los marcadores bajos tienen factores:

```text
τ(0,0) = 1 − λ_local × λ_visitante × ρ
τ(0,1) = 1 + λ_local × ρ
τ(1,0) = 1 + λ_visitante × ρ
τ(1,1) = 1 − ρ
τ(otros) = 1
```

`ρ` se estima sólo con la ventana pasada, con penalización hacia cero y límites que mantienen factores positivos. La cuadrícula informa la masa de cola retenida. Es una implementación regularizada inspirada en el modelo, no una reproducción de sus resultados históricos. [Dixon y Coles, 1997](https://www.research.lancs.ac.uk/portal/en/publications/modelling-association-football-scores-and-inefficiencies-in-the-football-betting-market%28d16276a2-d6e0-483b-a708-1d29663f1992%29.html).

La distribución conjunta permite resultado 1X2, ambos marcan, marcador exacto, doble oportunidad y líneas de goles. Una distribución de goles no es un modelo de córners, tarjetas, minutos de jugadores ni orden de goles.

## Probabilidades de mercado y consenso

Para cuotas completas `o_i`, las probabilidades implícitas brutas son `q_i = 1/o_i`; el overround es `suma(q_i) − 1`.

- **Proporcional:** `p_i = q_i / suma(q_j)`.
- **Power:** buscar `k > 0` con `suma(q_i^k) = 1`; usar `p_i = q_i^k`.

Power ajusta de forma distinta favoritos y cuotas altas. Sigue siendo una convención; no revela probabilidades verdaderas. El método y sus diferencias con la normalización se describen en [Clarke, Kovalchik e Ingram, 2017](https://researchbank.swinburne.edu.au/file/9986d69f-f5a0-4b32-8e5f-35d9ca1fb275/1/2017-clarke-adjusting_bookmakers_odds.pdf).

El consenso es la media de los vectores de probabilidad de casas válidas, no la media de sus cuotas. Conserva suma uno. La dispersión entre casas no es un intervalo de confianza de la probabilidad real.

Para evaluar un precio de la casa A, la referencia usa las otras casas, excluyendo A. Se exigen tres referencias completas: al menos cuatro casas válidas contando la objetivo. `Avg`, `Max`, `BbAv` y `BbMx` no son ofertas identificadas; exchange se excluye mientras no se modelen comisiones y reglas. Pinnacle se excluye desde 23/07/2025 por la advertencia de la fuente. Pre-closing y closing permanecen separados. Un CSV periódico sin timestamp individual no se convierte en una oferta ejecutable verificada. [Notas oficiales de Football-Data](https://www.football-data.co.uk/notes.txt).

El ensamble es `p = w × p_estructural + (1−w) × p_mercado`. Se compararon seis especificaciones: proporcional/power y pesos estructurales 0, 0,10 y 0,25. La selección usa exclusivamente log loss de 2022–2023. Si falta una fuente requerida, no se redistribuyen los pesos: un consenso puro sin cuotas deja la probabilidad seleccionada ausente.

## Primer tiempo, córners y amarillas

Hay estados separados por **liga y estadística**. Usan sus columnas específicas; los faltantes quedan ausentes. Todas las predicciones de la fecha preceden a sus actualizaciones.

El primer tiempo usa tasas Poisson regularizadas y sus propios marcadores al descanso. No presupone exactamente la mitad de la tasa del partido. Se evalúan 1X2, más de 0,5, más de 1,5 y ambos marcan.

Córners y amarillas usan una binomial negativa para admitir sobredispersión:

```text
E[N] = μ
Var(N) = μ + α × μ²
```

La media combina liga y fuerzas previas de equipos con regularización; `α` usa residuos anteriores y un prior. Poisson es el límite cuando `α` se aproxima a cero. Las bandas de la media son sensibilidad heurística, no intervalos calibrados. El benchmark es una frecuencia previa de esa liga, no una cuota inventada.

Las amarillas no equivalen a puntos por tarjetas ni a un total que incluya rojas. La fuente tiene convenciones diferentes para segundas amarillas; falta comprobar el contrato de cada casa. Estas familias no reciben ROI porque faltan precios históricos equivalentes.

## Tipos de apuesta y liquidación

El catálogo tiene **53 entradas de mercados**, doce familias de liquidación matemática y dieciséis evaluaciones numéricas en esta corrida. No son 53 modelos entrenados. Los contratos y estados están en [MARKETS.md](MARKETS.md).

Cada contrato conserva deporte, evento, participante, período, línea, prórroga y reglas de anulación. Ganador final de hockey no es resultado a 60 minutos; tenis requiere reglas de abandono; primer goleador exige participación y tratamiento de autogoles o ausencia de goleador.

Para una unidad se conservan fracciones ganada, perdida y devuelta:

```text
retorno_neto = fracción_ganada × (cuota−1) − fracción_perdida
EV = suma_estado [ P(estado) × retorno_neto(estado) ]
```

Se distinguen victoria, media victoria, devolución, media pérdida y pérdida. Una línea de cuarto divide el importe entre las líneas vecinas de medio punto. Local −0,25 divide entre 0 y −0,5: un empate produce media devolución y media pérdida.

`p × cuota − 1` sirve directamente para una apuesta binaria sin devoluciones. Aplicarla a DNB o un hándicap de cuarto puede dar EV incorrecto. Kelly generalizado maximiza la esperanza de log-capital sobre la distribución de retornos; después se fracciona y limita.

Las combinadas del mismo partido no multiplican marginales como si fueran independientes. Las intersecciones de sucesos del marcador usan la misma distribución conjunta. Eso tampoco determina cómo una casa trata patas anuladas o medias liquidaciones.

Primer gol del equipo continúa como derivación exploratoria de procesos Poisson competidores. Primer goleador individual permanece sin probabilidad del modelo mientras falten alineaciones, minutos y tasas por jugador validadas. Los 64 encuentros abiertos del Mundial 2022 no son cobertura universal de jugadores o ligas.

## Política financiera del experimento

La regla se declara antes de recorrer la auditoría; no se elige por su ROI:

1. Para cada resultado, buscar la mejor cuota de una casa real del mismo snapshot. El control Bet365 considera sólo esa casa.
2. Excluir esa casa del consenso; exigir tres referencias completas y margen dentro del límite configurado.
3. Exigir EV de al menos 3 % y cuota de 1,20 a 5,00.
4. Elegir una selección de mayor EV por evento.
5. Usar 10 % de Kelly, máximo de 0,25 % del capital por evento y 2 % por fecha. Los importes de la fecha usan el capital al iniciarla; no se reinvierten ganancias intradía todavía desconocidas.

El capital inicial es 1.000 unidades. ROI divide beneficio por importe acumulado apostado; retorno del capital divide beneficio por 1.000. El drawdown mide caída desde el máximo previo. El ledger manual tiene ajustes propios y no modifica retroactivamente el experimento.

El stress empeora 1 % las cotizaciones al liquidar **las mismas selecciones y los mismos importes del portfolio base**, incluso para fechas posteriores. No selecciona de nuevo después de observar precios peores. Es un escenario de precio, no un modelo completo de comisiones, impuestos, límites, latencia, anulaciones o aceptación del importe. Una falta de financiación del portfolio fijo bajo stress extremo se informa.

Los intervalos usan 400 réplicas bootstrap por fecha, con semilla fija. Describen variabilidad retrospectiva condicionada a esas selecciones e importes; no eliminan toda dependencia serial ni sesgo de selección.

La exigencia de tres referencias deja sin apuestas los experimentos OU2.5 y hándicap que sólo tienen una o dos casas compatibles. Cero apuestas significa `ROI = null`, no ROI cero ni rentabilidad demostrada por abstención.

## Resultados y alcance

Sobre 9.992 partidos emparejados, el log loss estructural pasó de 0,999166 a 0,991979; el consenso power obtuvo 0,970791. La mejora deportiva es medible, pero la referencia de precios sigue siendo más precisa.

La política de mejor precio produjo 137 selecciones, +41,53 unidades y ROI +16,81 %, con intervalo −8,17 % a +43,38 %: no excluye pérdidas. El ROI con cotización 1 % peor fue +15,64 %. Bet365 fijo produjo 23 selecciones y ROI −12,06 %. Esas políticas toman selecciones/eventos distintos; la diferencia no identifica sólo el efecto de comparar casas.

En selección, la misma política de mejor precio tuvo 159 selecciones y ROI +1,12 %, con intervalo −17,78 % a +20,77 %. La especificación no se eligió por esos retornos: el criterio fue log loss.

La recomendación sigue siendo `research_only`: posiciones actuales en cero y seguimiento prospectivo pendiente. Un porcentaje alto de aciertos, EV positivo o curva retrospectiva favorable no sustituye evidencia prospectiva ni precios verificables.

## Métricas, registro y otros deportes

Se calculan log loss, Brier y calibración. En 1X2, Brier suma errores de tres resultados y escala 0–2; en un suceso binario usa un error cuadrático y escala 0–1. Las comparaciones usan los mismos eventos. OU2.5 separa la muestra pareada con cuotas del conjunto más amplio que sólo tiene resultados.

Cada decisión guarda ID, fecha, modelo, fuentes, fecha máxima de entrenamiento, muestra, probabilidades, casa, referencia que la excluye, snapshot, línea, EV, Kelly, importe, liquidación y abstenciones. Capturas y fuentes matemáticas se archivan para conservar trazabilidad ante cambios del dato o código.

NBA y MLB mantienen Elo separado. Sin precios no se inventa ROI; archivos hasta 2015 y 2025 no habilitan por sí solos predicciones deportivas actuales. Jugadores, sets, innings, combate, críquet, carreras y futuros conservan requisitos y estados explícitos.

El arbitraje exige resultados exhaustivos y excluyentes, mismo contrato y cotizaciones sincronizadas. `suma(1/cuota) < 1` sólo da retorno teórico bajo esas condiciones y con todas las patas ejecutadas. No se fabrican arbitrajes ejecutables mezclando snapshots históricos.
