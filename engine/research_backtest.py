"""Fixed-policy historical research portfolios, never model/strategy selection.

Model choice must happen before calling these functions on an audit interval.
Price stress uses the SAME base selections and amounts, including later dates.
"""
from __future__ import annotations
import collections
import math
import random
from datetime import date
from itertools import groupby

from .ensemble import blend, consensus, devig
from .markets import (evaluate_market, expected_net_return, generalized_kelly,
                      market_distribution, net_return, settle_score)

DEFAULT_POLICY = {'min_ev': .03, 'min_odds': 1.2, 'max_odds': 5.,
                  'min_reference_books': 3, 'max_overround': .15,
                  'kelly_scale': .1, 'max_event_fraction': .0025,
                  'max_day_fraction': .02, 'initial_bankroll': 1000.}
EXCLUDED_BOOKS = {'avg', 'max', 'bbav', 'bbmx', 'bfe', 'betfair_exchange', 'market average', 'market maximum'}


def _policy(policy):
    values = dict(DEFAULT_POLICY)
    aliases = {'ev_threshold': 'min_ev', 'kelly_fraction': 'kelly_scale',
               'max_stake_fraction': 'max_event_fraction', 'day_cap': 'max_day_fraction',
               'max_date_fraction': 'max_day_fraction', 'max_book_overround':'max_overround'}
    for name, value in (policy or {}).items():
        values[aliases.get(name, name)] = value
    for name in DEFAULT_POLICY:
        value = values[name]
        if isinstance(value, bool):
            raise ValueError('Valor de política inválido: ' + name)
        values[name] = float(value)
        if not math.isfinite(values[name]):
            raise ValueError('Valor no finito: ' + name)
    if not 0 <= values['min_ev'] or not 1 < values['min_odds'] <= values['max_odds']:
        raise ValueError('Umbrales de precio/EV inválidos')
    if values['initial_bankroll'] <= 0 or not 1 <= values['min_reference_books'] <= 50 or int(values['min_reference_books']) != values['min_reference_books']:
        raise ValueError('Capital o cantidad de referencias inválidos')
    if not 0 <= values['max_overround'] <= 1:
        raise ValueError('Margen máximo inválido')
    for name in ('kelly_scale', 'max_event_fraction', 'max_day_fraction'):
        if not 0 <= values[name] <= 1:
            raise ValueError('Fracción inválida: ' + name)
    values['min_reference_books'] = int(values['min_reference_books'])
    return values


def _actual_book(name, day):
    normalized = str(name).lower().strip()
    return (isinstance(name, str) and normalized not in EXCLUDED_BOOKS and not normalized.endswith('_lay')
            and not (normalized in ('ps', 'pinnacle') and day >= '2025-07-23'))


def _valid_books(books, size, policy, day):
    result = {}
    for name, prices in books.items():
        if not _actual_book(name, day):
            continue
        try:
            vector = [float(o) for o in prices]
            data = devig(vector, 'proportional')
            if len(vector) == size and -.02 <= data['overround'] <= policy['max_overround']:
                result[name] = vector
        except (TypeError, ValueError, OverflowError):
            continue
    return result


def _validated_records(records):
    seen, result = set(), []
    for row in records:
        if row['id'] in seen:
            raise ValueError('Un evento duplicado no puede generar dos posiciones: ' + str(row['id']))
        seen.add(row['id'])
        date.fromisoformat(row['date'])
        prediction = row.get('prediction') or {}
        previous = prediction.get('training_max_date') or prediction.get('training_as_of')
        if previous and previous >= row['date']:
            raise ValueError('El modelo incorpora una fecha del evento o posterior')
        for key in ('home_score', 'away_score'):
            value = float(row[key])
            if not math.isfinite(value) or value < 0 or value != int(value):
                raise ValueError('Marcador final inválido')
        result.append(row)
    return sorted(result, key=lambda r: (r['date'], str(r['id'])))


def _simplex(vector, size):
    if vector is None:
        return None
    p = [float(x) for x in vector]
    if len(p) != size or any(not math.isfinite(x) or x < 0 or x > 1 for x in p) or abs(sum(p)-1) > 1e-6:
        raise ValueError('Distribución probabilística inválida')
    return p


def _loo_references(books, method):
    """Cache each devig once; algebraically identical to arithmetic consensus.

    Repeating a 64-step power solve for each candidate's other books needlessly
    multiplies replay cost. Removing one member from the probability sum gives
    exactly the same coherent leave-one-out pool.
    """
    if method not in ('power', 'proportional'):
        raise ValueError('Método de margen desconocido')
    if len(books) < 2:
        return {}
    members = {name: devig(prices, method)['probabilities'] for name, prices in books.items()}
    size = len(next(iter(members.values())))
    total = [sum(p[i] for p in members.values()) for i in range(size)]
    return {name: {'probabilities': [(total[i]-p[i])/(len(members)-1) for i in range(size)],
                   'books': sorted(other for other in members if other != name),
                   'count': len(members)-1}
            for name, p in members.items()}


def _summary_ci(daily):
    if len(daily) < 2:
        return {'low': None, 'high': None, 'replicates': 0, 'status': 'insufficient_dates',
                'method': 'bootstrap por fecha; requiere al menos dos fechas con posiciones'}
    rng = random.Random(481516)
    samples = []
    for _ in range(400):
        selected = [rng.choice(daily) for _ in daily]
        total = sum(x[1] for x in selected)
        if total:
            samples.append(sum(x[0] for x in selected)/total)
    samples.sort()
    def quantile(q):
        index = (len(samples)-1)*q
        lower = int(index); upper = min(lower+1, len(samples)-1)
        return samples[lower] + (samples[upper]-samples[lower])*(index-lower)
    return {'low': quantile(.025), 'high': quantile(.975), 'replicates': len(samples),
            'seed': 481516, 'status': 'retrospective_conditional',
            'method': '400 réplicas bootstrap de beneficio/importe agrupados por fecha',
            'limitation': 'Condicionado a selecciones e importes históricos; no corrige toda dependencia serial ni selección de estrategias.'}


def _portfolio(candidates, records, policy, haircut, metadata, rejected):
    haircut = float(haircut)
    if not math.isfinite(haircut) or not 0 <= haircut < 1:
        raise ValueError('Castigo de precio inválido')
    initial = policy['initial_bankroll']
    base_bankroll = bankroll = peak = initial
    worst = 0.; trades, daily, curve, shortfalls = [], [], [], []
    if records:
        curve.append({'date': records[0]['date'], 'bankroll': initial, 'value': initial, 'profit': 0., 'drawdown': 0.})
    for day, group in groupby(candidates, key=lambda r: r['date']):
        entries = list(group)
        exposure = sum(x['fraction'] for x in entries)
        scale = min(1., policy['max_day_fraction']/exposure) if exposure else 1.
        # The base portfolio fixes amounts. Stress does not change any sizing,
        # later selections, or later-date cash reference through its own P&L.
        reference_equity = base_bankroll
        day_base_profit = day_profit = day_stake = 0.
        for entry in entries:
            stake = reference_equity * entry['fraction'] * scale
            if stake <= 0:
                continue
            effective_odds = max(1., entry['odds']*(1-haircut))
            base_return = net_return(entry['settlement'], entry['odds'])
            # max(1, effective quote) is an explicit severe-stress floor.
            stress_return = entry['settlement']['win_fraction']*(effective_odds-1)-entry['settlement']['loss_fraction']
            profit, base_profit = stake*stress_return, stake*base_return
            trade = {key: value for key, value in entry.items() if key not in ('fraction', 'settlement')}
            trade.update({'stake': stake, 'pnl': profit, 'profit': profit, 'base_profit': base_profit,
                          'base_unit_return': base_return, 'unit_return': stress_return,
                          'effective_odds': effective_odds, 'price_haircut': haircut,
                          'capital_reference_for_stake': reference_equity,
                          'kelly_fraction': entry['fraction'], 'actual_fraction': entry['fraction']*scale,
                          'settlement': entry['settlement'], 'win': stress_return > 0, 'won': stress_return > 0,
                          'status': 'paper_settled', 'outcome': entry['settlement']['outcome'],
                          'mode': 'historical_research', 'is_simulation': True, 'execution_enabled': False})
            trades.append(trade)
            day_profit += profit; day_base_profit += base_profit; day_stake += stake
        if day_stake > bankroll + 1e-8:
            shortfalls.append(day)
        base_bankroll += day_base_profit
        bankroll += day_profit
        peak = max(peak, bankroll)
        drawdown = max(0., 1-bankroll/peak) if peak else 0.
        worst = max(worst, drawdown)
        if day_stake:
            daily.append((day_profit, day_stake))
            curve.append({'date': day, 'bankroll': bankroll, 'value': bankroll,
                          'profit': bankroll-initial, 'drawdown': drawdown})
    if not trades and records and records[-1]['date'] != records[0]['date']:
        curve.append({'date': records[-1]['date'], 'bankroll': initial, 'value': initial, 'profit': 0., 'drawdown': 0.})
    turnover = sum(t['stake'] for t in trades)
    profit = sum(t['profit'] for t in trades)
    assert math.isclose(initial+profit, bankroll, rel_tol=1e-10, abs_tol=1e-8)
    ci = _summary_ci(daily)
    return {'bets': len(trades), 'roi': profit/turnover if turnover else None,
            'profit': profit, 'pnl': profit, 'turnover': turnover,
            'initial_bankroll': initial, 'final_bankroll': bankroll,
            'bankroll_return': profit/initial, 'max_drawdown': worst,
            'base_final_bankroll': base_bankroll, 'curve': curve, 'trades': trades, 'ci': ci,
            'profit_ci': ci, 'flat_roi': sum(t['unit_return'] for t in trades)/len(trades) if trades else None,
            'flat_profit': sum(t['unit_return'] for t in trades),
            'wins': sum(t['win'] for t in trades), 'win_rate': sum(t['win'] for t in trades)/len(trades) if trades else None,
            'pushes': sum(t['outcome'] == 'push' for t in trades), 'date_clusters': len(daily),
            'policy': policy, 'price_haircut': haircut, 'stress_fixed_portfolio': True,
            'funding_shortfall_dates': shortfalls, 'records': len(records),
            'rejection_counts': dict(rejected), 'metadata': metadata,
            'is_simulation': True, 'currency': 'unidades simuladas', 'execution_enabled': False,
            'roi_used_to_select_model_or_policy': False,
            'assumptions': ['Ofertas históricas de casas identificadas; no hay reloj individual ni confirmación de aceptación.',
                            'Selección y stake fijados con precios base; el castigo modifica sólo la liquidación de ese mismo portfolio.',
                            'Todos los importes de una fecha usan el capital base al comienzo de esa fecha.',
                            'Una posición por evento; no se suman mercados correlacionados del mismo evento.',
                            'La auditoría retrospectiva ya observada no sustituye la prueba prospectiva.']}


def simulate_h2h(records, spec, policy, snapshot='pre', target_book=None, price_haircut=0):
    """1X2 using a coherent leave-target-book-out reference for each offer."""
    if snapshot not in ('pre', 'closing'):
        raise ValueError('Snapshot desconocido')
    policy = _policy(policy)
    records = _validated_records(records)
    method = spec.get('devig', 'power')
    weight = float(spec.get('structural_weight', 0))
    if not math.isfinite(weight) or not 0 <= weight <= 1:
        raise ValueError('Peso estructural inválido')
    candidates, rejected = [], collections.Counter()
    for row in records:
        structural = _simplex(row.get('structural'), 3)
        if weight and (row.get('prediction') or {}).get('eligible') is False:
            rejected['ineligible_structural_model'] += 1; continue
        if weight and structural is None:
            rejected['missing_structural_prediction'] += 1; continue
        books = _valid_books(row.get('quote', {}).get('h2h', {}).get(snapshot, {}), 3, policy, row['date'])
        references = _loo_references(books, method)
        offers = books if target_book is None else ({target_book: books[target_book]} if target_book in books else {})
        choices = []
        for index, side in enumerate(('home', 'draw', 'away')):
            if not offers:
                continue
            book = min(offers, key=lambda name: (-offers[name][index], name))
            odds = offers[book][index]
            if not policy['min_odds'] <= odds <= policy['max_odds']:
                continue
            reference = references.get(book)
            if reference is None or reference['count'] < policy['min_reference_books']:
                continue
            probs = blend(structural, reference['probabilities'], weight)
            p, reference_p = probs[index], reference['probabilities'][index]
            ev = p*odds-1
            if ev < policy['min_ev']:
                continue
            fraction = min(policy['max_event_fraction'], max(0., ev/(odds-1)*policy['kelly_scale']))
            if not fraction:
                continue
            settlement = settle_score(row['home_score'], row['away_score'], '1x2', side)
            choices.append({'id': row['id'], 'trade_id': str(row['id'])+':h2h', 'date': row['date'],
                            'event': row['home_team']+' — '+row['away_team'], 'league': row.get('league'),
                            'sport': row.get('sport', 'football'), 'home_team': row['home_team'], 'away_team': row['away_team'],
                            'home_score': row['home_score'], 'away_score': row['away_score'],
                            'market': '1X2', 'selection_index': index,
                            'selection': row['home_team'] if index == 0 else 'Empate' if index == 1 else row['away_team'],
                            'book': book, 'bookmaker': book, 'odds': odds, 'probability': p,
                            'predicted_p': p, 'model_probability': p, 'reference_p': reference_p,
                            'ref_p': reference_p, 'market_probability': reference_p,
                            'reference_books': reference['books'], 'reference_count': reference['count'],
                            'reference_excludes_target': book not in reference['books'],
                            'ev': ev, 'edge': p-reference_p, 'fraction': fraction, 'settlement': settlement,
                            'odds_snapshot': snapshot, 'quote_timestamp': None,
                            'probability_source': 'structural_and_leave_book_out_market_ensemble',
                            'model_spec': spec, 'source': row.get('quote', {}).get('source'),
                            'model': spec.get('id', 'fixed_structural_market_ensemble'), 'model_version': '0.2.0',
                            'training_as_of': (row.get('prediction') or {}).get('training_max_date'),
                            'sample_size': (row.get('prediction') or {}).get('sample_size'),
                            'effective_sample_size': (row.get('prediction') or {}).get('effective_sample_size'),
                            'reasons': ['Selección hipotética bajo una política fijada previamente.',
                                        'La casa cuyo precio se evalúa se excluye de la referencia.']})
        if choices:
            candidates.append(min(choices, key=lambda c: (-c['ev'], c['selection_index'], c['book'])))
        else:
            rejected['no_candidate_passed_fixed_policy'] += 1
    return _portfolio(candidates, records, policy, price_haircut,
                      {'market': 'h2h', 'snapshot': snapshot, 'target_book': target_book,
                       'spec': spec, 'reference': 'leave_target_book_out'}, rejected)


def simulate_score_market(records, market='totals25', policy=None, snapshot='pre',
                          target_book=None, price_haircut=0):
    """Score-model research with exact void/quarter-line settlement.

    The model is structural: no score-market model/policy is selected here.
    Same-market complete reference books are required according to the policy.
    A goals distribution is not used for cards, corners or player props.
    """
    if market not in ('totals25', 'asian_handicap') or snapshot not in ('pre', 'closing'):
        raise ValueError('Mercado o snapshot desconocido')
    from .models_v2 import score_grid
    policy = _policy(policy)
    records = _validated_records(records)
    candidates, rejected = [], collections.Counter()
    for row in records:
        raw_books = row.get('quote', {}).get(market, {}).get(snapshot, {})
        if len(raw_books) < policy['min_reference_books']+1:
            rejected['insufficient_complete_reference_candidates'] += 1; continue
        prediction = row.get('prediction') or {}
        if prediction.get('eligible') is False or prediction.get('neutral_venue_unsupported'):
            rejected['ineligible_structural_model'] += 1; continue
        grid = prediction.get('grid')
        if grid is None:
            try:
                grid = score_grid(prediction['home_rate'], prediction['away_rate'],
                                  prediction.get('rho_applied', prediction.get('rho', 0)))['grid']
            except (KeyError, TypeError, ValueError):
                rejected['missing_score_distribution'] += 1; continue
        books = {}
        if market == 'totals25':
            books = {book: {'line': 2.5, 'odds': odds} for book, odds in _valid_books(raw_books, 2, policy, row['date']).items()}
        else:
            for book, data in raw_books.items():
                odds = data.get('odds') or [data.get('home_odds'), data.get('away_odds')]
                if _valid_books({book: odds}, 2, policy, row['date']) and data.get('line') is not None:
                    books[book] = {'line': float(data['line']), 'odds': odds}
        offers = books if target_book is None else ({target_book: books[target_book]} if target_book in books else {})
        choices, cache = [], {}
        for book, offer in sorted(offers.items()):
            references = {name: data['odds'] for name, data in books.items()
                          if name != book and math.isclose(data['line'], offer['line'], abs_tol=1e-9)}
            reference = consensus(references, 'power', max_overround=policy['max_overround'])
            if reference['count'] < policy['min_reference_books']:
                continue
            for index, side in enumerate(('over', 'under') if market == 'totals25' else ('home', 'away')):
                odds = float(offer['odds'][index])
                if not policy['min_odds'] <= odds <= policy['max_odds']:
                    continue
                line = offer['line'] if market == 'totals25' or index == 0 else -offer['line']
                score_market = 'totals' if market == 'totals25' else 'asian_handicap'
                key = (side, line)
                if key not in cache:
                    cache[key] = market_distribution(grid, score_market, side, line=line)
                distribution = cache[key]
                ev = expected_net_return(distribution, odds)
                if ev < policy['min_ev']:
                    continue
                fraction = generalized_kelly(distribution, odds, scale=policy['kelly_scale'], cap=policy['max_event_fraction'])['kelly_fraction']
                if not fraction:
                    continue
                settlement = settle_score(row['home_score'], row['away_score'], score_market, side, line=line)
                p = distribution['probability_win']
                choices.append({'id': row['id'], 'trade_id': str(row['id'])+':'+market, 'date': row['date'],
                                'event': row['home_team']+' — '+row['away_team'], 'league': row.get('league'),
                                'sport': row.get('sport', 'football'), 'market': market, 'selection_index': index,
                                'selection': side, 'line': line, 'book': book, 'bookmaker': book, 'odds': odds,
                                'probability': p, 'predicted_p': p, 'model_probability': p,
                                'ref_p': reference['probabilities'][index],
                                'reference_p': reference['probabilities'][index],
                                'market_probability': reference['probabilities'][index] if market == 'totals25' else None,
                                'reference_probability_interpretation': 'conditional_price_reference_not_full_push_distribution',
                                'settlement_distribution': distribution['probabilities'],
                                'reference_books': reference['books'], 'reference_count': reference['count'],
                                'reference_excludes_target': True, 'ev': ev, 'fraction': fraction,
                                'settlement': settlement, 'odds_snapshot': snapshot, 'quote_timestamp': None,
                                'probability_source': 'structural_score_distribution',
                                'model': prediction.get('model', 'structural_score_distribution'), 'model_version': '0.2.0',
                                'training_as_of': prediction.get('training_max_date'),
                                'sample_size': prediction.get('sample_size'),
                                'effective_sample_size': prediction.get('effective_sample_size'),
                                'source': row.get('quote', {}).get('source'),
                                'reasons': ['Mercado de investigación con distribución de liquidaciones completa.',
                                            'No se sustituyen devoluciones o medias pérdidas por una probabilidad binaria.']})
        if choices:
            candidates.append(min(choices, key=lambda c: (-c['ev'], c['selection_index'], c['book'])))
        else:
            rejected['no_candidate_passed_fixed_policy'] += 1
    return _portfolio(candidates, records, policy, price_haircut,
                      {'market': market, 'snapshot': snapshot, 'target_book': target_book,
                       'spec': 'structural_score_distribution', 'reference': 'leave_target_book_out_same_line'}, rejected)
