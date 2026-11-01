/** The saved library is editable criteria over concrete quotes, not fabricated signals. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildFootballFormulaLibrary,seedFormulaLibrary,FORMULA_LIBRARY_COUNT} from '../app/football-formula-library.js';
import {normalizeUnifiedFormula,evaluateUnifiedFormula} from '../app/football-unified-formula.js';
import {mountUnifiedFormulaEditor} from '../app/football-formula-editor.js';
import {FOOTBALL_MARKET_CATALOG,defaultMarketSelection,marketDefinition} from '../app/football-market-catalog.js';
import {loadStrategies,saveStrategies,STRATEGY_STORAGE_KEY} from '../app/strategy-store.js';

const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const originalEntities=JSON.stringify(entities);
const library=buildFootballFormulaLibrary(entities);
assert.equal(FORMULA_LIBRARY_COUNT,120);
assert.equal(library.length,120);
assert.equal(JSON.stringify(entities),originalEntities,'building criteria cannot mutate the real catalog');
assert.deepEqual(buildFootballFormulaLibrary(entities),library,'library identifiers and criteria are reproducible');
assert.deepEqual(library.map(rule=>rule.id),Array.from({length:120},(_,i)=>`library-football-${String(i+1).padStart(3,'0')}`));
assert.equal(new Set(library.map(rule=>rule.name.trim().toLocaleLowerCase('es'))).size,120,'all saved formulas have distinct names');

const nodes=node=>[node,...(node.children||[]).flatMap(nodes)];
const leaves=rule=>nodes(rule.expression).filter(node=>node.type==='condition');
const stable=value=>value&&typeof value==='object'?Array.isArray(value)?value.map(stable):Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
function criterion(node){
  if(node.type==='group'){
    const children=node.children.flatMap(child=>child.type==='group'&&child.operator===node.operator?child.children:[child]).map(criterion);
    const unique=[...new Set(children)].sort();return unique.length===1?unique[0]:`${node.operator}(${unique.join(',')})`;
  }
  // Canonical selections already carry the resolved player identity. A node ID
  // or the spelling of its reference must not manufacture another criterion.
  const condition=Object.fromEntries(Object.entries(node).filter(([key])=>!['id','name','playerRef'].includes(key)));
  if(condition.field==='market'){
    condition.selection={...condition.selection};
    const selected=condition.selection,kind=marketDefinition(selected.market)?.kind;
    if(['count','player_count'].includes(kind)&&selected.selection==='at_least'){
      selected.selection='over';selected.line-=.5;
    }
  }
  return JSON.stringify(stable(condition));
}
assert.equal(new Set(library.map(rule=>criterion(rule.expression))).size,120,'criteria remain unique after removing names/IDs and normalizing commutative Y/O groups');

const markets=new Set(),fields=new Set(),operators=new Set();let nested=0,referenced=0;
for(const rule of library){
  assert.equal(rule.kind,'football-formula');assert.equal(rule.version,1);assert.ok(rule.name.trim());assert.ok(rule.stake>0);
  assert.deepEqual(normalizeUnifiedFormula(rule,entities),rule,`${rule.id}: saved format is canonical`);
  const all=nodes(rule.expression),ids=new Set(all.map(node=>node.id));assert.equal(ids.size,all.length,`${rule.id}: every group/condition has its own identity`);
  for(const node of all)if(node.type==='group'){operators.add(node.operator);if(node!==rule.expression)nested++;}
  for(const node of leaves(rule)){
    fields.add(node.field);
    if(node.field==='market')markets.add(node.selection.market);
    if(node.playerRef){
      const source=all.find(other=>other.id===node.playerRef);
      assert.equal(source?.field,'player',`${rule.id}: reference belongs to a player criterion`);
      assert.equal(source.playerId,node.selection.playerId,`${rule.id}: quoted statistic binds that exact player`);referenced++;
    }
  }
}
assert.deepEqual([...markets].sort(),FOOTBALL_MARKET_CATALOG.map(m=>m.id).sort(),'every actual catalog market has saved examples');
for(const field of ['team','home_team','away_team','player','league','odds'])assert.ok(fields.has(field),`${field} participates in real saved formulas`);
assert.deepEqual([...operators].sort(),['O','Y']);assert.ok(nested>0&&referenced>0,'nested alternatives and player references are represented');

// Expand the small expressions into conjunction branches. A quote can only
// carry one positive contract; alternatives must be inside O, never an
// impossible Y between distinct markets, selections, lines or players.
function branches(node){
  if(node.type==='condition')return [[node]];
  if(node.operator==='O')return node.children.flatMap(branches);
  return node.children.reduce((result,child)=>result.flatMap(a=>branches(child).map(b=>[...a,...b])),[[]]);
}
for(const rule of library)for(const branch of branches(rule.expression)){
  const positive=branch.filter(node=>node.field==='market'&&node.operator==='=');
  assert.ok(positive.length,`${rule.id}: each branch identifies a concrete quoted market`);
  assert.equal(new Set(positive.map(criterion)).size,1,`${rule.id}: an AND cannot require alternative contracts`);
  const people=branch.filter(node=>node.field==='player'&&node.operator==='=');
  assert.ok(new Set(people.map(node=>node.playerId)).size<=1,`${rule.id}: a quote cannot belong to two players`);
  for(const person of people)assert.equal(positive[0].selection.playerId,person.playerId,`${rule.id}: player and selected contract agree`);
  for(const field of ['home_team','away_team','league'])assert.ok(new Set(branch.filter(node=>node.field===field&&node.operator==='=').map(node=>node.value)).size<=1,`${rule.id}: ${field} requirements can coexist`);
}

// Exercise the actual editor, including its inactive category drafts. No
// rendered control is modified: opening/editing alone cannot rewrite a tree.
const container={ownerDocument:{},innerHTML:'',querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}};
const editor=mountUnifiedFormulaEditor(container,{entities});
for(const rule of library){
  editor.edit(structuredClone(rule));
  assert.deepEqual(editor.getDefinition(),rule,`${rule.id}: editor roundtrip retains every group, criterion, player reference and price`);
  assert.ok(!container.innerHTML.includes('Elegir condición'),`${rule.id}: saved example opens in category mothers`);
}

// Each branch gets a bounded synthetic quote fixture with real catalog
// identities. A high-priced different market and a low-priced right market
// cannot borrow one another's data to satisfy the criterion.
const byTeam=new Map(entities.teams.map(team=>[team.id,team]));
function fixture(rule,branch,index){
  const bet=branch.find(node=>node.field==='market'&&node.operator==='=').selection;
  const teamRequirements=branch.filter(node=>node.field==='team'&&node.operator==='=').map(node=>node.value);
  let home=branch.find(node=>node.field==='home_team'&&node.operator==='=')?.value;
  let away=branch.find(node=>node.field==='away_team'&&node.operator==='=')?.value;
  for(const team of teamRequirements){if(team===home||team===away)continue;if(!home)home=team;else if(!away)away=team;else assert.fail(`${rule.id}: impossible team requirements`);}
  if(bet.team==='selected'&&bet.teamId&&!['home','away'].some(side=>(side==='home'?home:away)===bet.teamId)){
    if(!home)home=bet.teamId;else if(!away)away=bet.teamId;
  }
  home??=entities.teams.find(team=>team.id!==away).id;
  away??=entities.teams.find(team=>team.id!==home).id;
  assert.notEqual(home,away,`${rule.id}: fixture has two different clubs`);
  const league=branch.find(node=>node.field==='league'&&node.operator==='=')?.value||byTeam.get(home)?.leagueIds?.[0]||entities.leagues[0].id;
  const event={id:`fixture-${rule.id}-${index}`,date:'2025-10-01',league,home:byTeam.get(home).name,away:byTeam.get(away).name,homeTeamId:home,awayTeamId:away,home_score:1,away_score:0,home_ht_score:0,away_ht_score:0,
    home_corners:6,away_corners:4,home_ht_corners:3,away_ht_corners:2,home_cards:2,away_cards:2,home_ht_cards:1,away_ht_cards:1,cardsRules:'bet365',home_shots:12,away_shots:9,home_shots_on_target:5,away_shots_on_target:3,home_offsides:2,away_offsides:1,firstTeamToScore:'home',lastTeamToScore:'home'};
  if(bet.playerId){
    event.playerStats=[{playerId:bet.playerId,teamId:bet.teamId,starter:true,minutes:90,goals:1,assists:1,shots:3,shotsOnTarget:2}];
    event.firstGoalscorer=bet.playerId;event.lastGoalscorer=bet.playerId;
  }
  const priceConditions=branch.filter(node=>node.field==='odds');
  assert.ok(priceConditions.length,`${rule.id}: branch filters the actual quote price`);
  let min=1.01,max=100;
  for(const node of priceConditions){
    assert.equal(node.operator,'between',`${rule.id}: library price fixture understands the declared range`);
    min=Math.max(min,node.min);max=Math.min(max,node.max);
  }
  assert.ok(max>=min,`${rule.id}: price intervals have a real intersection`);
  const quote={...bet,event:0,eventId:event.id,book:'LIBRARY_TEST',odds:(min+max)/2,source:'bounded-library-fixture'};
  const wrongPrice={...quote,odds:min>1.02?min-.01:max+.1};
  const usedMarkets=new Set(leaves(rule).filter(node=>node.field==='market'&&node.operator==='=').map(node=>node.selection.market));
  const unrelated=FOOTBALL_MARKET_CATALOG.find(definition=>!usedMarkets.has(definition.id)&&definition.group!=='Jugadores');
  assert.ok(unrelated,`${rule.id}: independent distractor contract exists`);
  const wrongContract={...defaultMarketSelection(unrelated.id),event:0,eventId:event.id,book:quote.book,odds:quote.odds,source:quote.source};
  return {event,quote,wrongPrice,wrongContract};
}
let evaluated=0;
for(const rule of library)for(const [index,branch] of branches(rule.expression).entries()){
  const {event,quote,wrongPrice,wrongContract}=fixture(rule,branch,index);
  for(const quotes of [[wrongContract,wrongPrice,quote],[quote,wrongPrice,wrongContract]]){
    const result=evaluateUnifiedFormula({events:[event],offers:quotes},rule,{entities});
    assert.equal(result.alerts.length,1,`${rule.id} branch${index}: only its own contract and price pass`);
    assert.deepEqual(result.alerts[0].sourceQuote,quote,`${rule.id}: source price and selection stay together`);
    assert.equal(result.alerts[0].odds,quote.odds,`${rule.id}: no manufactured or borrowed odds`);
    assert.equal(result.alerts[0].ev,null,`${rule.id}: fixture without a probability cannot invent EV`);
  }
  const invalid=evaluateUnifiedFormula({events:[event],offers:[wrongContract,wrongPrice]},rule,{entities});
  assert.equal(invalid.alerts.length,0,`${rule.id}: different-market price cannot satisfy the right-market price condition`);
  const pending={...event,home_score:null,away_score:null,home_ht_score:null,away_ht_score:null,playerStats:undefined};
  assert.equal(evaluateUnifiedFormula({events:[pending],offers:[quote]},rule,{entities}).alerts.length,1,`${rule.id}: acceptance does not require a winning or known result`);
  evaluated++;
}
assert.equal(JSON.stringify(entities),originalEntities,'evaluation and editor cannot mutate catalog identities');

// Seed into isolated storage: repeated starts keep user formulas and every
// existing library edit, including edits saved before a reload.
const memory=()=>{const values=new Map();return {values,storage:{getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value))}};};
const fresh=memory(),first=seedFormulaLibrary([],entities,fresh.storage);
assert.deepEqual(first,library);assert.deepEqual(JSON.parse(fresh.values.get(STRATEGY_STORAGE_KEY)),library,'first seed persists all 120 canonical definitions');
assert.deepEqual(seedFormulaLibrary(first,entities,fresh.storage),first,'repeat seed does not add duplicates');
const edited={...structuredClone(library[10]),name:'Mi edición de biblioteca',stake:7};
leaves(edited).find(node=>node.field==='odds').min+=.05;
const user={...structuredClone(library[0]),id:'my-own-football-formula',name:'Mi fórmula privada',stake:3};
const legacy={kind:'market-ev',id:'my-old-formula',name:'Mi cálculo anterior',expression:'ev > 0.03 Y cuota > 1.2',stake:2};
const existing=[user,edited,legacy],existingBefore=JSON.stringify(existing),saved=memory();
const merged=seedFormulaLibrary(existing,entities,saved.storage);
assert.equal(JSON.stringify(existing),existingBefore,'seeding cannot mutate caller-owned saved definitions');
assert.equal(merged.length,122);assert.equal(new Set(merged.map(rule=>rule.id)).size,merged.length,'existing library entry is never duplicated');
assert.deepEqual(merged.slice(0,3),existing,'original order, private rules and edited library definition remain intact');
assert.deepEqual(loadStrategies(saved.storage),merged,'all seeded and private formulas survive reload together');
const userEdit=merged.map(rule=>{
  if(rule.id!==library[119].id)return rule;
  const changed={...structuredClone(rule),name:'Última fórmula editada',stake:9};
  leaves(changed).find(node=>node.field==='odds').min+=.05;
  return changed;
});
const persisted=saveStrategies(userEdit,entities,saved.storage),reloaded=loadStrategies(saved.storage),reseeded=seedFormulaLibrary(reloaded,entities,saved.storage);
assert.deepEqual(reseeded,persisted,'a reload cannot overwrite a saved library edit');
assert.equal(reseeded.find(rule=>rule.id===library[119].id).stake,9);
assert.equal(reseeded.find(rule=>rule.id===edited.id).name,edited.name);
assert.deepEqual(JSON.parse(saved.values.get(STRATEGY_STORAGE_KEY)),persisted,'idempotent seeding preserves persisted edits');
console.log(`Football formula library: 120 unique canonical/editable definitions, all 28 markets, ${evaluated} satisfiable branches, same-contract price evaluation, scoped player references and preserved user edits passed.`);
