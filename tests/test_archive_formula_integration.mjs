/** Formula scopes load one selected archive/phase and retain exact provenance. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {FootballDataArchive,sourceForWorkspaceEvent} from '../app/football-data-archive.js';
import {FootballData} from '../app/workspace-data.js';
import {FormulaMetricsEngine,formulaMetricsKey,normalizeMetricsScope,createOfferIndex,metricsFromSummary} from '../app/formula-metrics.js';
import {newPriceFormula,normalizePriceFormula,evaluatePriceFormula} from '../app/football-price-engine.js';
import {newUnifiedFormula,normalizeUnifiedFormula,evaluateUnifiedFormula} from '../app/football-unified-formula.js';

const quoteColumns=['event','book','market','period','selection','line','phase','odds','sourceColumn','sourceRow'];
const eventColumns=['id','date','home','away','league','season','home_score','away_score','sourceRow'];
const selections=['home','draw','away'];
const triplet=(prices,phase)=>prices.map((odds,i)=>[0,'B365','match_result','full',selections[i],null,phase,odds,`B365${phase==='closing'?'C':''}${['H','D','A'][i]}`,2]);
const part=(id,odds)=>({events:{columns:eventColumns,rows:[[id,'2026-10-31','Alpha','Beta','E0','2026/2027',1,0,2]]},quotes:{columns:quoteColumns,rows:odds}});
const payloads={
  'expanded-football-manifest.json':{provider:'Football-Data.co.uk',books:[{code:'B365',name:'Bet365'}],leagues:[{id:'E0',name:'Premier League'}],partitions:[
    {id:'a',path:'part-a.json.gz',league:'E0',season:'2026/2027',source:{url:'https://www.football-data.co.uk/mmz4281/2627/E0.csv',sha256:'source-a',retrievedAt:'2026-11-01T02:00:00Z'}},
    {id:'b',path:'part-b.json.gz',league:'E0',season:'2026/2027',source:{url:'https://www.football-data.co.uk/mmz4281/2627/E1.csv',sha256:'source-b',retrievedAt:'2026-11-01T02:01:00Z'}},
  ]},
  'additional-market-manifest.json':{provider:'SGodds',partitions:[]},
  'research-market-manifest.json':{provider:'Research',partitions:[]},
  'part-a.json.gz':part('one',[...triplet([3.3,3.3,3.3],'pre_closing'),...triplet([2.3,3,3.5],'closing')]),
  'part-b.json.gz':part('two',[...triplet([3.6,3.6,3.6],'pre_closing'),...triplet([2,2,2],'closing')]),
};
const loads=new Map();
const archive=new FootballDataArchive({read:async path=>{loads.set(path,(loads.get(path)||0)+1);if(!payloads[path])throw new Error('Unexpected fixture '+path);return structuredClone(payloads[path]);}});
let defaultLoads=0;
const data={archive,async initialize(){this.entities={};},async unifiedStrategyUniverse(){defaultLoads++;return {events:[],offers:[],name:'Original'};}};
const engine=new FormulaMetricsEngine(data);
const rule=normalizePriceFormula({...newPriceFormula(),id:'pure',name:'Retorno positivo',structure:'three_outcomes',stake:100});
const selected=(partitionId,phase)=>({period:'all',archive:{dataset:'expanded',partitionId,phase}});
const opening=await engine.evaluate(rule,selected('a','pre_closing'));
const closing=await engine.evaluate(rule,selected('a','closing'));
const other=await engine.evaluate(rule,selected('b','pre_closing'));
assert.equal(opening.n,1);assert.equal(closing.n,0);assert.equal(closing.scenarioCandidates,1);assert.equal(closing.unknownCandidates,0);
assert.equal(other.n,1);assert.ok(other.meanMinReturn>opening.meanMinReturn,'different selected files cannot reuse the same cached metrics');
assert.equal(defaultLoads,0,'an expanded source never silently evaluates the original archive');
assert.equal(loads.get('part-a.json.gz'),1);assert.equal(loads.get('part-b.json.gz'),1,'only selected bounded partitions load');
assert.strictEqual(await engine.evaluate({...rule,name:'Renamed',id:'copy'},selected('a','pre_closing')),opening,'same exact archive scope may reuse its cached result');
assert.notEqual(formulaMetricsKey(rule,selected('a','pre_closing')),formulaMetricsKey(rule,selected('a','closing')));
assert.notEqual(formulaMetricsKey(rule,selected('a','pre_closing')),formulaMetricsKey(rule,selected('b','pre_closing')));
assert.notEqual(formulaMetricsKey(rule,selected('a','pre_closing')),formulaMetricsKey(rule,{...selected('a','pre_closing'),archive:{...selected('a','pre_closing').archive,book:'OTHER'}}));
for(const phase of ['pre_closing','closing']){
  const scope=selected('a',phase),universe=await archive.strategyUniverse(scope.archive);
  assert.equal(new Set(universe.offers.map(q=>q.phase)).size,1,'opening and closing are separate formula cohorts');
  const expected=evaluatePriceFormula({events:universe.events,offers:createOfferIndex(universe.offers,scope).offers},rule,{archiveScenario:true});
  assert.deepEqual(await engine.evaluate(rule,scope),metricsFromSummary(expected.summary,expected.coverage.unknownCandidates,expected.coverage));
  for(const q of universe.offers){assert.equal(q.sourceUrl,payloads['expanded-football-manifest.json'].partitions[0].source.url);assert.equal(q.sourceSha256,'source-a');assert.equal(q.sourceRow,2);assert.equal(q.capturedAt,undefined);assert.equal(q.rulesId,undefined);assert.equal(q.probability,null);assert.deepEqual(q.references,[]);}
}
const missingBook=await engine.evaluate(rule,{...selected('a','pre_closing'),book:'MISSING'});assert.equal(missingBook.n,0);assert.equal(missingBook.scenarioCandidates,0);
const filteredMarket=await engine.evaluate(rule,{...selected('a','pre_closing'),archive:{...selected('a','pre_closing').archive,market:'total_goals'}});assert.equal(filteredMarket.n,0);
const unified=normalizeUnifiedFormula({...newUnifiedFormula(),id:'unified',name:'Cuota',expression:{type:'group',id:'root',operator:'Y',children:[{type:'condition',id:'odds',field:'odds',operator:'>',value:3}]}});
const u=await archive.strategyUniverse(selected('a','pre_closing').archive),expectedUnified=evaluateUnifiedFormula(u,unified);
assert.deepEqual(await engine.evaluate(unified,selected('a','pre_closing')),metricsFromSummary(expectedUnified.summary,expectedUnified.coverage.unknownCandidates));
for(const old of [{kind:'market-ev',id:'old',name:'Old',expression:'ev > 0',stake:100},{kind:'football-alert',id:'legacy',name:'Legacy'}])await assert.rejects(engine.evaluate(old,selected('a','pre_closing')),/anterior.*archivos ampliados|no admite archivos ampliados/);
for(const archive of [{dataset:'research',partitionId:'x',phase:'raw'}, {dataset:'expanded',partitionId:'a'}, {dataset:'expanded',partitionId:'a',phase:'all'}, {dataset:'expanded',partitionId:'a',phase:'*'}, {dataset:'expanded',partitionId:'a',phase:'both'}])assert.throws(()=>normalizeMetricsScope({archive}),/archivo|fase/);
assert.deepEqual(normalizeMetricsScope({...selected('a','pre_closing'),archive:{...selected('a','pre_closing').archive,untrusted:'discard'}}),{...selected('a','pre_closing'),league:'',book:''},'cache scope retains only validated archive keys');
assert.ok(new FootballData().archive instanceof FootballDataArchive);
const record={season:'2026/2027',league:'E0'},source={url:'https://www.football-data.co.uk/mmz4281/2627/E0.csv',sha256:'verified-file',retrieved_at:'2026-11-01T02:00:00Z'};
assert.deepEqual(sourceForWorkspaceEvent({manifest:{sources:{provider:'Football-Data.co.uk',files:[source]}}},record),{provider:'Football-Data.co.uk',url:source.url,retrievedAt:source.retrieved_at,sha256:'verified-file',phase:'pre_closing',sourceRow:null,sourceColumn:null});

// A real partition is also bounded to one phase and retains every exact price.
const manifest=JSON.parse(readFileSync(new URL('../app/data/expanded-football-manifest.json',import.meta.url)));
const actual=manifest.partitions.find(p=>p.id==='2627-E0');
const real=new FootballDataArchive({read:async(path,gzip)=>{const bytes=readFileSync(new URL('../app/data/'+path,import.meta.url));return JSON.parse(gzip?gunzipSync(bytes):bytes);}});
const realSource=await real.strategyUniverse({dataset:'expanded',partitionId:actual.id,phase:'pre_closing',book:'B365',market:'match_result'});
assert.equal(realSource.events.length,actual.eventCount);assert.ok(realSource.offers.length>100);
const referenceTable=JSON.parse(gunzipSync(readFileSync(new URL('../app/data/'+actual.path,import.meta.url))));
const rawQuotes=referenceTable.quotes.rows.filter(q=>q[1]==='B365'&&q[2]==='match_result'&&q[6]==='pre_closing');
assert.deepEqual(realSource.offers.map(q=>q.odds),rawQuotes.map(q=>q[7]));
assert.equal(realSource.offers.every(q=>q.sourceUrl===actual.source.url&&q.sourceSha256===actual.source.sha256&&q.sourceRow>=2&&q.phase==='pre_closing'&&q.capturedAt===undefined),true);
console.log('Archive formula integration: bounded selected files, isolated phase/cache scopes, source provenance, exact real prices, external unsupported errors and preserved original archive passed.');
