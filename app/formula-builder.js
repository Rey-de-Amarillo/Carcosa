/** Visual formula authoring. Data values stay decimal; probability inputs show %. */
import {FIELD_DICTIONARY, DEFAULT_EXPRESSION, compileFormula} from './formula-engine.js';

export const FORMULA_STORAGE_KEY = 'workraken-football-formulas-v1';
const availableFields = FIELD_DICTIONARY.filter(field => field.preMatch !== false);
const fields = new Map(availableFields.map(field => [field.name, field]));
const operators = ['>=', '>', '<=', '<', '=', '!='];
const reverseOperator = {'>=':'<=','>':'<','<=':'>=','<':'>','=':'=','!=':'!='};
const clone = value => JSON.parse(JSON.stringify(value));
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

export const DEFAULT_FORMULA = Object.freeze({
  id:'conservative-3', name:'EV conservador ≥ 3%', expression:DEFAULT_EXPRESSION,
  onePerMatch:true, stake:1, join:'Y',
  conditions:Object.freeze([
    Object.freeze({field:'ev',operator:'>=',value:.03}),
    Object.freeze({field:'referencias',operator:'>=',value:3}),
    Object.freeze({field:'cuota',operator:'>=',value:1.2}),
    Object.freeze({field:'cuota',operator:'<=',value:5}),
  ]),
});

export function isPercentageField(name) {
  return ['probability','percentage'].includes(fields.get(name)?.unit);
}
export function inputToValue(field, value) {
  if (String(value).trim() === '' || !Number.isFinite(Number(value))) throw new Error('Ingresá un valor numérico.');
  return isPercentageField(field) ? Number(value)/100 : Number(value);
}
export function valueToInput(field, value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '';
  // Converting for display must not turn 3% into 3.0000000000000004.
  return String(Number((isPercentageField(field) ? value*100 : value).toPrecision(14)));
}

function normalizeCondition(condition) {
  if (!condition || !fields.has(condition.field)) throw new Error('Elegí un dato previo al partido.');
  if (!operators.includes(condition.operator)) throw new Error('Elegí una comparación válida.');
  if (typeof condition.value !== 'number' || !Number.isFinite(condition.value)) throw new Error('Ingresá un valor numérico para cada condición.');
  return {field:condition.field,operator:condition.operator,value:condition.value};
}

/** Return an expression; validation is shared with the production calculation engine. */
export function formulaFromConditions(definition) {
  if (!Array.isArray(definition.conditions) || !definition.conditions.length) throw new Error('Agregá al menos una condición.');
  if (definition.conditions.length > 40) throw new Error('Podés usar hasta 40 condiciones por fórmula.');
  const join = definition.join === 'O' ? ' O ' : ' Y ';
  const expression = definition.conditions.map(normalizeCondition).map(condition => `${condition.field} ${condition.operator} ${condition.value}`).join(join);
  compileFormula(expression);
  return expression;
}

function numericLiteral(node) {
  if (node?.kind === 'number') return node.value;
  if (node?.kind === 'unary' && ['-','+'].includes(node.op)) {
    const value = numericLiteral(node.arg);
    return value == null ? null : node.op === '-' ? -value : value;
  }
  return null;
}

/** Legacy expressions are converted only when the visual rows preserve their meaning. */
export function conditionsFromFormula(legacy) {
  const result = {...clone(legacy), onePerMatch:legacy.onePerMatch!==false, stake:Number(legacy.stake)||1};
  try {
    // Saved visual formulas carry expression and rows. Parse the expression as source
    // of truth, so a manually changed legacy expression cannot silently be replaced.
    const expression = legacy.expression || formulaFromConditions(legacy);
    const compiled = compileFormula(expression);
    let join = null;
    const conditions = [];
    function walk(node) {
      if (node.kind === 'binary' && ['and','or'].includes(node.op)) {
        if (join && join !== node.op) throw new Error('La fórmula combina grupos Y/O.');
        join = node.op;
        walk(node.left);walk(node.right);return;
      }
      if (node.kind !== 'binary' || !operators.includes(node.op)) throw new Error('La fórmula contiene un cálculo compuesto.');
      const rightNumber = numericLiteral(node.right), leftNumber = numericLiteral(node.left);
      if (node.left.kind === 'field' && rightNumber != null) conditions.push(normalizeCondition({field:node.left.name,operator:node.op,value:rightNumber}));
      else if (node.right.kind === 'field' && leftNumber != null) conditions.push(normalizeCondition({field:node.right.name,operator:reverseOperator[node.op],value:leftNumber}));
      else throw new Error('La fórmula compara cálculos compuestos.');
    }
    walk(compiled.ast);
    result.expression = expression;
    result.conditions = conditions;
    result.join = join === 'or' ? 'O' : 'Y';
    result.editable = true;
    delete result.editError;
  } catch (error) {
    result.expression = String(legacy.expression || '');
    result.conditions = [];
    result.join = 'Y';
    result.editable = false;
    result.editError = 'Esta fórmula guardada contiene grupos o cálculos compuestos. Se conserva intacta; duplicala como una fórmula nueva para usar el editor visual.';
  }
  return result;
}

export function loadFormulas(storage = globalThis.localStorage) {
  try {
    const saved = JSON.parse(storage?.getItem(FORMULA_STORAGE_KEY) || 'null');
    if (Array.isArray(saved)) {
      const valid = saved.filter(item => item && typeof item.id==='string' && typeof item.name==='string' && typeof item.expression==='string' && Number(item.stake)>0);
      if (valid.length) return valid.map(conditionsFromFormula);
    }
  } catch { /* An unavailable storage does not prevent opening the built-in rule. */ }
  return [conditionsFromFormula(DEFAULT_FORMULA)];
}

export function saveFormulas(list, storage = globalThis.localStorage) {
  if (!Array.isArray(list)) throw new Error('La lista de fórmulas no es válida.');
  const result = list.map(item => {
    if (!item || !item.id || !String(item.name||'').trim()) throw new Error('La fórmula necesita un nombre.');
    if (!(Number(item.stake)>0) || !Number.isFinite(Number(item.stake))) throw new Error('El importe debe ser mayor que cero.');
    compileFormula(item.expression);
    return conditionsFromFormula({...item,name:String(item.name).trim(),stake:Number(item.stake)});
  });
  if (!storage?.setItem) throw new Error('No se pudo guardar en este navegador.');
  storage.setItem(FORMULA_STORAGE_KEY,JSON.stringify(result));
  return result;
}

let instanceId = 0;

/**
 * mountFormulaBuilder(container,{onSave,onCancel}) -> {edit,reset,getDefinition}.
 * onSave receives a validated definition. Persistence and list selection belong
 * to the host; a new definition has id:null until the host assigns its identity.
 */
export function mountFormulaBuilder(container, {onSave=()=>{},onCancel=()=>{}} = {}) {
  if (!container?.ownerDocument) throw new Error('El editor necesita un contenedor.');
  const prefix = `formula-builder-${++instanceId}`;
  let state, conditionKeys=[], nextKey=0, editing=false, saving=false;
  const q = selector => container.querySelector(selector);
  function readCondition(row, preserveBlank=false) {
    const field=row.querySelector('[data-field]').value;
    const text=row.querySelector('[data-value]').value;
    const original=state.conditions[conditionKeys.indexOf(Number(row.dataset.condition))];
    // Preserve a legacy full-precision threshold when its displayed value was not
    // edited. Percent formatting must never move a selection boundary by itself.
    const value=preserveBlank && text.trim()==='' ? null : original?.field===field && text===valueToInput(field,original.value) ? original.value : inputToValue(field,text);
    return {field,operator:row.querySelector('[data-operator]').value,value};
  }
  const read = () => {
    if (state.editable === false) throw new Error(state.editError);
    const name=q('[data-name]').value.trim();
    if (!name) throw new Error('Poné un nombre a la fórmula.');
    const stake=Number(q('[data-stake]').value);
    if (!(stake>0) || !Number.isFinite(stake)) throw new Error('El importe debe ser mayor que cero.');
    const conditions = [...container.querySelectorAll('[data-condition]')].map(row=>readCondition(row));
    const definition={id:state.id||null,name,stake,onePerMatch:q('[data-selection]').value==='one',join:q('[data-join]').value,conditions};
    return {...definition,expression:formulaFromConditions(definition)};
  };
  function showError(error) { const el=q('[data-error]');el.textContent=error?.message||String(error||'');el.hidden=!el.textContent; }
  function preview() {
    if(state.editable===false){q('[data-preview]').textContent=state.expression;return;}
    try {
      const conditions=[...container.querySelectorAll('[data-condition]')].map(row=>readCondition(row));
      q('[data-preview]').textContent=conditions.length?formulaFromConditions({conditions,join:q('[data-join]').value}):'';
    }catch {q('[data-preview]').textContent='';}
  }
  const options = selected => availableFields.map(field=>`<option value="${field.name}" ${field.name===selected?'selected':''}>${escape(field.label)} · ${field.name}</option>`).join('');
  const operatorLabel={'>=':'Mayor o igual a ≥','>':'Mayor a >','<=':'Menor o igual a ≤','<':'Menor a <','=':'Igual a =','!=':'Diferente de ≠'};
  function renderCondition(condition,key,index) {
    const id=`${prefix}-${key}`;
    return `<form class="entry-form record-filter-form wk-field-grid formula-builder-grid" data-condition="${key}" aria-label="Condición ${index+1}">
      <label for="${id}-field">Dato ${index+1}<select id="${id}-field" data-field>${options(condition.field)}</select></label>
      <label for="${id}-operator">Comparación ${index+1}<select id="${id}-operator" data-operator>${operators.map(operator=>`<option value="${escape(operator)}" ${operator===condition.operator?'selected':''}>${escape(operatorLabel[operator])}</option>`).join('')}</select></label>
      <label for="${id}-value"><span data-value-label>Valor ${index+1}${isPercentageField(condition.field)?' (%)':''}</span><input id="${id}-value" data-value type="number" step="any" value="${escape(valueToInput(condition.field,condition.value))}" autocomplete="off"></label>
      <div class="formula-condition-action"><button type="button" class="button button-neutral" data-remove="${key}" aria-label="Quitar condición ${index+1}">Quitar condición</button></div>
    </form>`;
  }
  function render() {
    conditionKeys=state.conditions.map(()=>++nextKey);
    container.innerHTML=`<form class="entry-form record-filter-form wk-field-grid formula-builder-grid" data-definition>
      <label for="${prefix}-name">Nombre<input id="${prefix}-name" data-name type="text" maxlength="80" value="${escape(state.name)}" autocomplete="off" required></label>
      <label for="${prefix}-join">Combinar condiciones<select id="${prefix}-join" data-join><option value="Y" ${state.join!=='O'?'selected':''}>Todas (Y)</option><option value="O" ${state.join==='O'?'selected':''}>Cualquiera (O)</option></select></label>
      <label for="${prefix}-selection">Selección por partido<select id="${prefix}-selection" data-selection><option value="one" ${state.onePerMatch?'selected':''}>Una: la de mayor EV</option><option value="all" ${!state.onePerMatch?'selected':''}>Todas las coincidencias</option></select></label>
      <label for="${prefix}-stake">Importe por jugada (u)<input id="${prefix}-stake" data-stake type="number" min="0.01" step="any" value="${escape(state.stake)}" required></label>
    </form>
    <div class="formula-builder-conditions" data-conditions>${state.conditions.map((condition,index)=>renderCondition(condition,conditionKeys[index],index)).join('')}</div>
    <div class="formula-builder-actions"><button type="button" class="button button-neutral" data-add>Agregar condición</button><button type="button" class="button primary" data-save>${editing?'Guardar cambios':'Guardar fórmula'}</button><button type="button" class="button button-neutral" data-cancel ${editing?'':'hidden'}>Cancelar edición</button></div>
    <p class="formula-builder-error" data-error role="alert" hidden></p>
    <output class="formula-builder-preview" data-preview aria-label="Fórmula construida"></output>`;
    if(state.editable===false){
      for(const el of container.querySelectorAll('input,select,[data-add],[data-save]'))el.disabled=true;
      showError(new Error(state.editError));
      q('[data-cancel]').hidden=false;
    }
    preview();
  }
  function snapshot() {
    // Preserve blanks while arranging rows; validation happens at Save.
    state.name=q('[data-name]').value;
    state.join=q('[data-join]').value;
    state.onePerMatch=q('[data-selection]').value==='one';
    state.stake=q('[data-stake]').value;
    state.conditions=[...container.querySelectorAll('[data-condition]')].map(row=>readCondition(row,true));
  }
  container.addEventListener('submit',event=>event.preventDefault());
  container.addEventListener('input',()=>{showError('');preview();});
  container.addEventListener('change',event=>{
    if(event.target.matches('[data-field]')){
      const row=event.target.closest('[data-condition]'),index=[...container.querySelectorAll('[data-condition]')].indexOf(row);
      row.querySelector('[data-value-label]').textContent=`Valor ${index+1}${isPercentageField(event.target.value)?' (%)':''}`;
    }
    preview();
  });
  container.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||!container.contains(button))return;
    if(button.matches('[data-add]')){
      try{snapshot();if(state.conditions.length>=40)throw new Error('Podés usar hasta 40 condiciones.');state.conditions.push({field:'ev',operator:'>=',value:.03});render();}catch(error){showError(error);}
    }else if(button.matches('[data-remove]')){
      try{snapshot();const index=conditionKeys.indexOf(Number(button.dataset.remove));state.conditions.splice(index,1);render();}catch(error){showError(error);}
    }else if(button.matches('[data-cancel]')){reset();onCancel();}
    else if(button.matches('[data-save]')&&!saving){
      try{const definition=read();saving=true;button.disabled=true;await onSave(definition);showError('');}
      catch(error){showError(error);}
      finally{saving=false;if(button.isConnected)button.disabled=false;}
    }
  });
  function edit(formula) { state=conditionsFromFormula(formula);editing=Boolean(formula.id);render(); }
  function reset() { state={id:null,name:'',onePerMatch:true,stake:1,join:'Y',conditions:[{field:'ev',operator:'>=',value:.03}],editable:true};editing=false;render(); }
  reset();
  return {edit,reset,getDefinition:read};
}
