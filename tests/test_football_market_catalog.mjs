import assert from 'node:assert/strict';
import {FOOTBALL_MARKET_CATALOG,FOOTBALL_MARKET_SOURCES,marketDefinition,marketSelectionChoices,marketLineChoices,defaultMarketSelection,footballMarketLabel} from '../app/football-market-catalog.js';

assert.equal(FOOTBALL_MARKET_CATALOG.length,28);
assert.equal(new Set(FOOTBALL_MARKET_CATALOG.map(m=>m.id)).size,28);
assert.equal(marketDefinition('combination'),null,'combining bets must not masquerade as a market');
for(const definition of FOOTBALL_MARKET_CATALOG){
  const action=defaultMarketSelection(definition.id);
  assert.ok(definition.name&&definition.group&&definition.kind);
  assert.ok(definition.periods.includes(action.period));
  if(!['score','player_scorer'].includes(definition.kind))assert.ok(marketSelectionChoices(definition.id).some(([value])=>value===action.selection),definition.id);
  assert.ok(footballMarketLabel(action).length>3,definition.id);
  if(action.line!=null)assert.ok(marketLineChoices(definition.id,action.selection).includes(action.line),definition.id);
}
assert.deepEqual(marketSelectionChoices('double_chance',{home:'Arsenal',away:'Chelsea'}),[['home_draw','Arsenal o empate (1X)'],['draw_away','Empate o Chelsea (X2)'],['home_away','Arsenal o Chelsea (12)']]);
assert.equal(marketSelectionChoices('half_time_full_time').length,9);
assert.equal(marketSelectionChoices('result_btts').length,6);
assert.deepEqual(marketLineChoices('player_goals','at_least'),[1,2,3]);
assert.deepEqual(marketLineChoices('total_goals','over'),[.5,1.5,2.5,3.5,4.5,5.5,6.5,7.5,8.5,9.5]);
assert.ok(marketLineChoices('asian_handicap').every(line=>Number.isInteger(line*2)));
assert.ok(marketLineChoices('handicap_result').every(Number.isInteger));
assert.ok(marketLineChoices('cards','exact').every(Number.isInteger));
assert.ok(marketLineChoices('player_shots','at_least').every(line=>Number.isInteger(line)&&line>=1));
assert.equal(footballMarketLabel({...defaultMarketSelection('player_goals'),playerId:'saka'},{player:'Bukayo Saka'}),'Bukayo Saka · Anotará en cualquier momento');
assert.equal(footballMarketLabel({...defaultMarketSelection('player_goals'),line:2},{player:'Bukayo Saka'}),'Bukayo Saka · 2 o más goles');
assert.equal(footballMarketLabel({...defaultMarketSelection('player_goals'),selection:'exact',line:2},{player:'Bukayo Saka'}),'Bukayo Saka · exactamente 2 goles');
assert.ok(footballMarketLabel({...defaultMarketSelection('total_goals'),period:'first_half'}).includes('Primer tiempo'));
assert.ok(footballMarketLabel({...defaultMarketSelection('asian_handicap'),selection:'away',line:.5},{home:'Arsenal',away:'Chelsea'}).includes('Chelsea · Hándicap asiático +0.5'));
assert.equal(FOOTBALL_MARKET_SOURCES.every(source=>new URL(source.url).hostname.endsWith('bet365.com')),true);
console.log('Football market catalog: 28 actual markets, contextual selections, appropriate lines and readable wager labels passed.');
