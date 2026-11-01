"""Explainable, non-executing scanner over provenance-preserving quote snapshots."""
import csv
import json
import hashlib
import uuid
import gzip
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import storage
from .providers import OddsAPI, flatten_odds
from engine.core import expected_value, probability_sensitivity, remove_margin
from engine.inference_v2 import predict_fixture_v2 as predict_fixture
from engine.ensemble import consensus, blend


LEAGUES = {
    'soccer_epl': 'England Premier League', 'soccer_efl_champ': 'England Championship',
    'soccer_germany_bundesliga': 'Germany Bundesliga', 'soccer_spain_la_liga': 'Spain La Liga',
    'soccer_italy_serie_a': 'Italy Serie A', 'soccer_france_ligue_one': 'France Ligue 1',
    'soccer_netherlands_eredivisie': 'Netherlands Eredivisie',
    'soccer_portugal_primeira_liga': 'Portugal Primeira Liga',
    'soccer_belgium_first_div': 'Belgium First Division A', 'soccer_turkey_super_league': 'Turkey Super Lig',
    'soccer_spl': 'Scotland Premiership', 'soccer_argentina_primera_division': 'Argentina Liga Profesional',
    'soccer_brazil_campeonato': 'Brazil Serie A', 'soccer_usa_mls': 'USA MLS',
    'soccer_mexico_ligamx': 'Mexico Liga MX', 'basketball_nba': 'NBA', 'baseball_mlb': 'MLB',
}


def read_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def iso_time(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else None
    except (ValueError, AttributeError):
        return None


def h2h_market_probabilities(quotes, home, away, sport):
    expected = {home, 'Draw', away} if sport == 'football' else {home, away}
    if len(quotes) != len(expected) or {q['selection'] for q in quotes} != expected:
        return None
    try:
        fair = remove_margin([q['odds'] for q in quotes])
    except (ValueError, KeyError, TypeError):
        return None
    return {q['selection']: p for q, p in zip(quotes, fair['probabilities'])}


def v2_reference(books, target, prediction, index, sport='football'):
    """Price reference excludes the bookmaker whose quote is being evaluated."""
    spec_path = storage.ROOT / 'config/selected_model_v2.json'
    if not spec_path.exists():return None
    spec = json.loads(spec_path.read_text())
    ref = consensus({name:prices for name,prices in books.items() if name!=target},spec['devig'])
    if ref['count'] < 3:return None
    keys = ['home','draw','away'] if sport=='football' else ['home','away']
    structural = [prediction.get(k) for k in keys] if prediction.get('eligible') and (prediction.get('model_age_days') or 0)<=45 else None
    if structural and any(v is None for v in structural):structural=None
    probabilities = blend(structural,ref['probabilities'],spec['structural_weight'])
    if probabilities is None:return None
    return {'probability':probabilities[index],'priced_probabilities':probabilities,'market_probability':ref['probabilities'][index],
            'reference_books':ref['books'],'reference_count':ref['count'],'dispersion':ref['dispersion'][index],
            'model':'Consenso multicasa power (referencia de precios)' if spec['structural_weight']==0 else 'Ensamble v2 de historial y consenso',
            'structural_weight':spec['structural_weight'],'probability_source':'leave_book_out_market_consensus' if spec['structural_weight']==0 else 'v2_structural_market_ensemble'}


def sync_prospective(result):
    """Update observed counters without rewriting a frozen model/start date."""
    if not result.get('model_hash'):return
    mirror=storage.ROOT/'data/runtime/prospective_v2.json'
    if not mirror.exists():return
    frozen=json.loads(mirror.read_text())
    if frozen.get('model_hash')!=result['model_hash']:return
    update={**frozen,**result,'start':frozen['start'],'registered_at':frozen['registered_at']}
    for path in [mirror,storage.ROOT/'data/runtime/prospective'/f"{result['model_hash']}.json"]:
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(update,ensure_ascii=False));tmp.replace(path)
    for path in [storage.ROOT/'app/data/research.json',storage.ROOT/'data/analysis/research_v2.json']:
        if not path.exists():continue
        report=json.loads(path.read_text())
        if report.get('prospective',{}).get('model_hash')!=result['model_hash']:continue
        report['prospective']=update
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,allow_nan=False));tmp.replace(path)


def build_scan(data_dir=None, max_fixtures=60):
    data_dir = Path(data_dir or storage.ROOT / 'data/processed')
    histories = read_csv(data_dir / 'matches.csv')
    fixtures = read_csv(data_dir / 'fixtures.csv')
    index = defaultdict(list)
    for row in histories:
        index[(row['sport'], row['league'])].append(row)
    now = datetime.now(timezone.utc)
    records, quotes, events = [], [], []
    snapshots = []
    # All keys are internal. Never expose URLs containing provider credentials.
    with storage.connect() as c:
        rows = c.execute("SELECT cache_key FROM snapshots WHERE cache_key LIKE 'odds:%' ORDER BY created_at DESC").fetchall()
    for row in rows:
        snapshots.append(storage.cache_get(row[0]))
    snapshots.sort(key=lambda s: s['cache_key'].startswith('odds:event:'))
    seen = set()
    supplemental = []
    for snap in snapshots:
        flat = flatten_odds(snap)
        quotes.extend(flat)
        supplemental.extend(q for q in flat if q['market'] != 'h2h')
        grouped = defaultdict(list)
        for q in flat:
            grouped[q['event_id']].append(q)
        for event in snap['payload']:
            if event['id'] in seen:
                continue
            seen.add(event['id'])
            start = iso_time(event.get('commence_time'))
            if start is None or start <= now:
                continue  # Baseline models are pre-match, never pretend to model in-play.
            sport_key = event.get('sport_key', '')
            prefix = sport_key.split('_')[0]
            sport = {'soccer': 'football', 'icehockey': 'hockey', 'americanfootball': 'american_football',
                     'aussierules': 'australian_football', 'rugbyleague': 'rugby', 'rugbyunion': 'rugby'}.get(prefix, prefix)
            league = LEAGUES.get(sport_key, event.get('sport_title', sport_key))
            fixture = {'date': start.date().isoformat(), 'sport': sport, 'league': league,
                       'home_team': event.get('home_team', ''), 'away_team': event.get('away_team', '')}
            rows_for_event = grouped[event['id']]
            candidates = [q for q in rows_for_event if q['market'] == 'h2h']
            book_groups=defaultdict(list)
            for quote in candidates:book_groups[quote['bookmaker']].append(quote)
            expected_names=[fixture['home_team'],'Draw',fixture['away_team']] if sport=='football' else [fixture['home_team'],fixture['away_team']]
            full_books={}
            for name,group in book_groups.items():
                if h2h_market_probabilities(group,fixture['home_team'],fixture['away_team'],sport):
                    lookup={q['selection']:q['odds'] for q in group}
                    full_books[name]=[lookup[x] for x in expected_names]
            probs, prediction = {}, {}
            history = index.get((sport, league), [])
            if history:
                # Exact names only. Approximate string matching can join different teams.
                known = {r['home_team'] for r in history} | {r['away_team'] for r in history}
                if fixture['home_team'] in known and fixture['away_team'] in known:
                    prediction = predict_fixture(history, fixture)
                    probs = prediction.get('probabilities', prediction)
            spec_path=storage.ROOT/'config/selected_model_v2.json'
            spec=json.loads(spec_path.read_text()) if spec_path.exists() else None
            forecast_market=consensus(full_books,spec['devig']) if spec else None
            raw_vector=[probs.get(k) for k in (('home','draw','away') if sport=='football' else ('home','away'))] if prediction.get('eligible') else None
            if raw_vector and any(x is None for x in raw_vector):raw_vector=None
            forecast_vector=blend(raw_vector,forecast_market['probabilities'],spec['structural_weight']) if spec and forecast_market['count']>=3 else None
            event_info = {'id': event['id'], 'sport': sport, 'sport_key': sport_key, 'league': league,
                          'home_team':fixture['home_team'],'away_team':fixture['away_team'],
                          'event': fixture['home_team'] + ' — ' + fixture['away_team'],
                          'date': event['commence_time'], 'bookmakers': len(event.get('bookmakers', [])),
                          'source': 'The Odds API', 'snapshot_at': snap['created_at']}
            events.append(event_info)
            options = [('home', fixture['home_team']), ('draw', 'Draw'), ('away', fixture['away_team'])]
            for code, selection in options:
                available = [q for q in candidates if q['selection'] == selection]
                if not available:
                    continue
                best = max(available, key=lambda q: float(q['odds']))
                samebook = [q for q in candidates if q['bookmaker'] == best['bookmaker']]
                market_p = None
                reference = h2h_market_probabilities(samebook, fixture['home_team'], fixture['away_team'], sport)
                if reference:
                    market_p = reference[selection]
                p = probs.get(code)
                reasons = ['Sólo observación: modelo sin ventaja validada para recomendar operaciones actuales.',
                           'Reglas de liquidación, límites y disponibilidad en tu cuenta pendientes de verificar.']
                update = iso_time(best.get('last_update'))
                age = (now - update).total_seconds() if update else None
                if age is None or age < -60 or age > 900:
                    reasons.append('La cuota no tiene una actualización válida de los últimos 15 minutos.')
                reasons.extend(prediction.get('reasons', []))
                if not reference:
                    reasons.append('Mercado incompleto: no se calcula una probabilidad sin margen con resultados faltantes.')
                if not prediction.get('eligible') or prediction.get('neutral_venue_unsupported') or prediction.get('model_age_days') is None or prediction.get('model_age_days', 0) > 45:
                    p = None
                v2 = v2_reference(full_books,best['bookmaker'],prediction,expected_names.index(selection),sport) if selection in expected_names else None
                if v2:
                    p=v2['probability'];market_p=v2['market_probability']
                    reasons.append('Consenso que excluye la casa del precio; dispersión entre casas no equivale a confianza independiente.')
                if p is None:
                    reasons.append('Sin modelo actual validado e identidad exacta de participantes para este mercado.')
                if (prediction.get('model_age_days') or 0) > 45:
                    reasons.append('El historial del modelo está desactualizado.')
                record = dict(event_info, id=event['id'] + ':' + code, event_id=event['id'],selection_code=code,
                              forecast_probabilities=forecast_vector,
                              forecast_market_probabilities=forecast_market['probabilities'] if forecast_market else None,
                              market='1X2' if len(options) == 3 and sport == 'football' else 'Ganador',
                              selection=selection, odds=best['odds'], bookmaker=best['bookmaker_title'],bookmaker_key=best['bookmaker'],
                              model_probability=p, probability=p, market_probability=market_p,
                              edge=(p - market_p) if p is not None and market_p is not None else None,
                              ev=expected_value(p, best['odds']) if p is not None else None,
                              stake=0, status='blocked', reasons=reasons, sample_size=prediction.get('sample_size', 0),
                              model=v2['model'] if v2 else prediction.get('model', 'Sin modelo validado'),
                              uncertainty=probability_sensitivity(p, prediction.get('effective_sample_size', 1)) if p is not None else None,
                              quote_timestamp=best.get('last_update'), execution_enabled=False, mode='observation')
                record.update({'training_max_date': prediction.get('training_max_date'),
                               'model_age_days': prediction.get('model_age_days'),
                               'probability_source': 'historical_baseline' if p is not None else 'unavailable'})
                if v2:record.update(v2)
                records.append(record)
    # Props have different denominators (participation, voids, missing outcomes).
    # Keep observed prices; do not normalize a non-exhaustive player list.
    extra_groups = defaultdict(list)
    for q in supplemental:
        start = iso_time(q.get('commence_time'))
        if start is None or start <= now:
            continue
        key = (q['event_id'], q['market'], q.get('line'), q.get('description'), q['selection'])
        extra_groups[key].append(q)
    market_labels = {'player_first_goal_scorer': 'Primer goleador', 'btts': 'Ambos marcan',
                     'totals': 'Total de puntos/goles', 'spreads': 'Hándicap', 'correct_score': 'Marcador exacto',
                     'player_first_basket': 'Primera canasta', 'player_goal_scorer_first': 'Primer goleador',
                     'alternate_totals_corners': 'Total de córners', 'alternate_totals_cards': 'Total de tarjetas'}
    for key, available in extra_groups.items():
        best = max(available, key=lambda q: float(q['odds']))
        sport_key = best['sport_key'] or ''
        prefix = sport_key.split('_')[0]
        sport = {'soccer': 'football', 'icehockey': 'hockey', 'americanfootball': 'american_football'}.get(prefix, prefix)
        selection = (str(best['description']) + ' · ' if best.get('description') else '') + best['selection']
        if best.get('line') is not None:
            selection += ' ' + str(best['line'])
        records.append({'id': ':'.join(str(x or '') for x in key), 'event_id': best['event_id'], 'sport_key': sport_key,
                        'sport': sport, 'league': best['league'] or sport_key,
                        'event': best['home_team'] + ' — ' + best['away_team'], 'date': best['commence_time'],
                        'market': market_labels.get(best['market'], best['market']), 'market_key': best['market'],
                        'selection': selection, 'odds': best['odds'], 'bookmaker': best['bookmaker_title'],
                        'line': best.get('line'), 'source': 'The Odds API', 'snapshot_at': best['retrieved_at'],
                        'quote_timestamp': best.get('last_update'), 'model_probability': None, 'market_probability': None,
                        'ev': None, 'edge': None, 'stake': 0, 'status': 'blocked', 'mode': 'observation',
                        'reasons': ['Precio observado: sin modelo validado de este mercado, participación o liquidación.',
                                    'No se supone que la lista de jugadores sea exhaustiva ni que sus selecciones sean independientes.',
                                    'Se conservan la línea y el participante para evitar mezclar mercados diferentes.'],
                        'execution_enabled': False})
    # Periodic public CSV has no trustworthy quote clock or timezone. It supports research only.
    fixture_books=defaultdict(lambda:defaultdict(dict))
    for quote in read_csv(data_dir/'fixtures_odds.csv'):
        if quote.get('market')!='h2h' or quote.get('is_market_average')=='true':continue
        book=quote.get('bookmaker_key')
        if book in ('PS','Pinnacle') and quote.get('date','')>='2025-07-23':continue
        try:fixture_books[quote['event_id']][book][quote['selection']]=float(quote['odds'])
        except (ValueError,KeyError):continue
    current_fixtures = sorted((f for f in fixtures if f['date'] >= now.date().isoformat()), key=lambda f: f['date'])[:max_fixtures]
    for fixture in current_fixtures:
        history = index.get((fixture['sport'], fixture['league']), [])
        prediction = predict_fixture(history, fixture) if history else {}
        probabilities = prediction.get('probabilities', prediction)
        selections = [('home', fixture['home_team'], fixture.get('home_odds')),
                      ('draw', 'Empate', fixture.get('draw_odds')),
                      ('away', fixture['away_team'], fixture.get('away_odds')),
                      ('over25', 'Más de 2,5', fixture.get('over25_odds')),
                      ('under25', 'Menos de 2,5', fixture.get('under25_odds'))]
        market_prob = {}
        for group in [selections[:3], selections[3:]]:
            try:
                result = remove_margin([float(x[2]) for x in group])
                market_prob.update({x[0]: p for x, p in zip(group, result['probabilities'])})
            except (TypeError, ValueError):
                pass
        for code, selection, odds in selections:
            if not odds:
                continue
            p = probabilities.get(code)
            if not prediction.get('eligible') or prediction.get('neutral_venue_unsupported') or prediction.get('model_age_days') is None or prediction.get('model_age_days', 0) > 45:
                p = None
            mp = market_prob.get(code)
            v2=None
            if code in ('home','draw','away'):
                books={name:[prices[k] for k in ('home','draw','away')] for name,prices in fixture_books[fixture['id']].items() if set(prices)=={'home','draw','away'}}
                target='B365' if 'B365' in fixture.get('odds_source','') else fixture.get('odds_source','').split(':')[1] if ':' in fixture.get('odds_source','') else ''
                v2=v2_reference(books,target,prediction,('home','draw','away').index(code))
                if v2:p=v2['probability'];mp=v2['market_probability']
            records.append({'id': fixture['id'] + ':' + code, 'event_id': fixture['id'],
                            'event': fixture['home_team'] + ' — ' + fixture['away_team'], 'date': fixture['date'],
                            'sport': fixture['sport'], 'league': fixture['league'],
                            'market': '1X2' if code in ('home', 'draw', 'away') else 'Total 2,5',
                            'selection': selection, 'odds': float(odds), 'source': fixture['source'],
                            'snapshot_at': fixture.get('retrieved_at'), 'quote_timestamp': None,
                            'bookmaker': 'Bet365' if 'B365' in fixture.get('odds_source', '') else fixture.get('odds_source'),
                            'model_probability': p, 'probability': p, 'market_probability': mp,
                            'ev': expected_value(p, float(odds)) if p is not None else None,
                            'edge': p - mp if p is not None and mp is not None else None,
                            'stake': 0, 'status': 'blocked', 'mode': 'observation',
                            'reasons': ['CSV periódico: sin timestamp individual de cuota ni zona horaria confirmada.',
                                        'Modelo base sin ventaja operativa validada; sólo seguimiento.',
                                        'Reglas, límites y precio efectivo pendientes de verificar.'] + prediction.get('reasons', []),
                            'training_max_date': prediction.get('training_max_date'),
                            'model_age_days': prediction.get('model_age_days'),
                            'probability_source': v2['probability_source'] if v2 else 'structural_v2_research' if p is not None else 'unavailable',
                            'reference_books':v2['reference_books'] if v2 else [],
                            'reference_count':v2['reference_count'] if v2 else 0,
                            'sample_size': prediction.get('sample_size', 0),
                            'model': v2['model'] if v2 else prediction.get('model', 'Sin modelo'),
                            'uncertainty': probability_sensitivity(p, prediction.get('effective_sample_size', 1)) if p is not None else None,
                            'execution_enabled': False})
    catalog = storage.cache_get('sports')
    return {'generated_at': storage.utcnow(), 'mode': 'observation', 'events': events,
            'quotes': len(quotes), 'quote_events': len(seen), 'fixture_events': len(current_fixtures),
            'sport_catalog': catalog['payload'] if catalog else [], 'opportunities': records,
            'provider_status': OddsAPI().status(), 'execution_enabled': False,
            'notes': ['Precios informativos; no hay conexión de ejecución con casas de apuestas.',
                      'La probabilidad de ganar y el valor esperado son medidas diferentes.']}


def save_scan(output=None):
    scan = build_scan()
    history = storage.ROOT / 'data/processed/matches.csv'
    model_paths=sorted((storage.ROOT/'engine').glob('*.py'))
    model_paths += [p for p in [storage.ROOT/'backend/scanner.py',storage.ROOT/'backend/providers.py',
                               storage.ROOT/'backend/prospective.py',storage.ROOT/'config/experiment_v2.json',
                               storage.ROOT/'config/selected_model_v2.json'] if p.exists()]
    model_source = b''.join(str(p.relative_to(storage.ROOT)).encode()+b'\0'+p.read_bytes() for p in model_paths)
    scan.update({'scan_id': str(uuid.uuid4()), 'model_source_sha256': hashlib.sha256(model_source).hexdigest(),
                 'history_data_sha256': hashlib.sha256(history.read_bytes()).hexdigest() if history.exists() else None})
    # Keep exact inputs and model source locally so a hash remains reproducible
    # after a provider corrects an old result or the implementation changes.
    archive_dir = storage.ROOT / 'data/runtime/reproducibility'
    archive_dir.mkdir(parents=True, exist_ok=True)
    input_archives = []
    for source in (storage.ROOT / 'data/processed').glob('*.csv'):
        if any(word in source.name for word in ('fixture', 'first_goal', 'event')):
            continue
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        target = archive_dir / (digest + '.csv.gz')
        if not target.exists():
            with gzip.open(target, 'wb', compresslevel=6) as stream:
                stream.write(raw)
        input_archives.append({'file': source.name, 'sha256': digest,
                               'archive': str(target.relative_to(storage.ROOT))})
    model_archive = archive_dir / (scan['model_source_sha256'] + '.model.json.gz')
    if not model_archive.exists():
        model_files = {str(p.relative_to(storage.ROOT)):p.read_text() for p in model_paths}
        with gzip.open(model_archive, 'wt', encoding='utf-8') as stream:
            json.dump(model_files, stream, ensure_ascii=False)
    scan['reproducibility'] = {'inputs': input_archives, 'model_archive': str(model_archive.relative_to(storage.ROOT))}
    try:
        from .prospective import capture_scan,settle_from_history
        capture_scan(scan)
        scan['prospective']=settle_from_history()
        sync_prospective(scan['prospective'])
    except ImportError:
        pass
    storage.save_scan_archive(scan)
    output = Path(output or storage.ROOT / 'data/runtime/live.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix('.tmp')
    tmp.write_text(json.dumps(scan, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(output)
    storage.log('scan_completed', {'observations': len(scan['opportunities']), 'quote_events': scan['quote_events'],
                                   'quotes': scan['quotes'], 'execution_enabled': False, 'scan_id': scan['scan_id']})
    return scan
