# Kraken Edge

Laboratorio privado de probabilidades deportivas: descarga resultados reales, compara modelos con cuotas, reproduce decisiones históricas y registra por qué observa o descarta cada selección. La app y el motor funcionan con **Python 3.10 o posterior, sin dependencias externas**, y el presupuesto de datos es **sólo fuentes gratuitas**.

[Abrir la app privada publicada](https://kraken-edge-joaquin.workraken.chatgpt.site) · [Abrir la app local](http://127.0.0.1:8765). La primera muestra una captura privada; la segunda necesita iniciar el servidor de esta computadora.

## Interfaz actual de fútbol

El creador incluye 28 mercados, selecciones por mercado, filtros de cuota y combinadas. Los campos usan la grilla original de Workraken, con el mismo tamaño y sin texto suelto.

La interfaz abre con `python3 server.py` en http://127.0.0.1:8765. Los datos derivados necesarios están incluidos; las claves y los archivos locales de investigación quedan fuera del repositorio.

Comprobaciones del creador: `node tests/test_formula_field_layout.mjs`, `node tests/test_bet365_authoring.mjs` y `node tests/test_alert_workflow.mjs`. Las pruebas de ledger y de planteles históricos necesitan los archivos originales locales no versionados.

**Versión 0.2, revisión del 30/10/2026:** hay un nuevo modelo de goles ajustado por adversario y marcadores bajos, consenso multicasa sin margen, liquidación exacta de hándicaps y modelos separados de primer tiempo, córners y amarillas. El catálogo distingue **53 tipos de apuesta**, sus datos y sus límites; hay **16 evaluaciones numéricas** por mercado. Catalogar un mercado no implica tener un pronóstico entrenado o una estrategia rentable para él.

El modelo estructural mejoró el log loss de **0,999166 a 0,991979** sobre los mismos 9.992 partidos. En la selección de 2022–2023, la especificación más precisa fue **consenso power con peso estructural cero**: se utiliza información de precios; no se presenta como un pronóstico deportivo independiente que supere a las casas.

La regla fija de mejor precio produjo en la auditoría retrospectiva **137 apuestas hipotéticas, ROI +16,81 % y +41,53 unidades**, desde 1.000 hasta 1.041,53. Su intervalo de ROI va de **−8,17 % a +43,38 %**, por lo que todavía incluye pérdidas. El ROI con una cotización 1 % peor fue +15,64 %. La prueba con precio Bet365 fijo produjo −12,06 % en 23 selecciones distintas: no es una comparación causal del efecto de buscar precios. Todos estos resultados pertenecen a un período ya inspeccionado y no prueban rentabilidad futura.

El baseline anterior, con ROI −20,64 %, se conserva en `data/analysis/baseline_v1` y en su diagnóstico. La comprobación prospectiva comienza el **31/10/2026**, con cero eventos observados al registrar el protocolo. Las señales actuales siguen en observación y con importe cero.

La versión actual ofrece investigación, seguimiento y simulaciones manuales. **No envía apuestas ni movimientos de dinero a casas de apuestas.**

## Abrir la app local

Desde esta carpeta:

```bash
./run.sh
```

Abrir **http://127.0.0.1:8765**. También se puede ejecutar directamente:

```bash
python3 server.py
```

`run.sh` genera el informe si todavía no existe y luego inicia el servidor. Si ya existe, muestra esa versión: para incorporar nuevos históricos o capturas hay que reconstruirlo. Para elegir otro puerto:

```bash
./run.sh --port 8766
```

El servidor escucha sólo en `127.0.0.1`. Se detiene con `Ctrl+C`. No hace falta Node, npm, Docker ni instalar paquetes de Python.

## Qué se puede consultar

| Vista | Contenido |
| --- | --- |
| Resumen | Cobertura histórica, estado del modelo, métricas y evolución de una estrategia simulada. |
| Mercados | Cuotas observadas, probabilidad del modelo cuando existe, referencia del mercado, EV y motivos de bloqueo. |
| Historial de decisiones | Decisiones y abstenciones fuera de muestra, filtros, detalle matemático y exportación. |
| Motor matemático | Supuestos, evaluación cronológica, calibración, incertidumbre y límites de cada modelo. |
| Datos y conexiones | Fuentes conectadas, fechas de captura, cuota gratuita y mercados todavía sin modelo. |

El informe carga una muestra para abrir rápido. El historial completo se distribuye como JSONL comprimido con gzip; el recuento de la interfaz y `history_export.count` identifican la exportación vigente. La versión anterior tenía 23.940 decisiones y se preserva como baseline, sin confundirlas con las decisiones reconstruidas de v2. Si el navegador no permite descomprimir el archivo, se puede descargar.

Una probabilidad ausente se muestra como desconocida. Las bandas individuales son sensibilidad heurística, no intervalos de confianza calibrados.

## Cobertura obtenida

El conjunto normalizado inicial contiene **109.780 partidos, tres deportes y 17 ligas/competiciones**:

| Deporte | Partidos | Datos | Límite relevante |
| --- | ---: | --- | --- |
| Fútbol | 65.810 | Once ligas europeas, Argentina, Brasil, MLS y México; resultados y cuotas cuando existen | Sin cobertura universal de jugadores, alineaciones u orden de goles. |
| Básquet | 31.822 | NBA, archivo FiveThirtyEight desde 1990 | Termina en 2015; no permite pronósticos actuales ni ROI sin cuotas históricas. |
| Béisbol | 12.148 | MLB, temporada regular 2021–2025, Retrosheet | Ganador final incluyendo extra innings; sin cuotas ni playoffs en este conjunto. |

Hay además 64 historiales de eventos del Mundial 2022 para estudiar primer gol, y un CSV periódico de próximos partidos. Los datos de eventos no constituyen un modelo validado de primer goleador.

The Odds API está conectado mediante un plan Starter FREE. La exploración del 30/10/2026 devolvió 184 entradas del catálogo, 83 activas y 73 activas sin futuros; una captura por competición reunió 881 eventos. Esas cifras describen aquella captura: no significan que todos tengan históricos, modelos o precios ejecutables. La app muestra la fecha de cada observación.

La extracción multicasa privada conserva 65.810 identidades de partidos, separando precios pre-closing y closing. Incluye 1X2, más/menos 2,5 y hándicap asiático con línea explícita. Las casas objetivo se excluyen de su referencia al evaluar una oferta; promedios, máximos y exchange no se simulan como cuotas de una casa.

Ver fuentes, permisos, datos faltantes y descargas en [DATA_SOURCES.md](docs/DATA_SOURCES.md), el diagnóstico en [DIAGNOSIS_V1.md](docs/DIAGNOSIS_V1.md) y la verificación actual en [VALIDATION_V2.md](docs/VALIDATION_V2.md).

## Actualizar históricos e informe

Ejecutar en este orden:

```bash
python3 scripts/download_history.py
python3 scripts/download_us_sports.py
python3 scripts/build_report.py
```

El primer importador reconstruye el conjunto base de fútbol/NBA; el segundo incorpora MLB. Ambos deben ejecutarse antes del informe para conservar los tres deportes. Los históricos usan caché; `--refresh` solicita una nueva versión. Los fallos se registran en el manifiesto y nunca se rellenan cuotas faltantes con valores inventados.

Para refrescar únicamente el CSV gratuito de próximos partidos:

```bash
python3 scripts/download_history.py --fixtures-only
python3 scripts/build_report.py
```

El pipeline de informe predeterminado incorpora la investigación v2: extrae las casas históricas, reproduce las predicciones, selecciona con el intervalo declarado y genera el informe. **No consulta nuevos precios de The Odds API por sí mismo.** Las etapas también se pueden ejecutar por separado:

```bash
python3 scripts/build_quote_history.py
python3 scripts/research_v2.py
python3 scripts/build_report.py --reuse-research
```

`--reuse-research` reutiliza una investigación existente para tareas de integración/QA cuando sus entradas siguen correspondiendo a los datos. No convierte un resultado viejo en una evaluación nueva. `python3 scripts/build_report.py --legacy` permite reproducir el informe anterior. Para una reconstrucción normal de la versión actual, ejecutar `python3 scripts/build_report.py` sin esos flags.

La selección usa log loss de **2022–2023**. Los resultados de **2024 a 30/10/2026** se etiquetan como auditoría retrospectiva ya inspeccionada. El protocolo prospectivo y el código se identifican con un hash estable; repetir el informe con la misma especificación no debe reiniciar ese seguimiento.

## Iniciar el bot observador

Una pasada manual, también modo predeterminado de `python3 bot.py`:

```bash
python3 bot.py --once
```

Para mantener el proceso abierto y repetir con intervalo mínimo de 24 horas:

```bash
python3 bot.py --watch
```

Para actualizar también los resultados de fútbol disponibles:

```bash
python3 bot.py --watch --refresh-data
```

`--interval-hours` admite 24 o más. **No se instaló ningún servicio, daemon, tarea de sistema ni actualización automática al iniciar la computadora.** `--watch` funciona mientras el proceso y el equipo permanecen encendidos; `Ctrl+C` lo detiene. El bloqueo `flock` rechaza otra instancia simultánea del bot; este modo está preparado para el entorno Linux/Unix del proyecto.

Cada fecha UTC el bot selecciona hasta cuatro competiciones prioritarias activas (Argentina, Brasil, EPL y NBA) y ocho adicionales en rotación determinista, sin futuros. Consulta sólo `h2h`, región `eu`, con **máximo doce intentos de cuota por día**. Guarda cada intento antes de acceder a la red en `data/runtime/bot_state.json`: reiniciar el proceso ese día no vuelve a gastar la misma selección. Un fallo también conserva el intento. Respeta la caché de seis horas y el presupuesto SQLite de 450 reservas mensuales. Doce consultas diarias suman hasta 372 en 31 días; las capturas manuales consumen del mismo presupuesto.

Cada ciclo conserva snapshots, auditoría `bot_cycle` y una exploración con ID; actualiza atómicamente la parte `live` del informe. Mantiene el modo observación, las decisiones bloqueadas y los importes actuales en cero. Esto actualiza la app local; **no republica por sí solo el snapshot de Sites**.

`--refresh-data` es opcional y se intenta una sola vez por fecha UTC. Refresca los archivos de fútbol de la temporada europea actual y Argentina/Brasil/MLS/México, luego reconstruye el conjunto completo desde caché e incorpora Retrosheet. NBA y MLB siguen siendo archivos históricos: actualizar fútbol no los convierte en datos actuales. El backtest se recalcula sólo si cambia el hash de `matches.csv` o falta el informe. Ante un fallo del pipeline se restauran los normalizados y el informe coherentes anteriores; los archivos raw recién obtenidos permanecen como fuente. Las descargas parciales se registran como tales.

## Capturar cuotas sin contratar un plan

En este entorno la clave ya está configurada localmente. No hay que volver a registrarse. Para una instalación nueva, obtener una clave Starter FREE y guardarla mediante la entrada oculta del helper:

```bash
python3 scripts/configure_secret.py
```

La clave queda en `.env`, con permisos `600`, bajo `ODDS_API_KEY`. El archivo está excluido de Git y no se copia a la app ni a Sites. No se debe pegar la clave en comandos, URLs compartidas, HTML ni archivos del frontend.

Una consulta limitada:

```bash
python3 scripts/scan_odds.py --sport soccer_epl
python3 scripts/build_report.py
```

Una pasada por las competiciones activas que tienen partidos, excluyendo futuros:

```bash
python3 scripts/scan_odds.py --all-active
python3 scripts/build_report.py
```

La pasada utiliza un mercado `h2h` y una región por competición; `--limit 10` acota el número de competiciones. `--sport upcoming` devuelve eventos live y los próximos ocho entre deportes, **no todo el catálogo**. El scanner de modelos prepartido descarta los ya comenzados.

| Control | Comportamiento |
| --- | --- |
| Plan gratuito | 500 créditos mensuales del proveedor; históricos de cuotas excluidos. |
| Presupuesto local | Máximo 450 reservas por mes calendario UTC; configurable hacia abajo con `ODDS_API_MONTHLY_BUDGET`. |
| Caché de cuotas | Seis horas por deporte/región/mercados; repetir una consulta cacheada no vuelve a consultar al proveedor. |
| Catálogo | Caché de un día; el endpoint de deportes no consume créditos. |
| `--force` | Omite la caché, conserva el tope local y consume créditos cuando hay consulta. |
| Actualización automática | No hay servicio instalado; el modo `bot.py --watch` requiere iniciarlo y conservar el proceso abierto. Iniciar el servidor web no inicia el bot. |

Las reservas locales y la cuota real son registros distintos. Un error de red conserva la reserva de forma prudente; los encabezados del proveedor informan su consumo real y su período puede no coincidir con el mes UTC. No borrar la base para reiniciar artificialmente el contador.

La caché de seis horas ahorra créditos; una cuota almacenada seis horas **no se considera fresca para decidir**. El scanner exige una marca válida de los últimos 15 minutos, además de reglas, historial y modelo adecuados. La versión actual conserva el bloqueo global aunque alguna selección pase filtros descriptivos.

Primer goleador y otros props se consultan por evento desde el backend local. Descargar un precio no habilita un pronóstico: faltan modelo específico, participación/alineación, cobertura y reglas de liquidación. No se normaliza una lista incompleta de jugadores como si agotara todos los resultados posibles.

## Simulación manual y registro

El backend ofrece un ledger independiente del backtest. Una probabilidad introducida manualmente queda identificada como `manual_user_assumption`; no se atribuye al modelo. Los ajustes iniciales son 1.000 USD de capital ficticio, cuarto de Kelly, hasta 1 % por posición, 2 % por evento y 10 % de exposición total. Monedas admitidas: USD, ARS y EUR; no hay conversión de divisas automática.

Las simulaciones se crean y liquidan mediante la API local. Liquidaciones `won`, `lost` o `void`; una ya liquidada no cambia silenciosamente de resultado. Reutilizar un `request_id` UUID conserva una sola posición.

| Endpoint local | Función |
| --- | --- |
| `GET /api/health` | Estado y modo de ejecución. |
| `GET /api/report`, `/api/live` | Informe histórico y última exploración local. |
| `GET /api/provider-status` | Configuración y cuota, sin revelar la clave. |
| `GET /api/scans`, `/api/scans/{id}` | Historial de exploraciones y captura individual. |
| `GET /api/audit` | Actividad auditada. |
| `GET /api/settings`, `POST /api/settings` | Parámetros de simulación. |
| `POST /api/scan`, `/api/scan-event` | Consulta acotada de cuotas con caché y presupuesto. |
| `POST /api/calculate` | EV/Kelly de un supuesto manual; no ejecuta una posición. |
| `GET /api/paper-bets`, `/api/paper-equity` | Ledger y capital ficticio. |
| `POST /api/paper-bets`, `/api/paper-bets/settle` | Registrar y liquidar una simulación. |

Las operaciones POST requieren JSON y origen local. El ledger manual y los experimentos históricos son sistemas separados: la política v2 usa Kelly al 10 %, hasta 0,25 % por evento y 2 % por fecha; no cambia retroactivamente al modificar los ajustes del ledger manual.

## App local y Sites privado

La app local usa el backend, SQLite y la caché de esta computadora. La [versión publicada en Sites privado, sólo propietario](https://kraken-edge-joaquin.workraken.chatgpt.site) distribuye una captura del informe y del historial para consultar. El sitio estático no dispone del backend local, no contiene claves y no puede actualizar cuotas ni modificar el ledger de esta máquina. Para actualizarlo hay que regenerar y publicar una nueva captura.

No se publica el proyecto como repositorio público ni se incluyen datos raw/normalizados, `.env` o SQLite en el sitio. Sites conserva una copia privada del código de su panel para desplegarlo. El acceso privado se conserva al desplegar. Las atribuciones de las fuentes acompañan a los derivados mostrados.

## Archivos y comprobaciones

```text
app/                       Interfaz y artefactos del informe
backend/                   Proveedores, scanner, SQLite y simulación manual
engine/                    Modelos, métricas y replay cronológico
config/                    Catálogo de proveedores y mercados
scripts/                   Descargas, capturas y generación del informe
data/raw/                  Archivos originales locales, ignorados
data/processed/            Tablas normalizadas y exportaciones locales, ignoradas
data/analysis/             Experimentos, baseline v1 y precios multicasa privados, ignorados
data/runtime/              SQLite y última exploración, ignorados
data/manifest.json         Procedencia, recuentos y hashes
bot.py                     Observador diario acotado, manual o con proceso abierto
tests/                     Verificación matemática, backend y ciclo del bot
```

```bash
python3 -m unittest discover -s tests -v
```

La suite incluye controles del motor, backend, bot, consenso, selección temporal, modelos por estadística, hándicaps y portfolios con stress de precio. Usa datos acotados, proveedores simulados y bases temporales; no necesita consumir la API de cuotas. Los resultados de la revisión actual se documentan en [VALIDATION_V2.md](docs/VALIDATION_V2.md).

La prueba de integración inicial (v1) del 30/10/2026 ejecutó `bot.py --once`: terminó sin errores, reutilizó doce capturas cacheadas, reservó cero créditos adicionales y actualizó el informe con 2.560 observaciones. Se conservaron el hash del backtest y sus 23.940 decisiones completas. También se comprobó la app privada con sesión iniciada y la carga de todo ese historial. La revisión actual se distingue en [VALIDATION_V2.md](docs/VALIDATION_V2.md). No se dejó `--watch` activo; el servidor local se vuelve a iniciar con `./run.sh`. Para preservar el registro personal, conservar una copia de `data/runtime/kraken.sqlite3` con el servidor detenido. Las descargas públicas se pueden regenerar; el ledger y las capturas personales son datos locales propios. `data/runtime/reproducibility/` conserva comprimidos los CSV históricos usados y las fuentes matemáticas que identifica cada captura. El registro prospectivo v2 identifica además la especificación, política y fuentes relevantes por SHA-256.

La explicación completa del cálculo está en [METHODOLOGY.md](docs/METHODOLOGY.md), los contratos de mercados en [MARKETS.md](docs/MARKETS.md), el flujo técnico en [ARCHITECTURE.md](docs/ARCHITECTURE.md) y el trabajo pendiente en [NEXT_STEPS.md](docs/NEXT_STEPS.md).

El registro prospectivo se puede consultar mediante `GET /api/prospective` en el servidor local. Al cerrar esta versión hay 20 eventos registrados y pendientes; el contador de resultados completados sigue en cero. La referencia anterior se conserva localmente y el historial actual declara su propio recuento en el informe.

## Auditoría de mercados de fútbol

La pestaña «Fútbol · mercados» documenta 184 modalidades, 20 familias y 62 fuentes oficiales de 11 marcas. La captura del 30/10/2026 compara precios y pagos, separada del modelo v2 congelado. Sus nueve carteras de precio en seis partidos son teóricas y ninguna tiene ejecución confirmada; los escenarios de fricción eliminan sus retornos mínimos positivos. Ver [resultados y límites](docs/FOOTBALL_AUDIT_RESULTS.md), [catálogo de reglas](docs/FOOTBALL_MARKETS_AUDIT.md) y [derivaciones matemáticas](docs/MATHEMATICAL_EDGES.md).

Para reproducir desde la muestra guardada, sin consultar la API:

```bash
python3 scripts/build_sport_comparison.py
python3 scripts/build_football_audit.py
```

`scripts/football_audit_sample.py` realiza una descarga nueva, con control de cuota gratuita y un máximo local de 100 créditos reservados por ejecución. No hace falta ejecutarlo para recalcular el informe existente. La comparación entre deportes filtra región EU antes de construir los mercados completos, usa las mismas siete marcas y limita los eventos a los próximos siete días; sus índices de precio no estiman ROI.
