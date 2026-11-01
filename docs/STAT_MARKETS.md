# Primer tiempo, córners y amarillas

Estos modelos amplían la cobertura estadística con objetivos que sí existen en
el histórico descargado. Evalúan probabilidades con resultados reales y fechas
previas; **no tienen cuotas históricas equivalentes**, por lo que devuelven
`odds_events=0` y `roi=None`. Un porcentaje de clasificación correcto no es el
porcentaje de apuestas ganadas ni acredita una ventaja de precio.

## Separación de objetivos

Cada liga mantiene tres estados independientes:

| Familia | Etiquetas usadas | Salidas |
| --- | --- | --- |
| Primer tiempo | Goles locales y visitantes al descanso | 1X2, más de 0,5, más de 1,5 y ambos marcan en ese período |
| Córners | Córners locales y visitantes | Total esperado y probabilidades de superar 8,5, 9,5 y 10,5 |
| Amarillas | Amarillas locales y visitantes | Total esperado y probabilidades de superar 3,5 y 4,5 |

Primer tiempo **no usa la mitad de las tasas del marcador final**. Sus tasas
se aprenden de las columnas específicas del descanso y el cálculo ni siquiera
lee los goles finales. Sus priors débiles iniciales son 0,65 y 0,50 goles y
pierden relevancia al acumular resultados propios.

Las amarillas no se equiparan a puntos por tarjetas, rojas, faltas ni tarjetas
de jugadores. El dato del proveedor sólo respalda el conteo de amarillas de
equipo. Las reglas sobre segunda amarilla, suplentes y cuerpo técnico deben
verificarse antes de comparar el resultado con un contrato de una casa.

## Tasas y sobredispersión

Las medias local y visitante de cada estadística se regularizan con veinte
partidos equivalentes. Se estiman también factores de producción y concesión
por equipo, usando ambas localías, regularizados hacia la media de la liga.
La combinación de factores se encoge con una raíz cuadrada: es una decisión
fija de desarrollo para moderar la multiplicación de dos razones ruidosas.
Los conteos suficientes envejecen con semivida de 365 días.

El primer tiempo utiliza una distribución Poisson de marcadores. Córners y
amarillas utilizan una binomial negativa para el **total**:

`Var(total) = media + alpha × media²`.

`alpha` se estima con momentos de errores de predicciones anteriores: suma de
`(observado − media_previa)² − observado`, dividida por la suma de las medias
previas al cuadrado. Se regulariza con treinta observaciones equivalentes,
un prior `alpha=0,10`, y se limita a 0–1. Las intensidades de cada observación
se calculan antes de actualizar cualquier resultado de esa fecha. Si la
dispersión estimada llega a cero, se utiliza Poisson. El exceso de variación
puede recoger también errores del modelo; no es una medición pura de una
propiedad física del deporte.

Las probabilidades se calculan con recurrencias de las distribuciones y no
requieren simulaciones aleatorias. Las líneas de medio punto no tienen push.
Otros contratos o líneas requieren reglas de liquidación propias.

La banda de sensibilidad que acompaña a la media es heurística. No tiene
cobertura temporal comprobada y **no es un intervalo de confianza validado**.

## Cronología, faltantes y referencia

Se pronostica la fecha completa antes de actualizarla. Las ligas y familias
no comparten estados. Un dato vacío se conserva como faltante; nunca se
convierte en cero. Los ceros observados sí son resultados válidos. Las filas
incompletas no entrenan ni evalúan esa familia, aunque puedan servir para otra.

La elegibilidad exige 120 observaciones previas de liga, ocho por equipo, seis
equivalentes efectivos y una observación de la familia en los últimos 45 días.
Las canchas neutrales se abstienen y no actualizan los factores de localía.

Para cada mercado se calcula una referencia de **frecuencia previa de su propia
liga**, regularizada y con decaimiento temporal. El modelo y esa climatología
se puntúan en los mismos partidos. El Brier de 1X2 es la suma de tres errores
cuadráticos (0–2); en objetivos binarios se usa un error cuadrático (0–1).
Los rangos no se deben mezclar para declarar que un mercado es mejor que otro.

La auditoría desde 2024 es retrospectiva y sus datos generales ya fueron vistos
en el desarrollo anterior. No se presenta como una muestra prospectiva intacta
ni se optimizaron parámetros para mejorar un ROI sin cuotas.

## Uso

```python
from engine.stat_markets import run_stat_market_evaluation, predict_stat_fixture

metrics = run_stat_market_evaluation(rows, audit_start="2024-01-01")
prediction = predict_stat_fixture(rows, {
    "sport": "football", "league": "England Premier League",
    "date": "2026-10-31", "home_team": "Equipo A", "away_team": "Equipo B",
})
```

La predicción devuelve `period_half`, `corners` y `yellow_cards`, cada una con
su muestra, fecha de entrenamiento, elegibilidad y motivos. Los alias de líneas
`prob_over_9_5` y `prob_over_9.5` son equivalentes. Un equipo desconocido o una
familia sin datos conserva `eligible=False` y no habilita una decisión.

Los resultados reales de la corrida están en `/tmp/stat-market-evaluation.json`.
Las pruebas incluyen faltantes, ceros, causalidad, independencia de los goles
finales, sobredispersión, fallback Poisson, aislamiento por liga y ausencia de
cuotas o rentabilidad fabricadas.
