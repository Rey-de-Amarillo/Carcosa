/** Persist mathematical trees and measure the exact same scoped operations. */
import assert from 'node:assert/strict';
import {PRICE_FORMULA_KIND,normalizePriceFormula,evaluatePriceFormula} from '../app/football-price-engine.js';
import {FormulaMetricsEngine,metricsFromSummary,createOfferIndex} from '../app/formula-metrics.js';
import {FootballData} from '../app/workspace-data.js';
import {STRATEGY_STORAGE_KEY,loadStrategies,saveStrategies,defaultScoreAlert} from '../app/strategy-store.js';
import {isPaymentFormula} from '../app/football-price-library.js';

const condition=(id,field,value,operator='>=')=>({type:'condition',id,field,operator,value});
const group=(id,operator,...children)=>({type:'group',id,operator,children});
const valueRule=normalizePriceFormula({kind:PRICE_FORMULA_KIND,id:'price-value',name:'Pago por referencia',stake:100,mode:'value',onePerMatch:false,expression:group('root','Y',condition('positive','ev',.01),group('choice','O',condition('payout','gross_payout',300),condition('profit','expected_profit',5)))});
const coverageRule=normalizePriceFormula({...valueRule,id:'price-cover',name:'Tres pagos',mode:'coverage',structure:'three_outcomes',onePerMatch:true,expression:group('coverage-root','Y',condition('floor','min_return',.01))});
const values=new Map(),storage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};
const oldAlert=defaultScoreAlert(),oldEV={kind:'market-ev',id:'old-ev',name:'Anterior',stake:1,onePerMatch:true,expression:'ev >= 0.03'};
const saved=saveStrategies([valueRule,coverageRule,oldAlert,oldEV],{},storage);
assert.deepEqual(loadStrategies(storage),saved,'mathematical, old tree and legacy rule persistence coexist');
assert.deepEqual(saveStrategies(loadStrategies(storage),{},storage),saved,'repeat saves preserve all Y/O branches');
assert.deepEqual(loadStrategies(storage)[0].expression,valueRule.expression);
assert.ok(values.has(STRATEGY_STORAGE_KEY));
assert.throws(()=>saveStrategies([{...valueRule,expression:group('bad-root','Y',condition('human','team',1))}],{},storage),/condición de pago/,'human identity cannot enter price formulas through storage');

const events=[
  {id:'new',date:'2024-05-01',league:'L1',home:'Ejemplo A',away:'Ejemplo B',home_score:1,away_score:0},
  {id:'old',date:'2019-05-01',league:'L2',home:'Ejemplo C',away:'Ejemplo D',home_score:0,away_score:0},
];
const quote=(event,book,side,odds,probability)=>({id:events[event].id,event,date:events[event].date,league:events[event].league,book,side,odds,probability,references:['REF'],referenceSd:.01,snapshotId:'capture',capturedAt:'2024-04-30T15:00:00Z',rulesId:'football-90min-v1'});
const offers=[
  quote(0,'A',0,3.2,.35),quote(0,'A',1,3.2,.30),quote(0,'A',2,3.2,.35),
  quote(0,'B',0,2.8,.35),quote(0,'B',1,3.5,.30),quote(0,'B',2,3.8,.35),
  quote(1,'A',0,3.3,.35),quote(1,'A',1,3.3,.30),quote(1,'A',2,3.3,.35),
];
const unknownOffers=offers.slice(0,3).map(({snapshotId,capturedAt,...q})=>({...q,book:'NO-TIME'}));
const universe={events,offers:[...offers,...unknownOffers],name:'Fixture de precios'};
let init=0,universeLoads=0;
const data={async initialize(){init++;this.entities={};},async unifiedStrategyUniverse(){universeLoads++;return universe;}};
const metrics=new FormulaMetricsEngine(data);
const before=JSON.stringify({universe,valueRule,coverageRule});
for(const rule of [valueRule,coverageRule])for(const scope of [{period:'all'},{period:'test',book:'A'},{period:'validation'},{period:'test',league:'L1',book:'A|B'},{period:'test',book:'NO-TIME'}]){
  const scoped=createOfferIndex(universe.offers,scope).offers;
  const expected=evaluatePriceFormula({events,offers:scoped},rule,{entities:{},summaryOnly:true,archiveScenario:isPaymentFormula(rule)});
  assert.deepEqual(await metrics.evaluate(rule,scope),metricsFromSummary(expected.summary,expected.coverage.unknownCandidates,expected.coverage),'worker dispatch agrees with scoped mathematical operations');
}
assert.equal(init,1);
assert.ok(universeLoads>0);
const complete=await metrics.evaluate(coverageRule,{period:'test',book:'A'});
assert.equal(complete.n,1,'a coverage operation is one row, not three independent bets');
assert.equal(complete.meanEV,null,'unequal rounded payments do not invent an exact expected value');assert.ok(complete.roi>0);assert.equal(complete.scenario,true,'the hypothetical allocation remains a scenario');
assert.ok(complete.meanMinReturn>0,'positive minimum payments remain measurable while exact EV is unknown');
assert.equal((await metrics.evaluate(valueRule,{period:'all'})).meanMinReturn,null,'a single value bet does not claim a covered payoff floor');
const missingTime=await metrics.evaluate(coverageRule,{period:'test',book:'NO-TIME'});
assert.equal(missingTime.n,1);assert.equal(missingTime.meanEV,null);assert.ok(missingTime.meanMinReturn>0);assert.ok(missingTime.roi>0);assert.equal(missingTime.scenario,true,'complete archived prices permit hypothetical arithmetic');
assert.equal(missingTime.scenarioCandidates,1);assert.equal(missingTime.verifiedCandidates,0);assert.equal(missingTime.unknownCandidates,0,'a calculable archive scenario is separate from missing data');
const strict=evaluatePriceFormula({events,offers:unknownOffers},coverageRule);
assert.equal(strict.alerts.length,0);assert.ok(strict.coverage.unknownCandidates>0,'default strict evaluation still requires verified capture');
const scenario=evaluatePriceFormula({events,offers:unknownOffers},coverageRule,{archiveScenario:true});
assert.equal(scenario.alerts.length,1);assert.equal(scenario.alerts[0].captureVerified,false);assert.equal(scenario.alerts[0].scenarioBasis,'archive_unverified_capture');
assert.ok(scenario.alerts[0].statuses.includes('capture_unverified'));
for(const leg of scenario.alerts[0].legs){assert.equal(leg.capturedAt,null);assert.equal(leg.snapshotId,null);assert.equal(leg.sourceQuote.capturedAt,undefined);assert.equal(leg.sourceQuote.snapshotId,undefined);}
const rejecting={...coverageRule,id:'rejecting',expression:group('reject-root','Y',condition('too-high','min_return',1))};
const rejected=await metrics.evaluate(rejecting,{period:'test',book:'NO-TIME'});
assert.equal(rejected.n,0);assert.equal(rejected.scenarioCandidates,1);assert.equal(rejected.verifiedCandidates,0);assert.equal(rejected.unknownCandidates,0,'a fully evaluated negative case is not missing data');
const verified=await metrics.evaluate(coverageRule,{period:'test',book:'A'});
assert.equal(verified.verifiedCandidates,1);assert.equal(verified.scenarioCandidates,0);
const crossBook={...coverageRule,id:'archived-cross-book',bookPolicy:'cross_book'};
const strictLegacy=await metrics.evaluate(crossBook,{period:'test',book:'NO-TIME'});
assert.equal(strictLegacy.n,0);assert.equal(strictLegacy.scenarioCandidates,0);assert.ok(strictLegacy.unknownCandidates>0,'the worker never enables archive scenarios for other-house formulas');
for(const quotes of [unknownOffers.slice(0,2),[...unknownOffers,{...unknownOffers[0],odds:3.4}]]){
  const incomplete=new FormulaMetricsEngine({async initialize(){this.entities={};},async unifiedStrategyUniverse(){return {events,offers:quotes};}});
  const unresolved=await incomplete.evaluate(coverageRule,{period:'all'});
  assert.equal(unresolved.n,0);assert.equal(unresolved.scenarioCandidates,0);assert.equal(unresolved.verifiedCandidates,0);assert.ok(unresolved.unknownCandidates>0,'incomplete or ambiguous prices remain truly uncalculable');
}
assert.equal(JSON.stringify({universe,valueRule,coverageRule}),before,'metrics preserve source and criteria');

const route=new FootballData();let routeLoads=0;route.unifiedStrategyUniverse=async()=>{routeLoads++;return universe;};
assert.strictEqual(await route.strategyUniverse(valueRule),universe);assert.strictEqual(await route.strategyUniverse(coverageRule),universe);assert.equal(routeLoads,2);

// Optional provenance columns survive ingestion without deriving a timestamp
// from a match date. Unknown settlement remains unknown, including won:null.
const table={columns:['event','book','side','odds','probability','reference_mean','reference_sd','references','won','profit','captured_at','snapshot_id','rules_id','reference_probability','push_probability','extra_provenance'],rows:[
  [0,'A',0,2,.51,.5,.01,['REF'],null,null,'2024-04-30T15:00:00Z','snap-source','rules-source',.52,.02,{capture:'original'}],
  [0,'A',1,3,.3,.3,.02,['REF'],false,-1,null,null,null,null,null,null],
]};
const originalFetch=globalThis.fetch;
try{
  globalThis.fetch=async()=>new Response(JSON.stringify(table),{status:200,headers:{'Content-Type':'application/json'}});
  const loaded=new FootballData();loaded.events=[events[0]];loaded.manifest={tables:{offers:{parts:[{year:'2024',path:'fixture.json.gz'}]}}};
  await loaded.ensureOffers('all');
  const q=loaded.offers[0],missing=loaded.offers[1];
  assert.equal(q.captured_at,table.rows[0][10]);assert.equal(q.snapshotId,'snap-source');assert.equal(q.rulesId,'rules-source');assert.equal(q.referenceProbability,.52);assert.equal(q.pushProbability,.02);assert.equal(q.referenceSd,.01);assert.deepEqual(q.extra_provenance,{capture:'original'});assert.equal(q.won,null);
  assert.equal(missing.captured_at,null);assert.equal(missing.snapshot_id,null);assert.equal(missing.rules_id,null);assert.equal(missing.capturedAt,undefined,'event day does not become an observed quote time');assert.equal(missing.won,false);
}finally{globalThis.fetch=originalFetch;}
console.log('Price formula integration: exact scoped scenario metrics, strict verification, null versus rejected criteria, Y/O storage and intact provenance passed.');
