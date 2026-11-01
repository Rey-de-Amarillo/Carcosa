"""Small transactional store. No credentials or real wagering instructions."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data/runtime/kraken.sqlite3'


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@contextmanager
def connect(path=None):
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
            action TEXT NOT NULL, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS snapshots (
            cache_key TEXT PRIMARY KEY, created_at TEXT NOT NULL,
            payload TEXT NOT NULL, quota TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS quota (
            month TEXT PRIMARY KEY, reserved INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS paper_bets (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
            settled_at TEXT, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS snapshot_history (
            id INTEGER PRIMARY KEY, cache_key TEXT NOT NULL,
            created_at TEXT NOT NULL, payload TEXT NOT NULL, quota TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS scan_history (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
        ''')
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def log(action, payload, path=None):
    with connect(path) as c:
        c.execute('INSERT INTO audit(created_at,action,payload) VALUES(?,?,?)',
                  (utcnow(), action, json.dumps(payload, ensure_ascii=False)))


def audit(limit=100, path=None):
    with connect(path) as c:
        rows = c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT ?', (min(500, max(1, limit)),)).fetchall()
    return [dict(r, payload=json.loads(r['payload'])) for r in rows]


def cache_get(key, path=None):
    with connect(path) as c:
        r = c.execute('SELECT * FROM snapshots WHERE cache_key=?', (key,)).fetchone()
    return dict(r, payload=json.loads(r['payload']), quota=json.loads(r['quota'])) if r else None


def cache_put(key, payload, quota=None, path=None):
    stamp = utcnow()
    encoded = json.dumps(payload, ensure_ascii=False)
    quota_json = json.dumps(quota or {})
    with connect(path) as c:
        c.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?)',
                  (key, stamp, encoded, quota_json))
        c.execute('INSERT INTO snapshot_history(cache_key,created_at,payload,quota) VALUES(?,?,?,?)',
                  (key, stamp, encoded, quota_json))


def snapshot_history(key, path=None):
    with connect(path) as c:
        rows = c.execute('SELECT * FROM snapshot_history WHERE cache_key=? ORDER BY id', (key,)).fetchall()
    return [dict(r, payload=json.loads(r['payload']), quota=json.loads(r['quota'])) for r in rows]


def save_scan_archive(scan, path=None):
    with connect(path) as c:
        c.execute('INSERT INTO scan_history(id,created_at,payload) VALUES(?,?,?)',
                  (scan['scan_id'], scan['generated_at'], json.dumps(scan, ensure_ascii=False, allow_nan=False)))


def scan_history(limit=100, path=None):
    with connect(path) as c:
        rows = c.execute('SELECT id,created_at FROM scan_history ORDER BY created_at DESC LIMIT ?', (min(500, max(1, limit)),)).fetchall()
    return [dict(r) for r in rows]


def scan_get(scan_id, path=None):
    with connect(path) as c:
        r = c.execute('SELECT payload FROM scan_history WHERE id=?', (scan_id,)).fetchone()
    return json.loads(r[0]) if r else None


def reserve_credits(cost, budget, path=None, month=None):
    if cost < 0 or budget < 0:
        raise ValueError('Créditos inválidos')
    month = month or utcnow()[:7]
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT OR IGNORE INTO quota(month,reserved) VALUES(?,0)', (month,))
        used = c.execute('SELECT reserved FROM quota WHERE month=?', (month,)).fetchone()[0]
        if used + cost > budget:
            raise ValueError('Se alcanzó el límite mensual local. No se consultó el proveedor.')
        c.execute('UPDATE quota SET reserved=reserved+? WHERE month=?', (cost, month))
    return used + cost


def credits_used(path=None):
    with connect(path) as c:
        r = c.execute('SELECT reserved FROM quota WHERE month=?', (utcnow()[:7],)).fetchone()
    return r[0] if r else 0


DEFAULT_SETTINGS = {'bankroll': 1000.0, 'currency': 'USD', 'kelly_fraction': 0.25,
                    'max_stake_fraction': 0.01, 'max_event_fraction': 0.02,
                    'max_total_exposure': 0.10, 'mode': 'paper'}


def settings(path=None):
    with connect(path) as c:
        row = c.execute('SELECT payload FROM settings WHERE id=1').fetchone()
    return dict(DEFAULT_SETTINGS, **(json.loads(row[0]) if row else {}))


def save_settings(values, path=None):
    current = settings(path)
    previous_currency = current['currency']
    for key in DEFAULT_SETTINGS:
        if key in values:
            current[key] = values[key]
    if current['mode'] != 'paper':
        raise ValueError('Esta versión sólo admite simulación.')
    if current['currency'] not in ('USD', 'ARS', 'EUR'):
        raise ValueError('Moneda inválida')
    if current['currency'] != previous_currency:
        with connect(path) as c:
            if c.execute('SELECT COUNT(*) FROM paper_bets').fetchone()[0]:
                raise ValueError('El ledger ya tiene simulaciones. No se mezclan monedas sin una conversión explícita.')
    for key, low, high in [('bankroll', 1, 1e9), ('kelly_fraction', 0, 0.25),
                           ('max_stake_fraction', 0, .01), ('max_event_fraction', 0, .02),
                           ('max_total_exposure', 0, .10)]:
        import math
        if isinstance(current[key], bool):
            raise ValueError('Valor numérico inválido')
        value = float(current[key])
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Valor fuera de rango: ' + key)
        current[key] = value
    with connect(path) as c:
        c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)', (json.dumps(current),))
    log('settings_updated', current, path)
    return current
