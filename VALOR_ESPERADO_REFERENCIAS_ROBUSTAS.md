# Valor esperado con desacuerdo entre casas

**Apareció un candidato positivo al exigir que incluso la referencia menos favorable supere el precio ofrecido:** 219 apuestas anteriores a 2022, ROI +10,22%; 76 apuestas desde 2022, ROI +16,82%.

## Regla fija

Mercado 1X2: local, empate o visitante. Cuotas entre 1,20 y 5,00. Al menos tres casas reales distintas de la casa donde se apuesta. Se elimina el margen de cada casa con el método de potencia. Se excluyen columnas agregadas `Max`/`Avg`, exchange `BFE` y Pinnacle desde 23/07/2025.

Para un resultado `s`, cada casa de referencia produce una probabilidad `p_c(s)`. Se comparan tres reglas, todas con el mismo umbral:

```text
p_media = promedio_c p_c(s)
p_minima = mínimo_c p_c(s)
p_media_menos_sd = máximo(0, promedio_c p_c(s) − desvío_c p_c(s))

EV = p_regla × cuota_ofrecida − 1
seleccionar si EV >= 0,03
```

Se apuesta una unidad y se conserva una sola selección por partido: la de mayor EV según esa regla. La casa objetivo nunca participa en su propia referencia. `p_minima` y `media−SD` expresan robustez entre modelos de casas; no son intervalos estadísticos de la probabilidad verdadera.

## Resultados completos

| Casas permitidas | Referencia | Apuestas 2018–2021 | ROI 2018–2021 | Apuestas desde 2022 | ROI desde 2022 | ROI posterior con cuota 1% peor |
|---|---|---:|---:|---:|---:|---:|
| Todas | Media | 636 | +10,01% | 308 | +4,15% | +3,11% |
| Todas | **Mínima** | **219** | **+10,22%** | **76** | **+16,82%** | **+15,65%** |
| Todas | Media−1SD | 275 | +12,27% | 96 | +7,01% | +5,94% |
| Bet365 fija | Media | 131 | +3,77% | 42 | −36,93% | −37,56% |
| Bet365 fija | Mínima | 18 | −0,89% | 4 | +52,50% | +50,98% |
| Bet365 fija | Media−1SD | 33 | +25,94% | 9 | −32,22% | −32,90% |

Las cuatro apuestas de Bet365 no se tratan como una estrategia validada. Se muestran las tres reglas y ambos universos de casas, incluidas las pérdidas, sin escoger después el umbral ni el nivel de penalización que maximice el resultado final.

Las 76 apuestas con referencia mínima suman **+12,78 unidades**: 39 victorias de 76 (51,32%), cuota media 2,714 y EV estimado medio +6,34%. Las casas elegidas fueron IW16, WH16, Pinnacle10, 1XB8, BW7, Bet3654, BF4, BMGM4, VC3, BV2, LB1 y BFD1. La cuota se empeora un 1% sobre **las mismas apuestas**, sin cambiar la selección.

| Año | Apuestas, referencia mínima, todas las casas | ROI |
|---|---:|---:|
| 2022 | 26 | +21,73% |
| 2023 | 13 | +5,38% |
| 2024 | 14 | +35,36% |
| 2025 | 17 | −37,76% |
| 2026 | 6 | +131,67% |

Intervalo de ROI con bloques mensuales: **−10,57% a +43,07%**. El candidato es positivo en ambos períodos y resiste un precio 1% peor, con una muestra posterior pequeña y un año negativo. Son números de una hipótesis a seguir acumulando; no una demostración de rentabilidad infinita.

Ejemplo real de cómo se selecciona: Bayern–Mönchengladbach, 07/01/2022, victoria Bayern en IW a 1,45. La menor probabilidad sin margen entre Bet365/BW/VC/WH/Pinnacle era 0,72018775. Por tanto, `0,72018775 × 1,45 − 1 = +4,4272%`. Entró por precio, aunque esa apuesta individual perdió. La regla busca promedio positivo y admite derrotas.

## Procedencia de la prueba

Estas tres políticas fueron fijadas **después de revisar un experimento previo** de consenso medio. Por eso se registran como investigación exploratoria y no como una prueba final completamente independiente. No se ajustó ningún parámetro a las ganancias posteriores. El período 2018–2021 se informa como referencia histórica; no se usa para elegir un ganador entre estas tres reglas.

Se usan las columnas anteriores al cierre del archivo local `quote_history.jsonl`; no se emplean columnas de cierre ni resultados para calcular EV. El archivo original no contiene hora individual verificable de cada precio.

## Código y reproducción

```bash
python3 scripts/research_robust_reference_ev.py
python3 -m unittest tests.test_research_robust_reference_ev
```

Código: `scripts/research_robust_reference_ev.py`. Resultados: `data/analysis/research_robust_reference_ev.json`. Todas las selecciones, con su período y política: `data/analysis/research_robust_reference_ev.trades.jsonl`. Tres tests verifican los cálculos de mínimo/desvío, exclusión de la casa objetivo, cantidad mínima de referencias y que cambiar el resultado no altere el EV ni la regla.
