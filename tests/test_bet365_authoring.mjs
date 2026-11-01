/** Public market choices must survive the complete authoring/storage pipeline. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {FOOTBALL_MARKET_CATALOG,defaultMarketSelection,marketSelectionChoices,marketLineChoices} from '../app/football-market-catalog.js';
import {playersForTeam,newFootballAlert,normalizeFootballAlert} from '../app/football-alert-builder.js';
import {newSituationsDraft,compileSituationsAlert,situationsDraftFromAlert} from '../app/football-situations.js';
import {validateFootballStrategy} from '../app/football-strategy-engine.js';
import {loadStrategies,saveStrategies,STRATEGY_STORAGE_KEY} from '../app/strategy-store.js';

const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const available=entities.teams.filter(team=>team.currentLeagueIds?.includes('E0')&&playersForTeam(entities,team.id,'E0').length);
const [home,away]=available;
assert.ok(home&&away,'integration requires two real verified squads');
const context={league:'E0',homeTeam:home.id,awayTeam:away.id,teamId:'',playerId:'',period:'full'};
const playerFor=team=>playersForTeam(entities,team==='away'?away.id:home.id,'E0')[0];
const playerMarket=id=>id.startsWith('player_')||['first_goalscorer','last_goalscorer'].includes(id);
const prepared=action=>playerMarket(action.market)?{...action,teamId:action.team==='away'?away.id:home.id,playerId:playerFor(action.team).id}:{...action};
let sequence=0;
const draftFor=selection=>({...newSituationsDraft(),id:`catalog-${++sequence}`,name:`Prueba ${selection.market} ${sequence}`,context:{...context},situations:[{id:'bet-1',role:'bet',selection:prepared(selection),price:null}]});
const storageValues=new Map();
const storage={getItem:key=>storageValues.get(key)||null,setItem:(key,value)=>storageValues.set(key,value)};
const compiled=[];
function compileChoice(selection){
  const rule=compileSituationsAlert(draftFor(selection),entities);
  validateFootballStrategy(rule);
  assert.equal(rule.action.market,selection.market);
  assert.equal(rule.action.period,selection.period);
  assert.equal(rule.action.selection,selection.selection);
  assert.equal(rule.action.oddsSource,'archive');
  assert.equal(rule.action.odds,null,'choosing a market must not supply a price');
  assert.equal(rule.action.probability,null,'choosing a market must not supply a probability');
  assert.deepEqual(rule.conditions,[{field:'selected_odds',operator:'>',value:1}]);
  assert.equal(rule.authoring.situations.length,1);
  assert.equal(rule.authoring.situations[0].price,null);
  if(selection.line!=null)assert.equal(rule.action.line,selection.line);
  if(selection.market==='correct_score')assert.deepEqual([rule.action.homeGoals,rule.action.awayGoals],[selection.homeGoals,selection.awayGoals]);
  if(playerMarket(selection.market))assert.equal(rule.action.playerId,prepared(selection).playerId);
  if(selection.market==='asian_handicap')assert.equal(rule.action.team,selection.selection,'the selected handicap side is authoritative');
  assert.deepEqual(compileSituationsAlert(situationsDraftFromAlert(rule),entities),rule,'editing preserves the full contract');
  compiled.push(rule);
  return rule;
}

assert.equal(FOOTBALL_MARKET_CATALOG.length,28);
for(const definition of FOOTBALL_MARKET_CATALOG){
  const original=defaultMarketSelection(definition.id),rule=compileChoice(original);
  if(['both','match'].includes(definition.teamScope))assert.equal(rule.action.team,'total',definition.id+' defaults to the whole match');
  const choices=marketSelectionChoices(definition.id);
  for(const [selection]of choices){
    const action={...original,selection};
    const lines=marketLineChoices(definition.id,selection);
    if(lines.length){
      for(const line of new Set([lines[0],lines[Math.floor(lines.length/2)],lines.at(-1)]))compileChoice({...action,line});
    }else compileChoice(action);
  }
  for(const period of definition.periods)compileChoice({...original,period});
  if(['team','both'].includes(definition.teamScope)){
    for(const team of ['home','away'])compileChoice({...original,team});
  }
}
const stored=saveStrategies(compiled,entities,storage);
assert.ok(storageValues.has(STRATEGY_STORAGE_KEY));
assert.deepEqual(loadStrategies(storage),stored,'all market choices survive browser storage');
assert.deepEqual(saveStrategies(loadStrategies(storage),entities,storage),stored,'saving again preserves all contracts');
assert.equal(marketSelectionChoices('double_chance').length,3);
assert.equal(marketSelectionChoices('half_time_full_time').length,9);
assert.equal(marketSelectionChoices('result_btts').length,6);

// The side of an Asian handicap cannot retain an earlier home-team value.
const asianAway=compileChoice({...defaultMarketSelection('asian_handicap'),selection:'away',team:'home',line:1.5});
assert.equal(asianAway.action.team,'away');
assert.equal(asianAway.action.teamId,away.id);

for(const [homeGoals,awayGoals]of [[0,0],[0,3],[7,4]])compileChoice({...defaultMarketSelection('correct_score'),homeGoals,awayGoals});
for(const market of ['total_goals','corners','cards','player_goals','player_shots']){
  assert.throws(()=>compileSituationsAlert(draftFor({...defaultMarketSelection(market),selection:'exact',line:1.5}),entities),/entera/);
  assert.throws(()=>compileSituationsAlert(draftFor({...defaultMarketSelection(market),selection:'at_least',line:1.5}),entities),/entera/);
  assert.throws(()=>compileSituationsAlert(draftFor({...defaultMarketSelection(market),line:-.5}),entities),/cantidad|línea/);
}

// Price observations keep their own market identity and never become extra bets.
const goals=defaultMarketSelection('total_goals');
function observed(observation,bet=goals){
  const draft=draftFor(bet);
  draft.situations.unshift({id:'condition-1',role:'condition',selection:observation,price:{operator:'between',min:1.8,max:2}});
  const rule=compileSituationsAlert(draft,entities);
  validateFootballStrategy(rule);
  assert.equal(rule.action.market,bet.market);
  assert.equal(rule.action.odds,null);
  assert.equal(rule.authoring.situations.filter(s=>s.role==='bet').length,1);
  assert.deepEqual(compileSituationsAlert(situationsDraftFromAlert(rule),entities),rule);
  const [loaded]=saveStrategies([rule],entities,storage);
  assert.deepEqual(loadStrategies(storage),[loaded]);
  return rule;
}
assert.equal(observed({...goals}).conditions[0].field,'selected_odds','an identical contract can compare the selected quote');
for(const observation of [{...goals,line:3.5},{...goals,selection:'under'},{...goals,period:'first_half'}]){
  const rule=observed(observation);
  assert.equal(rule.conditions[0].field,'situation_1_odds');
  assert.equal(rule.conditions[0].selection.line,observation.line);
  assert.equal(rule.conditions[0].selection.selection,observation.selection);
  assert.equal(rule.conditions[0].selection.period,observation.period);
}
const teamGoals=defaultMarketSelection('team_goals');
const opposingTeam=observed({...teamGoals,team:'away'},teamGoals);
assert.equal(opposingTeam.conditions[0].field,'situation_1_odds');
assert.equal(opposingTeam.conditions[0].selection.team,'away');
const otherMarket=observed(defaultMarketSelection('btts'));
assert.equal(otherMarket.conditions[0].selection.market,'btts');

// Legacy player goals by half were already supported and must remain editable.
const oldPlayer=normalizeFootballAlert({...newFootballAlert(),id:'legacy-player-half',name:'Jugador primer tiempo',context:{...context},
  action:{...newFootballAlert().action,...prepared({...defaultMarketSelection('player_goals'),period:'first_half'})}},entities);
const migrated=compileSituationsAlert(situationsDraftFromAlert(oldPlayer),entities);
assert.deepEqual(migrated.action,oldPlayer.action);
assert.deepEqual(migrated.conditions,oldPlayer.conditions);
const legacyStored=saveStrategies([migrated],entities,storage);
assert.deepEqual(loadStrategies(storage),legacyStored);
assert.equal(compileSituationsAlert(situationsDraftFromAlert(legacyStored[0]),entities).action.period,'first_half');

console.log(`Bet365 authoring: ${compiled.length} default/selection/line/period contracts, 28 markets, exact storage, independent quotes and legacy player halves passed.`);
