"""Free-tier Odds API adapter. Secrets are read only on the server."""
import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import storage


def load_env():
    path = storage.ROOT / '.env'
    if path.is_file():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class OddsAPI:
    base = 'https://api.the-odds-api.com/v4'

    def __init__(self, key=None, db_path=None):
        load_env()
        self.key = key or os.environ.get('ODDS_API_KEY')
        self.budget = min(450, max(0, int(os.environ.get('ODDS_API_MONTHLY_BUDGET', '450'))))
        self.db_path = db_path

    def status(self):
        with storage.connect(self.db_path) as c:
            latest = c.execute("SELECT cache_key FROM snapshots WHERE cache_key LIKE 'odds:%' ORDER BY created_at DESC,rowid DESC LIMIT 1").fetchone()
        snapshot = storage.cache_get(latest[0], self.db_path) if latest else None
        return {'configured': bool(self.key), 'plan': 'Starter FREE', 'monthly_credits': 500,
                'local_monthly_limit': self.budget, 'local_reserved_credits': storage.credits_used(self.db_path),
                'last_snapshot': snapshot['created_at'] if snapshot else None,
                'provider_quota': snapshot['quota'] if snapshot else {},
                'automatic_refresh': False, 'mode': 'paper'}

    def _get(self, path, params, cache_key, cost, ttl=21600, force=False):
        cached = storage.cache_get(cache_key, self.db_path)
        if cached and not force:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached['created_at'])).total_seconds()
            if age < ttl:
                return dict(cached, cached=True)
        if not self.key:
            raise ValueError('ODDS_API_KEY no configurada. Usá los históricos o configurá una clave del plan gratuito.')
        storage.reserve_credits(cost, self.budget, self.db_path)
        params = dict(params, apiKey=self.key)
        req = Request(self.base + path + '?' + urlencode(params), headers={'User-Agent': 'KrakenEdge/0.1 personal-research'})
        try:
            with urlopen(req, timeout=25) as response:
                payload = json.load(response)
                quota = {name: response.headers.get('x-requests-' + name) for name in ('remaining', 'used', 'last')}
                if isinstance(payload, dict) and 'id' in payload:
                    payload = [payload]
        except HTTPError as e:
            storage.log('provider_error', {'provider': 'The Odds API', 'status': e.code}, self.db_path)
            raise ValueError('The Odds API respondió HTTP ' + str(e.code) + '. Revisá clave y cuota; no se registra la URL privada.') from None
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            raise ValueError('No se pudo consultar The Odds API. La reserva local de créditos se conserva de forma prudente.') from None
        storage.cache_put(cache_key, payload, quota, self.db_path)
        storage.log('provider_snapshot', {'provider': 'The Odds API', 'resource': cache_key, 'cost_reserved': cost,
                                         'records': len(payload), 'quota': quota}, self.db_path)
        return dict(storage.cache_get(cache_key, self.db_path), cached=False)

    def sports(self, force=False):
        return self._get('/sports/', {'all': 'true'}, 'sports', cost=0, ttl=86400, force=force)

    def odds(self, sport='upcoming', regions='eu', markets='h2h', force=False):
        if not re.fullmatch(r'[a-z0-9_]{1,100}', sport):
            raise ValueError('Deporte inválido')
        if regions not in ('eu', 'uk', 'us', 'us2', 'au'):
            raise ValueError('Se admite una región por consulta para cuidar el plan gratuito.')
        market_list = markets.split(',')
        if not market_list or len(set(market_list)) != len(market_list) or any(m not in ('h2h', 'spreads', 'totals') for m in market_list):
            raise ValueError('Mercados admitidos: h2h,spreads,totals')
        return self._get('/sports/' + sport + '/odds/',
                         {'regions': regions, 'markets': markets, 'oddsFormat': 'decimal', 'dateFormat': 'iso'},
                         f'odds:{sport}:{regions}:{markets}', cost=len(market_list), force=force)

    def event_odds(self, sport, event_id, markets='player_first_goal_scorer', regions='us', force=False):
        if not re.fullmatch(r'[a-z0-9_]{1,100}', sport) or not re.fullmatch(r'[a-f0-9]{32}', event_id):
            raise ValueError('Identificador de competición o evento inválido')
        if regions not in ('us', 'us2', 'eu', 'uk', 'au'):
            raise ValueError('Región inválida')
        allowed = {'h2h', 'totals', 'spreads', 'btts', 'correct_score', 'double_chance', 'draw_no_bet',
                   'player_first_goal_scorer', 'player_goal_scorer_anytime', 'player_shots_on_target',
                   'player_to_receive_card', 'player_first_basket', 'player_points', 'player_rebounds',
                   'player_assists', 'player_goal_scorer_first', 'player_goals', 'player_shots_on_goal',
                   'batter_home_runs', 'pitcher_strikeouts', 'player_1st_td', 'player_pass_yds',
                   'h2h_h1', 'totals_h1', 'alternate_totals_corners', 'alternate_totals_cards'}
        catalog_path = storage.ROOT / 'config/market_catalog_v2.json'
        if catalog_path.is_file():
            for item in json.loads(catalog_path.read_text()).get('markets', []):
                allowed.update(item.get('provider_keys', []))
        discovered = storage.cache_get(f'markets:{sport}:{event_id}:{regions}', self.db_path)
        if discovered:
            for event in discovered['payload']:
                for book in event.get('bookmakers', []):
                    allowed.update(m['key'] for m in book.get('markets', []) if m.get('key'))
        requested = markets.split(',')
        if not 1 <= len(requested) <= 3 or len(set(requested)) != len(requested) or any(m not in allowed for m in requested):
            raise ValueError('Consultá entre uno y tres mercados reconocidos por evento.')
        return self._get(f'/sports/{sport}/events/{event_id}/odds/',
                         {'regions': regions, 'markets': markets, 'oddsFormat': 'decimal', 'dateFormat': 'iso'},
                         f'odds:event:{sport}:{event_id}:{regions}:{markets}', cost=len(requested), force=force)

    def event_markets(self, sport, event_id, regions='us', force=False):
        if not re.fullmatch(r'[a-z0-9_]{1,100}', sport) or not re.fullmatch(r'[a-f0-9]{32}', event_id):
            raise ValueError('Identificador de competición o evento inválido')
        if regions not in ('us', 'us2', 'eu', 'uk', 'au'):
            raise ValueError('Región inválida')
        return self._get(f'/sports/{sport}/events/{event_id}/markets',
                         {'regions': regions, 'dateFormat': 'iso'},
                         f'markets:{sport}:{event_id}:{regions}',cost=1,ttl=21600,force=force)


def flatten_odds(snapshot):
    """Keep market line/participant identity; never mix h2h with lay prices."""
    result = []
    for event in snapshot['payload']:
        for book in event.get('bookmakers', []):
            for market in book.get('markets', []):
                if market.get('key', '').endswith('_lay'):
                    continue
                for outcome in market.get('outcomes', []):
                    result.append({'event_id': event['id'], 'sport_key': event.get('sport_key'),
                                   'league': event.get('sport_title'), 'home_team': event.get('home_team'),
                                   'away_team': event.get('away_team'), 'commence_time': event.get('commence_time'),
                                   'bookmaker': book['key'], 'bookmaker_title': book['title'],
                                   'market': market['key'], 'selection': outcome['name'], 'odds': outcome['price'],
                                   'line': outcome.get('point'), 'description': outcome.get('description'),
                                   'last_update': market.get('last_update') or book.get('last_update'),
                                   'retrieved_at': snapshot['created_at'], 'source': 'The Odds API',
                                   'rules_verified': False, 'executable': False})
    return result
