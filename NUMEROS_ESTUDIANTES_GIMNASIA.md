# Estudiantes Río Cuarto–Gimnasia LP · números de Bet365

Partido:30/10/2026,19:00 de Salta. Captura13:36:46–14:08:24:12 secciones inspeccionadas,485 lecturas de precios y467 selecciones sintácticas distintas. Hay repeticiones/equivalencias; no son485 oportunidades independientes. Algunas secciones abiertas mostraron etiquetas sin precios.

## Candidato principal: Gimnasia menos de5,5 córners a1,80

| Referencia | Partidos | Media de córners | Cumplió menos de6 |
|---|---:|---:|---:|
| Gimnasia visitante, córners propios | 17 | 3,706 | 14/17 |
| Visitantes contra Río Cuarto local | 15 | 4,333 | 10/15 |

No se cuentan esos15 partidos como partidos de Gimnasia. La media del modelo es λ=(3,7059+4,3333)/2=4,0196. La ponderación50/50 es un supuesto exploratorio.

| Modelo | p(0–5 córners) | Cuota de equilibrio | EV por $100 a1,80 |
|---|---:|---:|---:|
| Poisson | 78,21% | 1,2787 | +$40,77 |
| Binomial negativa | 76,58% | 1,3058 | +$37,84 |

**EV=$100×(p×1,80−1).** Con p=76,58%, el modelo da +$37,84 esperados por100. Una apuesta individual devuelve beneficio+80 si acierta o−100 si falla.

Poisson usa P(C≤5)=exp(−λ)×Σ(k=0..5)λ^k/k!. Binomial negativa admite varianza μ+αμ²; α=0,065631.

El remuestreo de20.000 muestras, separado por las dos cohortes, da EV binomial-negativo de +$17,38 a +$55,47 por100. Es incertidumbre del modelo bajo estacionariedad; no cubre cambios tácticos, alineación, selección entre muchas cuotas ni demuestra rentabilidad futura.

| Cambio de media | Córners esperados | EV Poisson por100 | EV binomial negativa por100 |
|---|---:|---:|---:|
| +0% | 4,02 | +$40,77 | +$37,84 |
| +10% | 4,42 | +$28,93 | +$27,00 |
| +20% | 4,82 | +$16,44 | +$15,93 |
| +30% | 5,23 | +$3,76 | +$4,96 |
| +40% | 5,63 | −$8,70 | −$5,67 |
| +50% | 6,03 | −$20,63 | −$15,77 |

El equilibrio Poisson se alcanza en λ=5,3456: una subida de 32,99% sobre la media estimada. El mercado exige p>55,56% a cuota1,80. La cuota se reconfirmó a las14:08:24 de Salta.

## Goles y combinaciones concretas

Son EV de la distribución conjunta de goles, no ROI histórico observado. Se conservan las mismas políticas y dos ventanas históricas; no se multiplican marginales de selecciones correlacionadas.

| Selección | Cuota | EV central por100 | Peor ventana | Percentil2,5 de EV remuestreado |
|---|---:|---:|---:|---:|
| Menos de2,25 asiático | 1,80 | +$11,19 | +$1,40 | −$5,66 |
| Menos de2,5 | 1,61 | +$9,45 | +$0,53 | −$5,98 |
| Menos de3,5 | 1,22 | +$4,82 | +$0,11 | −$3,62 |
| Ambos marcan:No | 1,75 | +$6,82 | +$2,08 | −$6,73 |
| Menos de2,5 + Ambos marcan:No | 2,00 | +$8,34 | −$1,04 | −$10,14 |

Menos de2,5 + BTTSNo a2,00 gana con00,10,01,20o02. Su probabilidad es la suma de esas cinco celdas: 54,17%. El EV central es +$8,34 por100, pero cambia de signo con la otra ventana. Ninguna ofertaFT de goles conserva EV positivo en el percentil2,5 de los remuestreos.

En Under2,25 a1,80, con100 apostados:0–1goles deja+80; exactamente2goles deja+40;3omás deja−100. Fórmula:EV=0,80P(G≤1)+0,40P(G=2)−P(G≥3). Su probabilidad de media ganancia no permite usar1/p como cuota justa.

## Boosts y diferencias de precio

- Gimnasia gana + mayoría estricta de córners +3omásgoles a7,00:se dio3/32 veces2026 (9,38%), frente a14,29% necesario. Sensibilidad usando esa frecuencia y precioactual:−34,38por100. Se interpreta Over2Goals como3omás, sin tratarlo como Asian2 conpush; la regla exacta de la combinación sigue sin verificar.
- Auzmendi1+rematealarco + Torres1+rematealarco + Gimnasia gana a6,50:3/26 con ambos participantes;2/9 siendo ambos titulares. Cada condición requiere su propia muestra; faltan alineaciones y valoración de Suplente+.
- Boost9,00:ambos equipos2+córners en cada mitad + BTTS. Las61 fichas no tienen córners por mitad:probabilidad/EV sin estimar.
- Menos de0,5goles paga8,00;0–0paga7,50;empate+BTTSNo paga7,50. Bajo iguales reglas de período/liquidación,8,00 devuelve50másporcada100 si acierta que7,50. Es mejorprecio para igual marcador; no una cobertura de beneficio seguro.

## Alcance y procedencia

El motor de goles usa6.445 partidos argentinos. La validaciónFT tiene1.499 partidos; OU/BTTS no superan claramente la frecuencia base. Los datos ampliados son61 partidos únicos2026, con30 deRíoCuarto y32deGimnasia y un encuentro compartido. El test por mitades es exploratorio:41eventos.59de64jugadores se identificaron por coincidencias exactas/aliases explícitos; cinco quedan sin correspondencia.
La auditoría de pagos no encontró coberturas positivas en su búsqueda acotada de hasta tres patas. No prueba ausencia universal de arbitraje. Capturas, reglas y límites no están confirmados como contratación simultánea; no se realizaron apuestas.
Fuentes: [Bet365, partido y córners](https://www.bet365.bet.ar/#/AC/B1/C1/D8/E202426204/F3/I5/), [ESPN, ficha oficial del evento](https://site.api.espn.com/apis/site/v2/sports/soccer/arg.1/summary?event=401841655). Se conservaron las61 fichas históricas, CSV originales y hashes localmente.

Archivos completos: data/analysis/bet365_arg_quotes.json, arg_betting_numbers.json, arg_count_empirics.json, arg_player_empirics.json y arg_corner_stress.json. Hash de captura:06da733ad85623c837a7c8c1dc7f0d567233fd70bdc7adec178cdb4aed31e6ed.

## Tabla de todos los contratos con modelo de goles

p=retorno positivo, incluidas medias ganancias; EVpor100 neto. Mitades y combinaciones de mitades están marcadas como exploratorias. Los campos vacíos de otros contratos se conservan enJSON con motivo, sin inventar probabilidades.

| ID | Contrato | Cuota | p | EV por100 | Método/estado |
|---|---|---:|---:|---:|---|
| q0001 | Full Time Result · home · ft | 4,20 | 23,33% | −$2,01 | modelled_final_score_contract |
| q0002 | Full Time Result · draw · ft | 3,30 | 31,77% | +$4,85 | modelled_final_score_contract |
| q0003 | Full Time Result · away · ft | 1,95 | 44,90% | −$12,45 | modelled_final_score_contract |
| q0004 | Goals Over/Under · over · línea0.5 · ft | 1,08 | 85,44% | −$7,47 | modelled_final_score_contract |
| q0005 | Goals Over/Under · under · línea0.5 · ft | 8,00 | 14,56% | +$16,47 | modelled_final_score_contract |
| q0006 | Goals Over/Under · over · línea1.5 · ft | 1,40 | 59,95% | −$16,07 | modelled_final_score_contract |
| q0007 | Goals Over/Under · under · línea1.5 · ft | 2,75 | 40,05% | +$10,14 | modelled_final_score_contract |
| q0008 | Goals Over/Under · over · línea2.5 · ft | 2,25 | 32,02% | −$27,96 | modelled_final_score_contract |
| q0009 | Goals Over/Under · under · línea2.5 · ft | 1,61 | 67,98% | +$9,45 | modelled_final_score_contract |
| q0010 | Goals Over/Under · over · línea3.5 · ft | 4,00 | 14,08% | −$43,69 | modelled_final_score_contract |
| q0011 | Goals Over/Under · under · línea3.5 · ft | 1,22 | 85,92% | +$4,82 | modelled_final_score_contract |
| q0012 | Goals Over/Under · over · línea4.5 · ft | 10,00 | 5,16% | −$48,39 | modelled_final_score_contract |
| q0013 | Goals Over/Under · under · línea4.5 · ft | 1,06 | 94,84% | +$0,72 | modelled_final_score_contract |
| q0014 | Goals Over/Under · over · línea5.5 · ft | 21,00 | 1,61% | −$66,09 | modelled_final_score_contract |
| q0015 | Goals Over/Under · under · línea5.5 · ft | 1,01 | 98,39% | −$0,14 | modelled_final_score_contract |
| q0016 | Goals Over/Under · over · línea6.5 · ft | 51,00 | 0,44% | −$77,58 | modelled_final_score_contract |
| q0017 | Goals Over/Under · under · línea6.5 · ft | 1,00 | 99,56% | −$0,24 | modelled_final_score_contract |
| q0018 | Both Teams to Score · yes · ft | 2,00 | 38,96% | −$22,08 | modelled_final_score_contract |
| q0019 | Both Teams to Score · no · ft | 1,75 | 61,04% | +$6,82 | modelled_final_score_contract |
| q0020 | Draw No Bet · home · ft | 3,00 | 23,33% | +$1,76 | modelled_final_score_contract |
| q0021 | Draw No Bet · away · ft | 1,36 | 44,90% | −$7,17 | modelled_final_score_contract |
| q0022 | Result/Both Teams to Score · and · ft | 9,50 | 7,81% | −$25,81 | modelled_final_score_contract |
| q0023 | Result/Both Teams to Score · and · ft | 6,50 | 15,52% | +$0,89 | modelled_final_score_contract |
| q0024 | Result/Both Teams to Score · and · ft | 4,75 | 13,94% | −$33,80 | modelled_final_score_contract |
| q0025 | Result/Both Teams to Score · and · ft | 3,00 | 30,96% | −$7,12 | modelled_final_score_contract |
| q0026 | Result/Both Teams to Score · and · ft | 4,75 | 17,21% | −$18,23 | modelled_final_score_contract |
| q0027 | Result/Both Teams to Score · and · ft | 7,50 | 14,56% | +$9,19 | modelled_final_score_contract |
| q0028 | Match Goals Range 2–4 · yes · rango2–4 · ft | 1,57 | 54,79% | −$13,98 | modelled_final_score_contract |
| q0029 | Match Goals Range 2–4 · no · rango2–4 · ft | 2,25 | 45,21% | +$1,72 | modelled_final_score_contract |
| q0030 | Correct Score 0–0 · score · [0, 0] · ft | 7,50 | 14,56% | +$9,19 | modelled_final_score_contract |
| q0031 | Half Time Correct Score 0–0 · score · [0, 0] · ht | 2,50 | 44,15% | +$10,37 | modelled_exploratory_timing_contract |
| q0053 | Correct Score · All · score · [1, 0] · ft | 10,00 | 9,91% | −$0,90 | modelled_final_score_contract |
| q0054 | Correct Score · All · score · [2, 0] · ft | 21,00 | 4,24% | −$10,94 | modelled_final_score_contract |
| q0055 | Correct Score · All · score · [2, 1] · ft | 15,00 | 5,09% | −$23,58 | modelled_final_score_contract |
| q0056 | Correct Score · All · score · [3, 0] · ft | 41,00 | 1,11% | −$54,38 | modelled_final_score_contract |
| q0057 | Correct Score · All · score · [3, 1] · ft | 41,00 | 1,34% | −$45,20 | modelled_final_score_contract |
| q0058 | Correct Score · All · score · [3, 2] · ft | 41,00 | 0,80% | −$67,08 | modelled_final_score_contract |
| q0059 | Correct Score · All · score · [4, 0] · ft | 126,00 | 0,22% | −$72,41 | modelled_final_score_contract |
| q0060 | Correct Score · All · score · [4, 1] · ft | 81,00 | 0,26% | −$78,70 | modelled_final_score_contract |
| q0061 | Correct Score · All · score · [4, 2] · ft | 126,00 | 0,16% | −$80,10 | modelled_final_score_contract |
| q0062 | Correct Score · All · score · [4, 3] · ft | 201,00 | 0,06% | −$87,28 | modelled_final_score_contract |
| q0063 | Correct Score · All · score · [5, 0] · ft | 501,00 | 0,03% | −$82,73 | modelled_final_score_contract |
| q0064 | Correct Score · All · score · [5, 1] · ft | 351,00 | 0,04% | −$85,47 | modelled_final_score_contract |
| q0065 | Correct Score · All · score · [5, 2] · ft | 501,00 | 0,02% | −$87,54 | modelled_final_score_contract |
| q0066 | Correct Score · All · score · [1, 1] · ft | 6,00 | 13,81% | −$17,13 | modelled_final_score_contract |
| q0067 | Correct Score · All · score · [2, 2] · ft | 17,00 | 3,06% | −$47,98 | modelled_final_score_contract |
| q0068 | Correct Score · All · score · [3, 3] · ft | 67,00 | 0,32% | −$78,46 | modelled_final_score_contract |
| q0069 | Correct Score · All · score · [4, 4] · ft | 451,00 | 0,02% | −$91,43 | modelled_final_score_contract |
| q0070 | Correct Score · All · score · [0, 1] · ft | 6,00 | 15,58% | −$6,51 | modelled_final_score_contract |
| q0071 | Correct Score · All · score · [0, 2] · ft | 8,50 | 9,88% | −$16,02 | modelled_final_score_contract |
| q0072 | Correct Score · All · score · [1, 2] · ft | 9,00 | 7,78% | −$30,02 | modelled_final_score_contract |
| q0073 | Correct Score · All · score · [0, 3] · ft | 17,00 | 3,96% | −$32,75 | modelled_final_score_contract |
| q0074 | Correct Score · All · score · [1, 3] · ft | 17,00 | 3,11% | −$47,07 | modelled_final_score_contract |
| q0075 | Correct Score · All · score · [2, 3] · ft | 34,00 | 1,23% | −$58,34 | modelled_final_score_contract |
| q0076 | Correct Score · All · score · [0, 4] · ft | 41,00 | 1,19% | −$51,29 | modelled_final_score_contract |
| q0077 | Correct Score · All · score · [1, 4] · ft | 41,00 | 0,94% | −$61,66 | modelled_final_score_contract |
| q0078 | Correct Score · All · score · [2, 4] · ft | 51,00 | 0,37% | −$81,23 | modelled_final_score_contract |
| q0079 | Correct Score · All · score · [3, 4] · ft | 151,00 | 0,10% | −$85,42 | modelled_final_score_contract |
| q0080 | Correct Score · All · score · [0, 5] · ft | 81,00 | 0,29% | −$76,88 | modelled_final_score_contract |
| q0081 | Correct Score · All · score · [1, 5] · ft | 81,00 | 0,22% | −$81,80 | modelled_final_score_contract |
| q0082 | Correct Score · All · score · [2, 5] · ft | 151,00 | 0,09% | −$86,65 | modelled_final_score_contract |
| q0083 | Correct Score · All · score · [3, 5] · ft | 401,00 | 0,02% | −$90,70 | modelled_final_score_contract |
| q0084 | Correct Score · All · score · [0, 6] · ft | 201,00 | 0,06% | −$88,51 | modelled_final_score_contract |
| q0085 | Correct Score · All · score · [1, 6] · ft | 251,00 | 0,04% | −$88,71 | modelled_final_score_contract |
| q0086 | Correct Score · All · score · [2, 6] · ft | 501,00 | 0,02% | −$91,13 | modelled_final_score_contract |
| q0175 | Result/Total Goals2.5 · and · ft | 8,50 | 9,18% | −$21,97 | modelled_final_score_contract |
| q0176 | Result/Total Goals2.5 · and · ft | 7,00 | 14,15% | −$0,95 | modelled_final_score_contract |
| q0177 | Result/Total Goals2.5 · and · ft | 3,60 | 19,44% | −$30,03 | modelled_final_score_contract |
| q0178 | Result/Total Goals2.5 · and · ft | 3,75 | 25,46% | −$4,52 | modelled_final_score_contract |
| q0179 | Result/Total Goals2.5 · and · ft | 15,00 | 3,40% | −$48,98 | modelled_final_score_contract |
| q0180 | Result/Total Goals2.5 · and · ft | 3,75 | 28,37% | +$6,39 | modelled_final_score_contract |
| q0181 | Total Goals/BTTS2.5 · and · ft | 2,75 | 25,15% | −$30,84 | modelled_final_score_contract |
| q0182 | Total Goals/BTTS2.5 · and · ft | 10,00 | 6,87% | −$31,30 | modelled_final_score_contract |
| q0183 | Total Goals/BTTS2.5 · and · ft | 6,00 | 13,81% | −$17,13 | modelled_final_score_contract |
| q0184 | Total Goals/BTTS2.5 · and · ft | 2,00 | 54,17% | +$8,34 | modelled_final_score_contract |
| q0185 | Half BTTS · yes · ht | 5,50 | 10,74% | −$40,96 | modelled_exploratory_timing_contract |
| q0186 | Half BTTS · no · ht | 1,14 | 89,26% | +$1,76 | modelled_exploratory_timing_contract |
| q0187 | Half BTTS · yes · sh | 4,00 | 19,28% | −$22,87 | modelled_exploratory_timing_contract |
| q0188 | Half BTTS · no · sh | 1,22 | 80,72% | −$1,52 | modelled_exploratory_timing_contract |
| q0189 | Team Goals Range2–4 · yes · home · rango2–4 · ft | 4,00 | 18,53% | −$25,90 | modelled_final_score_contract |
| q0190 | Team Goals Range2–4 · no · home · rango2–4 · ft | 1,22 | 81,47% | −$0,60 | modelled_final_score_contract |
| q0191 | Team Goals Range2–4 · yes · away · rango2–4 · ft | 2,25 | 33,01% | −$25,73 | modelled_final_score_contract |
| q0192 | Team Goals Range2–4 · no · away · rango2–4 · ft | 1,57 | 66,99% | +$5,18 | modelled_final_score_contract |
| q0195 | Goal Range All · yes · rango1–2 · ft | 1,83 | 53,42% | −$2,23 | modelled_final_score_contract |
| q0196 | Goal Range All · no · rango1–2 · ft | 1,83 | 46,58% | −$14,77 | modelled_final_score_contract |
| q0197 | Goal Range All · yes · rango1–3 · ft | 1,36 | 71,36% | −$2,95 | modelled_final_score_contract |
| q0198 | Goal Range All · no · rango1–3 · ft | 3,00 | 28,64% | −$14,09 | modelled_final_score_contract |
| q0199 | Goal Range All · yes · rango1–4 · ft | 1,18 | 80,28% | −$5,27 | modelled_final_score_contract |
| q0200 | Goal Range All · no · rango1–4 · ft | 4,50 | 19,72% | −$11,26 | modelled_final_score_contract |
| q0201 | Goal Range All · yes · rango1–5 · ft | 1,11 | 83,83% | −$6,95 | modelled_final_score_contract |
| q0202 | Goal Range All · no · rango1–5 · ft | 6,50 | 16,17% | +$5,13 | modelled_final_score_contract |
| q0203 | Goal Range All · yes · rango1–6 · ft | 1,10 | 85,00% | −$6,50 | modelled_final_score_contract |
| q0204 | Goal Range All · no · rango1–6 · ft | 7,00 | 15,00% | +$4,98 | modelled_final_score_contract |
| q0205 | Goal Range All · yes · rango2–3 · ft | 2,00 | 45,87% | −$8,26 | modelled_final_score_contract |
| q0206 | Goal Range All · no · rango2–3 · ft | 1,72 | 54,13% | −$6,90 | modelled_final_score_contract |
| q0207 | Goal Range All · yes · rango2–4 · ft | 1,57 | 54,79% | −$13,98 | modelled_final_score_contract |
| q0208 | Goal Range All · no · rango2–4 · ft | 2,25 | 45,21% | +$1,72 | modelled_final_score_contract |
| q0209 | Goal Range All · yes · rango2–5 · ft | 1,44 | 58,34% | −$16,00 | modelled_final_score_contract |
| q0210 | Goal Range All · no · rango2–5 · ft | 2,62 | 41,66% | +$9,16 | modelled_final_score_contract |
| q0211 | Goal Range All · yes · rango2–6 · ft | 1,44 | 59,51% | −$14,30 | modelled_final_score_contract |
| q0212 | Goal Range All · no · rango2–6 · ft | 2,62 | 40,49% | +$6,08 | modelled_final_score_contract |
| q0213 | Goal Range All · yes · rango3–4 · ft | 2,75 | 26,86% | −$26,14 | modelled_final_score_contract |
| q0214 | Goal Range All · no · rango3–4 · ft | 1,40 | 73,14% | +$2,40 | modelled_final_score_contract |
| q0215 | Goal Range All · yes · rango3–5 · ft | 2,50 | 30,40% | −$23,99 | modelled_final_score_contract |
| q0216 | Goal Range All · no · rango3–5 · ft | 1,50 | 69,60% | +$4,40 | modelled_final_score_contract |
| q0217 | Goal Range All · yes · rango3–6 · ft | 2,25 | 31,58% | −$28,95 | modelled_final_score_contract |
| q0218 | Goal Range All · no · rango3–6 · ft | 1,57 | 68,42% | +$7,42 | modelled_final_score_contract |
| q0219 | Goal Range All · yes · rango4–5 · ft | 5,00 | 12,46% | −$37,68 | modelled_final_score_contract |
| q0220 | Goal Range All · no · rango4–5 · ft | 1,16 | 87,54% | +$1,54 | modelled_final_score_contract |
| q0221 | Goal Range All · yes · rango4–6 · ft | 4,33 | 13,64% | −$40,94 | modelled_final_score_contract |
| q0222 | Goal Range All · no · rango4–6 · ft | 1,20 | 86,36% | +$3,63 | modelled_final_score_contract |
| q0223 | Goal Range All · yes · rango5–6 · ft | 11,00 | 4,72% | −$48,06 | modelled_final_score_contract |
| q0224 | Goal Range All · no · rango5–6 · ft | 1,05 | 95,28% | +$0,04 | modelled_final_score_contract |
| q0225 | Goal Range All · yes · home · rango1–2 · ft | 1,80 | 49,92% | −$10,14 | modelled_final_score_contract |
| q0226 | Goal Range All · no · home · rango1–2 · ft | 1,90 | 50,08% | −$4,86 | modelled_final_score_contract |
| q0227 | Goal Range All · yes · home · rango1–3 · ft | 1,61 | 53,62% | −$13,67 | modelled_final_score_contract |
| q0228 | Goal Range All · no · home · rango1–3 · ft | 2,20 | 46,38% | +$2,03 | modelled_final_score_contract |
| q0229 | Goal Range All · yes · home · rango1–4 · ft | 1,61 | 54,35% | −$12,49 | modelled_final_score_contract |
| q0230 | Goal Range All · no · home · rango1–4 · ft | 2,20 | 45,65% | +$0,43 | modelled_final_score_contract |
| q0231 | Goal Range All · yes · home · rango1–5 · ft | 1,61 | 54,47% | −$12,31 | modelled_final_score_contract |
| q0232 | Goal Range All · no · home · rango1–5 · ft | 2,20 | 45,53% | +$0,18 | modelled_final_score_contract |
| q0233 | Goal Range All · yes · home · rango1–6 · ft | 1,61 | 54,48% | −$12,29 | modelled_final_score_contract |
| q0234 | Goal Range All · no · home · rango1–6 · ft | 2,20 | 45,52% | +$0,14 | modelled_final_score_contract |
| q0235 | Goal Range All · yes · home · rango2–3 · ft | 4,33 | 17,80% | −$22,94 | modelled_final_score_contract |
| q0236 | Goal Range All · no · home · rango2–3 · ft | 1,20 | 82,20% | −$1,36 | modelled_final_score_contract |
| q0237 | Goal Range All · yes · home · rango2–4 · ft | 4,00 | 18,53% | −$25,90 | modelled_final_score_contract |
| q0238 | Goal Range All · no · home · rango2–4 · ft | 1,22 | 81,47% | −$0,60 | modelled_final_score_contract |
| q0239 | Goal Range All · yes · home · rango2–5 · ft | 4,00 | 18,64% | −$25,44 | modelled_final_score_contract |
| q0240 | Goal Range All · no · home · rango2–5 · ft | 1,22 | 81,36% | −$0,74 | modelled_final_score_contract |
| q0241 | Goal Range All · yes · home · rango2–6 · ft | 4,00 | 18,66% | −$25,38 | modelled_final_score_contract |
| q0242 | Goal Range All · no · home · rango2–6 · ft | 1,22 | 81,34% | −$0,76 | modelled_final_score_contract |
| q0243 | Goal Range All · yes · home · rango3–4 · ft | 13,00 | 4,43% | −$42,45 | modelled_final_score_contract |
| q0244 | Goal Range All · no · home · rango3–4 · ft | 1,04 | 95,57% | −$0,60 | modelled_final_score_contract |
| q0245 | Goal Range All · yes · home · rango3–5 · ft | 13,00 | 4,54% | −$40,96 | modelled_final_score_contract |
| q0246 | Goal Range All · no · home · rango3–5 · ft | 1,04 | 95,46% | −$0,72 | modelled_final_score_contract |
| q0247 | Goal Range All · yes · home · rango3–6 · ft | 13,00 | 4,56% | −$40,77 | modelled_final_score_contract |
| q0248 | Goal Range All · no · home · rango3–6 · ft | 1,04 | 95,44% | −$0,74 | modelled_final_score_contract |
| q0249 | Goal Range All · yes · home · rango4–5 · ft | 41,00 | 0,84% | −$65,46 | modelled_final_score_contract |
| q0250 | Goal Range All · no · home · rango4–5 · ft | 1,00 | 99,16% | −$0,45 | modelled_final_score_contract |
| q0251 | Goal Range All · yes · home · rango4–6 · ft | 41,00 | 0,86% | −$64,85 | modelled_final_score_contract |
| q0252 | Goal Range All · no · home · rango4–6 · ft | 1,00 | 99,14% | −$0,46 | modelled_final_score_contract |
| q0253 | Goal Range All · yes · home · rango5–6 · ft | 101,00 | 0,13% | −$86,91 | modelled_final_score_contract |
| q0254 | Goal Range All · no · home · rango5–6 · ft | 1,00 | 99,87% | −$0,03 | modelled_final_score_contract |
| q0255 | Goal Range All · yes · away · rango1–2 · ft | 1,57 | 57,84% | −$9,19 | modelled_final_score_contract |
| q0256 | Goal Range All · no · away · rango1–2 · ft | 2,25 | 42,16% | −$5,14 | modelled_final_score_contract |
| q0257 | Goal Range All · yes · away · rango1–3 · ft | 1,33 | 66,53% | −$11,51 | modelled_final_score_contract |
| q0258 | Goal Range All · no · away · rango1–3 · ft | 3,25 | 33,47% | +$8,77 | modelled_final_score_contract |
| q0259 | Goal Range All · yes · away · rango1–4 · ft | 1,28 | 69,14% | −$11,50 | modelled_final_score_contract |
| q0260 | Goal Range All · no · away · rango1–4 · ft | 3,50 | 30,86% | +$8,00 | modelled_final_score_contract |
| q0261 | Goal Range All · yes · away · rango1–5 · ft | 1,25 | 69,77% | −$12,79 | modelled_final_score_contract |
| q0262 | Goal Range All · no · away · rango1–5 · ft | 3,75 | 30,23% | +$13,37 | modelled_final_score_contract |
| q0263 | Goal Range All · yes · away · rango1–6 · ft | 1,25 | 69,89% | −$12,63 | modelled_final_score_contract |
| q0264 | Goal Range All · no · away · rango1–6 · ft | 3,75 | 30,11% | +$12,89 | modelled_final_score_contract |
| q0265 | Goal Range All · yes · away · rango2–3 · ft | 2,50 | 30,40% | −$24,01 | modelled_final_score_contract |
| q0266 | Goal Range All · no · away · rango2–3 · ft | 1,50 | 69,60% | +$4,41 | modelled_final_score_contract |
| q0267 | Goal Range All · yes · away · rango2–4 · ft | 2,25 | 33,01% | −$25,73 | modelled_final_score_contract |
| q0268 | Goal Range All · no · away · rango2–4 · ft | 1,57 | 66,99% | +$5,18 | modelled_final_score_contract |
| q0269 | Goal Range All · yes · away · rango2–5 · ft | 2,20 | 33,63% | −$26,01 | modelled_final_score_contract |
| q0270 | Goal Range All · no · away · rango2–5 · ft | 1,61 | 66,37% | +$6,85 | modelled_final_score_contract |
| q0271 | Goal Range All · yes · away · rango2–6 · ft | 2,20 | 33,76% | −$25,73 | modelled_final_score_contract |
| q0272 | Goal Range All · no · away · rango2–6 · ft | 1,61 | 66,24% | +$6,65 | modelled_final_score_contract |
| q0273 | Goal Range All · yes · away · rango3–4 · ft | 5,50 | 11,30% | −$37,84 | modelled_final_score_contract |
| q0274 | Goal Range All · no · away · rango3–4 · ft | 1,14 | 88,70% | +$1,12 | modelled_final_score_contract |
| q0275 | Goal Range All · yes · away · rango3–5 · ft | 5,50 | 11,93% | −$34,39 | modelled_final_score_contract |
| q0276 | Goal Range All · no · away · rango3–5 · ft | 1,14 | 88,07% | +$0,40 | modelled_final_score_contract |
| q0277 | Goal Range All · yes · away · rango3–6 · ft | 5,00 | 12,05% | −$39,73 | modelled_final_score_contract |
| q0278 | Goal Range All · no · away · rango3–6 · ft | 1,16 | 87,95% | +$2,02 | modelled_final_score_contract |
| q0279 | Goal Range All · yes · away · rango4–5 · ft | 15,00 | 3,24% | −$51,44 | modelled_final_score_contract |
| q0280 | Goal Range All · no · away · rango4–5 · ft | 1,03 | 96,76% | −$0,33 | modelled_final_score_contract |
| q0281 | Goal Range All · yes · away · rango4–6 · ft | 15,00 | 3,36% | −$49,55 | modelled_final_score_contract |
| q0282 | Goal Range All · no · away · rango4–6 · ft | 1,03 | 96,64% | −$0,46 | modelled_final_score_contract |
| q0283 | Goal Range All · yes · away · rango5–6 · ft | 34,00 | 0,75% | −$74,41 | modelled_final_score_contract |
| q0284 | Goal Range All · no · away · rango5–6 · ft | 1,00 | 99,25% | −$0,26 | modelled_final_score_contract |
| q0285 | Half Time Result · home · ht | 4,75 | 16,73% | −$20,53 | modelled_exploratory_timing_contract |
| q0286 | Half Time Result · draw · ht | 2,05 | 51,49% | +$5,55 | modelled_exploratory_timing_contract |
| q0287 | Half Time Result · away · ht | 2,62 | 31,78% | −$16,74 | modelled_exploratory_timing_contract |
| q0288 | Half Time Double Chance · home_draw · ht | 1,44 | 68,22% | −$1,76 | modelled_exploratory_timing_contract |
| q0289 | Half Time Double Chance · draw_away · ht | 1,16 | 83,27% | −$3,41 | modelled_exploratory_timing_contract |
| q0290 | Half Time Double Chance · home_away · ht | 1,72 | 48,51% | −$16,56 | modelled_exploratory_timing_contract |
| q0291 | Half Time European Handicap · home · línea1.0 · ht | 1,44 | 68,22% | −$1,76 | modelled_exploratory_timing_contract |
| q0292 | Half Time European Handicap · draw · línea1.0 · ht | 3,25 | 24,40% | −$20,68 | modelled_exploratory_timing_contract |
| q0293 | Half Time European Handicap · away · línea1.0 · ht | 9,00 | 7,38% | −$33,62 | modelled_exploratory_timing_contract |
| q0294 | Team to Score in Half · over · home · línea0.5 · ht | 2,75 | 26,27% | −$27,77 | modelled_exploratory_timing_contract |
| q0295 | Team to Score in Half · under · home · línea0.5 · ht | 1,40 | 73,73% | +$3,23 | modelled_exploratory_timing_contract |
| q0296 | Team to Score in Half · over · home · línea0.5 · sh | 2,25 | 38,27% | −$13,90 | modelled_exploratory_timing_contract |
| q0297 | Team to Score in Half · under · home · línea0.5 · sh | 1,57 | 61,73% | −$3,08 | modelled_exploratory_timing_contract |
| q0298 | Team to Score in Half · over · away · línea0.5 · ht | 2,00 | 40,32% | −$19,35 | modelled_exploratory_timing_contract |
| q0299 | Team to Score in Half · under · away · línea0.5 · ht | 1,72 | 59,68% | +$2,64 | modelled_exploratory_timing_contract |
| q0300 | Team to Score in Half · over · away · línea0.5 · sh | 1,72 | 49,60% | −$14,70 | modelled_exploratory_timing_contract |
| q0301 | Team to Score in Half · under · away · línea0.5 · sh | 2,00 | 50,40% | +$0,81 | modelled_exploratory_timing_contract |
| q0302 | Half Time Correct Score All · score · [1, 0] · ht | 6,00 | 13,26% | −$20,42 | modelled_exploratory_timing_contract |
| q0303 | Half Time Correct Score All · score · [2, 0] · ht | 23,00 | 2,04% | −$53,02 | modelled_exploratory_timing_contract |
| q0304 | Half Time Correct Score All · score · [2, 1] · ht | 34,00 | 1,05% | −$64,15 | modelled_exploratory_timing_contract |
| q0305 | Half Time Correct Score All · score · [3, 0] · ht | 81,00 | 0,21% | −$83,19 | modelled_exploratory_timing_contract |
| q0306 | Half Time Correct Score All · score · [3, 1] · ht | 126,00 | 0,11% | −$86,51 | modelled_exploratory_timing_contract |
| q0307 | Half Time Correct Score All · score · [3, 2] · ht | 301,00 | 0,03% | −$91,68 | modelled_exploratory_timing_contract |
| q0308 | Half Time Correct Score All · score · [4, 0] · ht | 501,00 | 0,02% | −$92,08 | modelled_exploratory_timing_contract |
| q0309 | Half Time Correct Score All · score · [1, 1] · ht | 8,50 | 7,07% | −$39,94 | modelled_exploratory_timing_contract |
| q0310 | Half Time Correct Score All · score · [2, 2] · ht | 67,00 | 0,27% | −$81,76 | modelled_exploratory_timing_contract |
| q0311 | Half Time Correct Score All · score · [0, 1] · ht | 3,75 | 22,57% | −$15,36 | modelled_exploratory_timing_contract |
| q0312 | Half Time Correct Score All · score · [0, 2] · ht | 11,00 | 5,86% | −$35,51 | modelled_exploratory_timing_contract |
| q0313 | Half Time Correct Score All · score · [1, 2] · ht | 23,00 | 1,79% | −$58,91 | modelled_exploratory_timing_contract |
| q0314 | Half Time Correct Score All · score · [0, 3] · ht | 41,00 | 1,01% | −$58,64 | modelled_exploratory_timing_contract |
| q0315 | Half Time Correct Score All · score · [1, 3] · ht | 67,00 | 0,31% | −$79,40 | modelled_exploratory_timing_contract |
| q0316 | Half Time Correct Score All · score · [2, 3] · ht | 201,00 | 0,05% | −$90,59 | modelled_exploratory_timing_contract |
| q0317 | Half Time Correct Score All · score · [0, 4] · ht | 126,00 | 0,13% | −$83,59 | modelled_exploratory_timing_contract |
| q0318 | Half Time Correct Score All · score · [1, 4] · ht | 251,00 | 0,04% | −$90,04 | modelled_exploratory_timing_contract |
| q0319 | Asian Handicap · home · línea0.5 · ft | 1,85 | 55,10% | +$1,94 | modelled_final_score_contract |
| q0320 | Asian Handicap · away · línea-0.5 · ft | 1,95 | 44,90% | −$12,45 | modelled_final_score_contract |
| q0321 | Asian Goals2.0,2.5 · over · línea2.25 · ft | 2,00 | 32,02% | −$22,00 | modelled_final_score_contract |
| q0322 | Asian Goals2.0,2.5 · under · línea2.25 · ft | 1,80 | 67,98% | +$11,19 | modelled_final_score_contract |
| q0337 | Win To Nil · and · ft | 6,50 | 15,52% | +$0,89 | modelled_final_score_contract |
| q0338 | Win Either Half · home · ft | 2,50 | 35,03% | −$12,42 | modelled_exploratory_timing_contract |
| q0339 | Win Both Halves · and · ft | 17,00 | 3,78% | −$35,80 | modelled_exploratory_timing_contract |
| q0340 | Score Both Halves · and · ft | 6,50 | 10,05% | −$34,67 | modelled_exploratory_timing_contract |
| q0342 | Win To Nil · and · ft | 3,00 | 30,96% | −$7,12 | modelled_final_score_contract |
| q0343 | Win Either Half · away · ft | 1,57 | 55,54% | −$12,81 | modelled_exploratory_timing_contract |
| q0344 | Win Both Halves · and · ft | 6,50 | 11,28% | −$26,67 | modelled_exploratory_timing_contract |
| q0345 | Score Both Halves · and · ft | 3,50 | 20,00% | −$30,01 | modelled_exploratory_timing_contract |
