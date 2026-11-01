# Valor esperado a partir de diferencias entre cuotas

**La comparación entre casas produjo una señal histórica positiva, pero Bet365 por separado fue negativa.** Se mantuvo la misma regla para todo el período posterior a 2022; no se eligió el umbral que más dinero hubiera ganado.

## Regla y fórmula

1. Tomar las cuotas anteriores al cierre de un mercado completo. Para 1X2, exigir al menos tres casas de referencia y excluir la casa donde se apuesta. Para más/menos de 2,5 goles, el archivo solo trae Bet365 y Pinnacle: se usa la otra casa como referencia.
2. Quitar el margen con el método de potencia: encontrar `k` tal que `sum((1/cuota_i)^k) = 1`; la probabilidad de cada resultado queda `(1/cuota_i)^k`. Promediar las probabilidades de las casas de referencia.
3. Estimar `EV = probabilidad × cuota_ofrecida − 1`. Apostar una unidad cuando `EV >= 0,03`, cuota entre 1,20 y 5,00 y margen del mercado entre −2% y 15%.
4. Si un mismo partido ofrece varias opciones, conservar solamente la de mayor EV. Nunca sumar posiciones correlacionadas como si fueran partidos independientes.

Por ejemplo, probabilidad `0,55` y cuota `1,90` dan `0,55 × 1,90 − 1 = +0,045`: **4,50 por cada 100 apostados de valor esperado**, siempre que esa probabilidad describa bien los partidos seleccionados. El porcentaje de victorias necesario cambia con la cuota: `1 / cuota`.

## Separación temporal

- 1X2: entrenamiento hasta 2018; validación 2019–2021; prueba final desde 2022.
- Goles: entrenamiento hasta 2020; validación 2021; prueba final desde 2022. Los precios de goles comparables empiezan en 2019.
- Se compararon tres estimadores: consenso sin transformar; ajuste de temperatura y sesgo por resultado; mezcla del consenso con la probabilidad sin margen de la casa ofrecida. Los ajustes se entrenaron solo en el período anterior y se eligieron por pérdida logarítmica de validación, sin usar rentabilidad final. En ambos mercados ganó el consenso sin transformar.
- Se evaluaron 18.080 partidos 1X2 y 13.317 partidos de goles posteriores a 2022 con referencia válida. El número de apuestas es menor porque se exige superar el precio y el umbral.

## Resultados con una unidad fija por partido

| Casas donde se permite apostar | EV mínimo | Apuestas | Beneficio/unidades | ROI | ROI con cuota 1% peor |
|---|---:|---:|---:|---:|---:|
| Bet365, primario | 3% | 67 | −14,12 | **−21,07%** | −21,86% |
| Bet365, sensibilidad | 0% | 769 | −25,47 | −3,31% | −4,28% |
| Bet365, sensibilidad | 5% | 29 | −4,71 | −16,24% | −17,08% |
| Todas las casas reales, secundario | 3% | 349 | +12,73 | **+3,65%** | +2,61% |
| Todas las casas reales, sensibilidad | 0% | 5.709 | −36,65 | −0,64% | −1,64% |
| Todas las casas reales, sensibilidad | 5% | 105 | +8,39 | +7,99% | +6,91% |

Los cambios de cuota se aplican a **las mismas apuestas**, con el mismo importe, sin volver a seleccionarlas. El 5% aparece como sensibilidad declarada, no como nuevo umbral ganador elegido después del resultado.

Para la regla secundaria de EV ≥3%, el EV medio estimado fue +5,49%, la cuota media 3,206 y se ganaron 135 de 349 apuestas (38,68%; probabilidad media estimada 38,26%). La rentabilidad observada fue +3,65%. La regla fija de Bet365 estimaba +7,64% pero ganó 16 de 67 apuestas (23,88%, frente a 30,43% estimado): un precio aparentemente alto no alcanzó para producir una probabilidad útil en esa selección.

| Año | Apuestas, todas las casas, EV ≥3% | ROI |
|---|---:|---:|
| 2022 | 130 | −0,73% |
| 2023 | 71 | −11,83% |
| 2024 | 49 | +28,84% |
| 2025 | 70 | −10,46% |
| 2026 | 29 | +52,66% |

El intervalo del ROI con remuestreo de bloques mensuales es −13,84% a +21,10% para las 349 apuestas. La suma fue positiva y tres años fueron negativos: **todavía no aparece una regla de valor positivo sostenida en estos precios**. No se convirtió una casa, liga o año ganador a posteriori en estrategia elegida.

## Variables y auditoría

Se registran precio ofrecido, probabilidad sin margen de cada referencia, identidad y cantidad de casas, dispersión entre probabilidades, margen del mercado, resultado, liga, fecha, selección, cuota y beneficio. El JSON incluye Brier, pérdida logarítmica, calibración por intervalos, resultados por mercado/casa/liga/año y remuestreo por fechas y meses.

No se usan columnas `Max`/`Avg` como casas, precios de exchange `BFE`, columnas de cierre como si fueran anteriores, ni resultados actuales para construir probabilidades. Se excluye Pinnacle desde 23/07/2025 por el problema conocido del suministro de cuotas. Las columnas anteriores al cierre no incluyen hora exacta verificable de observación.

La revisión detectó una discrepancia grande de origen: Giresunspor–Sivasspor, 02/04/2022, más de 2,5 Bet365 2,30 frente a Pinnacle 1,51; el margen Pinnacle era 11,27%. Está así en el archivo original `2122_T1.csv`. El código mantiene el resultado primario y calcula aparte un diagnóstico exploratorio que exige margen Pinnacle ≤5% cuando es referencia. Se etiqueta expresamente como introducido después de la primera prueba y no reemplaza la regla principal.

Ese diagnóstico dejó 42 apuestas Bet365 con ROI −17,88%, y 320 apuestas entre todas las casas con ROI +3,69% (intervalo mensual −12,29% a +20,76%). Por lo tanto, retirar referencias Pinnacle con mayor margen no cambia la conclusión principal.

## Reproducción

```bash
python3 scripts/research_market_reference_ev.py
python3 -m unittest tests.test_research_market_reference_ev
```

Código: `scripts/research_market_reference_ev.py`. Resultados completos: `data/analysis/research_market_reference_ev.json`. Apuestas primarias: `data/analysis/research_market_reference_ev.trades.jsonl`. Todas las sensibilidades con su etiqueta: `data/analysis/research_market_reference_ev.scenarios.jsonl`. Se verifica que la cuota objetivo no altere su propia referencia, que datos futuros no cambien la selección del calibrador, que cada partido genere una sola apuesta y que el estrés mantenga las selecciones.
