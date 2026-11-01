# Menos de 2,5 goles: comprobación en la base grande

Misma métrica que la prueba SGodds, usando cuotas Bet365 reales registradas en Club Football / Football-Data.

| Muestra | Partidos | Aciertos | ROI simulado |
|---|---:|---:|---:|
| Completa | 156684 | 79577 (50.79%) | -6.20% |
| Posterior a partir de 2019-08-25 | 52272 | 25903 (49.55%) | -6.16% |

Una unidad por partido; beneficio exacto = suma(acierto × cuota individual − 1).
Se apostaron 156684 unidades simuladas, se devolvieron 146966.38; resultado -9717.62.
El calibrador entrenado con fechas anteriores seleccionó 1 apuestas posteriores con EV estimado positivo.

No se buscaron ligas, equipos ni rangos de cuota ganadores. Esta comprobación es retrospectiva, sin intervalo de confianza calculado aquí.
El archivo se superpone con otras fuentes; sus partidos no deben sumarse como observaciones independientes.
Los precios no están verificados como ofertas ejecutables.

Código reproducible: `python3 scripts/validate_under25_large_archive.py --as-of 2026-10-30`.
Auditoría: `data/analysis/under25_large_archive_check.json` (SHA, filtros, duplicados, fechas y resultados).
