/** One expression survives storage and runs over actual, distinct source quotes. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {FootballData} from '../app/workspace-data.js';
import {loadStrategies,saveStrategies,STRATEGY_STORAGE_KEY,defaultScoreAlert} from '../app/strategy-store.js';
import {UNIFIED_FORMULA_KIND,normalizeUnifiedFormula,formatUnifiedFormula,evaluateUnifiedFormula} from '../app/football-unified-formula.js';

const readJSON=path=>JSON.parse(readFileSync(new URL(`../app/data/${path}`,import.meta.url)));
const readGzip=path=>JSON.parse(gunzipSync(readFileSync(new URL(`../app/data/${path}`,import.meta.url))));
const entities=readJSON('entities.json'),manifest=readJSON('workspace.json');
const archive=readGzip('football-market-history.json.gz');
const eventTable=readGzip(manifest.tables.events.path),offerTable=readGzip(manifest.tables.offers.parts[0].path);
const expand=(table,row)=>Object.fromEntries(table.columns.map((key,index)=>[key,row[index]]));
const sourceEvents=eventTable.rows.slice(0,3).map(row=>{const e=expand(eventTable,row);return {...e,home:e.home_team,away:e.away_team};});
const sourceOffers=offerTable.rows.filter(row=>row[0]<3).map(row=>{
  const raw=expand(offerTable,row),event=sourceEvents[raw.event];
  return {...raw,id:event.id,date:event.date,league:event.league,home:event.home,away:event.away,referenceMean:raw.reference_mean,referenceSd:raw.reference_sd,ownProbability:raw.own_probability,bookmakerMargin:raw.bookmaker_margin};
});
assert.ok(sourceOffers.length);
const route=new FootballData();
route.events=[...sourceEvents,{...sourceEvents[0],id:`market-history:${archive.events[0].id}`}];
route.offers=sourceOffers;
let mainLoads=0,historyLoads=0;
route.ensureOffers=async period=>{assert.equal(period,'all');mainLoads++;};
route.ensureMarketHistory=async()=>{historyLoads++;return {...archive,events:archive.events.slice(0,2)};};
const inputBefore=JSON.stringify({events:route.events,offers:route.offers,archive:archive.events.slice(0,2)});
const universe=await route.strategyUniverse({kind:UNIFIED_FORMULA_KIND});
assert.equal(await route.strategyUniverse({kind:UNIFIED_FORMULA_KIND}),universe,'combined source universe is cached');
assert.equal(mainLoads,1);assert.equal(historyLoads,1);
assert.equal(universe.events.length,route.events.length+2);
assert.equal(new Set(universe.events.map(e=>e.id)).size,universe.events.length,'source identifiers cannot collide');
assert.equal(JSON.stringify({events:route.events,offers:route.offers,archive:archive.events.slice(0,2)}),inputBefore,'source arrays and numbers remain intact');
assert.equal(universe.offers.length,sourceOffers.length+archive.events.slice(0,2).reduce((n,e)=>n+e.marketQuotes.length,0),'every added offer is an actual archived quote');
for(const [index,offer] of sourceOffers.entries())assert.equal(universe.offers[index],offer,'main offer precision is retained');
for(const [sourceIndex,source] of archive.events.slice(0,2).entries()){
  const event=universe.events[route.events.length+sourceIndex];
  assert.equal(event.sourceEventId,source.id);assert.notEqual(event.id,source.id);
  const offers=universe.offers.filter(q=>q.event===route.events.length+sourceIndex);
  assert.equal(offers.length,source.marketQuotes.length);
  for(const [index,quote] of source.marketQuotes.entries()){
    const offer=offers[index];
    for(const [key,value] of Object.entries(quote))assert.deepEqual(offer[key],value,key+' preserves the actual contract');
    assert.equal(offer.eventId,event.id);assert.equal(offer.probability,null);assert.equal(offer.ev,null);
  }
}

const team=entities.teams.find(t=>t.name==='Leicester');assert.ok(team);
const rule={kind:UNIFIED_FORMULA_KIND,version:1,id:'one-formula',name:'Equipo y cuotas o goles',stake:3,expression:{type:'group',id:'root',operator:'O',children:[
  {type:'group',id:'prices',operator:'Y',children:[
    {type:'condition',id:'team',field:'team',operator:'=',value:team.id},
    {type:'condition',id:'price',field:'odds',operator:'>=',value:2},
  ]},
  {type:'condition',id:'goals',field:'market',operator:'=',selection:{market:'btts',period:'full',selection:'yes'}},
]}};
const normalized=normalizeUnifiedFormula(rule,entities);
const player=entities.players.find(p=>p.teamId);assert.ok(player);
const playerRule={...rule,id:'linked-player',name:'Equipo jugador y cuota',expression:{type:'group',id:'player-root',operator:'Y',children:[
  {type:'condition',id:'club',field:'team',operator:'=',value:player.teamId},
  {type:'condition',id:'person',field:'player',operator:'=',playerId:player.id,teamId:player.teamId},
  {type:'group',id:'player-options',operator:'O',children:[
    {type:'condition',id:'player-price',field:'odds',operator:'>=',value:2},
    {type:'condition',id:'player-goals',field:'market',operator:'=',playerRef:'person',selection:{market:'player_goals',period:'full',selection:'at_least',line:1,team:'selected'}},
  ]},
]}};
const values=new Map(),storage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};
const originalDefaults=loadStrategies(storage),legacy=originalDefaults.find(f=>f.kind==='market-ev');
const originalAlert=defaultScoreAlert();
const saved=saveStrategies([normalized,playerRule,originalAlert,legacy],entities,storage);
assert.ok(values.has(STRATEGY_STORAGE_KEY));
assert.deepEqual(loadStrategies(storage),saved,'tree and legacy rules coexist through persistence');
assert.equal(loadStrategies(storage)[0].kind,UNIFIED_FORMULA_KIND);
const playerContract=loadStrategies(storage)[1].expression.children[2].children[1];
assert.equal(playerContract.playerRef,'person');assert.equal(playerContract.selection.playerId,player.id);assert.equal(playerContract.selection.teamId,player.teamId);
assert.deepEqual(saveStrategies(loadStrategies(storage),entities,storage),saved,'repeat saves do not turn the expression into an old alert');
assert.ok(formatUnifiedFormula(saved[0],entities).includes(' O '));
assert.ok(formatUnifiedFormula(saved[0],entities).includes(' Y '));
const copy={...structuredClone(saved[0]),id:'copy',name:'Copia'};
const copyStored=saveStrategies([...saved,copy],entities,storage).at(-1);
assert.deepEqual(copyStored.expression,saved[0].expression,'duplication preserves every branch');

const result=evaluateUnifiedFormula(universe,saved[0],{entities});
assert.ok(result.alerts.length);
assert.equal(new Set(result.alerts.map(r=>`${r.id}|${r.book}`)).size,result.alerts.length,'different selections have distinct result identities');
const expectedOffers=universe.offers.filter(offer=>{
  const event=universe.events[offer.event];
  const teamMatch=[event.home,event.away].some(name=>[team.name,...team.aliases].includes(name));
  return teamMatch&&offer.odds>=2||offer.market==='btts'&&offer.period==='full'&&offer.selection==='yes';
});
assert.equal(result.alerts.length,expectedOffers.length,'market branches select the actual offered contract without filtering by the match result');
assert.ok(result.alerts.some(row=>row.market==='btts'&&row.selection==='yes'&&row.won===false),'a quoted selection remains eligible when it historically lost');
const expectedQuotes=new Set(expectedOffers.map(offer=>JSON.stringify(offer)));
for(const row of result.alerts){
  assert.ok(universe.events[row.event]);
  assert.ok(expectedQuotes.has(JSON.stringify(row.sourceQuote)),'every result is a matching actual quote');
  const source=row.sourceQuote;
  if(source.references?.length){
    assert.equal(row.probability,source.probability,'market filtering retains independent quote probabilities');
    assert.ok(Math.abs(row.ev-(source.probability*source.odds-1))<1e-12);assert.equal(row.expectedProfit,row.ev*3);
  }else {assert.equal(row.probability,null);assert.equal(row.ev,null);assert.equal(row.expectedProfit,null);}
  assert.equal(row.stake,3);
}
assert.equal(result.summary.expectedPriced,expectedOffers.filter(offer=>offer.references?.length).length);
const finalResultOnly={...normalized,id:'home-quote',expression:{type:'group',id:'home-root',operator:'Y',children:[
  {type:'condition',id:'home-market',field:'market',operator:'=',selection:{market:'match_result',period:'full',selection:'home'}},
  {type:'condition',id:'home-price',field:'odds',operator:'>=',value:2},
]}};
const concrete=evaluateUnifiedFormula(universe,finalResultOnly,{entities});
const expectedHome=universe.offers.filter(offer=>offer.odds>=2&&(offer.market==='match_result'&&offer.period==='full'&&offer.selection==='home'||offer.market==null&&offer.side===0));
assert.equal(concrete.alerts.length,expectedHome.length);
assert.ok(concrete.alerts.every(row=>row.market==='match_result'&&row.selection==='home'&&row.odds>=2),'a local-result predicate never selects draw or away offers');
const noPlayerQuotes=evaluateUnifiedFormula(universe,saved[1],{entities});
assert.equal(noPlayerQuotes.alerts.length,0,'a selected player cannot match generic match quotes or a current roster');
const none=evaluateUnifiedFormula({events:universe.events,offers:[]},saved[0],{entities});
assert.equal(none.alerts.length,0,'attached market quotes cannot bypass the selected offer scope');
const onlyBook=sourceOffers[0].book;
const filtered=evaluateUnifiedFormula({events:universe.events,offers:universe.offers.filter(o=>o.book===onlyBook)},saved[0],{entities});
assert.ok(filtered.alerts.every(r=>r.book===onlyBook),'book filters cannot be expanded by attached quotes');
console.log(`Unified formula integration verified: nested Y/O persistence, ${universe.offers.length} exact source quotes, scoped evaluation and preserved legacy rules.`);
