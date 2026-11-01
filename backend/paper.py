"""An append-audited ledger for manual simulations, with hard exposure limits."""
import json
import math
import uuid
from . import storage


def number(value, name, low, high):
    if isinstance(value, bool):
        raise ValueError('Valor inválido: ' + name)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError('Valor inválido: ' + name) from None
    if not math.isfinite(v) or not low <= v <= high:
        raise ValueError('Valor fuera de rango: ' + name)
    return v


def list_bets(path=None):
    with storage.connect(path) as c:
        return [json.loads(r[0]) for r in c.execute('SELECT payload FROM paper_bets ORDER BY created_at DESC')]


def equity(path=None):
    cfg = storage.settings(path)
    return cfg['bankroll'] + sum(r.get('profit') or 0.0 for r in list_bets(path) if r['status'] != 'open')


def create(values, path=None):
    cfg = storage.settings(path)
    odds = number(values.get('odds'), 'odds', 1.00001, 10000)
    probability = number(values.get('probability'), 'probability', 0, 1)
    stake = number(values.get('stake'), 'stake', 0.01, 1e9)
    event = str(values.get('event', '')).strip()[:200]
    selection = str(values.get('selection', '')).strip()[:200]
    if not event or not selection:
        raise ValueError('Indicar evento y selección')
    event_id = ' '.join(str(values.get('event_id') or event).strip().casefold().split())[:200]
    rid = str(values.get('request_id') or uuid.uuid4())
    try:
        uuid.UUID(rid)
    except ValueError:
        raise ValueError('request_id debe ser UUID') from None
    with storage.connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        existing = c.execute('SELECT payload FROM paper_bets WHERE id=?', (rid,)).fetchone()
        if existing:
            return json.loads(existing[0])
        all_bets = [json.loads(r[0]) for r in c.execute('SELECT payload FROM paper_bets')]
        current_equity = cfg['bankroll'] + sum(r.get('profit') or 0.0 for r in all_bets if r['status'] != 'open')
        if current_equity <= 0 or stake > current_equity * cfg['max_stake_fraction'] + 1e-8:
            raise ValueError('El importe supera el 1 % del capital actual de simulación.')
        opened = [r for r in all_bets if r['status'] == 'open']
        if sum(r['stake'] for r in opened) + stake > current_equity * cfg['max_total_exposure'] + 1e-8:
            raise ValueError('La exposición total supera el límite de simulación.')
        if sum(r['stake'] for r in opened if r.get('event_id', r['event'].casefold()) == event_id) + stake > current_equity * cfg['max_event_fraction'] + 1e-8:
            raise ValueError('La exposición en el mismo evento supera el límite; no se asume independencia.')
        record = {'id': rid, 'created_at': storage.utcnow(), 'event': event, 'event_id': event_id, 'selection': selection,
                  'market': str(values.get('market', 'manual'))[:80], 'odds': odds,
                  'probability': probability, 'probability_source': 'manual_user_assumption',
                  'stake': stake, 'currency': cfg['currency'], 'status': 'open', 'profit': None,
                  'mode': 'paper', 'real_money': False, 'equity_at_creation': current_equity}
        c.execute('INSERT INTO paper_bets(id,created_at,payload) VALUES(?,?,?)', (rid, record['created_at'], json.dumps(record)))
    storage.log('paper_bet_created', record, path)
    return record


def settle(rid, result, path=None):
    if result not in ('won', 'lost', 'void'):
        raise ValueError('Resultado admitido: won, lost, void')
    with storage.connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT payload,settled_at FROM paper_bets WHERE id=?', (rid,)).fetchone()
        if not row:
            raise ValueError('Simulación inexistente')
        record = json.loads(row[0])
        if row[1]:
            if record['status'] != result:
                raise ValueError('Ya fue liquidada; el resultado original se conserva.')
            return record
        record['status'] = result
        record['profit'] = record['stake'] * (record['odds'] - 1) if result == 'won' else -record['stake'] if result == 'lost' else 0.0
        record['settled_at'] = storage.utcnow()
        c.execute('UPDATE paper_bets SET payload=?,settled_at=? WHERE id=?',
                  (json.dumps(record), record['settled_at'], rid))
    storage.log('paper_bet_settled', {'id': rid, 'result': result, 'profit': record['profit']}, path)
    return record
