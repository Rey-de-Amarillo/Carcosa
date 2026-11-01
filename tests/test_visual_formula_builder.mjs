import assert from 'node:assert/strict';
import {DEFAULT_FORMULA, FORMULA_STORAGE_KEY, loadFormulas, saveFormulas, formulaFromConditions, conditionsFromFormula, inputToValue, valueToInput} from '../app/formula-builder.js';
import {DEFAULT_EXPRESSION,compileFormula} from '../app/formula-engine.js';

assert.equal(formulaFromConditions(DEFAULT_FORMULA),DEFAULT_EXPRESSION);
assert.equal(inputToValue('ev','3'),.03);
assert.equal(inputToValue('probabilidad_min','77'),.77);
assert.equal(inputToValue('cuota','3'),3);
assert.equal(inputToValue('referencias','3'),3);
assert.equal(valueToInput('ev',.03),'3');
assert.equal(valueToInput('probabilidad_min',.77),'77');
assert.equal(valueToInput('cuota',1.95),'1.95');
assert.throws(()=>inputToValue('ev',''),/numérico/);
assert.throws(()=>inputToValue('ev','Infinity'),/numérico/);

const defaultVisual=conditionsFromFormula(DEFAULT_FORMULA);
assert.equal(defaultVisual.editable,true);
assert.deepEqual(defaultVisual.conditions,DEFAULT_FORMULA.conditions);
const selected=compileFormula(formulaFromConditions(defaultVisual));
for(const row of [
  {odds:2,probability:.6,references:3},
  {odds:2,probability:.5,references:3},
  {odds:6,probability:.3,references:6},
  {odds:2,probability:.6,references:2},
])assert.equal(selected.test(row),compileFormula(DEFAULT_EXPRESSION).test(row));

const reversed=conditionsFromFormula({id:'reversed',name:'Cuota',expression:'1.2 <= odds Y 5 >= cuota',stake:1});
assert.equal(reversed.editable,true);
assert.deepEqual(reversed.conditions,[{field:'cuota',operator:'>=',value:1.2},{field:'cuota',operator:'<=',value:5}]);
const alternative=conditionsFromFormula({id:'or',name:'O',expression:'ev > 5% O margen_casa < -0.01',stake:2});
assert.equal(alternative.join,'O');
assert.equal(alternative.conditions[0].value,.05);
assert.equal(alternative.conditions[1].value,-.01);
assert.equal(compileFormula(formulaFromConditions(alternative)).test({odds:2,probability:.4,bookmakerMargin:-.02}),true);

// A complex stored formula must survive a migration without changing its meaning.
const complex={id:'complex',name:'Cálculo propio',expression:'(probabilidad_min * cuota - 1 >= 0.03 Y cuota > 1.2) O referencias > 5',onePerMatch:false,stake:2};
const complexVisual=conditionsFromFormula(complex);
assert.equal(complexVisual.editable,false);
assert.equal(complexVisual.expression,complex.expression);
assert.equal(complexVisual.onePerMatch,false);
assert.equal(complexVisual.stake,2);
assert.ok(complexVisual.editError.length>0);
const mixed=conditionsFromFormula({...complex,expression:'ev >= 0.03 Y (cuota > 2 O referencias > 5)'});
assert.equal(mixed.editable,false);
assert.equal(mixed.expression,'ev >= 0.03 Y (cuota > 2 O referencias > 5)');

const store=new Map();
const storage={getItem:key=>store.get(key)??null,setItem:(key,value)=>store.set(key,value)};
assert.deepEqual(loadFormulas(storage)[0].conditions,DEFAULT_FORMULA.conditions);
saveFormulas([DEFAULT_FORMULA,complex],storage);
assert.ok(store.has(FORMULA_STORAGE_KEY));
const restored=loadFormulas(storage);
assert.equal(restored.length,2);
assert.equal(restored[1].expression,complex.expression);
assert.equal(restored[1].editable,false);
store.set(FORMULA_STORAGE_KEY,'broken json');
assert.equal(loadFormulas(storage)[0].id,DEFAULT_FORMULA.id);
assert.throws(()=>formulaFromConditions({conditions:[]}),/al menos una/);
assert.throws(()=>formulaFromConditions({conditions:[{field:'acierto',operator:'=',value:1}]}),/previo/);
assert.throws(()=>saveFormulas([{...DEFAULT_FORMULA,name:'   '}],storage),/nombre/);
assert.throws(()=>saveFormulas([{...DEFAULT_FORMULA,stake:0}],storage),/importe/);
console.log('Visual formula builder: named conditions, percent units, AST migration and persistence passed.');
