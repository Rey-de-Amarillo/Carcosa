"""Collect free-tier snapshots. No paid endpoint and no bet placement."""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.providers import OddsAPI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sport', default='upcoming')
    parser.add_argument('--all-active', action='store_true', help='Una consulta h2h por competición activa sin futuros; consume créditos gratis.')
    parser.add_argument('--limit', type=int, default=80)
    parser.add_argument('--force', action='store_true', help='Ignorar caché de 6 horas. Sigue vigente el límite mensual de 450.')
    args = parser.parse_args()
    provider = OddsAPI()
    sports = provider.sports()['payload']
    keys = [s['key'] for s in sports if s.get('active') and not s.get('has_outrights')][:max(0, min(80, args.limit))] if args.all_active else [args.sport]
    results = []
    def get(key):
        try:
            snap = provider.odds(sport=key, force=args.force)
            return {'sport': key, 'events': len(snap['payload']), 'cached': snap['cached'], 'quota': snap['quota']}
        except ValueError as e:
            return {'sport': key, 'error': str(e)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(get, key) for key in keys]):
            results.append(future.result())
    print(json.dumps({'requests': len(results), 'events': sum(r.get('events', 0) for r in results),
                      'errors': [r for r in results if 'error' in r], 'status': provider.status()}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
