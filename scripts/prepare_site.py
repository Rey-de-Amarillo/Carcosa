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
          'football-formula-library.js',
          'football-price-engine.js', 'football-price-editor.js', 'football-price-library.js',
          'formula-metrics.js', 'formula-metrics-worker.js', 'formula-metrics-view.js',
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

El creador matemático reúne cuotas, importes, pagos, valor esperado y cobertura
en una sola fórmula con condiciones y grupos unidos por Y/O. Los desplegables
madre contienen campos del tamaño original de Workraken. Incluye 120 fórmulas
iniciales basadas en relaciones de precio; las fórmulas propias se conservan.
La grilla incluye búsqueda, paginación y filtros por EV, ROI y muestra.

EV = probabilidad de referencia × cuota + probabilidad de devolución − 1 − costo.
La casa evaluada se excluye de las referencias. La cobertura reparte el importe
y evalúa el pago total en cada resultado posible, incluida doble oportunidad
con pagos superpuestos. Los registros deben tener contratos compatibles y
captura verificable; sin ella no se presenta un arbitraje histórico. La
calculadora manual y las variantes de costo/cuota se identifican como escenarios.
Los datos ausentes permanecen nulos. EV estimado y ROI histórico son métricas
separadas. Las fórmulas anteriores mantienen su evaluación y pueden editarse.

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
