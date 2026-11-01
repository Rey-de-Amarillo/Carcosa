# Ventajas matemáticas entre mercados

Este auditor compara **precios y liquidaciones**, sin predecir resultados y sin colocar apuestas. Una cobertura que paga más en todos los marcadores normales no acredita que se puedan contratar todas las patas, ni elimina las diferencias de reglas o las anulaciones. La rentabilidad esperada de una apuesta individual requiere además probabilidades validadas.

Implementación: `engine/market_audit.py`. Validación: `tests/test_market_audit.py`.

## Qué significa cada resultado

| Resultado | Qué demuestra | Qué sigue pendiente |
| --- | --- | --- |
| `payoff_dominance` | Un contrato paga al menos lo mismo que otro con igual capital en cada estado del marcador. | Que cualquiera tenga EV positivo. |
| `double_chance_replication` / `dnb_replication` | Otra combinación reproduce el mismo flujo de caja. | Un precio mejor no permite vender la otra combinación ni crea automáticamente arbitraje. |
| `middle_interval` | Dos patas pueden ganar en un intervalo, con pérdida fuera de él. | Probabilidad del intervalo, costes y disponibilidad. |
| `conditional_non_loss_cover` | Bajo el contrato modelado hay estados de ganancia y estados de retorno cero. | Una ganancia estrictamente positiva para todos los estados; comprobar ejecución y reglas. |
| `theoretical_price_candidate`, con `strictly_positive_under_contract=true` | El retorno mínimo calculado es positivo para todos los estados de liquidación normal del contrato. | Relojes, reglas verificadas, límites, liquidez, contratación completa y costes restantes. |
| `verified_arbitrage` | No se asigna a ningún hallazgo de esta herramienta. | No existe integración que confirme llenados ni ejecución. |

Todos los resultados tienen `executable=false`. `verified_arbitrage=false` incluso cuando el cálculo de precios es positivo. `relation_only=true` señala falta de sincronización o reloj sin verificar; esas relaciones no incrementan `synchronized_positive_contract_candidates`. Las anulaciones externas no forman parte del espacio de marcador: el certificado lo informa con `external_void_states_included=false`.

## Cobertura ordinaria y margen

Para resultados **mutuamente excluyentes y exhaustivos**, sin reembolso ni costes, sean `o_i` las mejores cuotas decimales compatibles. Con `S = Σ(1/o_i)`, la asignación de capital `w_i = (1/o_i)/S` produce retorno neto constante `1/S − 1`. Sólo `S < 1` da beneficio positivo. No sirve sumar precios de períodos diferentes, líneas distintas o resultados incompletos.

En 1X2, cuotas 3,20 / 3,20 / 3,20 darían `S = 0,9375` y un retorno teórico de 6,6667%, con un tercio del capital en cada resultado. Es un ejemplo algebraico; no se presenta como precio encontrado en una casa.

Con cuotas de una sola casa, `S − 1` es el *overround*, una propiedad de los precios. No equivale directamente al porcentaje de pérdida de un apostador concreto. Tampoco identifica un deporte intrínsecamente rentable. El mismo criterio funciona en tenis, básquet u otro deporte cuando los resultados y reglas forman la misma partición completa.

## Doble oportunidad: los resultados se solapan

Las tres selecciones `1X`, `X2`, `12` no forman una partición. Cada resultado 1/X/2 hace ganar exactamente dos de ellas. Sus probabilidades justas suman **2**, no 1. Normalizarlas como un mercado 1X2 sería un error.

Incluso si `Σ1/o > 1`, puede existir cobertura positiva: tres dobles oportunidades a 1,60, con un tercio de capital cada una, devuelven `2 × 1,60 / 3 = 1,0666667` en cualquier resultado. A 1,50 devuelven exactamente 1: cobertura sin beneficio. El auditor usa la matriz de pagos para este caso y registra que el test de suma inversa no corresponde.

Una doble oportunidad puede replicarse comprando sus dos resultados 1X2, con igual cobro bruto en ambos:

```text
o_sintética(1X) = 1 / (1/o_local + 1/o_empate)
```

Una cuota distinta identifica un precio más favorable para el mismo flujo de caja. Para convertirlo en beneficio seguro haría falta una cobertura adicional o poder vender el contrato caro, con costes incluidos.

## DNB, asiático cero y reembolsos

Empate no apuesta (DNB) y hándicap asiático cero del mismo equipo son equivalentes en el marcador normal. En el empate se devuelve el capital: no se pierde ni se gana una cuota. El auditor detecta la equivalencia y compara precios.

Es posible replicar DNB local usando 1X2: colocar `1/o_empate` del capital en empate y el resto en local. El empate devuelve exactamente una unidad; el flujo local equivale a:

```text
o_DNB_sintética = o_local × (1 − 1/o_empate)
```

Por ejemplo, local a 2 y empate a 4 reproducen un DNB a 1,50, con 25% del capital en empate y 75% en local.

Dos DNB opuestos a 2,10, con mitades iguales, dan +5% cuando gana cualquiera y **0% si empatan**. El auditor los clasifica como `conditional_non_loss_cover`, sin afirmar ganancia positiva en todos los resultados.

## Hándicaps y totales enteros, medios y cuartos

El cálculo utiliza las fracciones de capital ganadas, perdidas y devueltas de `engine.markets.settle_score`:

```text
retorno_neto = fracción_ganada × (cuota − 1) − fracción_perdida
```

Una línea de cuarto divide la inversión entre las dos medias líneas vecinas. Una cuota 2,20 en local −0,25 y 2,20 en visitante +0,25 no produce el mismo beneficio mínimo que dos apuestas binarias: el empate liquida media pérdida y media ganancia/reembolso. El optimizador encuentra capitales 16/33 y 17/33 y piso +6,6667%; la asignación 1/2 y 1/2 sólo da piso +5%. Una línea entera puede devolver ambas patas y reducir el piso a cero.

Las [reglas oficiales de Pinnacle](https://www.pinnacle.com/en/future/betting-rules) describen la división de capital en cuartos. También distinguen el resultado normal de 90 minutos de la prórroga, y el hándicap asiático en vivo sobre el tramo restante. El adaptador debe conservar esas diferencias; el auditor exige `settlement_basis` explícito cuando `in_play=true`.

## BTTS y total de goles: dependencia e implicación

Que ambos equipos marquen implica al menos dos goles. Por eso `BTTS sí` es un subconjunto de `más de 1,5`, no un evento independiente ni un sinónimo. Si `más de 1,5` paga una cuota igual o mayor, con idénticas reglas, domina a `BTTS sí` con el mismo capital. Eso compara dos apuestas; no demuestra que la mejor tenga EV positivo.

La probabilidad de una combinada del mismo partido no se obtiene multiplicando sus probabilidades marginales. Para mercados derivados del marcador debe usarse la intersección sobre una distribución conjunta. Los mercados de orden de goles, jugadores, tiempos, VAR, tarjetas, córners o participación necesitan estados y reglas adicionales; un marcador final de goles no los identifica.

## Middles: un intervalo favorable no basta

Más de 2,5 y menos de 3,5, ambas a 1,80 y con capitales iguales, dan +80% si hay exactamente tres goles y −10% en cualquier otro total. El EV es `0,90 × P(total=3) − 0,10`, antes de costes. Se necesitaría `P(total=3) > 1/9` para EV positivo. El auditor muestra el intervalo y sus pérdidas; no inventa esa probabilidad ni los llama arbitraje.

## Exchange, apuestas lay y comisión

Una apuesta lay tiene responsabilidad `stake_del_backer × (cuota_lay − 1)`. El auditor expresa todas las asignaciones como **capital comprometido**: una unidad es stake para back y responsabilidad para lay. Por unidad de responsabilidad, un lay gana `1/(cuota_lay−1)` cuando pierde la selección, y pierde 1 cuando ésta gana; los reembolsos y medias liquidaciones conservan sus fracciones.

La comisión del exchange se descuenta del **beneficio neto positivo del mercado**, no del cobro bruto ni de cada pata ganadora por separado. Así lo establece [Betfair Charges](https://www.betfair.com/GBR/en/aboutUs/Betfair.Charges/); la tasa aplicable depende de la cuenta y región, por lo que no se presupone un porcentaje universal. Debe enviarse `commission_rate` incluso si es cero. `exchange_market_id` identifica las patas que pueden compensarse antes de comisión; si falta, el motor las trata como grupos separados, una cota conservadora.

La comisión por grupo `g` es `c_g × max(P/L_g, 0)`. El retorno total es una función cóncava por tramos. El auditor representa exactamente su envolvente inferior de funciones lineales para los subconjuntos evaluados. Esto permite hallar cruces back/lay estrechos sin descontar erróneamente comisión a una pata que queda compensada dentro del mismo mercado. Tasas incompatibles para el mismo grupo se rechazan. Otros cargos, impuestos, cambios de moneda o promociones no están modelados.

## Optimización y cobertura de estados

Para cada subconjunto de dos o tres patas se maximiza `z` sujeto a capitales no negativos, suma de capitales 1 y retorno neto al menos `z` en cada estado. Dos patas se resuelven mediante extremos e intersecciones de rectas. Tres patas se resuelven por vértices de la envolvente sobre el triángulo de asignaciones; se evalúan también sus bordes. La implementación no depende de SciPy y no atribuye una probabilidad a los estados.

No se recorta una cuadrícula de goles suponiendo que más goles son imposibles. Para las funciones de liquidación implementadas, sea `K` mayor o igual que todos los umbrales absolutos, componentes de cuarto y marcadores exactos. Los representantes de `[0, 2K+4]²` contienen cada clase posible de pagos, incluidos desbordes:

1. Con ambas coordenadas hasta `K` se conserva el marcador tal cual.
2. Si una coordenada supera `K`, las comparaciones individuales, total y marcador exacto que le conciernen ya están saturadas. Se conserva la otra coordenada y la diferencia cuando cae entre `−K` y `K`; fuera de ese rango basta un representante de magnitud `K+1` o `K+2` con la misma paridad.
3. Si ambas superan `K`, se coloca la menor en `K+1` y se aplica la misma regla a la diferencia. Esto conserva ganador, margen, hándicaps, BTTS, todas las comparaciones con umbrales y paridad del total.

Por eso la comprobación de la cola es una partición exacta de pagos, no una aproximación a la masa de probabilidad. Umbrales mayores que 64 se rechazan para evitar una matriz de tamaño descontrolado; no se aproximan. El certificado informa límite de umbrales, representantes y `overflow_checked`.

Para deportes/mercados categóricos ajenos al marcador se utiliza `expected_outcomes`, declarado exhaustivo por el adaptador. El motor marca `unverified_outcome_partition` hasta que el adaptador verifique esa enumeración. No mezcla particiones categóricas diferentes sin un mapa conjunto.

## Contratos, relojes y límites de búsqueda

Sólo se comparan el mismo `event_id`, `period`, `settlement_rules`, `statistic` y `settlement_basis`. `statistic=goals`, `corners` y `cards` crean matrices distintas. La ausencia de `statistic` se interpreta como `match_score`; es responsabilidad del adaptador identificar correctamente la métrica, no convertir mercados de córners o tarjetas en goles. Nombres de equipos distintos deben normalizarse antes de ingresar.

Por defecto se rechazan cotizaciones sin timestamp con zona horaria, de más de 900 segundos o más de dos segundos en el futuro. Un desfase entre patas superior a 120 segundos deja el hallazgo como relación sin sincronización. Las ventanas son configurables. Para investigar históricos sin fecha de cuota puede activarse `allow_unverified_timestamps=True`: el resultado será únicamente una relación de precios y no una oportunidad sincronizada. La hora de descarga no prueba la hora de cada precio.

Se conserva la mejor cuota de cada pata idéntica antes de construir matrices. La prueba de suma inversa examina los contratos completos disponibles, incluso si tienen muchos resultados categóricos. La búsqueda entre mercados evalúa sólo dos o tres patas y, por defecto, hasta 24 patas distintas por grupo. Las relaciones de dominancia/síntesis se limitan a 64. El orden prioriza mercados de resultado y líneas cercanas al total 2,5. `coverage` informa las patas examinadas y los certificados; `cross_search_capped`, `relation_search_capped` y `search_exhaustive=false` hacen visible el alcance.

No encontrar una cobertura con ese alcance **no demuestra ausencia de arbitraje**, ni constituye una búsqueda completa de todas las combinaciones o de todo el catálogo de una casa.

## API

```python
from datetime import datetime, timezone
from engine.market_audit import audit_event

quotes = [{
    "event_id": "fixture-id",
    "market": "totals",
    "selection": "over",
    "line": 2.5,
    "odds": 2.05,
    "bookmaker": "bookmaker-id",
    "period": "90m",
    "statistic": "goals",
    "settlement_basis": "whole_period_score",
    "settlement_rules": "documented-common-contract-id",
    "last_update": "2026-10-30T12:00:00+00:00",
    "verified_rules": False,
    "available_limit": None,
}]
result = audit_event(quotes, now=datetime.now(timezone.utc),
                     max_cross_quotes=18, max_relation_quotes=48)
# result: summary, candidates, relations, rejected, coverage
```

Mercados canónicos de marcador: `1x2`, `double_chance`, `dnb`, `btts`, `correct_score`, `totals`, `team_totals`, `asian_handicap`, `european_handicap`, `odd_even`, `winning_margin`. Se aceptan alias `h2h`, `draw_no_bet`, `spreads`, `alternate_spreads`, `alternate_totals` y `alternate_team_totals`. En asiático la línea pertenece al equipo seleccionado: local −0,25 y visitante +0,25. En europeo la línea se suma siempre al local. Un total de equipo necesita `team=home|away`; un marcador exacto puede indicar `score=[2,1]`.

Selecciones: `home/draw/away`, `home_draw/draw_away/home_away`, `yes/no`, `over/under`, `odd/even`. Mercados arbitrarios necesitan `expected_outcomes` y selecciones normalizadas de ese mismo conjunto. Se conservan las denominaciones de la fuente en `source` si el adaptador las proporciona; no se consulta ninguna API ni se gastan créditos desde este módulo.

Los ejemplos de este documento son pruebas algebraicas y casos de test, no cuotas observadas ni una rentabilidad histórica estimada.
