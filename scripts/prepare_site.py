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
          'football-data-archive.js', 'football-data-browser.js', 'data/legacy-sgodds-provenance.json',
          'football-alert-builder.js', 'football-formula-editor.js', 'football-unified-formula.js',
          'football-formula-library.js',
          'football-price-engine.js', 'football-price-editor.js', 'football-reference-price-editor.js', 'football-price-library.js',
          'formula-metrics.js', 'formula-metrics-worker.js', 'formula-metrics-view.js',
          'football-market-catalog.js', 'football-situations.js', 'football-strategy-engine.js', 'strategy-store.js',
          'data/entities.json', 'data/entity-badges.json', 'data/football-market-history.json',
          'data/football-market-history.json.gz',
          'data/workspace.json', 'data/' + manifest['tables']['events']['path']]
assets += ['data/' + part['path'] for part in manifest['tables']['offers']['parts']]
for archive_name in ['expanded-football-manifest.json', 'additional-market-manifest.json', 'research-market-manifest.json']:
    archive_manifest = json.loads((source / 'data' / archive_name).read_text())
    assets.append('data/' + archive_name)
    for partition in archive_manifest['partitions']:
        name = partition['path']
        if Path(name).name != name or not name.endswith('.json.gz'):
            raise ValueError(f'Invalid archive partition: {name}')
        assets.append('data/' + name)
assets = list(dict.fromkeys(assets))
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

Espacio privado de cuotas, importes, fórmulas y pagos de fútbol.

El creador matemático trabaja con las cuotas de una misma casa y calcula el
pago en cada resultado posible. Sus campos son suma inversa, pago mínimo,
beneficio mínimo y retorno mínimo, unidos por Y/O. Las mismas cuotas producen
el mismo cálculo con cualquier equipo o casa. Usa los campos originales de
Workraken y una grilla con búsqueda, paginación y orden por métricas.

Incluye 120 fórmulas iniciales: tres estructuras de resultados, cinco retornos
mínimos y ocho variantes de costo o caída de cuota, con importe inicial 100.
No requiere probabilidades deportivas ni precios de otras casas. Reparte el
importe, redondea a centavos y comprueba el pago más bajo de todos los casos,
incluida doble oportunidad con pagos superpuestos.

Las cotizaciones se agrupan por evento, casa, mercado, período y línea. Un grupo
completo sin precios ambiguos puede calcularse como escenario de archivo aunque
falten tiempo o reglas verificables. No prueba simultaneidad ni posibilidad de
ejecución. Los grupos incompletos o ambiguos quedan sin evaluar y se conservan
las marcas originales sin inventar capturas. El retorno mínimo y el ROI de
escenarios se distinguen de una captura verificada. Las
fórmulas propias anteriores se conservan en el archivo; se respalda la colección
antes de reemplazar ejemplos automáticos sin editar.

La pestaña Datos muestra fuentes, casas de apuestas, URL de origen, fecha de
consulta, mercados y SHA-256 en grillas con búsqueda y paginación. El archivo
ampliado contiene 6.595.472 cotizaciones de 21 casas, 22 ligas y 27 temporadas;
se conservan separadas las fases previas y de cierre. SGodds aporta 94.798
precios adicionales atribuidos a Singapore Pools. Otros 6.429.081 registros de
investigación incluyen series temporales y muestras; no son partidos únicos.
Cada proveedor conserva su identidad. Los LTP de Betfair son operaciones
publicadas, y el archivo atribuido a Betcity tiene formato/duración no verificados.
El explorador carga un archivo por vez. Los datos normalizados pueden aplicarse
a las fórmulas eligiendo una sola fase; la colección de investigación se consulta
sin transformar sus contratos en apuestas normalizadas.

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
