"""Provider evidence, club scoping, and reproducibility for the dropdown catalog."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
class FootballEntitiesTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.path=ROOT/'app/data/entities.json';cls.catalog=json.loads(cls.path.read_text())
  cls.players={p['id']:p for p in cls.catalog['players']};cls.teams={t['id']:t for t in cls.catalog['teams']};cls.sources={s['id']:s for s in cls.catalog['sources']}
 def test_fk_and_no_retroactive_roster_interval(self):
  self.assertGreaterEqual(len(self.players),641)
  self.assertTrue(all(p['membershipScope']=='snapshot_only' for p in self.players.values()))
  self.assertTrue(all('validFrom' not in p for p in self.players.values()))
  for p in self.players.values():self.assertIn(p['id'],self.teams[p['teamId']]['playerIds'])
  for row in self.catalog['historicalMemberships']:
   self.assertIn(row['playerId'],self.players);self.assertIn(row['teamId'],self.teams)
 def test_official_chelsea_transfer_names_are_not_removed_using_old_memory(self):
  roster={p['name']:p for p in self.players.values() if p['teamId']=='team:fpl:8'}
  for name in ['Cole Palmer','Danny Welbeck','Jordan Henderson','Morgan Rogers','Emiliano Martínez']:
   self.assertIn(name,roster)
   self.assertTrue(any(proof['source']=='espn:eng1:363:20261030' for proof in roster[name]['corroboratedBy']))
 def test_known_current_loan_is_not_offered_under_old_club(self):
  self.assertNotIn('player:fpl:567119',self.teams['team:fpl:8']['playerIds'])
  self.assertEqual(self.players['player:fpl:567119']['teamId'],'team:fd:sco:celtic')
  coverage=self.teams['team:fpl:8']['playersCoverage'];case=next(q for q in coverage['quarantined'] if q['providerPlayerCode']==567119)
  self.assertEqual(case['playingClub'],'Celtic')
  source=self.sources[case['source']];self.assertIn('chelseafc.com',source['url']);raw=(ROOT/source['path']).read_text()
  self.assertTrue(all(token in raw for token in ['Mheuka','Celtic','2026/27']))
  self.assertEqual(hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest(),source['sha256'])
 def test_united_new_signings_and_registered_u21_have_current_evidence(self):
  roster={p['name']:p for p in self.players.values() if p['teamId']=='team:fpl:1'}
  for name in ['Karl Darlow','Carlos Baleba','Andrey Santos','Youri Tielemans','Bruno Fernandes']:
   self.assertIn(name,roster);self.assertTrue(roster[name].get('corroboratedBy'))
  self.assertTrue(self.players['player:fpl:576620'].get('corroboratedBy'))
 def test_current_squads_cover_twelve_leagues_and_prominent_clubs(self):
  self.assertEqual(self.catalog['coverage']['rosterSources'],234)
  self.assertEqual(self.catalog['coverage']['rosterDownloadFailures'],0)
  for tid in ['team:fd:esp:realmadrid','team:fd:esp:barcelona','team:espn:5','team:espn:16','team:fd:sco:celtic']:
   self.assertGreater(len(self.teams[tid]['playerIds']),10)
  leagues={self.teams[tid]['providers']['espn']['league'] for tid in self.teams if self.teams[tid].get('providers',{}).get('espn')}
  self.assertTrue({'eng.1','eng.2','esp.1','ita.1','ger.1','fra.1','ned.1','por.1','tur.1','bel.1','sco.1','arg.1'}<=leagues)
 def test_preexisting_ids_survive_catalog_expansion(self):
  baseline=json.loads((ROOT/'tests/fixtures/entities_baseline_20261030.json').read_text())
  self.assertTrue(set(baseline['teams'])<=self.teams.keys());self.assertTrue(set(baseline['players'])<=self.players.keys())
 def test_espn_identities_are_unique_and_match_current_provider_club(self):
  links={};accepted=set()
  marker=json.loads((ROOT/'data/raw/football_entities_rosters/latest.json').read_text());manifest=json.loads((ROOT/marker['manifest']).read_text())
  import re
  for meta in manifest['sources']:
   if meta.get('team_id') is None:continue
   payload=json.loads((ROOT/meta['path']).read_text());tid=str(meta['team_id'])
   for athlete in payload.get('athletes',[]):
    default=re.search(r'/teams/(\d+)',(athlete.get('defaultTeam') or {}).get('$ref',''))
    if (not default or default[1]==tid) and (athlete.get('status') or {}).get('type') in (None,'active'):accepted.add((str(athlete['id']),tid))
  for player in self.players.values():
   provider=player.get('providers',{}).get('espn')
   if not provider:continue
   key=str(provider['playerId']);self.assertNotIn(key,links,'Same athlete duplicated across FPL/ESPN ids');links[key]=player['id']
   self.assertIn((key,str(provider['teamId'])),accepted)
 def test_same_sources_regenerate_identical_catalog(self):
  before=hashlib.sha256(self.path.read_bytes()).hexdigest()
  subprocess.run(['python3',str(ROOT/'scripts/export_football_entities.py')],cwd=ROOT,check=True,capture_output=True)
  self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
if __name__=='__main__':unittest.main()
