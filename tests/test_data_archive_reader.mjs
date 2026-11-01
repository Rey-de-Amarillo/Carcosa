/** Bounded source catalogs: exact quote values, phase separation and provenance. */
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {FootballDataArchive,safeSourceURL,sourceForPlayer,sourceForWorkspaceEvent} from '../app/football-data-archive.js';
const sourceURL=safeSourceURL('https://user:private@example.test/history?apiKey=private&fixture=123&ACCESS_TOKEN=secret&signature=secret#private');
assert.equal(sourceURL,'https://example.test/history?fixture=123');
for(const bad of ['',null,'not a URL','file:///tmp/private','javascript:alert(1)'])assert.equal(safeSourceURL(bad),'');
const table=(columns,...rows)=>({columns,rows});
const manifest=(part,extras={})=>({provider:'Primary source',books:[{code:'B365',name:'Bet365'}],markets:[{id:'match_result',name:'1X2'}],partitions:[part],...extras});
const expandedPart={id:'fixture',path:'expanded-fixture.json.gz',eventCount:1,quoteCount:4,league:'L',season:'2026',source:{provider:'Football-Data.co.uk',url:'https://source.test/data.csv?api_key=secret',sha256:'a'.repeat(64),retrievedAt:'2026-10-30T12:00:00Z'}};
const additionalPart={id:'nested',path:'nested-fixture.json.gz',eventCount:1,quoteCount:2,source:{provider:'SGodds',url:'https://sgodds.com/football/data',sha256:'b'.repeat(64)}};
const researchPart={id:'temporal',path:'research-fixture.json.gz',eventCount:1,quoteCount:1,source:{provider:'Archive summary',url:'https://summary.test/data',sha256:'c'.repeat(64)}};
const fixtures={
 'expanded-football-manifest.json':manifest(expandedPart),
 'additional-market-manifest.json':manifest(additionalPart),
 'research-market-manifest.json':manifest(researchPart,{sources:[
  {id:'event-file',provider:'Fixture metadata',url:'https://api.test/fixtures',sha256:'d'.repeat(64)},
  {id:'quote-file',provider:'OddsPapi',url:'https://api.test/historical-odds?fixtureId=7&apiKey=secret',sha256:'e'.repeat(64),retrievedAt:'2026-10-30T13:00:00Z'},
 ]}),
 'expanded-fixture.json.gz':{
  events:table(['id','date','home','away','league','season'],['raw-1','2026-10-01','A','B','L','2026']),
  quotes:table(['event','book','market','period','selection','line','phase','odds','sourceColumn','sourceRow'],
   [0,'B365','match_result','full','home',null,'pre_closing',2.05,'B365H',2],
   [0,'B365','match_result','full','away',null,'pre_closing',3.75,'B365A',2],
   [0,'B365','match_result','full','home',null,'closing',2.15,'B365CH',2],
   [0,'B365','match_result','full','away',null,'closing',3.55,'B365CA',2]),
 },
 'nested-fixture.json.gz':{events:[{id:'sg:1',date:'2026-10-02',home:'C',away:'D',quotePhase:'opening_source_label',marketQuotes:[
  {book:'SGP',market:'btts',selection:'yes',odds:1.7,sourceField:'Bg_01'},
  {book:'SGP',market:'btts',selection:'no',odds:2.05,sourceField:'Bg_02'},
 ]}]},
 'research-fixture.json.gz':{
  events:table(['id','date','home','away','sourceFileId','scope'],['id7','2026-10-03','E','F','event-file','research_not_verified']),
  quotes:table(['event','book','market','period','selection','phase','odds','sourceColumn','sourceRow','sourceFileId','capturedAt','rawTimestamp','active','limit','playerId','rawMarketId','rawMarketName'],
   [0,'pinnacle','oddspapi:101','fulltime','1','historical_timestamp',2.87654321,'bookmakers/pinnacle/markets/101/outcomes/101/players/0',0,'quote-file','2026-10-02T12:00:00.123456789Z','2026-10-02T12:00:00.123456789Z',false,0,'0','101','Full Time Result']),
 },
};
const original=JSON.stringify(fixtures),calls=[];
const reader=new FootballDataArchive({cacheLimit:2,read:async(path,gzip)=>{calls.push([path,Boolean(gzip)]);if(!fixtures[path])throw new Error('Missing source');return structuredClone(fixtures[path]);}});
await Promise.all([reader.initialize(),reader.initialize()]);assert.equal(calls.length,3,'parallel initialization reads each small manifest once');
assert.equal(reader.catalog().length,3);assert.equal(reader.catalog()[0].quotes,4);assert.ok(reader.catalog().every(item=>!item.sourceUrl.includes('secret')));
const selection={dataset:'expanded',partitionId:'fixture',phase:'pre_closing'};
const [loaded,same]=await Promise.all([reader.loadPartition(selection),reader.loadPartition(selection)]);assert.strictEqual(loaded,same);assert.equal(calls.filter(([path])=>path==='expanded-fixture.json.gz').length,1,'parallel callers share one partition download');
assert.deepEqual(loaded.offers.map(q=>q.odds),[2.05,3.75,2.15,3.55]);assert.equal(loaded.events.length,1);
assert.equal(loaded.offers[0].sourceProvider,'Football-Data.co.uk');assert.equal(loaded.offers[0].sourceColumn,'B365H');assert.equal(loaded.offers[0].sourceRow,2);assert.equal(loaded.offers[0].sourceSha256,'a'.repeat(64));
assert.ok(loaded.offers.every(q=>!Object.hasOwn(q,'capturedAt')),'download time, phase and event date do not become captured quote timestamps');
assert.ok(loaded.offers.every(q=>q.probability===null&&q.references.length===0),'reader does not derive probabilities from prices');
const pre=await reader.strategyUniverse(selection),closing=await reader.strategyUniverse({...selection,phase:'closing'});
assert.deepEqual(pre.offers.map(q=>q.odds),[2.05,3.75]);assert.deepEqual(closing.offers.map(q=>q.odds),[2.15,3.55]);
assert.deepEqual((await reader.strategyUniverse({...selection,book:'B365',market:'match_result'})).offers,pre.offers);
await assert.rejects(reader.strategyUniverse({...selection,phase:''}),/fase|mezclar/);
await assert.rejects(reader.strategyUniverse({...selection,phase:'all'}),/fase|mezclar|válid/);
await assert.rejects(reader.strategyUniverse({...selection,phase:'not-a-real-phase'}),/fase|válid/);
const nested=await reader.loadPartition({dataset:'additional',partitionId:'nested'});assert.equal(nested.offers.length,2);assert.equal(nested.offers[0].sourceColumn,'Bg_01');assert.equal(nested.offers[0].phase,'opening_source_label','source phase on a nested event is preserved');
const research=await reader.loadPartition({dataset:'research',partitionId:'temporal'}),q=research.offers[0];
assert.equal(q.sourceProvider,'OddsPapi');assert.equal(q.sourceUrl,'https://api.test/historical-odds?fixtureId=7');assert.equal(q.sourceSha256,'e'.repeat(64),'quote sourceFileId wins over the fixture metadata source');
assert.equal(q.odds,2.87654321);assert.equal(q.capturedAt,'2026-10-02T12:00:00.123456789Z');assert.equal(q.rawTimestamp,q.capturedAt);assert.equal(q.active,false);assert.equal(q.limit,0);assert.equal(q.playerId,'0');assert.equal(q.rawMarketId,'101');
await assert.rejects(reader.strategyUniverse({dataset:'research',partitionId:'temporal',phase:'historical_timestamp'}),/Datos|sin normalizar/);
await reader.loadPartition(selection);assert.equal(calls.filter(([path])=>path==='expanded-fixture.json.gz').length,2,'partition cache stays bounded');
await assert.rejects(reader.loadPartition({dataset:'../private',partitionId:'fixture'}),/válido/);await assert.rejects(reader.loadPartition({...selection,partitionId:'not-listed'}),/catálogo/);
assert.equal(JSON.stringify(fixtures),original,'source data remain intact');
const workspace={manifest:{sources:{provider:'Football-Data.co.uk',provider_url:'https://www.football-data.co.uk/',files:[{url:'https://www.football-data.co.uk/mmz4281/2526/E0.csv',sha256:'f'.repeat(64),retrieved_at:'2026-10-30T10:00:00Z'}]}}};
assert.equal(sourceForWorkspaceEvent(workspace,{season:'2025/2026',league:'E0'}).sha256,'f'.repeat(64));assert.equal(sourceForWorkspaceEvent(workspace,{season:'2025/26',league:'E0'}).sourceRow,null);
const playerSource=sourceForPlayer({entities:{sources:[{id:'roster',url:'https://site.api.espn.com/roster?apiKey=private',sha256:'1'.repeat(64),asOf:'2026-10-30T00:00:00Z'}]}},{source:'roster'});assert.equal(playerSource.provider,'ESPN');assert.equal(playerSource.url,'https://site.api.espn.com/roster');

// Actual small partitions prove the same parser accepts shipped tables.
const read=async(path)=>{const bytes=readFileSync(new URL('../app/data/'+path,import.meta.url));return JSON.parse(path.endsWith('.gz')?gunzipSync(bytes):bytes);};
const actual=new FootballDataArchive({read});await actual.initialize();
const fdManifest=actual.datasets.get('expanded').manifest,fdPart=fdManifest.partitions.find(p=>p.id==='2627-E0');assert.ok(fdPart);
const fd=await actual.loadPartition({dataset:'expanded',partitionId:fdPart.id});assert.equal(fd.offers.length,fdPart.quoteCount);assert.equal(fd.events.length,fdPart.eventCount);assert.ok(fd.offers.every(row=>row.sourceColumn&&row.sourceRow>=2&&row.sourceProvider==='Football-Data.co.uk'&&!row.capturedAt));
const rm=actual.datasets.get('research').manifest,bfPart=rm.partitions.find(p=>p.provider==='betfair_sample');assert.ok(bfPart);
const bf=await actual.loadPartition({dataset:'research',partitionId:bfPart.id});assert.equal(bf.offers.length,bfPart.quoteCount);assert.equal(bf.events.length,1);assert.ok(bf.offers.every(row=>row.priceType==='last_traded_price'&&row.sourceProvider.includes('Betfair')&&row.sourceSha256===bfPart.source.sha256));
if(existsSync(new URL('../app/data/additional-market-manifest.json',import.meta.url))){const am=actual.datasets.get('additional').manifest,part=[...am.partitions].sort((a,b)=>a.quoteCount-b.quoteCount)[0],data=await actual.loadPartition({dataset:'additional',partitionId:part.id});assert.equal(data.offers.length,part.quoteCount);assert.ok(data.offers.every(row=>row.sourceColumn&&row.sourceUrl&&!row.capturedAt));}
console.log('Archive reader: exact prices and source files, source phase isolation, timestamp/credential preservation, bounded cache, nested legacy records and real shipped partitions passed.');
