# Verificación de Kraken Edge — 30/10/2026

El motor y el panel se comprobaron con datos reales. Esta verificación acredita
el funcionamiento de la herramienta y sus controles; la evaluación deportiva
inicial **rechaza** la hipótesis de que el modelo de fútbol supere al mercado.

## Datos y trazabilidad

- 109.780 partidos únicos, tres deportes y 17 competiciones.
- Fútbol: 65.810 partidos; NBA: 31.822; MLB: 12.148.
- Se conservaron los partidos de doble jornada de MLB. Los suspendidos se
  fechan al completarse para evitar incorporar su resultado antes de tiempo.
- 208 archivos originales con hashes y procedencia en `data/manifest.json`.
- 23.940 decisiones de evaluación disponibles en el historial completo gzip.
- Catálogo de cuotas: 184 competiciones, 83 activas y 73 activas sin futuros
  en la captura inicial. Se recibieron 881 eventos y 32.494 observaciones de
  precios, incluyendo la consulta específica de primer goleador.
- Primer goleador: 202 precios de seis casas para un evento, agrupados en 45
  selecciones observadas. No se inventó una probabilidad para esos jugadores.
- Las capturas de decisiones se guardan completas e inmutables en SQLite.
  Entradas normalizadas y código del modelo se archivan con gzip por SHA-256
  en `data/runtime/reproducibility` para conservar la posibilidad de reproducirlas.

## Resultado matemático inicial

| Evaluación de fútbol | Resultado |
| --- | ---: |
| Partidos de test | 15.138 |
| Log loss del modelo, muestra pareada | 1,013758 |
| Log loss del mercado sin margen, misma muestra | 0,987560 |
| Selecciones simuladas con casa identificable | 8.970 |
| Importe acumulado simulado | 4.686,57 unidades |
| Resultado neto hipotético | −967,45 unidades |
| ROI sobre importe apostado | −20,6431 % |
| Capital inicial / final | 1.000 / 32,55 unidades |
| Caída máxima del capital simulado | 96,7453 % |

Menor log loss indica mejor predicción. La comparación pareada favorece al
mercado. ROI y caída del capital tienen denominadores distintos: una pérdida
del 20,64 % sobre el volumen acumulado apostado produjo una pérdida del 96,75 %
del capital inicial en esta simulación repetida. Ninguna cifra representa
movimientos de dinero reales.

NBA y MLB se evalúan por separado. Sus archivos no contienen cuotas; no se
calcula una rentabilidad inventada. El archivo NBA termina en 2015 y MLB en
2025: no se presentan como historiales deportivos actuales.

## Comprobaciones de funcionamiento

- `python3 -m unittest discover -s tests -v`: **37 pruebas aprobadas**.
- Fórmulas de probabilidades, EV, margen y Kelly; mercados completos;
  aislamiento de ligas; neutralidad; partidos del mismo día; reglas y marcas
  temporales de arbitraje; ausencia de fuga temporal.
- Presupuesto concurrente, caché, conservación de capturas, liquidación
  idempotente, capital después de ganancias/pérdidas y exposición por evento.
- Bot: rotación, límite diario persistido, exclusión de futuros, fallo parcial,
  ocultación de secretos, bloqueo de segunda instancia y restauración de datos.
- Una ejecución real de `python3 bot.py --once` terminó sin errores: 12 aciertos
  de caché, cero consultas nuevas y cero créditos adicionales reservados.
  Conservó exactamente el backtest y el archivo de historial completo.
- Revisión en Chrome: resumen, filtros, historial de 23.940 registros,
  primer goleador, detalle y calculadora. Para cuota 2 y probabilidad supuesta
  55 %, la calculadora dio EV +10 % y un importe limitado al 1 % del capital.
- Revisión de HTTP: origen ajeno rechazado, Host ajeno rechazado, modo de
  dinero real rechazado, probabilidad inválida rechazada y `.env` inaccesible.
- No se encontró la clave ni una URL privada con ella en los archivos web.
- Todas las selecciones actuales conservan importe cero y ejecución desactivada.
- Publicación privada verificada: carga del panel y del historial completo con
  la cuenta propietaria. El código publicado corresponde al commit
  `cf48e4928e5b9e75ae29776d81f3ac48509b9605` del checkout de Sites.

## Límites de la entrega

El panel publicado es una captura privada. El bot y las consultas nuevas se
ejecutan localmente. No quedó instalado un proceso automático: `--watch` permite
iniciarlo de forma explícita. La cobertura de cuotas es más amplia que la de
modelos; cada mercado pendiente se conserva como tal. La versión actual no
dispone de una estrategia validada para recomendar apuestas con dinero.
