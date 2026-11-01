# Mercados, liquidación y valor esperado

El catálogo v2 contiene **53 tipos de apuesta**, agrupados en **21 familias**, con datos disponibles,
precios históricos, modelo y reglas requeridas por separado. Agrupa variantes;
no afirma que una fuente ofrezca todas ellas ni que exista un modelo validado
para cada una. La línea, período, participante y regla exactos forman parte de
la identidad de un contrato.

Las claves y la cobertura del proveedor se contrastaron con la [documentación
oficial de The Odds API](https://the-odds-api.com/sports-odds-data/betting-markets.html).
Los mercados adicionales y de jugadores se consultan por evento y su presencia
depende de la competición y las casas. La disponibilidad de un precio actual
no demuestra disponibilidad de un histórico comparable.

## Qué calcula el nuevo motor

`engine/markets.py` transforma una distribución **conjunta** del marcador en
liquidaciones de 1X2, doble oportunidad, empate no apuesta, ambos marcan,
marcador exacto, totales, totales por equipo, hándicap asiático, hándicap europeo,
par/impar y margen exacto de victoria. Las líneas asiáticas incluyen enteras,
medias y cuartos. También calcula intersecciones de sucesos del mismo partido
para combinados binarios con reglas compatibles.

Cada celda `grid[local][visitante]` debe ser la probabilidad del marcador de la
estadística y período seleccionados. La matriz debe sumar uno; una masa de
cola faltante no se normaliza silenciosamente en el módulo de liquidación.
Si un modelo construye una cuadrícula truncada y luego la normaliza, debe
informar por separado la masa retenida y la aproximación aplicada.

Una cuadrícula de goles finales **no** es una distribución de córners,
tarjetas, goles del primer tiempo, puntos de jugadores, sets o primeros
goleadores. Esos mercados requieren sus propias etiquetas y modelos. Un
modelo de un período debe usar exactamente la misma definición de ese período
que el contrato cotizado.

## Por qué no siempre sirve `p × cuota − 1`

Esa fórmula corresponde a una apuesta binaria que gana todo el importe o lo
pierde. Un empate puede devolver el importe; una línea de cuarto puede ganar
o perder sólo la mitad. El motor conserva cinco estados:

| Estado | Fracción ganadora | Fracción perdida | Fracción devuelta | Retorno neto por unidad a cuota `o` |
| --- | ---: | ---: | ---: | ---: |
| Victoria completa | 1 | 0 | 0 | `o − 1` |
| Media victoria | 0,5 | 0 | 0,5 | `0,5 × (o − 1)` |
| Reembolso | 0 | 0 | 1 | `0` |
| Media pérdida | 0 | 0,5 | 0,5 | `−0,5` |
| Pérdida completa | 0 | 1 | 0 | `−1` |

El valor esperado es la suma de la probabilidad de cada estado multiplicada
por su retorno. Si `W = P(victoria) + 0,5P(media victoria)` y
`L = P(pérdida) + 0,5P(media pérdida)`, se obtiene:

`EV(o) = (o − 1) × W − L`

`cuota_de_equilibrio = 1 + L / W`, cuando `W > 0`.

Por ejemplo, en empate no apuesta, con 60 % de victoria, 30 % de empate
reembolsable y 10 % de derrota, una cuota 2 tiene `EV = 0,60 − 0,10 = 0,50`.
Usar `0,60 × 2 − 1` daría 0,20 y evaluaría un contrato distinto.

En mercados con reembolso, una referencia extraída de cuotas DNB representa
probabilidad **condicionada a que no haya empate**, bajo las hipótesis de
remoción del margen. No se compara directamente con una probabilidad de
victoria incondicional. En líneas de cuarto, la masa ganadora ponderada tampoco
equivale a la probabilidad de ganar todo el importe.

## Cuartos de línea

Un cuarto divide el importe en dos líneas vecinas de media unidad. Por ejemplo,
−1,25 se divide entre −1 y −1,5; total 2,75 se divide entre 2,5 y 3. Es el criterio
de las [reglas oficiales de Pinnacle](https://www.pinnacle.com/en/future/betting-rules)
y de la [explicación de Betfair](https://support.betfair.com/app/answers/detail/a_id/6418).
Se conserva la misma cuota para ambas mitades del contrato modelado.

En el código, el hándicap siempre corresponde al **equipo seleccionado**:

```python
from engine.markets import settle_score, net_return

result = settle_score(2, 1, 'asian_handicap', 'home', line=-1.25)
assert result['outcome'] == 'half_loss'
assert net_return(result, odds=2) == -0.5
```

El hándicap europeo tiene tres resultados. Su empate ajustado es una selección
ganadora para quien la eligió; no es el reembolso de un hándicap asiático. En
el motor europeo la línea se aplica al local antes de clasificar el resultado.

## Kelly sobre la distribución de retornos

Con ganancias parciales y reembolsos se maximiza:

`E[log(1 + f × retorno)] = suma_estado P(estado) × log(1 + f × retorno_estado)`

`generalized_kelly` encuentra el óptimo en `[0, 1]` mediante la derivada
monótona y después aplica una fracción y un límite. Devuelve cero si el EV
es no positivo. El supuesto sigue siendo que la distribución estimada es
adecuada: la optimización no corrige errores de probabilidad. Tampoco sustituye
los topes de exposición conjunta entre apuestas del mismo evento o fecha.

## Combinados y dependencia

Para ganar local y ambos marcan, el cálculo correcto en esta representación
es sumar las celdas en que **ambas** condiciones se cumplen. No se multiplica
`P(local)` por `P(ambos marcan)`; los sucesos comparten el marcador y pueden
estar fuertemente relacionados.

`joint_event_probability` admite intersecciones binarias win/loss. Rechaza
reembolsos y cuartos porque la liquidación de esos productos requiere un
contrato adicional. No convierte partidos diferentes en independientes ni
construye una rentabilidad ficticia de un bet builder sin su precio real.

## Qué puede evaluarse con los históricos actuales

- **1X2:** resultados y precios de una casa identificada, con snapshot
  pre-closing/closing preservado; no se comprueba ejecutabilidad real.
- **Más/menos 2,5:** resultados finales y precios archivados cuando existen;
  se evalúa por separado de 1X2 y se preserva el origen de la cuota.
- **Hándicap asiático:** algunos archivos originales contienen línea y cuotas.
  Deben normalizarse la línea y ambas cotizaciones de la misma casa y snapshot
  antes de usarlas en una prueba económica.
- **Descanso, córners y amarillas:** se evalúan baselines específicos con
  resultados anteriores al evento. Siguen siendo exploratorios: falta un
  histórico equivalente de todas las cuotas y una validación operativa.
- **Primer goleador:** hay secuencias de 64 partidos y una captura actual de
  precios. Falta cobertura suficiente de alineaciones, participación, minutos,
  goles individuales y reglas para probar una estrategia de jugadores.
- **NBA y MLB:** resultados descargados permiten evaluar probabilidades del
  ganador final. Sin cuotas históricas no se inventa un ROI; tampoco se
  presenta un archivo antiguo como fuente actual.
- **Otros deportes:** el catálogo distingue modelos pendientes y las reglas
  del deporte. Existir en la API de precios no significa tener datos de
  entrenamiento o resultados para liquidar su mercado.

## Contratos que deben conservarse

El catálogo enumera los campos relevantes: 90 minutos o prórroga en fútbol;
ganador de 60 minutos o incluyendo shootout en hockey; extra innings y mínimo
de innings en béisbol; abandono y tie-break en tenis; participación de jugadores;
amarilla/roja/puntos por tarjetas; córners ejecutados; y reglas de empate,
dead heat, anulación y comisión cuando correspondan. Son requisitos por
verificar con la casa concreta, no reglas uniformes adjudicadas a todas ellas.

Los mercados en vivo necesitan estado, reloj y cotización sincronizados. Un
modelo previo al encuentro no puede aplicarse al remanente de juego ignorando
goles, expulsiones o tiempo transcurrido. El módulo actual se declara
`selected_period_pre_match`, conserva `execution_enabled = false` y rechaza
un mercado de jugador que se intente derivar sólo de goles por equipo.

## API breve

```python
from engine.markets import evaluate_market

evaluation = evaluate_market(
    score_grid, 'totals', 'over', line=2.25, odds=1.95,
    kelly_scale=0.25, kelly_cap=0.01,
)
# evaluation['probabilities']: win, half_win, push, half_loss, loss
# evaluation['ev']: retorno esperado por unidad según esa distribución
# evaluation['fair_odds']: cuota de equilibrio del contrato
# evaluation['kelly_fraction']: fracción limitada; no es una orden
```

Los tests verifican liquidaciones opuestas, parciales y reembolsos, conservación
de probabilidad, EV con empates, Kelly generalizado, dependencia en combinados
y rechazo de entradas inválidas o mercados que la matriz no puede representar.

## Comparaciones entre casas

Las políticas de selección pueden aceptar conjuntos distintos de partidos. En la
revisión actual, multicasa selecciona 137 posiciones y Bet365 selecciona 23; sus
ROI no son una comparación causal del efecto de buscar otros precios. Para
aislar ese efecto habría que comparar el mismo contrato y cohorte, con precios
simultáneos, reglas compatibles y límites de ejecución verificados.
