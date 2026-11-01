import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {newFootballAlert,normalizeFootballAlert,playersForTeam} from '../app/football-alert-builder.js';
import {newSituationsDraft,newSituationSelection,situationsDraftFromAlert,synchronizeSituationResults,compileSituationsAlert,canonicalSavedAlert} from '../app/football-situations.js';
import {evaluateFootballStrategy,validateFootballStrategy} from '../app/football-strategy-engine.js';
import {loadStrategies,saveStrategies,STRATEGY_STORAGE_KEY} from '../app/strategy-store.js';
import {FootballData} from '../app/workspace-data.js';

const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const original=normalizeFootballAlert({...newFootballAlert(),id:'score',name:'Precios opuestos y marcador'},entities);
const migrated=situationsDraftFromAlert(original);
assert.deepEqual(migrated.situations.map(s=>s.role),['condition','condition','bet']);
const saved=compileSituationsAlert(migrated,entities);
assert.deepEqual(saved.conditions,original.conditions);
assert.deepEqual(saved.action,original.action);
assert.equal(saved.action.market,'correct_score');
assert.equal(saved.authoring.version,3);
assert.equal(saved.authoring.situations.filter(s=>s.role==='bet').length,1);
assert.deepEqual(canonicalSavedAlert(saved,entities),saved);
assert.deepEqual(canonicalSavedAlert(original,entities),original);

const reversed=synchronizeSituationResults({...migrated,result:'away'});
assert.deepEqual(reversed.situations.slice(0,2).map(s=>s.selection.selection),['away','home']);
assert.deepEqual(reversed.situations[2],migrated.situations[2]);
const drawn=synchronizeSituationResults({...migrated,result:'draw'});
assert.deepEqual(drawn.situations.slice(0,2).map(s=>s.selection.selection),['draw','draw']);
assert.deepEqual(drawn.situations[2],migrated.situations[2]);
const thirdComparison={...migrated.situations[0],id:'comparison-extra',selection:{...migrated.situations[0].selection,selection:'away'}};
const threeCompared=synchronizeSituationResults({...migrated,result:'draw',situations:[...migrated.situations,thirdComparison]});
assert.equal(threeCompared.situations.at(-1).selection.selection,'away');

const empty=newSituationsDraft();
assert.equal(empty.situations.length,1,'a new formula starts with one visible bet');
assert.equal(empty.situations[0].role,'bet');
assert.equal(empty.situations[0].price,null,'price filters are optional');
assert.equal(empty.situations[0].selection.market,'match_result');
assert.equal(empty.situations[0].selection.selection,'home');
const simple=compileSituationsAlert({...empty,name:'Gana el local'},entities);
assert.equal(simple.action.market,'match_result');
assert.equal(simple.action.selection,'home');
assert.deepEqual(simple.conditions,[{field:'selected_odds',operator:'>',value:1}]);
assert.throws(()=>compileSituationsAlert({...empty,name:''},entities),/nombre/);
assert.throws(()=>compileSituationsAlert({...migrated,situations:migrated.situations.filter(s=>s.role==='condition')},entities),/para apostar/);
assert.throws(()=>compileSituationsAlert({...migrated,situations:migrated.situations.map((s,i)=>i===0?{...s,price:null}:s)},entities),/cuota de la situación 1/);

// An independent goal price remains a comparison; it does not become a leg.
const goalComparison={id:'goal-price',role:'condition',selection:{...newSituationSelection('total_goals'),selection:'over',line:2.5},price:{operator:'around',value:1.9,margin:.1}};
const independent=compileSituationsAlert({...migrated,situations:[goalComparison,migrated.situations[2]]},entities);
assert.equal(independent.action.market,'correct_score');
assert.equal(independent.conditions[0].field,'situation_1_odds');
assert.equal(independent.conditions[0].selection.market,'total_goals');
assert.deepEqual([independent.conditions[0].min,independent.conditions[0].max],[1.8,2]);
assert.deepEqual(canonicalSavedAlert(independent,entities),independent);
const importedIndependent=situationsDraftFromAlert({...independent,authoring:undefined});
assert.equal(importedIndependent.situations[0].selection.market,'total_goals');
assert.deepEqual(compileSituationsAlert(importedIndependent,entities).conditions,independent.conditions);
assert.deepEqual(compileSituationsAlert(importedIndependent,entities).action,independent.action);

// With no explicit price filter, only a valid archived price is required.
const unfiltered=compileSituationsAlert({...migrated,situations:[migrated.situations[2]]},entities);
assert.deepEqual(unfiltered.conditions,[{field:'selected_odds',operator:'>',value:1}]);
assert.deepEqual(unfiltered.action,original.action);
assert.deepEqual(canonicalSavedAlert(unfiltered,entities),unfiltered);

// Two explicitly chosen bets need their joint archived price. No multiplication.
const combination=compileSituationsAlert({...migrated,situations:[migrated.situations[0],
  {id:'bet-home',role:'bet',selection:{...newSituationSelection('team_goals'),selection:'at_least',team:'home',line:2},price:{operator:'between',min:1.8,max:2}},
  {id:'bet-away',role:'bet',selection:{...newSituationSelection('team_goals'),selection:'at_least',team:'away',line:1},price:{operator:'between',min:3.8,max:4.2}},
]},entities);
assert.equal(combination.action.market,'combination');
assert.deepEqual(combination.conditions.map(c=>c.field),['home_odds','leg_1_odds','leg_2_odds']);
assert.equal(combination.action.oddsSource,'archive');assert.equal(combination.action.odds,null);assert.equal(combination.action.probability,null);
assert.equal(combination.action.legs.length,2);

const home=entities.teams.find(t=>t.currentLeagueIds?.includes('E0')&&playersForTeam(entities,t.id,'E0').length);
const away=entities.teams.find(t=>t.id!==home.id&&t.currentLeagueIds?.includes('E0')&&playersForTeam(entities,t.id,'E0').length);
const player=playersForTeam(entities,home.id,'E0')[0],wrongPlayer=playersForTeam(entities,away.id,'E0')[0];
const playerDraft={...migrated,context:{...migrated.context,league:'E0',homeTeam:home.id,awayTeam:away.id},situations:[
  {id:'scorer-price',role:'condition',selection:{...newSituationSelection('player_goals'),selection:'at_least',team:'home',playerId:player.id,line:1},price:{operator:'>=',value:4}},
  migrated.situations[2],
]};
assert.equal(compileSituationsAlert(playerDraft,entities).conditions[0].selection.playerId,player.id);
assert.throws(()=>compileSituationsAlert({...playerDraft,situations:[{...playerDraft.situations[0],selection:{...playerDraft.situations[0].selection,playerId:wrongPlayer.id}},playerDraft.situations[1]]},entities),/jugador/);

// The legacy saved action and price filters produce exactly the same alerts.
const events=[{id:'event',date:'2026-01-01',home:'Local',away:'Visitante',home_score:2,away_score:1,marketQuotes:[{market:'correct_score',period:'full',selection:'2-1',odds:8,book:'A'}]}];
const offers=[1.9,3.3,4].map((odds,side)=>({event:0,book:'A',odds,side}));
assert.deepEqual(evaluateFootballStrategy({events,offers},saved).alerts,evaluateFootballStrategy({events,offers},original).alerts);
validateFootballStrategy(saved);

// Saving, loading, editing and saving again cannot discard situation metadata.
const storedValues=new Map(),storage={getItem:key=>storedValues.get(key)||null,setItem:(key,value)=>storedValues.set(key,value)};
const stored=saveStrategies([saved,{...independent,id:'independent'},{...combination,id:'combination'}],entities,storage);
assert.ok(storedValues.has(STRATEGY_STORAGE_KEY));
assert.deepEqual(loadStrategies(storage),stored);
for(const loaded of loadStrategies(storage)){
  const edited=situationsDraftFromAlert(loaded);
  assert.deepEqual(compileSituationsAlert(edited,entities),loaded);
  edited.name+=' · editada';
  const editedSaved=compileSituationsAlert(edited,entities);
  assert.deepEqual(editedSaved.conditions,loaded.conditions);
  assert.deepEqual(editedSaved.action,loaded.action);
  assert.deepEqual(editedSaved.authoring,loaded.authoring);
}
assert.deepEqual(saveStrategies(loadStrategies(storage),entities,storage),stored);

// Authoring metadata cannot override the derived contract or supply hidden quotes.
const tampered=structuredClone(migrated);
tampered.valuation={...tampered.valuation,market:'match_result',selection:'away',legs:[{market:'btts',selection:'no'}],references:[{odds:1000}]};
tampered.situations[0].price={...tampered.situations[0].price,field:'away_odds',selection:{market:'correct_score',homeGoals:9,awayGoals:9},odds:9999,probability:1};
tampered.situations[2].selection={...tampered.situations[2].selection,odds:9999,probability:1,references:[{odds:9999}],quote:{odds:9999}};
const sanitized=compileSituationsAlert(tampered,entities);
assert.deepEqual(sanitized.conditions,saved.conditions);
assert.deepEqual(sanitized.action,saved.action);
assert.equal(JSON.stringify(sanitized).includes('9999'),false);
const contaminatedLegacy={...migrated,legacyConditions:[{field:'ev',operator:'>=',value:.03,quote:{odds:9999}}]};
assert.equal(JSON.stringify(compileSituationsAlert(contaminatedLegacy,entities)).includes('9999'),false);

// The complete real Singapore Pools ledger remains exactly unchanged after
// migration and storage, including the price sources and prior-only estimates.
const archive=JSON.parse(gunzipSync(readFileSync(new URL('../app/data/football-market-history.json.gz',import.meta.url))));
const legacyLedger=evaluateFootballStrategy(archive,original,{entities});
const migratedLedger=evaluateFootballStrategy(archive,loadStrategies(storage)[0],{entities});
assert.equal(legacyLedger.alerts.length,52);assert.equal(legacyLedger.summary.settled,51);assert.equal(legacyLedger.summary.expectedPriced,21);
assert.deepEqual(migratedLedger,legacyLedger);
const routing=new FootballData();
assert.equal(routing.usesGoalArchive(independent),true);
assert.equal(routing.usesGoalArchive({...independent,action:{...independent.action,oddsSource:'manual',odds:8}}),true);
for(const market of ['double_chance','draw_no_bet','handicap_result','asian_handicap',
  'half_time_full_time','odd_even','team_to_score','clean_sheet','win_to_nil','result_btts']){
  const action={market,period:'full'};
  assert.equal(routing.usesGoalArchive({action,conditions:[]}),false,market+' keeps the larger match universe');
  assert.equal(routing.usesGoalArchive({action,conditions:independent.conditions}),true,market+' can observe an archived goals price');
}
for(const market of ['shots','shots_on_target','offsides','cards','player_shots','first_goalscorer','first_team_to_score']){
  assert.equal(routing.usesGoalArchive({action:{market,period:'full'},conditions:independent.conditions}),false,market+' needs its own statistics');
}
assert.equal(routing.usesGoalArchive({action:{market:'combination',legs:[{market:'double_chance'},{market:'btts'}]},conditions:[]}),false,'new combinations do not claim archived joint prices');
assert.equal(routing.usesGoalArchive({action:{market:'combination',legs:[{market:'double_chance'},{market:'btts'}]},conditions:independent.conditions}),true,'score-only combinations may observe archived goals conditions');
console.log('Situation authoring: storage/edit round trips, 52 exact real-ledger alerts, explicit bets, independent quotes, metadata sanitization and player membership passed.');
