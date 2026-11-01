# Fuentes y cobertura real

Verificado el **30 de octubre de 2026**. Presupuesto: **cero planes pagos**. Un histórico descargado no equivale a un modelo validado, y un resultado final no contiene el orden de los goles. El catálogo legible por la app está en `config/providers.json`; recuentos, fechas, URLs originales y SHA-256 están en `data/manifest.json`.

## Fuentes conectadas

| Fuente | Qué se descarga | Qué permite estudiar | Límites prácticos |
| --- | --- | --- | --- |
| [Football-Data.co.uk](https://www.football-data.co.uk/data.php) | CSV de once ligas europeas, temporadas 2015/16–2026/27; Argentina, Brasil, MLS y México | Ganador/empate, totales 2.5; marcadores HT, córners y tarjetas como resultados cuando existen | CSV periódico; no player props ni secuencia de goles. Uso privado según sus términos, sin redistribución de datos. |
| [Fixtures Football-Data](https://www.football-data.co.uk/fixtures.csv) | Próximos partidos y cuotas de varias casas | Exploración de diferencias de precios y probabilidades | No ticks live; timestamp individual de cada precio y zona horaria del kickoff sin verificar. Ninguna cuota se marca ejecutable. |
| [StatsBomb Open Data, ahora Hudl](https://github.com/hudl/open-data) | Eventos del Mundial masculino 2022, hasta 64 partidos | Primer gol observado por equipo/jugador; resultado 90 minutos; sin cuotas | Muestra pequeña y seleccionada. No habilita un modelo fiable de primer goleador. Atribución y logo de StatsBomb si se publican análisis. |
| [FiveThirtyEight NBA Elo](https://github.com/fivethirtyeight/data/tree/master/nba-elo) | Archivo de resultados NBA, reteniendo desde 1990 | Evaluación cronológica de un baseline Elo | El archivo termina en 2015; no sirve para decisiones actuales, no contiene odds ni props. [CC BY 4.0](https://raw.githubusercontent.com/fivethirtyeight/data/master/LICENSE), crédito original Basketball-Reference. |

Los datos raw se conservan localmente y no se incluyen en la publicación de la app. Los análisis de esta versión son privados y de investigación. Football-Data presenta acceso gratuito para particulares y excluye productos comerciales o de entrenamiento de datos mediante bots/AI; no se interpreta como una licencia abierta. Consultar [su página](https://www.football-data.co.uk/data.php) antes de ampliar el alcance o redistribuir. La licencia completa de StatsBomb está [aquí](https://github.com/hudl/open-data/blob/master/LICENSE.pdf).

## APIs gratuitas investigadas

| Proveedor | Plan gratis verificado | Uso razonable | Lo que no se debe prometer |
| --- | --- | --- | --- |
| [The Odds API](https://the-odds-api.com/) | 500 créditos/mes, cuenta gratuita conectada; clave sólo en backend | Ventanas selectivas de cuotas multideporte; todos los mercados permitidos según cobertura; guardar snapshots hacia adelante | Históricos no incluidos. El costo crece con mercados y regiones; cubrir todos los deportes cada minuto no entra en 500 créditos. |
| [API-Football](https://www.api-football.com/pricing) | 100 solicitudes/día, sin tarjeta; temporadas limitadas | Partidos, eventos, alineaciones y otros endpoints con cobertura por liga/temporada | No se asume archivo completo de cuotas ni todos los mercados/player props. |
| [BALLDONTLIE NBA](https://docs.balldontlie.io/) | 5 solicitudes/minuto para equipos, jugadores y partidos | Actualizar resultados de NBA con cuenta gratuita | Cuotas, props, box scores y play-by-play requieren GOAT. No activar prueba que pida tarjeta. |

The Odds API permite almacenar datos y usarlos en modelos/apps analíticas, pero prohíbe revenderlos como una fuente raw independiente. Ver [términos vigentes](https://the-odds-api.com/terms-and-conditions.html) y [documentación de costos](https://the-odds-api.com/liveapi/guides/v4/). No se confunde `the-odds-api.com` con otros sitios de nombre parecido.

## Tenis: disponibilidad real, no fuentes inventadas

- **Jeff Sackmann ATP/WTA:** los dos repositorios originales responden HTTP 404 en esta fecha. [El perfil original](https://github.com/JeffSackmann) conserva Match Charting Project, un producto distinto. No se descargaron mirrors como si fueran originales activos.
- **[Tennis-Data.co.uk](https://www.tennis-data.co.uk/alldata.php):** devuelve HTTP 403 desde este entorno, también para CSV/XLSX. No se intentó evadir el bloqueo.
- **[TennisData.App](https://tennisdata.app/downloads/):** anuncia CSV ATP/WTA 2021–2026 con ganador y primer set, odds cuando existen. Presenta comprobación humana; no se saltó. Sus cuotas suelen ser de cierre. Puede ser una vía de importación manual gratuita.
- **[TennisMyLife](https://stats.tennismylife.org/tennis-match-database):** CSV accesibles y actualizados. Sus términos permiten investigación personal/no comercial, excluyen uso comercial de modelos sin autorización y no autorizan redistribuir raw. Se cataloga sin descargar para el bot operativo. Además `tourney_date` representa la semana del torneo, no la fecha exacta: usarla para ordenar rondas produciría riesgo de fuga temporal.

## Más deportes y mercados

[Retrosheet](https://www.retrosheet.org/gamelogs/index.html) ya está conectado: **12.148 juegos de temporada regular MLB 2021–2025**, sin odds. Su aviso permite reutilización con atribución. No se anuncian como conectados NFL, NHL, cricket, rugby, MMA, esports o player props.

Cada deporte y mercado requiere su propio modelo y su propia validación temporal. Córners/tarjetas necesitan modelos de conteo; primer gol requiere secuencia de eventos, ningún gol y reglas de autogoles; goleador por jugador requiere minutos esperados/alineaciones/sustituciones y cuotas comparables. No se convierte una tasa de victorias o una frecuencia histórica en probabilidad predictiva sin evaluación fuera de muestra.

## Contrato de los archivos

`data/processed/matches.csv`:

```text
id,sport,league,season,date,home_team,away_team,home_score,away_score,
home_odds,draw_odds,away_odds,odds_source,league_code,source,odds_snapshot,
over25_odds,under25_odds,odds25_source,home_ht_score,away_ht_score,
home_corners,away_corners,home_yellow,away_yellow,home_shots,away_shots,
home_shots_on_target,away_shots_on_target,neutral_venue
```

- Fechas ISO `YYYY-MM-DD`; todos los partidos tienen marcador final conocido.
- Campos faltantes permanecen vacíos; nunca se fabrican cuotas. NBA no tiene cuotas.
- Se elige el triplete completo Bet365, luego media de mercado; un mismo mercado no mezcla casas. Se registra la selección en `odds_source`. Las columnas Bet365 sin `C` son **pre-closing**, no necesariamente apertura ni precio capturado a una hora fija: [diccionario oficial](https://www.football-data.co.uk/notes.txt).
- Argentina/Brasil/MLS/México publican principalmente closing y están etiquetados `odds_snapshot=closing`. Un backtest a esos precios es histórico; no prueba que el usuario pudiera ejecutarlos.
- El proveedor advierte precios Pinnacle desactualizados desde el 23/07/2025. La preferencia normal es Bet365/media, sin usar máximos sintéticos como cuotas ejecutables.
- En NBA cada encuentro aparecía dos veces; se conserva una perspectiva y se orienta local/visitante con `game_location`. Fecha original estadounidense parseada explícitamente. Se excluyen partidos ABA; neutralidad registrada.
- `fixtures.csv`: próximos partidos, `retrieved_at` UTC y `source_last_modified` cuando el servidor lo entrega. `odds_timestamp` vacío y `kickoff_reliable=false` expresan información desconocida, no un error oculto.
- `fixtures_odds.csv`: una fila por partido/casa/mercado/selección, separación de medias de mercado y bookmaker real. `is_executable_quote=false` hasta comprobar frescura, disponibilidad, reglas y límites.
- `first_goals.csv`: eventos observados del Mundial 2022; sólo períodos 1 y 2, sin prórroga ni penales. Autogoles tratados como gol del equipo beneficiado, pero no como gol del jugador para primer goleador. No es un dataset de cuotas ni un modelo entrenado.

## Reproducibilidad

```bash
python3 scripts/download_history.py
python3 scripts/download_us_sports.py
python3 scripts/download_history.py --fixtures-only
python3 scripts/download_history.py --refresh --skip-events
```

La descarga usa caché local para archivos históricos y refresca fixtures. Cada resultado registra URL, fecha de acceso, Last-Modified cuando está disponible, bytes, cantidad de filas y hash SHA-256. Fallos de red quedan en `data/manifest.json`; una descarga incompleta no se anuncia como completa. Las actualizaciones con `--refresh` son una nueva versión de los datos y deben producir una nueva corrida del modelo.

### Mercados adicionales The Odds API

La clave FREE ya fue conectada por el backend. La [tabla oficial de planes](https://the-odds-api.com/) incluye todos los mercados y excluye sólo históricos. Primer goleador de fútbol usa `player_first_goal_scorer`: la [cobertura oficial](https://the-odds-api.com/sports-odds-data/betting-markets.html) se limita a EPL, Ligue 1, Bundesliga, Serie A, La Liga y MLS, en casas estadounidenses. Se consulta por evento (`/sports/{sport}/events/{eventId}/odds`), no en el endpoint masivo. No se interpreta una respuesta vacía como prohibición del plan. El endpoint `upcoming` devuelve partidos live y los próximos ocho entre deportes; el catálogo completo requiere consultas por deporte.

Logo oficial StatsBomb incluido en `app/assets/statsbomb-logo.png`, descargado del repositorio de la fuente, carpeta `img/`. En vistas de resultados derivados de StatsBomb debe mostrarse junto con el crédito y enlace al repositorio.

### MLB autorizado y NHL pendiente

Se usaron ZIP anuales descargables de [Retrosheet](https://www.retrosheet.org/gamelogs/index.html), no el bulk de MLB StatsAPI. El [aviso Retrosheet](https://www.retrosheet.org/notice.txt) autoriza reutilización con crédito. Mostrar prominentemente el texto de `data/RETROSHEET_ATTRIBUTION.txt` en vistas de resultados derivados.

`baseball.csv` conserva resultados finales, **incluyendo extra innings**, de temporada regular; no incluye playoffs, odds ni ROI. Las cinco temporadas publicadas descargadas son 2021–2025; no se inventa disponibilidad de 2026. Los 440 encuentros de doble jornada conservan el número de juego en su ID. Para los 22 suspendidos, la fecha canónica se mueve a la finalización, conservando `original_date`: usar su resultado en la fecha inicial habría filtrado información futura. Hay 1.058 partidos con diez innings o más; en 2021 también existieron encuentros programados a siete, por lo que no se interpreta automáticamente un partido de ocho o nueve innings como reglamentario sin consultar sus reglas.

Los nombres de franquicias se normalizaron para continuidad (Cleveland Guardians y Athletics); los códigos originales están conservados. Las estadísticas finales del game log se usan sólo como resultados/etiquetas, nunca como predictores prepartido. `neutral_venue=unknown`: no se presume localía efectiva en partidos internacionales. El [diccionario de campos](https://www.retrosheet.org/gamelogs/glfields.txt) permite reproducir la transformación.

MLB StatsAPI quedó `bulk_permission_required`: su [aviso específico](https://gdx.mlb.com/components/copyright.txt) limita las descargas masivas sin autorización. NHL quedó `permission_required_and_http403`; sus [términos](https://www.nhl.com/info/terms-of-service) requieren autorización para compilación automatizada. No se importaron historiales oficiales mediante esos endpoints.

El pipeline completo debe ejecutar primero `download_history.py` y luego `download_us_sports.py`; el primero reconstruye el archivo base y el segundo incorpora MLB atómicamente. Repetir el segundo es idempotente. El manifiesto agregado registra fuentes, cinco hashes ZIP y reglas de resultado. Las cuotas actuales h2h de béisbol/hockey deben comprobar sus reglas de extra innings/prórroga/shootouts antes de compararse con modelos de resultado final.
