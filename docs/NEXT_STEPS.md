# Trabajo pendiente y criterio de avance

La prioridad es mejorar y comprobar probabilidades. El baseline inicial de fútbol pierde en la simulación: **ROI −20,6431 %; drawdown 96,7453 %**. Añadir mercados o conectar más casas no corrige por sí solo esa falta de ventaja. La siguiente versión debe poder explicar qué hipótesis mejoró, sobre qué período y con qué incertidumbre.

## 1. Congelar una referencia reproducible

Conservar manifiesto, hashes, versión del modelo, reglas de decisión y exportación completa de la corrida inicial. Separar entrenamiento, validación y test y registrar cada experimento, incluyendo los que no mejoran. Cualquier problema de ingesta o fuga temporal tiene prioridad sobre ampliar el modelo.

**Resultado esperado:** reproducir métricas y decisiones con los mismos archivos; documentar cualquier diferencia antes de comparar un modelo nuevo. Las cuotas medias siguen excluidas del P&L; NBA y MLB siguen sin ROI hasta obtener odds históricas compatibles.

## 2. Mejorar el modelo de fútbol sin elegir el mejor pasado

Investigar por separado ajuste explícito por adversario/fuerza de calendario, estimación conjunta de ataque/defensa, corrección de marcadores bajos, decaimiento temporal, ascensos y cambios de temporada. Después, evaluar si un método de recalibración ajustado sólo con entrenamiento/validación mejora las probabilidades frente al benchmark del mercado.

No habilitar una estrategia por tener mayor porcentaje de aciertos. Comparar log loss, Brier, calibración, estabilidad por liga y diferencia pareada contra mercado. La precisión de favoritos puede subir sin mejorar rentabilidad.

**Resultado esperado:** mejoras consistentes sobre validación y un período futuro nuevo, con reglas e hiperparámetros congelados antes de observar ese período. El test inicial que ya se examinó pasa a ser evidencia histórica conocida: no se reutiliza como test intacto para elegir variantes.

## 3. Acumular evidencia prospectiva gratuita

Guardar snapshots hacia adelante con hora, casa, mercado, línea, participante, reglas y momento del partido. Mantener una lista explícita de datos disponibles en cada predicción. Usar el presupuesto gratuito para competiciones y ventanas seleccionadas, en lugar de agotar 500 créditos intentando cubrir todo permanentemente.

Registrar también abstenciones y precios ausentes. Guardar cuota de cierre sólo cuando exista una captura genuina y sea comparable con la inicial; sin ella, CLV es desconocido. No reconstruir precios previos a partir de resultados o de la última cuota disponible.

**Resultado esperado:** un conjunto futuro con resultados y cotizaciones fechadas, sin modificar decisiones después del desenlace. Medir calibración y costes prácticos; definir de antemano tamaño, duración y criterio estadístico. El filtro histórico implementado —500 partidos, 100 fechas y bootstrap pareado por fecha— es sólo una referencia inicial, no una autorización operativa automática.

## 4. Evaluar mercados de fútbol uno por uno

| Mercado | Datos y trabajo necesarios | Estado actual |
| --- | --- | --- |
| 1X2 | Resultados, precios de la misma casa, evaluación contra mercado y calibración. | Baseline implementado; ventaja no demostrada. |
| Totales y ambos marcan | Definición de línea/período, odds comparables y evaluación específica. | Probabilidades exploradas; sin estrategia operativa validada. |
| Córners y tarjetas | Conteos, reglas de doble amarilla/puntos de tarjetas, arbitraje de mercado y modelos adecuados a dispersión. | Algunos resultados históricos y posibilidad de observar precios; sin modelo específico. |
| Primer equipo en marcar | Secuencia de goles, ningún gol, autogoles, reglas y backtest de ese contrato. | Derivación Poisson exploratoria; 64 partidos de eventos seleccionados, insuficientes para cobertura general. |
| Primer goleador por jugador | Alineación, minutos esperados, sustituciones, penales, suplentes, autogoles, reglas de no participación y precio del mismo contrato. | Consulta de precios posible según cobertura; probabilidad y EV desconocidos. |
| Hándicap asiático | Línea exacta, medias/cuarto de línea, pushes y liquidación por mitades. | Datos raw disponibles en algunas ligas; falta implementación de liquidación/evaluación. |

No sumar selecciones del mismo partido como si fueran independientes. No repartir probabilidad entre una lista parcial de jugadores. Consultar `player_first_goal_scorer` no habilita una decisión sin modelo y participación verificados.

## 5. Ampliar deportes donde haya datos permitidos

| Deporte | Próximo paso | Límite de la primera versión |
| --- | --- | --- |
| NBA | Conseguir resultados actuales autorizados y luego estudiar descanso/plantel; odds históricas cuando existan gratis. | Archivo FiveThirtyEight termina en 2015; no habilita inferencia actual. |
| MLB | Actualizar Retrosheet cuando publique 2026; estudiar abridor, lineup y bullpen únicamente con datos conocidos antes del partido. | 2021–2025 regular; Elo preliminar, sin cuotas históricas ni ROI. |
| Tenis ATP/WTA | Resolver importación permitida con fecha exacta de partido, superficie y reglas de abandono. | Repos originales retirados; una alternativa requiere comprobación humana y otra limita uso a investigación personal. No evadir controles ni asumir derechos comerciales. |
| NHL | Obtener permiso o una fuente explícitamente descargable y autorizada. | Endpoint oficial devuelve 403; recopilación masiva no autorizada. El Elo preparado no significa dataset conectado. |
| NFL y otros | Investigar proveedores originales con acceso y términos adecuados, más definición de mercado y backtest propios. | Catálogo de cuotas disponible no equivale a histórico ni modelo. |

Para NHL, ganador final con prórroga/shootout y ganador en tiempo reglamentario son contratos distintos. Para MLB hay que comprobar extra innings, juegos acortados y reglas sobre pitchers. No aplicar un modelo binario genérico a cuotas con desenlaces incompatibles.

## 6. Mejorar incertidumbre y control de experimentos

La banda individual actual es heurística. Evaluar alternativas que representen incertidumbre de parámetros y calibración temporal, y comprobar su comportamiento prospectivo. Para comparación de modelos, explorar remuestreo que conserve mejor dependencia serial y sensibilidad a liga/temporada.

Controlar el sesgo de múltiples pruebas: un registro de experimentos debe explicar cuántas variantes se probaron y cómo se eligió la final. Una ganancia aislada en una liga descubierta después de mirar cientos de cortes necesita confirmación nueva.

**Resultado esperado:** métodos con supuestos y alcance explícitos; no rotular como intervalo de probabilidad verdadera una fórmula que sólo mide sensibilidad del baseline.

## 7. Operación y app

- Conservar la base local y ofrecer una copia/exportación del ledger con procedencia y fecha.
- Mantener catálogos de cobertura reales: conectado, histórico obsoleto, precio observado, modelo por validar o permiso pendiente.
- Mostrar el estado de cuota y la diferencia entre una respuesta cacheada y una cuota fresca.
- Si se agrega una tarea programada, fijar presupuesto y frecuencia a partir del consumo real; hoy no hay polling permanente.
- Si se desea un backend remoto, diseñar persistencia, identidad y secretos en servidor antes de publicar. El Sites estático actual conserva una captura privada y no accede al backend local.

La incorporación de ejecución real sería un proyecto separado: requiere autorización específica, reglas/límites/capital definidos y una ventaja demostrada con datos futuros. Esta versión permanece en investigación y simulación mientras se completan esos requisitos.

Ver [arquitectura](ARCHITECTURE.md), [metodología](METHODOLOGY.md) y [fuentes](DATA_SOURCES.md) para las reglas implementadas y su evidencia.
