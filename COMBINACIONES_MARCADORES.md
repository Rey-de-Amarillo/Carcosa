# Combinaciones de marcadores y goles

Se revisaron 100020 coberturas explícitas en 3257 partidos y 50 variantes de plantilla. Positivas al precio registrado: **0**.

Incluye ganador/empate/visitante; empate dividido entre 0–0, 1–1, 2–2, 3–3, 4–4 y otro marcador; Over más todos los marcadores bajos; Under más todos los totales altos, incluido el extremo sin límite; ambos marcan; primer equipo en marcar; y sustituciones descanso/final.

Mejor plantilla: FT: Under 3.5 + all high buckets including tail, Racing vs Villarreal (2026-08-16 23:00:00); piso teórico -3.160139%.

| Apuesta | Cuota | Importe por 100 |
|---|---:|---:|
| Ou_02 | 1.53 | 63.294027 |
| Tg_04 | 5.2 | 18.623050 |
| Tg_05 | 10.0 | 9.683986 |
| Tg_06 | 21.0 | 4.611422 |
| Tg_07 | 50.0 | 1.936797 |
| Tg_08 | 90.0 | 1.075998 |
| Tg_09 | 125.0 | 0.774719 |

Una cobertura exige que TODOS los resultados estén incluidos, también los marcadores extremos. Se usan pagos de apuestas separadas y reparto inverso a la cuota; no se multiplican cuotas de sucesos correlacionados.

También se liquidaron históricamente 95 selecciones con resultado determinable por marcador. 0 tienen ROI nominal positivo al mirar toda la muestra; esto es exploratorio, no una ventaja probada.

La cartera elegida sólo con el tramo anterior seleccionó 0 campos. Resultado posterior: {'bets': 0, 'returned_units': 0.0, 'profit_units': 0.0, 'roi': None}.

Los campos de primer goleador local/visitante quedan fuera del ROI por falta de orden de goles. El campo ningún gol sí es determinable. Las cuotas no están verificadas como ejecutables o simultáneas.

Resultados, fórmulas de cobertura y datos de cada mejor plantilla: `data/analysis/football_score_combinations.json`.
Código: `python3 scripts/football_score_combinations.py`.
