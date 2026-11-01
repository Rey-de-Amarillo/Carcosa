# Datos gratuitos de fútbol descargados

Base consultable: `data/processed/free_football_history.sqlite` (532,422,656 bytes).
Se conserva cada proveedor por separado. **Las filas de distintas fuentes no se suman como partidos únicos.**

| Fuente | Registros conservados | Precios válidos | Cobertura |
|---|---:|---:|---|
| Club Football Match Data / Football-Data | 238,858 partidos; 238.854 con marcador | 2,297,290 celdas de cuotas, incluidos máximos del mercado | 1X2, total 2,5 y hándicap; 2000–2026 |
| SGodds / Singapore Pools | 3,257 partidos; 3,143 con HT y FT | 319,975 precios | 18 familias: primer tiempo, resultado exacto, goles exactos, BTTS, HT/FT, primer equipo en marcar, hándicap; 2025–2026 |
| Archivo de investigación atribuido a Betcity | 422,178 filas; 406,330 con marcador interpretable | 4,857,197 precios | Totales por partido/equipo, hándicap, resultado/doble oportunidad y ambos marcan; 2022–2025 |
| Muestra pública oficial de Betfair BASIC | **1 partido**, 77 mercados | 5,628 cambios de último precio negociado | Middlesbrough–Manchester City, 30/04/2017; muestra de formato, no archivo masivo |
| Instantánea pública de SharpAPI | **2 fixtures identificados**, además de contratos de torneo/preguntas; sin resultados | 6,132 precios; 99 tipos de mercado, 20 fuentes | Goleadores, remates, tarjetas de jugadores, córners, primeros tiempos y más; captura del 13/07/2026 |
| OddsPapi, Pinnacle + DraftKings | 5 IDs de partidos finalizados según API, sin marcadores importados | 1,560,124 observaciones históricas | Mercados por partido y jugador, con marcas de tiempo, actividad y límites originales |


El primer tiempo en SGodds sí tiene cuotas históricas: `Htou_01` y `Htou_02` son over/under con su línea original `Htou_Hcap`. Las filas pendientes conservan resultado nulo. Los precios de primer equipo en marcar no pueden liquidarse en general solamente con HT/FT; faltan secuencias de goles.

Se contrastaron 280 resultados de Premier League: 280 coincidieron en marcador de descanso y final con los CSV locales, con alias documentados y tolerancia de fecha de un día. Esta comprobación no verifica cuotas ni otros campeonatos.

El archivo Betcity conserva todas las filas originales, incluso duplicados y competiciones señaladas: 23 ciber/simuladas, 33 de variantes y 58 con duración personalizada. **Los otros 422.064 registros también tienen formato y duración sin verificar**. Su `id` original se repite; se usa una clave de fila propia. `P1/P2` significa equipo local/visitante. Las fechas no tienen zona horaria y la antelación real de las cuotas no está verificada.

Los archivos grandes guardan sus precios en columnas u objetos originales y ofrecen vistas largas (`cf_prices`, `betcity_prices`), sin copiar millones de precios. Betfair conserva por separado cada selección y hándicap; sus metadatos parciales se acumulan en orden, y `pt` es publicación del mensaje. LTP es una operación previa: no representa una oferta ejecutable ni liquidez disponible.

No se encontraron en los CSV/Parquet grandes cuotas históricas de jugadores, córners o tarjetas. **La instantánea SharpAPI sí contiene esos precios**, pero no una temporada ni resultados: 5.501 filas corresponden a los dos IDs de fixture identificados (Francia–España e Inglaterra–Argentina); los otros contratos incluyen apuestas de torneo, preguntas y comparaciones entre jugadores. Los 250 `event_id` de origen no representan 250 partidos. Sus 16 colisiones de `id` se conservan sin deduplicar precios diferentes. La muestra Betfair permite inspeccionar mercados disponibles en **ese solo partido**. No se inventan cuotas de combinadas multiplicando cuotas individuales.

OddsPapi se incorpora desde la cuenta gratuita: cinco partidos de Premier League del 17/10/2026, con historial de Pinnacle y DraftKings. Las observaciones repetidas se conservan: no son 1,56 millones de apuestas diferentes ni cambios de precio. Los IDs de jugadores no se convierten en nombres inventados. `active`, `limit`, campos nulos/ausentes y `createdAt` quedan conservados. Algunos nombres de mercado incluyen prórroga; no se presupone liquidación a 90 minutos ni se inventan resultados. La consulta de historial fue gratuita; la auditoría registra 4/250 solicitudes consumidas al terminar.


Football-Data limita el uso a particulares y excluye productos comerciales o de entrenamiento automatizado; la licencia MIT del recopilador no sustituye las condiciones originales. SGodds no aporta licencia abierta de redistribución. Betcity tiene descarga pública de investigación, sin licencia explícita de datos. SharpAPI declara CC BY 4.0, con atribución a SharpAPI. Las condiciones, URL, fecha de descarga y SHA-256 quedan en `sources` y `source_files`; los archivos originales siguen locales.

## Consultas útiles

```sql
-- Cuotas de un gol o más durante el primer tiempo, con HT/FT reales:
SELECT m.match_name, m.start_time_source, p.decimal_odds, m.ht_home, m.ht_away
FROM sgodds_prices p JOIN sgodds_matches m USING(match_row_id)
WHERE p.market='ht_goal_total' AND p.selection='over'
  AND CAST(p.line_source AS REAL)=0.5 AND m.has_ht_ft_result=1
ORDER BY m.start_time_source LIMIT 20;

-- Inventario de los 18 mercados de SGodds:
SELECT market, COUNT(*) FROM sgodds_prices GROUP BY market;

-- Precios de ambos marcan en Betcity; no implica duración o ejecución verificadas:
SELECT event_name, event_date_source, source_key, decimal_odds, scope_flag
FROM betcity_prices WHERE market_family='both_teams_to_score' LIMIT 20;

-- Últimos precios negociados publicados antes de pasar a en vivo, muestra Betfair:
SELECT event_name, market_name, runner_name, publication_ms, ltp
FROM betfair_named_ltp_updates WHERE in_play=0
ORDER BY publication_ms DESC LIMIT 20;

-- Procedencia exacta:
SELECT source_id, path, url, retrieved_at, sha256 FROM source_files;

-- Precios de goleadores/jugadores en la instantánea; no contiene resultados:
SELECT sportsbook, home_team, away_team, market_type, selection,
       decimal_odds_valid, timestamp
FROM sharpapi_quotes
WHERE identified_fixture_source_id=1
  AND market_type IN('anytime_goal_scorer','first_goal_scorer','player_cards')
LIMIT 20;

-- Historial real adquirido por partido/casa/mercado/selección/jugador:
SELECT fixture_id,bookmaker,market_id,outcome_id,player_id_source,
       created_at_source,decimal_odds,active_json_type,active_source,
       limit_json_type,limit_source
FROM oddspapi_history_ticks LIMIT 20;

-- Consultar etiqueta y alcance de un mercado conservado en el catálogo:
SELECT market_id,market_name,period_source,handicap_source,player_prop_source
FROM oddspapi_market_catalog WHERE sport_id=10 AND market_id='101';

```

Reconstrucción sin descargas ni cambios al modelo:

```bash
python3 scripts/build_free_football_database.py --pyarrow-path /tmp/football-research-pyarrow
```

Verificaciones: `PRAGMA integrity_check = ok`, claves foráneas sin errores y recuentos reconciliados con 6 auditorías fuente. No se calcularon retornos ni se entrenó el bot con esta incorporación.
