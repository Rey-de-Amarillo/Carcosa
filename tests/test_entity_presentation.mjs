import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createEntityPresentation} from '../app/entity-presentation.js';

const app=new URL('../app/',import.meta.url);
const entitiesBytes=readFileSync(new URL('data/entities.json',app));
const entities=JSON.parse(entitiesBytes);
const badges=JSON.parse(readFileSync(new URL('data/entity-badges.json',app)));
const view=createEntityPresentation(entities,badges);
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
assert.equal(badges.entitiesSha256,hash(entitiesBytes),'Badges must refer to this entity snapshot');
const sourceByPath=new Map(badges.sources.map(source=>[source.path,source]));
let aliases=0,crests=0;
for(const team of entities.teams){
  assert.equal(view.resolveTeam(team.id),team.id);
  assert.equal(view.resolveTeam('team:'+team.id),team.id,'Explicit selected-team values preserve identity');
  assert.strictEqual(view.teamBadge(team.id),badges.teams[team.id]);
  assert.ok(badges.teams[team.id]?.flagSrc,`${team.name}: country flag present`);
  for(const league of team.leagueIds||[])for(const alias of [team.name,...team.aliases||[]]){
    assert.equal(view.resolveTeam(alias,league),team.id,`${league}: ${alias} resolves to the correct club`);aliases++;
  }
  const badge=badges.teams[team.id];
  if(badge.logoSrc){
    crests++;
    const source=sourceByPath.get(badge.logoSrc);
    assert.ok(source?.evidence,`${team.name}: crest has provenance`);
    assert.equal(source.evidence.teamId,team.providers.espn.teamId,`${team.name}: crest provider identity matches the club`);
  }
  const country=badges.countryExceptions?.[team.id]?.countryCode;
  if(country)assert.equal(badge.countryCode,country,`${team.name}: flag respects cross-border clubs`);
}
for(const league of entities.leagues){
  const badge=badges.leagues[league.id];assert.ok(badge?.flagSrc,`${league.name}: flag present`);
  assert.equal(view.images(badge).length,1);
  assert.ok(view.leagueHTML(league.id).includes(badge.flagSrc));
}
for(const source of badges.sources){
  const bytes=readFileSync(new URL(source.path,app));
  assert.equal(hash(bytes),source.sha256,`${source.path}: packaged asset matches its provenance`);
  assert.equal(bytes.subarray(0,8).toString('hex'),'89504e470d0a1a0a',`${source.path}: real PNG`);
}
assert.equal(crests,badges.coverage.clubCrests);
assert.equal(view.resolveTeam('Unknown Club 123'),null);
assert.equal(view.teamBadge('Unknown Club 123'),null);

// Identical aliases must never silently choose one of two clubs.
const duplicates=createEntityPresentation({teams:[{id:'a',name:'United',aliases:['Atlético']},{id:'b',name:'United',aliases:['Atletico']}],teamAliasIndex:{'E0|united':'a','ARG1|united':'b'}});
assert.equal(duplicates.resolveTeam('United'),null);
assert.equal(duplicates.resolveTeam('Atlético'),null);
assert.equal(duplicates.resolveTeam('United','E0'),'a');
assert.equal(duplicates.resolveTeam('United','ARG1'),'b');

// Club/league labels are data, never executable markup. Only packaged PNG paths
// may produce image attributes; URLs, traversal and attribute payloads fail shut.
const injection='<img src=x onerror="alert(1)">';
const unsafe=createEntityPresentation({teams:[{id:'bad',name:injection}],leagues:[{id:'bad-league',name:injection}]},{teams:{bad:{logoSrc:'javascript:alert(1)',flagSrc:'assets/football/flags/ar.png" onerror="alert(1)'}},leagues:{'bad-league':{flagSrc:'https://example.com/a.png'}}});
assert.ok(unsafe.teamHTML('bad').includes('&lt;img'));
assert.ok(unsafe.leagueHTML('bad-league').includes('&lt;img'));
assert.ok(!unsafe.teamHTML('bad').includes('<img'));
assert.ok(!unsafe.leagueHTML('bad-league').includes('<img'));
assert.ok(view.teamHTML(injection).includes('&lt;img'));
for(const path of ['javascript:alert(1)','https://example.com/a.png','//example.com/a.png','assets/football/../a.png','assets/football/a.svg','assets/football/a.png?x=1','assets/football/a.png" onerror="x'])assert.deepEqual(view.images({logoSrc:path}),[],path);
assert.deepEqual(view.images({logoSrc:'assets/football/clubs/a1.png',flagSrc:'assets/football/flags/gb-eng.png'}),[{src:'assets/football/clubs/a1.png',kind:'crest'},{src:'assets/football/flags/gb-eng.png',kind:'flag'}]);
console.log(`Entity presentation: ${entities.teams.length} clubs, ${entities.leagues.length} leagues, ${aliases} scoped aliases, ${crests} crest identities, asset hashes and HTML/path safety passed.`);
