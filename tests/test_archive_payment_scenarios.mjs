/** Recorded prices may support explicit hypothetical payments, never fake captures. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {newPriceFormula,normalizePriceFormula,evaluatePriceFormula,evaluatePaymentFormula} from '../app/football-price-engine.js';
import {FormulaMetricsEngine,metricsFromSummary} from '../app/formula-metrics.js';
const near=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-8,`${actual} != ${expected}`);
let sequence=0;
const c=(field,value,operator='>=')=>({type:'condition',id:`archive-c-${++sequence}`,field,operator,value});
const g=(...children)=>({type:'group',id:`archive-g-${++sequence}`,operator:'Y',children});
const rule=overrides=>normalizePriceFormula({...newPriceFormula(),id:'archive-math',name:'Pagos del archivo',onePerMatch:false,...overrides});
const accepting=rule({expression:g(c('min_return',-1,'>'))});
const positive=rule();
const event={id:'recorded',date:'2024-05-01',league:'L',home:'A',away:'B',home_score:1,away_score:0};
const quote=(selection,odds,extra={})=>({event:0,book:'Bet365',market:'btts',period:'full',selection,odds,date:event.date,league:event.league,probability:.999,references:['OTHER'],...extra});
const pair=[quote('yes',2),quote('no',1.75)];
const universe={events:[event],offers:pair};
const run=(offers=pair,definition=accepting,options={archiveScenario:true},events=[event])=>evaluatePriceFormula({events,offers},definition,options);
const original=JSON.stringify(universe);
assert.equal(evaluatePriceFormula(universe,accepting).alerts.length,0,'strict default still requires captured compatible prices');
assert.ok(evaluatePriceFormula(universe,accepting).coverage.unknownCandidates>0);
const hypothetical=run();
assert.equal(hypothetical.alerts.length,1,'a full unambiguous same-house historical set supports an explicit hypothetical calculation');
const row=hypothetical.alerts[0],payment=evaluatePaymentFormula(accepting,{odds:[2,1.75]});
near(row.minPayout,payment.minPayout);near(row.minProfit,payment.minProfit);near(row.minReturn,payment.minReturn);
assert.equal(hypothetical.coverage.scenarioCandidates,1);assert.equal(hypothetical.coverage.verifiedCandidates,0);
assert.equal(row.captureVerified,false);assert.equal(row.scenarioBasis,'archive_unverified_capture');assert.ok(row.statuses.includes('capture_unverified'));
assert.equal(row.isScenario,true);assert.equal(row.probability,null);assert.equal(row.probabilityN,null);assert.deepEqual(row.reference,[]);
assert.equal(row.legs.length,2);assert.ok(row.legs.every(leg=>leg.capturedAt==null&&leg.snapshotId==null&&!leg.rulesId),'missing capture and rules provenance stay absent');
assert.equal(JSON.stringify(universe),original,'scenario evaluation never changes original prices or metadata');
assert.equal(run(pair,positive).alerts.length,0,'the negative Bet365 example remains a calculated failure');
assert.ok(run(pair,positive).coverage.falseCandidates>0,'calculated false and unavailable data are distinct');
assert.equal(run(pair,positive).coverage.unknownCandidates,0,'a complete hypothetical set is not counted as missing just because it fails the criterion');
near(row.profit,93.32-100,'actual result settles the allocated losing-case payout');
for(const offers of [[pair[0]],[pair[0],{...pair[1],book:'Another'}]]){
 const result=run(offers);assert.equal(result.alerts.length,0,'partial or cross-house quotes cannot manufacture a complete hypothetical operation');assert.ok(result.coverage.unknownCandidates>0);
}
assert.equal(run(pair,{...accepting,bookPolicy:'cross_book'}).alerts.length,0,'archive fallback is forbidden for a cross-house policy');
const duplicated=run([...pair,{...pair[0]}]);assert.equal(duplicated.alerts.length,1,'an identical repeated record is not ambiguous or a second operation');
for(const conflict of [{odds:2.3},{active:false},{suspended:true},{active:false,odds:null}]){
 const result=run([...pair,{...pair[0],...conflict}]);assert.equal(result.alerts.length,0,'different untimed prices or suspension cannot pick a favorable imagined quote');assert.ok(result.coverage.unknownCandidates>0);
}
const incompatibleRules=run([{...pair[0],rulesId:'rule-A'},{...pair[1],rulesId:'rule-B'}]);
assert.equal(incompatibleRules.alerts.length,0,'known incompatible settlement rules remain separate');
const incompatibleSnapshots=run([{...pair[0],snapshotId:'capture-A'},{...pair[1],snapshotId:'capture-B'}]);
assert.equal(incompatibleSnapshots.alerts.length,0,'known different snapshots remain separate');
const distant=run([{...pair[0],capturedAt:'2024-04-30T10:00:00Z'},{...pair[1],capturedAt:'2024-04-30T10:02:00Z'}]);
assert.equal(distant.alerts.length,0,'explicit captures outside the compatibility window do not become simultaneous');
const withRules=run(pair.map(q=>({...q,rulesId:'regulation'})));assert.equal(withRules.alerts.length,1,'missing time alone may be labeled hypothetical');
const verifiedOffers=pair.map(q=>({...q,rulesId:'regulation',snapshotId:'original-snapshot',capturedAt:'2024-04-30T10:00:00Z'}));
const verified=run(verifiedOffers);assert.equal(verified.alerts.length,1);assert.equal(evaluatePriceFormula({events:[event],offers:verifiedOffers},accepting).alerts.length,1);
assert.equal(verified.coverage.verifiedCandidates,1);assert.equal(verified.coverage.scenarioCandidates,0);assert.equal(verified.alerts[0].captureVerified,true);
assert.ok(verified.alerts[0].legs.every(leg=>leg.rulesId==='regulation'&&leg.snapshotId==='original-snapshot'&&leg.capturedAt==='2024-04-30T10:00:00Z'));
const cachedSource={events:[event],offers:pair};
assert.equal(evaluatePriceFormula(cachedSource,accepting,{immutableUniverse:true}).alerts.length,0);
assert.equal(evaluatePriceFormula(cachedSource,accepting,{immutableUniverse:true,archiveScenario:true}).alerts.length,1,'strict preparation cache cannot disable the explicit scenario path');
assert.equal(evaluatePriceFormula(cachedSource,accepting,{immutableUniverse:true}).alerts.length,0,'scenario cache cannot enable fallback in the strict default');
const unsettled=run(pair,accepting,{archiveScenario:true},[{...event,home_score:null,away_score:null}]);
assert.equal(unsettled.alerts.length,1);assert.equal(unsettled.alerts[0].profit,null);assert.equal(unsettled.summary.profit,null);assert.equal(unsettled.summary.roi,null,'a missing result never turns hypothetical payment into historical profit');

// A bounded sample uses the real stored Bet365 rows, retaining source odds.
const table=path=>{const bytes=readFileSync(new URL(path,import.meta.url));return JSON.parse(path.endsWith('.gz')?gunzipSync(bytes):bytes);};
const rows=payload=>payload.rows.map(values=>Object.fromEntries(payload.columns.map((column,i)=>[column,values[i]])));
const sourceEvents=rows(table('../app/data/workspace-events.json.gz'));
const sourceOffers=rows(table('../app/data/workspace-offers-2026.json.gz'));
const byEvent=new Map();
for(const offer of sourceOffers){if(offer.book!=='B365')continue;if(!byEvent.has(offer.event))byEvent.set(offer.event,[]);byEvent.get(offer.event).push(offer);}
const sample=[...byEvent].filter(([,quotes])=>new Set(quotes.map(q=>q.side)).size===3&&quotes.length===3).slice(0,6);
assert.equal(sample.length,6,'the source contains a bounded complete Bet365 sample');
const events=sample.map(([index])=>{const e=sourceEvents[index];return {...e,home:e.home_team,away:e.away_team};});
const offers=sample.flatMap(([,quotes],event)=>quotes.map(q=>({...q,event,date:events[event].date,league:events[event].league})));
assert.ok(offers.every(q=>q.capturedAt==null&&q.snapshotId==null&&q.rulesId==null));
const completeThree=rule({structure:'three_outcomes',expression:g(c('min_return',-1,'>'))});
const real=evaluatePriceFormula({events,offers},completeThree,{archiveScenario:true});
assert.equal(real.coverage.scenarioCandidates,6);assert.equal(real.coverage.verifiedCandidates,0);
assert.equal(real.alerts.length,6);assert.equal(real.coverage.unknownCandidates,0);assert.equal(real.summary.n,6);
for(const operation of real.alerts){
 const source=offers.filter(q=>events[q.event].id===operation.eventId).sort((a,b)=>a.side-b.side);
 assert.deepEqual(operation.legs.map(leg=>leg.odds),source.map(q=>q.odds));
 const expected=evaluatePaymentFormula(completeThree,{odds:source.map(q=>q.odds)});near(operation.minPayout,expected.minPayout);near(operation.minProfit,expected.minProfit);near(operation.minReturn,expected.minReturn);
 assert.equal(operation.probability,null);assert.deepEqual(operation.reference,[]);assert.ok(operation.legs.every(leg=>leg.capturedAt==null&&leg.snapshotId==null&&!leg.rulesId));
}
const failed=evaluatePriceFormula({events,offers},rule({structure:'three_outcomes'}),{archiveScenario:true});
assert.equal(failed.alerts.length,0,'ordinary same-house margin does not become positive coverage');
assert.equal(failed.coverage.scenarioCandidates,6,'scenario counters include calculated failures before formula filtering');assert.equal(failed.coverage.verifiedCandidates,0);
assert.equal(failed.coverage.unknownCandidates,0);assert.equal(failed.coverage.falseCandidates,6,'the recorded prices are tested and fail, rather than being hidden as no data');
let initialized=0;
const data={async initialize(){initialized++;this.entities={};},async unifiedStrategyUniverse(){return {events,offers,name:'Bet365 bounded archive'};}};
const metrics=new FormulaMetricsEngine(data),actual=await metrics.evaluate(completeThree,{period:'test',book:'B365'});
assert.equal(initialized,1);assert.deepEqual(actual,metricsFromSummary(real.summary,real.coverage.unknownCandidates,real.coverage),'worker metrics and direct hypothetical rows measure the same actual archive operations');
console.log('Archive payment scenarios: strict provenance retained, explicit same-house hypothetical fallback, ambiguity and incomplete outcomes rejected, real Bet365 math and worker metrics coherent.');
