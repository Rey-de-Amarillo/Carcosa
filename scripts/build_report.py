"""Build the real historical report and enrich it with cached current observations."""
import json
import gzip
import hashlib
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.report import build_report
from backend.scanner import save_scan


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-report', help='Reutilizar una evaluación ya generada de los mismos datos.')
    p.add_argument('--legacy', action='store_true', help='Generar únicamente la referencia v1 para comparación.')
    p.add_argument('--reuse-research', action='store_true', help='Reutilizar la investigación v2 ya calculada de estos datos para QA.')
    args = p.parse_args()
    history_output = ROOT / 'data/processed/decisions.jsonl'
    report = json.loads(Path(args.engine_report).read_text()) if args.engine_report else build_report(ROOT / 'data/processed', history_output=history_output)
    for item in report.get('data_quality', {}).get('files', []):
        source = ROOT / 'data/processed' / item['file']
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('El informe no coincide con los datos actuales. Recalculá sin --engine-report.')
    use_v2=not args.legacy and (ROOT/'config/experiment_v2.json').exists()
    if use_v2:
        if not args.reuse_research:
            for script in ['build_quote_history.py','research_v2.py']:
                subprocess.run([sys.executable,str(ROOT/'scripts'/script)],cwd=ROOT,check=True)
        from engine.report_v2 import integrate_report
        from scripts.research_v2 import fingerprint
        research_path=ROOT/'data/analysis/research_v2.json'
        if not research_path.exists() or json.loads(research_path.read_text())['meta']['data_fingerprint']!=fingerprint():
            raise ValueError('La investigación v2 no corresponde a los datos actuales. Regenerá sin --reuse-research.')
        report=integrate_report(report,ROOT,history_output)
    report['live'] = save_scan()
    if report['live'].get('prospective') and report.get('research'):
        report['research']['prospective']=report['live']['prospective']
    cfg = json.loads((ROOT / 'config/providers.json').read_text())
    report['providers'] = cfg.get('providers', [])
    if not use_v2:report['market_catalog'] = json.loads((ROOT / 'config/markets.json').read_text())
    report['data_manifest'] = json.loads((ROOT / 'data/manifest.json').read_text())
    if history_output.exists():
        digest=hashlib.sha256(history_output.read_bytes()).hexdigest()
        target = ROOT / f'app/data/history-{digest[:16]}.jsonl.gz'
        target.parent.mkdir(parents=True, exist_ok=True)
        compressed_temp=target.with_suffix('.gz.tmp')
        with history_output.open('rb') as source, gzip.open(compressed_temp, 'wb', compresslevel=6) as dest:
            import shutil
            shutil.copyfileobj(source, dest)
        compressed_temp.replace(target)
        shutil.copy2(target,ROOT/'app/data/history.jsonl.gz')
        with history_output.open() as f:
            history_count = sum(1 for line in f if line.strip())
        report['history_export'] = {'url': '/data/'+target.name, 'count': history_count,
                                    'format': 'JSONL', 'compression': 'gzip',
                                    'sha256': digest}
    attribution = ROOT / 'data/RETROSHEET_ATTRIBUTION.txt'
    if attribution.exists():
        report['attributions'] = {'retrosheet': attribution.read_text().strip()}
    report['meta'].update({'title': 'Kraken Edge · laboratorio de probabilidades',
                           'mode': 'historical_research', 'currency': 'USD',
                           'private_use': True, 'execution_enabled': False,
                           'report_kind': 'historical_backtest_and_observation',
                           'current_odds_at': report['live']['generated_at']})
    output = ROOT / 'app/data/report.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(output)
    print(json.dumps({'report': str(output), 'matches': report.get('overview', {}).get('matches'),
                      'current_observations': len(report['live']['opportunities']),
                      'quote_events': report['live']['quote_events'], 'quotes': report['live']['quotes']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
