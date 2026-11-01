"""Publish the football workspace assets without raw archives or credentials.

Regenerate data first with scripts/export_football_workspace.py when source
archives change. The Site receives only the named UI files and derived tables.
"""
from pathlib import Path
import json
import shutil

root = Path(__file__).resolve().parents[1]
source = root / 'app'
target = root / 'site/dist'
manifest = json.loads((source / 'data/workspace.json').read_text())
assets = ['index.html', 'styles.css', 'app.js', 'formula-engine.js',
          'formula-builder.js', 'workspace-data.js', 'entity-presentation.js',
          'football-alert-builder.js', 'football-formula-editor.js', 'football-unified-formula.js',
          'football-market-catalog.js', 'football-situations.js', 'football-strategy-engine.js', 'strategy-store.js',
          'data/entities.json', 'data/entity-badges.json', 'data/football-market-history.json',
          'data/football-market-history.json.gz',
          'data/workspace.json', 'data/' + manifest['tables']['events']['path']]
assets += ['data/' + part['path'] for part in manifest['tables']['offers']['parts']]
assets += [p.relative_to(source).as_posix() for p in (source / 'assets/football').rglob('*.png')]
assets += [p.relative_to(source).as_posix() for p in (source / 'vendor/workraken').rglob('*')
           if p.is_file() and p.suffix != '.md']
for relative in assets:
    path = source / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size >= 25 * 1024 * 1024:
        raise ValueError(f'Static asset exceeds hosting limit: {relative}')
# dist is generated from this allowlist; remove stale previous dashboard assets.
if target.exists():
    shutil.rmtree(target)
target.mkdir(parents=True)
for relative in assets:
    dest = target / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / relative, dest)
(root / 'site/README.md').write_text('''# WorKraken · Fútbol

Espacio privado de datos y fórmulas: 1X2, probabilidades de otras casas sin
margen, EV estimado y rendimiento de las jugadas históricas coincidentes.

El creador reúne equipos, jugadores, cuotas y mercados en una sola fórmula,
con condiciones y grupos unidos por Y/O. Los desplegables madre Equipos,
Jugadores, Goles, Cuotas y las demás familias contienen sus campos, usando
los paneles originales de Workraken. Las fórmulas guardadas conservan
íntegramente sus condiciones y agrupaciones. Los desplegables usan mercados
reales de fútbol y conservan los controles originales de Workraken.
Incluye resultado, doble oportunidad, empate no válido, hándicaps, goles,
descanso/final, córners, tarjetas y mercados de jugadores.
Los jugadores se vinculan a equipos mediante identidades verificadas y capturas
de planteles. Jugador y mercado filtran la selección cotizada: elegir un jugador
no incluye apuestas genéricas de su equipo, y elegir gana el local no incluye
otras selecciones del mismo partido. Las cuotas y probabilidades se conservan
cuando existen referencias independientes para la apuesta elegida.
Las alertas anteriores conservan su evaluación original, que utiliza
exclusivamente fechas anteriores.
Las combinadas requieren precio conjunto y no multiplican probabilidades marginales.
Cuotas ingresadas se distinguen del archivo. Los datos ausentes permanecen nulos.

La regla 1X2 conservada usa EV >= 3%, al menos tres referencias, cuota entre 1.2 y 5,
y una selección de mayor EV por partido. El precio de la casa evaluada no se
incluye en sus referencias. La interfaz permite editar expresiones con nombres,
guardar fórmulas en el navegador, filtrar períodos/ligas/casas, revisar cada
selección y exportar CSV. EV estimado y ROI histórico son métricas separadas.

Datos derivados de Football-Data.co.uk, para uso personal privado. La carpeta
dist no incluye claves, archivos originales ni conexiones autenticadas.
También contiene precios archivados de SGodds / Singapore Pools y un catálogo
verificado de jugadores de FPL, ESPN y referencias oficiales de los clubes.
Los gzip por año se descomprimen en el navegador. No ejecuta apuestas.

Fuente reproducible en el proyecto local: scripts/export_football_workspace.py.
Otros exportadores: scripts/export_football_market_history.py,
scripts/export_football_entities.py, scripts/vendor_workraken_ui.py.
Validación del motor: node tests/test_formula_engine.mjs.
Validación de alertas: node tests/test_alert_workflow.mjs.
''', encoding='utf-8')
print(f'Prepared {len(assets)} allowlisted football workspace assets.')
