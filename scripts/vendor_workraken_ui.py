#!/usr/bin/env python3
"""Vendor the actual WorKraken UI stylesheet bundle and referenced local assets.

The CSS is not restyled. Only /static and /assets URL roots are relocated so
this standalone football app can serve the same assets under its vendor root.
No application code, business data, credentials, templates or repository state
are copied. Source and output hashes record provenance for every shipped file.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path('/home/joaquin/Escritorio/GitHub Proyectos/WorKraken-web')
CSS_FILES = ('styles.css', 'neptuno-merged.css', 'neptuno-vertical.css',
             'account-profile.css', 'shell.css')
BRAND_FILES = ('workraken_mark.png', 'workraken_wordmark_light.png',
               'workraken_wordmark_dark.png', 'favicon.png')
SIDEBAR_FILES = ('engranaje.png', 'engranaje-dark.png')
JS_FILES = {
    'search.js': 'webapp/static/js/modules/estacionamiento/compartido/busqueda.js',
    'date-picker.js': 'webapp/static/js/shared/date-picker.js',
    'single-select.js': 'webapp/static/js/shared/currency-country-picker.js',
    'floating-dropdowns.js': 'webapp/static/js/shared/floating-dropdowns.js',
}
REFERENCE_FILES = ('webapp/templates/base.html', 'webapp/templates/_pagination.html',
                   'webapp/templates/_parking_contracts_panel.html')
LOCAL_URL = re.compile(r'''url\((['"]?)(/(?:static|assets)/[^)'"\s]+)\1\)''')
VENDOR_URL = '/vendor/workraken'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_asset(source: Path, url: str) -> Path:
    raw = url.split('?', 1)[0]
    relative = 'webapp/' + raw.lstrip('/') if raw.startswith('/static/') else raw.lstrip('/')
    path = (source / relative).resolve()
    if not path.is_relative_to(source.resolve()):
        raise ValueError('Asset escapes source directory')
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    source = args.source.resolve()
    target = ROOT / 'app/vendor/workraken'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    source_paths = [f'webapp/static/{name}' for name in CSS_FILES]
    source_paths += [f'assets/branding/{name}' for name in BRAND_FILES]
    source_paths += [f'assets/sidebar/{name}' for name in SIDEBAR_FILES]
    source_paths += list(JS_FILES.values())
    # Refuse to silently label locally edited styles as the committed reference.
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', *source_paths], cwd=source,
                   check=True, stdout=subprocess.DEVNULL)
    records = []
    copied = set()

    def write(src: Path, dest: Path, content: bytes | None = None, rewrite: bool = False):
        relative = dest.relative_to(target).as_posix()
        if relative in copied:
            return
        original = src.read_bytes()
        payload = original if content is None else content
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        copied.add(relative)
        records.append({'source_path': src.relative_to(source).as_posix(),
                        'path': relative, 'source_sha256': sha(original),
                        'sha256': sha(payload), 'bytes': len(payload),
                        'url_roots_relocated': rewrite})

    for name in CSS_FILES:
        src = source / 'webapp/static' / name
        original = src.read_text()
        references = sorted(set(match[1] for match in LOCAL_URL.findall(original)))
        relocated = LOCAL_URL.sub(lambda m: f'url({m.group(1)}{VENDOR_URL}{m.group(2)}{m.group(1)})', original)
        write(src, target / 'static' / name, relocated.encode(), rewrite=True)
        for url in references:
            src_asset = source_asset(source, url)
            write(src_asset, target / url.split('?', 1)[0].lstrip('/'))
    for name in BRAND_FILES:
        write(source / 'assets/branding' / name, target / 'assets/branding' / name)
    for name in SIDEBAR_FILES:
        write(source / 'assets/sidebar' / name, target / 'assets/sidebar' / name)
    for name, path in JS_FILES.items():
        write(source / path, target / name)

    provenance = {'source_repository': 'Workraken/WorKraken-web', 'source_commit': commit,
                  'css_order': [f'static/{name}' for name in CSS_FILES],
                  'transform': 'Only CSS url roots /static and /assets move below /vendor/workraken; all CSS declarations retained.',
                  'reference_templates': [{'path': path, 'sha256': sha((source/path).read_bytes())}
                                          for path in REFERENCE_FILES],
                  'files': records}
    (target / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    (target / 'README.md').write_text(
        '# WorKraken UI reference\n\n'
        f'Source: `Workraken/WorKraken-web`, commit `{commit}`.\n\n'
        'These are the original production CSS files, loaded in the order used by '
        '`webapp/templates/base.html`. Only local asset URL roots were relocated '
        'to `/vendor/workraken`; no declarations, colors, sizes or components were redesigned. '
        '`provenance.json` records each original and output SHA-256.\n\n'
        'The football app supplies its own content and controller. No business records, '
        'credentials, source templates or backend code are included.\n')
    print(f'Vendored {len(records)} original WorKraken UI assets from {commit}; '
          f'{sum(r["bytes"] for r in records):,} bytes.')


if __name__ == '__main__':
    main()
