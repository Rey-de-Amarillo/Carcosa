# Combinaciones históricas OddsPapi

Se compararon cinco partidos antes del inicio programado, con precios activos de Pinnacle y DraftKings. Los intervalos se reconstruyen cronológicamente; no se usan cuotas finales ni se mezclan partidos.

| Antigüedad máxima de cada precio | Intervalos positivos | Duran ≥5 segundos | Grupos con señal | Capacidad de 100 documentada |
|---|---:|---:|---:|---:|
| 60s | 0 | 0 | 0 | 0 |
| 300s | 0 | 0 | 0 | 0 |
| 3600s | 4 | 1 | 1 | 0 |
| 86400s | 4 | 1 | 1 | 0 |

Señal estrictamente positiva condicional, admitiendo una cotización anterior de 38 minutos: **Manchester City–Ipswich Town**, 2026-10-17T10:58:44.922000-03:00 (21.565s registrados). Ipswich gana el primer tiempo a 10,04 en Pinnacle, frente a Manchester City o empate al descanso a 1,111 en DraftKings. La suma inversa es 0.9996916026; beneficio mínimo continuo 0.03085 por cada 100.

Con apuestas de 9.97 y 90.03, beneficio mínimo redondeado 0.02333 por cada 100. Un costo de capital del 0,5% elimina el beneficio estricto; también lo elimina un recorte del 1% de las cuotas. La cotización antigua seguía marcada activa en el historial hasta después del inicio, pero no se confirmó aceptación por las casas.

Partición completa más cercana al equilibrio entre las examinadas con precios de hasta 60s y duración ≥5s: Manchester City–Ipswich Town, equivalent:teamtotals-team2:p1:line:0.5, 2026-10-17T13:59:11.081000+00:00. Retorno mínimo -0.9325% (negativo).

| Selección | Casa | Cuota | Apuesta sobre 100 |
|---|---|---:|---:|
| Over | pinnacle | 3.24 | 30.58 |
| Under | draftkings | 1.427 | 69.42 |

Cobertura con devolución: Manchester City–Ipswich Town, direct:10596:player:0, 2026-10-17T13:58:39.926000+00:00. Suma inversa 0.98308668; el escenario de devolución deja beneficio mínimo cero. Aparece sólo admitiendo precios de hasta una hora; no se encontró con ventanas de 60s o 300s.

Estos cinco intervalos corresponden a una misma cobertura asiática, no a cinco oportunidades independientes. La antigüedad de una cotización no demuestra que estuviera retirada: se conserva el último registro activo y la actualización siguiente.

| Intervalo UTC | Intervalo Salta | Cuotas | Beneficio por 100 fuera de devolución, sin redondeo |
|---|---|---|---:|
| 2026-10-17T13:58:39.605000+00:00 a 2026-10-17T13:58:39.926000+00:00 | 2026-10-17T10:58:39.605000-03:00 a 2026-10-17T10:58:39.926000-03:00 | 2.2, 1.862 | 0.84687 |
| 2026-10-17T13:58:39.926000+00:00 a 2026-10-17T13:58:40.598000+00:00 | 2026-10-17T10:58:39.926000-03:00 a 2026-10-17T10:58:40.598000-03:00 | 2.2, 1.892 | 1.72043 |
| 2026-10-17T13:58:40.598000+00:00 a 2026-10-17T13:58:44.922000+00:00 | 2026-10-17T10:58:40.598000-03:00 a 2026-10-17T10:58:44.922000-03:00 | 2.2, 1.877 | 1.28526 |
| 2026-10-17T13:58:44.922000+00:00 a 2026-10-17T13:59:06.487000+00:00 | 2026-10-17T10:58:44.922000-03:00 a 2026-10-17T10:59:06.487000-03:00 | 2.2, 1.862 | 0.84687 |
| 2026-10-17T13:59:06.487000+00:00 a 2026-10-17T13:59:55.994000+00:00 | 2026-10-17T10:59:06.487000-03:00 a 2026-10-17T10:59:55.994000-03:00 | 2.2, 1.854 | 0.61174 |

En la mejor pareja, apostar 46.24 a Man City −1 al descanso (DraftKings 2.2) y 53.76 al lado contrario (Pinnacle 1.892) devuelve 100 si City llega al descanso ganando por exactamente un gol, y al menos 101.71392 en otro marcador. Las dos posiciones son del mismo hándicap −1 para el equipo local, período p1.

Este beneficio es condicional a disponibilidad, aceptación y reglas coincidentes. Los límites de DraftKings no vienen informados; no se verificó ejecución. Un costo fijo de capital del 0,5% convierte el caso de devolución en pérdida; eso no prueba por sí solo expectativa negativa en los otros resultados.

Se comprueban particiones completas, goles y marcadores exactos bajos cubiertos por una cola Over, equivalencias de ningún gol y goles por equipo, y devoluciones asiáticas. Las listas de goleadores de una sola cara y los resultados acumulados superpuestos no se tratan como particiones completas.

Son candidatos matemáticos sobre registros históricos, no ganancias ejecutadas ni ofertas confirmadas. La disponibilidad simultánea, identidad de reglas, límites y capacidad real siguen sin verificar. Los recuentos incluyen intervalos solapados; no son apuestas independientes.

Detalle de posiciones, escenarios, fechas, límites, estrés y hashes: `data/analysis/oddspapi_temporal_arb.json`.
Código: `python3 scripts/oddspapi_temporal_arb.py`.
