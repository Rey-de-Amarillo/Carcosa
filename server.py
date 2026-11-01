#!/usr/bin/env python3
"""Run the private local app: python3 server.py . No external dependencies."""
import argparse
import json
import mimetypes
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from backend import paper, storage
from backend.providers import OddsAPI, load_env
from backend.scanner import save_scan
from engine.core import expected_value, kelly_fraction

ROOT = Path(__file__).resolve().parent
MUTATION_LOCK = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'app'), **kwargs)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def json_response(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_port
        if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return self.json_response({'error': 'Host no permitido'}, 403)
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.json_response({'ok': True, 'name': 'Kraken Edge', 'mode': 'paper', 'execution_enabled': False})
        if path == '/api/provider-status':
            return self.json_response(OddsAPI().status())
        if path == '/api/prospective':
            from backend.prospective import summary
            return self.json_response(summary())
        if path == '/api/settings':
            return self.json_response(storage.settings())
        if path == '/api/audit':
            return self.json_response(storage.audit())
        if path == '/api/paper-bets':
            return self.json_response(paper.list_bets())
        if path == '/api/paper-equity':
            return self.json_response({'equity': paper.equity(), 'currency': storage.settings()['currency'], 'mode': 'paper'})
        if path == '/api/scans':
            return self.json_response(storage.scan_history())
        if path.startswith('/api/scans/'):
            payload = storage.scan_get(path.rsplit('/', 1)[-1])
            return self.json_response(payload or {'error': 'Registro inexistente'}, 200 if payload else 404)
        if path == '/api/live':
            live = ROOT / 'data/runtime/live.json'
            return self.json_response(json.loads(live.read_text()) if live.exists() else {'opportunities': [], 'mode': 'observation'})
        if path in ('/api/providers', '/api/markets'):
            name = 'providers.json' if path == '/api/providers' else 'markets.json'
            file = ROOT / 'config' / name
            return self.json_response(json.loads(file.read_text()) if file.exists() else {})
        if path == '/api/report':
            file = ROOT / 'app/data/report.json'
            return self.json_response(json.loads(file.read_text()) if file.exists() else {'error': 'Ejecutá python3 scripts/build_report.py'}, 200 if file.exists() else 503)
        if path.startswith('/api/'):
            return self.json_response({'error': 'Ruta inexistente'}, 404)
        if any(segment.startswith('.') for segment in path.split('/') if segment):
            return self.json_response({'error': 'Ruta privada'}, 404)
        return super().do_GET()

    def do_POST(self):
        port = self.server.server_port
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
            return self.json_response({'error': 'Origen no permitido'}, 403)
        if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return self.json_response({'error': 'Host no permitido'}, 403)
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.json_response({'error': 'Usar application/json'}, 415)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1048576:
                raise ValueError('Cuerpo vacío o demasiado grande')
            values = json.loads(self.rfile.read(length), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Número no finito')))
            if not isinstance(values, dict):
                raise ValueError('Se espera objeto JSON')
            path = urlsplit(self.path).path
            with MUTATION_LOCK:
                if path == '/api/settings':
                    result = storage.save_settings(values)
                elif path == '/api/scan':
                    # A single manually requested sport, with cache and an independent monthly cap.
                    provider = OddsAPI()
                    provider.odds(sport=values.get('sport', 'upcoming'), regions=values.get('regions', 'eu'),
                                  markets=values.get('markets', 'h2h'), force=False)
                    result = save_scan()
                elif path == '/api/scan-event':
                    OddsAPI().event_odds(sport=values.get('sport_key', ''), event_id=values.get('event_id', ''),
                                         markets=values.get('markets', 'player_first_goal_scorer'), regions=values.get('regions', 'us'))
                    result = save_scan()
                elif path == '/api/market-discovery':
                    result = OddsAPI().event_markets(sport=values.get('sport_key',''),event_id=values.get('event_id',''),
                                                     regions=values.get('regions','us'))
                elif path == '/api/calculate':
                    probability = paper.number(values.get('probability'), 'probability', 0, 1)
                    odds = paper.number(values.get('odds'), 'odds', 1.00001, 10000)
                    cfg = storage.settings()
                    result = {'ev': expected_value(probability, odds), 'break_even_probability': 1 / odds,
                              'kelly_fraction': kelly_fraction(probability, odds, cfg['kelly_fraction'], cfg['max_stake_fraction']),
                              'probability_source': 'manual_user_assumption', 'execution_enabled': False}
                elif path == '/api/paper-bets':
                    result = paper.create(values)
                elif path == '/api/paper-bets/settle':
                    result = paper.settle(str(values.get('id')), values.get('result'))
                else:
                    return self.json_response({'error': 'Ruta inexistente'}, 404)
            return self.json_response(result)
        except (ValueError, TypeError, KeyError) as e:
            return self.json_response({'error': str(e)}, 400)
        except Exception:
            # Errors never include the provider URL or environment variables.
            return self.json_response({'error': 'Falló la operación; se conserva el historial anterior.'}, 500)

    def log_message(self, fmt, *args):
        # Query strings are unnecessary in this app and may accidentally contain secrets.
        message = (fmt % args).split('?')[0]
        print('[Kraken Edge]', message, flush=True)


def main():
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=int(os.environ.get('KRAKEN_PORT', '8765')))
    args = p.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Kraken Edge: http://127.0.0.1:{args.port} (investigación y simulación)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
