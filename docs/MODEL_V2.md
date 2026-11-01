# Modelo de goles V2

V2 reemplaza las cuatro medias separadas por localía del baseline por un ajuste
conjunto de ataque y defensa de cada equipo. Se calcula con la biblioteca
estándar de Python y no necesita servicios de inteligencia artificial, cuentas
pagas ni dependencias científicas instaladas.

## Qué cambia

La intensidad de goles del local es `base_local × ataque_local × defensa_visitante`.
La visitante usa `base_visitante × ataque_visitante × defensa_local`. Un valor
de defensa mayor que uno significa que el equipo permite más goles. La fuerza
de un equipo se estima contra sus adversarios y con sus partidos en ambas
localías. No se confunde marcar dos goles contra una defensa débil con hacerlo
contra una defensa fuerte.

El ajuste alterna bloques condicionales de factores Poisson. Cada factor se
regulariza hacia uno con un prior Gamma y fuerza fija de 12 pseudo-goles. Las
tasas de liga se regularizan con diez partidos equivalentes y medias iniciales
de 1,45 y 1,15 goles. La ventana abarca tres años y cada observación pierde la
mitad del peso cada 365 días. Se realizan doce iteraciones, con inicio en el
ajuste anterior. Estos son parámetros de desarrollo fijados para comparar los
candidatos, no una búsqueda de la combinación que maximiza el ROI del test.

La escala de ataque y defensa tiene una ambigüedad: multiplicar una y dividir
la otra puede conservar las intensidades. El código fija su media geométrica
en uno y ajusta los interceptos conservando las intensidades. Esta operación
se prueba explícitamente.

Los parámetros se vuelven a ajustar cada catorce días. La fecha de entrenamiento
del registro es la última fecha realmente usada por ese ajuste, mientras que
la última fecha de resultados observados se conserva en otro campo. Tras una
pausa larga, la llegada de resultados nuevos fuerza un ajuste adicional para
no aparentar que parámetros de una temporada anterior están actualizados.

## Marcadores bajos

Se compara una variante independiente con otra que corrige las celdas 0–0,
0–1, 1–0 y 1–1 mediante el factor propuesto por Dixon y Coles. La correlación
`rho` se estima únicamente en la ventana pasada, con una penalización fuerte
hacia cero. Se limita al dominio que conserva probabilidades positivas para
las intensidades de cada nuevo partido. La corrección mantiene las marginales
de goles de cada equipo.

Es una aproximación propia en dos etapas: ajuste regularizado de intensidades
y posterior ajuste de la corrección. **No reproduce el estimador de máxima
verosimilitud completo del artículo ni sus resultados de apuestas.** La idea
de fuerzas conjuntas y corrección de marcadores bajos viene de
[Dixon y Coles (1997)](https://research.lancaster-university.uk/en/publications/modelling-association-football-scores-and-inefficiencies-in-the-f/).
El uso de fuerzas que cambian con el tiempo también está motivado por la
literatura de modelos dinámicos; este código no implementa el modelo bayesiano
de [Rue y Salvesen (2000)](https://doi.org/10.1111/1467-9884.00243).

## Distribución y mercados derivados

`score_grid` devuelve una cuadrícula normalizada de marcadores, su masa retenida
antes de normalizar y el `rho` efectivamente aplicado. La cuadrícula incluye
como mínimo hasta 16 goles por equipo y se amplía con las intensidades.
De ella se obtienen 1X2, totales y ambos marcan de forma coherente. La misma
distribución permite liquidar hándicaps y líneas asiáticas cuando existen las
reglas correspondientes; disponer de una probabilidad calculable no demuestra
que el mercado sea rentable.

Una distribución del marcador final no identifica al primer goleador, el minuto
del primer gol, las tarjetas ni los córners. Esos mercados requieren otros
modelos y datos, y no reciben una validación prestada de V2.

## Cronología y abstenciones

`predict` sólo puede usar resultados de fechas anteriores. `update_batch`
recibe una sola fecha completa y se ejecuta después de pronosticar todos sus
partidos. Cada liga mantiene estado independiente. El replay ordena los datos
antes de procesarlos, por lo que cambiar el orden del archivo no cambia sus
probabilidades.

La elegibilidad exige 120 partidos previos de liga, ocho de cada participante,
seis partidos equivalentes efectivos y un ajuste con información de no más de
45 días. Equipos desconocidos y canchas neutrales generan abstención. Los
partidos neutrales no se incorporan al ajuste de localía.

## Protocolo de comparación

Se usa el período anterior a 2022 para acumular estado y 2022–2023 como período
de comparación de desarrollo. Los dos candidatos son V2 independiente y V2
con corrección de marcadores bajos. La selección se hace por log loss pareado,
no por beneficio retrospectivo. Los resultados de 2024–2026 del primer baseline
ya fueron inspeccionados y no pueden rebautizarse como una muestra virgen.
Una comprobación prospectiva nueva comienza después de congelar los cambios,
con resultados todavía no disponibles a la fecha de desarrollo.

El archivo `/tmp/model-v2-development.json` contiene la comparación reproducida
con los candidatos fijados. El análisis final debe preservar la muestra común
y presentar el mercado sin margen en esos mismos partidos. Mejorar al baseline
anterior y superar a las casas son dos comprobaciones distintas.

En la corrida de desarrollo, sobre los mismos **10.855 partidos de 2022–2023**:

| Referencia | Log loss | Brier multiclase |
| --- | ---: | ---: |
| Baseline V1 | 1,011641 | 0,604907 |
| V2 independiente | 1,007097 | 0,601768 |
| V2 con corrección de marcadores bajos | 1,006531 | 0,601509 |
| Mercado sin margen proporcional | 0,988567 | 0,589365 |

V2 mejoró al baseline en ambos años por separado, pero el mercado mantuvo un
error menor. La mejora media de log loss de V2 corregido frente a V1 fue
0,005110, con banda bootstrap por fecha de 0,003315–0,007137 (400 réplicas,
semilla 20261030 y fechas ordenadas de forma determinista).
Esta banda resume una comparación de desarrollo: no acredita una ventaja de
apuestas ni corrige todos los efectos de selección de modelos o dependencia
serial. No se eligieron parámetros según el ROI de este período.

## Interfaz

```python
from engine.models_v2 import OnlineGoalsV2, replay_predictions, score_grid

model = OnlineGoalsV2(rho_mode="fitted")
prediction = model.predict("Equipo A", "Equipo B", "2026-10-31")
# Sólo después de finalizar toda esa fecha:
model.update_batch(partidos_finalizados_de_la_fecha)

for record in replay_predictions(historial, include_grid=False):
    # prediction conserva intensidades, rho, probabilidades y fecha del ajuste.
    procesar(record)
```

`replay_predictions` es un iterador. Omitir la cuadrícula en una caché evita
almacenar millones de números repetidos; se puede reconstruir con las
intensidades y `rho_applied`. La implementación devuelve `ready_for_live=False`:
el experimento y las cuotas necesitan una validación operativa adicional.
