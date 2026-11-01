/** Same-house payoff recipes and reversible, exact-fingerprint seed migration. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PRICE_FORMULA_KIND,normalizePriceFormula} from '../app/football-price-engine.js';
import {buildPriceFormulaLibrary,buildReferencePriceFormulaLibrary,seedPriceFormulaLibrary,isPaymentFormula,PRICE_LIBRARY_COUNT,PRICE_LIBRARY_BACKUP_KEY} from '../app/football-price-library.js';
import {buildFootballFormulaLibrary} from '../app/football-formula-library.js';
import {loadStrategies,defaultScoreAlert,STRATEGY_STORAGE_KEY} from '../app/strategy-store.js';
import {DEFAULT_FORMULA,conditionsFromFormula} from '../app/formula-builder.js';
const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const walk=node=>[node,...(node.children||[]).flatMap(walk)];
const leaves=rule=>walk(rule.expression).filter(node=>node.type==='condition');
const criteria=rule=>JSON.stringify({stake:rule.stake,mode:rule.mode,structure:rule.structure,bookPolicy:rule.bookPolicy,costRate:rule.costRate,oddsDrop:rule.oddsDrop,conditions:leaves(rule).map(({field,operator,value,min,max})=>({field,operator,value,min,max}))});
const library=buildPriceFormulaLibrary();
assert.equal(PRICE_LIBRARY_COUNT,120);assert.equal(library.length,120);
assert.deepEqual(buildPriceFormulaLibrary(),library,'factory definitions are deterministic');
assert.equal(new Set(library.map(rule=>rule.id)).size,120);assert.equal(new Set(library.map(rule=>rule.name)).size,120);assert.equal(new Set(library.map(criteria)).size,120,'IDs and names cannot manufacture mathematical variation');
assert.deepEqual(library.map(rule=>rule.id),Array.from({length:120},(_,i)=>`library-payment-${String(i+1).padStart(3,'0')}`));
const floors=[.001,.0025,.005,.01,.02],stress=[[0,0],[.0025,0],[.005,0],[.01,0],[0,.0025],[0,.005],[0,.01],[.005,.005]];
for(const structure of ['two_outcomes','three_outcomes','double_chance'])for(const floor of floors)for(const [costRate,oddsDrop] of stress){
 const matches=library.filter(rule=>rule.structure===structure&&rule.costRate===costRate&&rule.oddsDrop===oddsDrop&&leaves(rule).some(node=>node.field==='min_return'&&node.value===floor));
 assert.equal(matches.length,1,'every payout structure, floor and stress case occurs exactly once');
}
for(const rule of library){
 assert.equal(rule.kind,PRICE_FORMULA_KIND);assert.equal(rule.mode,'coverage');assert.equal(rule.bookPolicy,'same_book');assert.equal(rule.stake,100);assert.equal(rule.onePerMatch,true);
 assert.deepEqual(normalizePriceFormula(rule),rule);assert.equal(isPaymentFormula(rule),true);
 assert.deepEqual(leaves(rule).map(node=>node.field),['min_return','min_profit']);
 assert.ok(leaves(rule).some(node=>node.field==='min_profit'&&node.operator==='>'&&node.value===0));
 assert.equal(Object.hasOwn(rule,'context'),false);
}
const validCustom={...structuredClone(library[0]),id:'custom-payment',expression:{type:'group',id:'custom-root',operator:'O',children:[{type:'condition',id:'inverse',field:'inverse_sum',operator:'<',value:1},{type:'group',id:'limits',operator:'Y',children:[{type:'condition',id:'payout',field:'min_payout',operator:'>',value:100},{type:'condition',id:'floor',field:'min_return',operator:'>',value:0}]}]}};
assert.equal(isPaymentFormula(validCustom),true,'all four payoff criteria and mixed Y/O remain eligible');
for(const invalid of [{...library[0],mode:'value'},{...library[0],bookPolicy:'cross_book'},{...library[0],kind:'football-formula'},{...library[0],expression:{type:'group',id:'root',operator:'Y',children:[{type:'condition',id:'refs',field:'references',operator:'>=',value:3}]}},{...library[0],expression:{type:'group',id:'root',operator:'Y',children:[]}},null])assert.equal(isPaymentFormula(invalid),false);

const reference=buildReferencePriceFormulaLibrary(),football=buildFootballFormulaLibrary(entities);
assert.equal(reference.length,120);assert.equal(reference.filter(rule=>rule.mode==='value').length,72);assert.equal(reference.filter(rule=>rule.mode==='coverage').length,48,'old factory remains exact for migration fingerprints');
const editedReference={...structuredClone(reference[0]),name:'Mi regla por referencia'};
const editedFootball={...structuredClone(football[0]),stake:4};
const customReference={...structuredClone(reference[1]),id:'custom-reference',name:'Mi comparación guardada'};
const customEV={...conditionsFromFormula(DEFAULT_FORMULA),kind:'market-ev',id:'my-ev',name:'Mi EV'};
const customAlert={...defaultScoreAlert(),id:'my-alert',name:'Mi alerta'};
const editedPayment={...structuredClone(library[0]),name:'Mi cobertura',costRate:.002};
const defaults=loadStrategies({getItem:()=>null});
const originalEV=defaults.find(rule=>rule.kind==='market-ev');assert.ok(originalEV);
const existing=[...football.slice(1),...reference.slice(1),defaultScoreAlert(),originalEV,editedReference,editedFootball,customReference,customEV,customAlert,editedPayment,validCustom];
const before=JSON.stringify(existing),values=new Map([['workraken-football-strategies-price-backup-v1','legacy-backup']]);
const storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value))};
const merged=seedPriceFormulaLibrary(existing,entities,storage);
assert.equal(JSON.stringify(existing),before,'migration never mutates saved definitions');
assert.equal(merged.length,126,'120 payment seeds include one edited seed and preserve six other user rules');
for(const rule of [editedReference,editedFootball,customReference,customEV,customAlert,editedPayment,validCustom])assert.deepEqual(merged.find(item=>item.id===rule.id),rule,'edited or custom rules preserve their original meaning');
assert.equal(merged.filter(rule=>rule.id.startsWith('library-payment-')).length,120);
assert.equal(merged.some(rule=>rule.id===reference[1].id),false);assert.equal(merged.some(rule=>rule.id===football[1].id),false);assert.equal(merged.some(rule=>rule.id===originalEV.id),false);assert.equal(merged.some(rule=>rule.id==='odds-to-score-2-1'),false);
assert.deepEqual(JSON.parse(values.get(PRICE_LIBRARY_BACKUP_KEY)),existing,'backup contains the complete pre-migration collection');
assert.equal(PRICE_LIBRARY_BACKUP_KEY,'workraken-football-strategies-price-backup-v2');assert.equal(values.get('workraken-football-strategies-price-backup-v1'),'legacy-backup','v1 backup is untouched');
assert.deepEqual(JSON.parse(values.get(STRATEGY_STORAGE_KEY)),merged);assert.deepEqual(loadStrategies(storage),merged);
const backup=values.get(PRICE_LIBRARY_BACKUP_KEY),repeat=seedPriceFormulaLibrary(merged,entities,storage);
assert.strictEqual(repeat,merged,'repeat migration is a no-op');assert.equal(values.get(PRICE_LIBRARY_BACKUP_KEY),backup);
seedPriceFormulaLibrary([...merged,reference[1]],entities,storage);assert.equal(values.get(PRICE_LIBRARY_BACKUP_KEY),backup,'later removal never overwrites the first v2 snapshot');

// Default variants are recognized by exact known content, never only by ID.
for(const original of [DEFAULT_FORMULA,conditionsFromFormula(DEFAULT_FORMULA),{...DEFAULT_FORMULA,kind:'market-ev'},{...conditionsFromFormula(DEFAULT_FORMULA),kind:'market-ev'}]){
 const result=seedPriceFormulaLibrary([original],entities);assert.equal(result.some(rule=>rule.id==='conservative-3'),false);
 const changed={...structuredClone(original),stake:2};assert.deepEqual(seedPriceFormulaLibrary([changed],entities).find(rule=>rule.id==='conservative-3'),changed,'edited original EV remains archived intact');
}
let storeWasWritten=false;
const failedBackup={getItem:()=>null,setItem:key=>{if(key===PRICE_LIBRARY_BACKUP_KEY)throw new Error('Backup unavailable');storeWasWritten=true;}};
assert.throws(()=>seedPriceFormulaLibrary([reference[0]],entities,failedBackup),/Backup unavailable/);assert.equal(storeWasWritten,false,'failed backup cannot persist removals');
console.log('Payment library: 120 distinct same-house payoff recipes, pure eligibility, exact legacy migration, preserved edits and immutable backup passed.');
