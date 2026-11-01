import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {evaluateUnifiedFormula,normalizeUnifiedFormula} from '../app/football-unified-formula.js';
import {evaluateFootballStrategy,summarizeFootballAlerts} from '../app/football-strategy-engine.js';
import {buildFootballFormulaLibrary} from '../app/football-formula-library.js';
import {defaultMarketSelection} from '../app/football-market-catalog.js';
import {defaultScoreAlert} from '../app/strategy-store.js';
import {matchAndRank,summarize} from '../app/formula-engine.js';
import {periodMatches} from '../app/workspace-data.js';
import {FormulaMetricsEngine,createOfferIndex,candidateOffers,positiveMarketConstraint,formulaMetricsKey,metricsFromSummary,createFormulaMetricsRunner} from '../app/formula-metrics.js';

const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const home=entities.teams.find(t=>t.name==='Boca Juniors'),away=entities.teams.find(t=>t.name==='River Plate');
const person=entities.players.find(p=>p.name==='Miguel Merentiel');
const events=[
  {id:'current',date:'2024-05-01',league:'ARG1',home:home.name,away:away.name,homeTeamId:home.id,awayTeamId:away.id,home_score:2,away_score:0,home_ht_score:1,away_ht_score:0,home_corners:6,away_corners:3,playerStats:[{playerId:person.id,teamId:home.id,played:true,goals:1,shots:3,shotsOnTarget:2}]},
  {id:'earlier',date:'2019-05-01',league:'ARG1',home:home.name,away:away.name,homeTeamId:home.id,awayTeamId:away.id,home_score:0,away_score:2,home_ht_score:0,away_ht_score:1},
  {id:'pending',date:'2024-05-03',league:'E0',home:home.name,away:away.name,homeTeamId:home.id,awayTeamId:away.id},
];
const quote=(event,book,side,odds,p)=>({id:events[event].id,event,book,side,odds,date:events[event].date,league:events[event].league,home:events[event].home,away:events[event].away,probability:p,references:[book==='A'?'B':'A'],ev:p*odds-1,won:side===0,profit:side===0?odds-1:-1,snapshotId:'one'});
const offers=[
  quote(0,'A',0,1.9,.53),quote(0,'A',1,3.4,.25),quote(0,'A',2,4.2,.22),
  quote(0,'B',0,2,.51),quote(0,'B',1,3.5,.25),quote(0,'B',2,4,.24),
  quote(1,'A',0,2.1,.5),quote(1,'A',1,3.6,.25),quote(1,'A',2,3.8,.25),
  {...quote(0,'A',0,2.1,.5),market:'totals25',period:'full',selection:'over',line:2.5,team:'total'},
  {...quote(0,'A',0,1.8,.5),market:'total_goals',period:'full',selection:'under',line:2.5,team:'total'},
  {...quote(0,'A',0,1.95,.5),market:'btts',period:'full',selection:'yes',probability:null,references:[]},
  {...quote(0,'A',0,2.5,.5),market:'player_goals',period:'full',selection:'at_least',line:1,team:'selected',teamId:home.id,playerId:person.id,probability:null,references:[]},
  {...quote(2,'A',0,2.2,.5),won:null,profit:null},
  {...quote(0,'A',0,2.5,.5),market:'invalid-market'},
];
offers.push({...offers[0]}); // duplicate archived quote must stay deduplicated.
const universe={events,offers,name:'Bounded actual-contract fixture'};
const leaf=(id,field,value,operator='=')=>({type:'condition',id,field,operator,...(field==='market'?{selection:value}:{value})});
const group=(id,operator,...children)=>({type:'group',id,operator,children});
const market=(id,name='match_result',selection='home')=>leaf(id,'market',{market:name,period:'full',selection});
const rule=(id,expression)=>normalizeUnifiedFormula({kind:'football-formula',version:1,id,name:id,stake:2,expression},entities);
const homeMarket=()=>market('contract');
const cases=[
  rule('market',group('root','Y',homeMarket(),leaf('price','odds',1.8,'>='))),
  rule('unrestricted-or',group('root','O',market('goals','btts','yes'),leaf('club','team',home.id))),
  rule('bounded-or',group('root','O',homeMarket(),market('goals','btts','yes'))),
  rule('negation',group('root','Y',market('not-goals','btts','yes'),{...homeMarket(),id:'not-home',operator:'!='})),
  rule('only-negation',group('root','Y',{...homeMarket(),operator:'!='})),
  rule('side-prices',group('root','Y',market('goals','btts','yes'),leaf('context-price','home_odds',1.8,'>='))),
  rule('unknown-player',group('root','Y',{type:'condition',id:'person',field:'player',operator:'=',playerId:person.id,teamId:home.id})),
  rule('unknown-btts-player',group('root','Y',market('goals','btts','yes'),{type:'condition',id:'person',field:'player',operator:'=',playerId:person.id,teamId:home.id})),
  rule('metadata-only',group('root','Y',leaf('club','team',home.id))),
];
const before=JSON.stringify({universe,cases});
for(const current of cases){
  const full=evaluateUnifiedFormula(universe,current,{entities});
  const light=evaluateUnifiedFormula(universe,current,{entities,summaryOnly:true});
  assert.deepEqual(light.alerts,[],'summaryOnly does not return detailed alerts');
  assert.deepEqual(light.summary,full.summary,current.id+' has exactly the same summary');
  assert.deepEqual(light.coverage,full.coverage,current.id+' has exactly the same coverage');
}
const allIndex=createOfferIndex(offers,{period:'all'});
assert.equal(positiveMarketConstraint(cases[1].expression),null,'an unrestricted OR cannot be globally filtered by one branch');
assert.strictEqual(candidateOffers(allIndex,cases[5]),allIndex.offers,'side odds retain companion 1X2 quotes');
assert.strictEqual(candidateOffers(allIndex,cases[4]),allIndex.offers,'negative market leaf is not a positive index restriction');
assert.deepEqual([...positiveMarketConstraint(cases[2].expression)].sort(),['btts','match_result']);

let initializes=0,loads=0;
const data={
  async initialize(){initializes++;this.manifest={generated_at:'fixture'};this.entities=entities;return this;},
  events,offers,
  async unifiedStrategyUniverse(){loads++;return universe;},
  async strategyUniverse(){return universe;},
  async ensureOffers(){},
};
const engine=new FormulaMetricsEngine(data);
const library=buildFootballFormulaLibrary(entities);
for(const scope of [{period:'all'},{period:'test',book:'A'},{period:'validation',league:'ARG1'}]){
  const index=createOfferIndex(offers,scope);
  for(const current of [...cases,...library]){
    const reference=evaluateUnifiedFormula({events,offers:index.offers},current,{entities});
    const optimized=await engine.evaluate(current,scope);
    assert.deepEqual(optimized,metricsFromSummary(reference.summary,reference.coverage.unknownCandidates),current.id+' index preserves actual metrics and unknown candidates');
  }
}
assert.equal(initializes,1,'worker data initializes only once');
assert.ok(engine.cache.size<=512);assert.ok(engine.scopeIndexes.size<=8);
assert.equal(JSON.stringify({universe,cases}),before,'indexing/evaluation never mutates source or saved rules');
const cached=await engine.evaluate(cases[0],{period:'all'}),loadsBefore=loads;
assert.strictEqual(await engine.evaluate({...cases[0],id:'copy',name:'Renamed'},{period:'all'}),cached,'same criteria reuse metric cache after a rename/copy');
assert.equal(loads,loadsBefore,'cache hit does not reload a universe');
assert.equal(formulaMetricsKey(cases[0],{period:'all'}),formulaMetricsKey({...cases[0],name:'Other',id:'other'},{period:'all'}));
const changed=await engine.evaluate({...cases[0],stake:3},{period:'all'});assert.notEqual(changed.profit,cached.profit,'stake edit invalidates cached monetary result');
assert.equal(changed.roi,cached.roi,'stake scaling preserves ROI');
const empty=await engine.evaluate(cases[0],{period:'test',league:'missing'});
assert.equal(empty.n,0);assert.equal(empty.meanEV,null);assert.equal(empty.roi,null);assert.equal(empty.expectedPriced,0);
const sgp=await engine.evaluate(rule('btts-only',group('root','Y',market('btts','btts','yes'))),{period:'all'});
assert.equal(sgp.meanEV,null,'missing independent probability never becomes historical ROI');assert.equal(sgp.expectedPriced,0);assert.equal(sgp.settledPriced,1);assert.equal(sgp.roi,-1,'a settled loss still has a real historical return');

// Legacy pricing and temporal training keep the exact Usar evaluation order.
const legacy={...defaultScoreAlert(),id:'legacy',conditions:[],onePerMatch:false,action:{...defaultScoreAlert().action,...defaultMarketSelection('match_result'),minSample:1}};
const legacyResult=evaluateFootballStrategy(universe,legacy,{entities});
const legacyExpected=summarizeFootballAlerts(legacyResult.alerts.filter(r=>periodMatches(r,'test')));
assert.deepEqual(await engine.evaluate(legacy,{period:'test'}),metricsFromSummary(legacyExpected));
assert.notEqual(legacyExpected.meanEV,null,'the earlier 2019 event supplies actual prior training for the 2024 display window');
const evRule={kind:'market-ev',id:'ev',name:'EV',expression:'cuota >= 1.8 Y cuota <= 4',stake:2,onePerMatch:false};
const evRows=matchAndRank(offers.filter(r=>periodMatches(r,'test')&&r.book==='A'),evRule.expression,{onePerMatch:false}),evExpected=summarize(evRows,2);
const evMetrics=await engine.evaluate(evRule,{period:'test',book:'A'});
assert.equal(evMetrics.meanEV,evExpected.meanEV);assert.equal(evMetrics.roi,evExpected.roi);assert.equal(evMetrics.profit,evExpected.profit);
assert.equal(evMetrics.meanOdds,evExpected.meanOdds);assert.equal(evMetrics.winRate,evExpected.winRate);
assert.equal(evMetrics.unknownCandidates,null,'the original EV evaluator does not measure unknown candidates');

// A scope change can arrive after manifest/entities but before events load.
let release,initializationCalls=0;
const gate=new Promise(resolve=>{release=resolve;});
const delayed={
  async initialize(){initializationCalls++;this.manifest={};this.entities=entities;await gate;this.events=events;this.offers=offers;},
  async unifiedStrategyUniverse(){assert.strictEqual(this.events,events,'all events finish loading before universe evaluation');return {events:this.events,offers:this.offers};},
};
const racing=new FormulaMetricsEngine(delayed);
const first=racing.evaluate(cases[0],{period:'test'});await Promise.resolve();await Promise.resolve();
assert.ok(delayed.manifest&&delayed.entities,'initial metadata is already visible');
const second=racing.evaluate(cases[0],{period:'validation'});release();
const raceResults=await Promise.all([first,second]);assert.equal(initializationCalls,1);assert.ok(raceResults.every(metrics=>metrics.n>0));
let attempts=0;
const retrying=new FormulaMetricsEngine({async initialize(){attempts++;this.manifest={};this.entities=entities;if(attempts===1)throw new Error('Events unavailable');}});
await assert.rejects(retrying.initialize(),/Events unavailable/);await retrying.initialize();assert.equal(attempts,2,'partial failed initialization cannot be mistaken for ready data');

// Cancellation is processed between recipes; stale generations never finish.
const messages=[];let newer,runner;
const fake={initialize:async()=>{},evaluate:async current=>({n:current.value})};
runner=createFormulaMetricsRunner(fake,message=>{messages.push(message);if(message.type==='progress'&&message.requestId==='old'&&message.completed===1)newer=runner({type:'evaluate',requestId:'new',formulas:[{id:'fresh',value:3}]});},{yieldTask:async()=>{}});
await runner({type:'evaluate',requestId:'old',formulas:[{id:'first',value:1},{id:'stale',value:2}]});await newer;
assert.ok(!messages.some(m=>m.type==='metric'&&m.id==='stale'));
assert.ok(!messages.some(m=>m.type==='complete'&&m.requestId==='old'));
assert.ok(messages.some(m=>m.type==='metric'&&m.id==='fresh'));
assert.ok(messages.some(m=>m.type==='complete'&&m.requestId==='new'));
const errors=[];
await createFormulaMetricsRunner({initialize:async()=>{},evaluate:async()=>{throw new Error('Bad rule');}},m=>errors.push(m),{yieldTask:async()=>{}})({type:'evaluate',requestId:7,formulas:[{id:'bad'}]});
assert.ok(errors.some(m=>m.type==='error'&&m.id==='bad'&&m.message==='Bad rule'));
assert.ok(!errors.some(m=>m.type==='metric'),'failed rules never receive zero-valued fake metrics');
assert.ok(errors.some(m=>m.type==='complete'));
console.log('Formula metrics: exact summary-only values, conservative indexed Y/O, 120 recipes, null samples, legacy dispatch, caching, cancellation and explicit errors passed.');
