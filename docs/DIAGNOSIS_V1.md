# Por qué perdió el modelo v1

Este informe describe el modelo `0.1.0` y su estrategia original, sin elegir
umbrales, ligas o mercados a partir del resultado observado. El período de
test ya se inspeccionó: cambiar parámetros después y volver a llamarlo un
holdout intacto produciría una conclusión engañosa.

Se puede reproducir sin red ni créditos de API:

```bash
python3 scripts/diagnose_v1.py
python3 scripts/build_quote_history.py
```

Los resultados completos están en `data/analysis/v1_diagnosis.json`. La tabla
privada multicasa está en `data/analysis/quote_history.jsonl`. No deben
redistribuirse como una fuente de datos ni publicarse como archivos originales.

## La pérdida no se explica sólo por Kelly

La evaluación contiene 15.138 decisiones de fútbol. La regla fija eligió 8.970
apuestas hipotéticas, el 59,25 % de esos partidos. Sus cifras se reconcilian:

| Medida | Resultado |
| --- | ---: |
| Capital inicial | 1.000 unidades |
| Volumen acumulado apostado | 4.686,57 unidades |
| Beneficio/pérdida | −967,45 unidades |
| ROI con los importes de Kelly | −20,64 % |
| ROI con una unidad fija por selección | −14,78 % |
| Frecuencia real de acierto | 22,46 % |
| Probabilidad media estimada por el modelo | 32,20 % |
| Referencia media del mercado sin margen | 24,35 % |

Cambiar los importes no convierte estas selecciones en rentables. La diferencia
central es probabilística: el modelo sobreestimó el acierto de sus propias
selecciones en **9,74 puntos porcentuales**. La referencia de mercado quedó
mucho más cerca de la frecuencia observada en esa misma selección de apuestas.

El EV medio ponderado por importe era **+33,28 %**. Eso implicaba un beneficio
esperado por el modelo de +1.559,74 unidades; el resultado fue −967,45. Una señal
tan positiva y tan frecuente exige comprobar calibración y selección antes de
interpretarla como ventaja deportiva.

## Elegir el mayor EV seleccionaba errores optimistas

El método elegía, entre tres resultados del partido, el de mayor EV. Cuando las
probabilidades tienen error, esa operación tiende a seleccionar la estimación
excesivamente optimista. Las cuotas altas amplifican el efecto porque
`EV = p × cuota − 1`.

| Cuota de la selección | Apuestas | ROI Kelly | Probabilidad modelo | Acierto observado |
| --- | ---: | ---: | ---: | ---: |
| Menor que 2 | 261 | −31,07 % | 61,38 % | 49,04 % |
| 2 a menos de 3 | 1.881 | −11,98 % | 46,37 % | 35,14 % |
| 3 a menos de 5 | 3.543 | −18,49 % | 33,20 % | 23,45 % |
| 5 a menos de 10 | 2.667 | −18,84 % | 22,29 % | 13,65 % |
| 10 o más | 618 | −56,98 % | 13,79 % | 5,02 % |

En 5.436 apuestas, el 60,60 % del total, se eligió el resultado con la cuota más
alta del mercado. Ese grupo perdió 23,26 % del volumen apostado. Las 1.587
selecciones con EV calculado de al menos 50 % perdieron 39,63 %. El entusiasmo
del modelo no fue evidencia de mayor precisión.

Estos grupos describen el fallo. No justifican una nueva estrategia que elija
el mejor grupo de esta tabla y anuncie su resultado como una prueba futura.

## Qué se revisó y qué no se encontró

- Cada beneficio o pérdida coincide con el marcador, la selección, la cuota y
  el importe: **cero inconsistencias de liquidación**.
- En los registros de fútbol, la última fecha de entrenamiento es anterior al
  evento: **cero violaciones detectadas de esa condición**.
- No hay apuestas a columnas `Avg`: se habían excluido correctamente del P&L.
  Las 8.970 selecciones proceden de Bet365, salvo una de Pinnacle anterior al
  período advertido por la fuente.
- Las descomposiciones por cuota, probabilidad, liga, año, selección, EV y
  snapshot suman exactamente el mismo número de apuestas, volumen y P&L.
- No se encontró una inversión del signo de ataque o defensa en las tasas.
  El problema del baseline es su simplificación y calibración, no una promesa
  de corregir todo intercambiando local y visitante.

El modelo combina promedios de goles por localía mediante un producto de
fuerzas regularizadas. No ajusta conjuntamente el calendario de adversarios,
no corrige dependencia de marcadores bajos y no aprende una calibración fuera
de muestra. Sus bandas individuales son sensibilidad heurística, no una prueba
de que una ventaja calculada sea positiva con alta confianza.

## La composición importa

El ROI de apuestas a precios pre-closing fue −21,80 %; a closing, −2,14 %.
No es una comparación controlada: los países, años, equipos y muestras difieren.
No demuestra que cambiar a closing arregle el modelo ni que ambas capturas
estuvieran disponibles simultáneamente.

El desglose por liga también es heterogéneo. Hay resultados descriptivos
positivos en algunas muestras y pérdidas en la mayoría. Seleccionar las ligas
positivas después de observarlas introduce sesgo de selección. La misma
advertencia se aplica a los 196 empates simulados, que tuvieron un retorno
positivo aislado con una muestra pequeña frente a los otros resultados.

## Datos que ya permiten un experimento mejor

Los archivos originales conservan más información que las columnas elegidas
por el importador v1. El nuevo extractor preserva cada casa identificada y
separa las dos capturas:

| Mercado | Partidos pre-closing con alguna casa | Partidos closing con alguna casa |
| --- | ---: | ---: |
| Resultado 1X2 | 42.612 | 65.629 |
| Más/menos 2,5 goles | 27.549 | 27.558 |
| Hándicap asiático con línea explícita | 27.531 | 27.556 |

Para 1X2 hay al menos dos casas en 42.610 partidos pre-closing y 27.558 closing.
Esto permite construir una referencia de consenso y comparar precios
identificados. Conviene excluir la casa objetivo del consenso cuando se evalúa
su precio, o declarar expresamente su participación.

Los campos `Avg`, `Max`, `BbAv` y `BbMx` quedan fuera de los precios de casas.
Betfair Exchange también se excluye mientras no exista un tratamiento de
comisiones y reglas. Pinnacle se excluye a partir del 23/07/2025 por el aviso de
desactualización de la propia fuente. No se completa una cuota ausente.

La documentación oficial distingue capturas pre-closing/closing y los códigos
de cada casa; también define las estadísticas de descanso, córners y tarjetas.
Los resultados de tarjetas no tienen una regla universal: la forma de contar
la segunda amarilla difiere entre competiciones en el archivo.
[Notas oficiales](https://www.football-data.co.uk/notes.txt).

La fuente ofrece estos archivos para particulares y advierte sobre los precios
de Pinnacle desde la fecha indicada. Los datos siguen siendo investigación
privada; una descarga no concede licencia para un producto comercial de datos.
[Cobertura y condiciones actuales](https://www.football-data.co.uk/data.php).

## Qué debe cambiar en la evaluación v2

1. Ajustar ataque y defensa conjuntamente, con regularización y recencia,
   usando únicamente resultados anteriores al partido.
2. Medir calibración y precisión frente a una referencia del mercado en los
   mismos partidos y con el mismo tipo de captura.
3. Evaluar pocos candidatos fijados previamente y elegir con un período de
   desarrollo separado. Mantener el período ya visto como auditoría
   retrospectiva, no como confirmación independiente.
4. Usar correctamente devoluciones y medias liquidaciones en DNB, totales y
   hándicaps: `p × cuota − 1` sólo sirve directamente para una apuesta binaria
   de ganar o perder sin devoluciones.
5. Reservar desde el 31/10/2026 una prueba prospectiva con decisiones guardadas
   antes del resultado. Ese período todavía no puede tener un ROI observado.
6. Mantener visibles las estrategias que fracasan y la cantidad de variantes
   probadas. Cero apuestas porque ninguna regla pasó validación es abstención,
   no una mejora demostrada del ROI de apuestas efectivamente tomadas.

La revisión puede mejorar mucho la herramienta sin garantizar rentabilidad.
Una mejora de log loss o calibración es útil; debe distinguirse de un retorno
positivo que todavía no se haya demostrado.
