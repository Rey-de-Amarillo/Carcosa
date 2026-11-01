#!/usr/bin/env python3
"""Cache authentic country flags and provider-verified football club crests.

Run: python3 scripts/export_entity_badges.py
No club is matched by a fuzzy name or by a guessed CDN ID. A club crest is
accepted only from the archived ESPN team list with its existing provider ID.
Uncovered historical clubs use their country flag instead. Cached assets keep
their source URL, metadata evidence and content hash in entity-badges.json.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / 'app/assets/football'
OUTPUT = ROOT / 'app/data/entity-badges.json'
WORKRAKEN_FLAGS = Path('/home/joaquin/Escritorio/GitHub Proyectos/WorKraken-web/assets/banderas')
LEAGUE_COUNTRIES = {
    'E0': 'gb-eng', 'E1': 'gb-eng', 'SC0': 'gb-sct', 'B1': 'be',
    'D1': 'de', 'F1': 'fr', 'I1': 'it', 'N1': 'nl', 'P1': 'pt',
    'SP1': 'es', 'T1': 'tr', 'ARG1': 'ar', 'SGP_AUS': 'au',
    'SGP_JPN': 'jp', 'SGP_KOR': 'kr', 'SGP_SWE': 'se', 'SGP_USA': 'us',
}
# A competition's country is not always the club's own country. These explicit
# canonical identities are exceptions; no substring matching is performed.
COUNTRY_EXCEPTIONS = {
    'team:fd:eng:cardiff': 'gb-wls',
    'team:fd:eng:swansea': 'gb-wls',
    'team:fd:eng:wrexham': 'gb-wls',
    'team:fd:fra:monaco': 'mc',
    'team:fd:usa:montrealimpact': 'ca',
    'team:fd:usa:torontofc': 'ca',
    'team:fd:usa:vancouverw': 'ca',
    'team:fd:aus:aucklandfc': 'nz',
    'team:fd:aus:wellington': 'nz',
}
COUNTRY_REFERENCES = {
    'gb-wls': 'https://cdn.cardiffcityfc.co.uk/sites/default/files/2025-01/CCST%20Meeting%20Minutes%20January%202025_0.pdf',
    'mc': 'https://www.asmonaco.com/en/club/histoire',
    'ca': 'https://canadasoccer.com/fr/championship/canChamp/2026/',
    'nz': 'https://aleagues.com.au/news/a-league-men-preview-storylines-to-follow-mata-costa-signings-news-latest/',
}
MAX_BYTES = 25 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def web_path(path):
    return path.relative_to(ROOT / 'app').as_posix()


def validate_png(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('PNG is empty or exceeds the per-file size limit')
    with Image.open(BytesIO(data)) as image:
        if image.format != 'PNG' or not (0 < image.width <= 8192 and 0 < image.height <= 8192):
            raise ValueError('Expected a valid PNG with bounded dimensions')
        dimensions = {'width': image.width, 'height': image.height}
        image.verify()
    return dimensions


def download(url):
    last_error = None
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': 'FootballResearchAssets/1.0'})
            with urlopen(request, timeout=30) as response:
                if urlparse(response.url).scheme != 'https':
                    raise ValueError('Asset download redirected away from HTTPS')
                data = response.read(MAX_BYTES + 1)
            validate_png(data)
            return data
        except (OSError, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f'Could not download {url}: {last_error}')


def cache_asset(destination, url, previous, *, local_source=None, evidence=None):
    """Keep valid, provenance-matched local bytes; otherwise fetch the original."""
    relative = web_path(destination)
    old = previous.get(relative, {})
    data = None
    reused = False
    if destination.is_file() and old.get('url') == url:
        candidate = destination.read_bytes()
        if sha256(candidate) == old.get('sha256'):
            validate_png(candidate)
            data, reused = candidate, True
    if data is None:
        data = local_source.read_bytes() if local_source and local_source.is_file() else download(url)
        validate_png(data)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.png.tmp')
        temporary.write_bytes(data)
        temporary.replace(destination)
    source = {
        'path': relative, 'url': url, 'sha256': sha256(data), 'bytes': len(data),
        **validate_png(data), 'retrievedAt': old['retrievedAt'] if reused else now(),
    }
    if local_source and local_source.is_file():
        source['copiedFrom'] = str(local_source)
    if evidence:
        source['evidence'] = evidence
    return source


def load_verified_logo_catalog():
    marker = ROOT / 'data/raw/football_entities_rosters/latest.json'
    manifest_path = ROOT / json.loads(marker.read_text())['manifest']
    manifest = json.loads(manifest_path.read_text())
    catalog = {}
    for metadata in manifest['sources']:
        if metadata.get('team_id') is not None:
            continue
        path = ROOT / metadata['path']
        data = path.read_bytes()
        if sha256(data) != metadata['sha256']:
            raise ValueError(f'Team-list evidence hash changed: {metadata["path"]}')
        payload = json.loads(data)
        for sport in payload.get('sports', []):
            for league in sport.get('leagues', []):
                for item in league.get('teams', []):
                    team = item.get('team', item)
                    default = [logo for logo in team.get('logos', []) if 'default' in logo.get('rel', [])]
                    if not default:
                        continue
                    logo = default[0]
                    parsed = urlparse(logo['href'])
                    if parsed.scheme != 'https' or parsed.hostname != 'a.espncdn.com':
                        raise ValueError(f'Unrecognized crest host for ESPN club {team["id"]}')
                    key = (metadata['league'], str(team['id']))
                    catalog[key] = {
                        'url': logo['href'],
                        'evidence': {
                            'provider': 'espn', 'teamId': str(team['id']),
                            'league': metadata['league'], 'teamName': team['displayName'],
                            'path': metadata['path'], 'url': metadata['url'],
                            'sha256': metadata['sha256'], 'asOf': metadata['retrieved_at'],
                        },
                    }
    return catalog, manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workraken-flags', type=Path, default=WORKRAKEN_FLAGS)
    args = parser.parse_args()
    entities_path = ROOT / 'app/data/entities.json'
    entities_data = entities_path.read_bytes()
    entities = json.loads(entities_data)
    old = json.loads(OUTPUT.read_text()) if OUTPUT.is_file() else {}
    previous = {source['path']: source for source in old.get('sources', [])}
    catalog, manifest_path = load_verified_logo_catalog()
    leagues = {}
    teams = {}
    for league in entities['leagues']:
        country = LEAGUE_COUNTRIES[league['id']]
        leagues[league['id']] = {'flagSrc': f'assets/football/flags/{country}.png', 'countryCode': country}
    for team in entities['teams']:
        league_ids = team.get('currentLeagueIds') or team['leagueIds']
        countries = {LEAGUE_COUNTRIES[league] for league in league_ids}
        if len(countries) != 1:
            raise ValueError(f'Cannot determine one country for {team["id"]}: {league_ids}')
        country = COUNTRY_EXCEPTIONS.get(team['id'], next(iter(countries)))
        teams[team['id']] = {'flagSrc': f'assets/football/flags/{country}.png', 'countryCode': country}
    sources = []
    jobs = []
    for country in sorted({row['countryCode'] for row in [*leagues.values(), *teams.values()]}):
        destination = ASSET_ROOT / 'flags' / f'{country}.png'
        jobs.append((None, destination, f'https://flagcdn.com/w320/{country}.png', args.workraken_flags / f'{country}.png', None))
    for team in entities['teams']:
        provider = team.get('providers', {}).get('espn')
        if not provider:
            continue
        key = (provider['league'], str(provider['teamId']))
        if key not in catalog:
            raise ValueError(f'No corroborated team-list crest for {team["id"]}: {key}')
        entry = catalog[key]
        filename = sha256(team['id'].encode())[:20] + '.png'
        jobs.append((team['id'], ASSET_ROOT / 'clubs' / filename, entry['url'], None, entry['evidence']))
    failures = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        pending = {
            executor.submit(cache_asset, destination, url, previous, local_source=local_source, evidence=evidence): (team_id, destination)
            for team_id, destination, url, local_source, evidence in jobs
        }
        for future in as_completed(pending):
            team_id, destination = pending[future]
            try:
                source = future.result()
            except Exception as error:
                failures.append({'teamId': team_id, 'path': web_path(destination), 'error': str(error)})
                continue
            sources.append(source)
            if team_id:
                teams[team_id]['logoSrc'] = web_path(destination)
    # Missing flags or silently dropping a known crest must never publish a
    # partially valid catalog. Downloaded cache files can be reused on retry.
    if failures:
        raise RuntimeError(json.dumps({'assetFailures': failures}, ensure_ascii=False))
    result = {
        'schemaVersion': 1,
        'entitiesAsOf': entities.get('asOf'),
        'entitiesSha256': sha256(entities_data),
        'leagues': leagues, 'teams': teams,
        'sources': sorted(sources, key=lambda source: source['path']),
        'countryExceptions': {
            team_id: {'countryCode': country, 'sourceUrl': COUNTRY_REFERENCES[country]}
            for team_id, country in COUNTRY_EXCEPTIONS.items() if team_id in teams
        },
        'teamListManifest': manifest_path.relative_to(ROOT).as_posix(),
        'coverage': {
            'leagues': len(leagues), 'teams': len(teams),
            'clubCrests': sum('logoSrc' in row for row in teams.values()),
            'countryFlagFallbacks': sum('logoSrc' not in row for row in teams.values()),
            'assetFiles': len(sources), 'assetBytes': sum(source['bytes'] for source in sources),
        },
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps(result['coverage'], ensure_ascii=False))


if __name__ == '__main__':
    main()
