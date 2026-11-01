/** Mathematical price authoring in the shared Workraken fields and sections. */
import {newPriceFormula,newPriceCondition,normalizePriceFormula,formatPriceFormula,PRICE_FIELD_LABELS,calculatePaymentCoverage} from './football-price-engine.js';
const clone=x=>JSON.parse(JSON.stringify(x));
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const numeric=x=>String(x??'').trim()===''?null:Number(x);
const percentages=new Set(['ev','reference_probability','dispersion','min_return']);
const fmt=x=>Number.isFinite(x)?x.toLocaleString('es-AR',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
export const PRICE_FORMULA_CATEGORIES=Object.freeze([
  {id:'prices',name:'Cuotas',fields:['odds']},
  {id:'payments',name:'Pagos',fields:['gross_payout','profit_if_win','expected_payout','fair_payout','payout_edge']},
  {id:'value',name:'Valor esperado',fields:['ev','expected_profit','reference_probability','references','dispersion']},
  {id:'coverage',name:'Cobertura',fields:['inverse_sum','min_payout','min_profit','min_return']},
]);
const comparisons=[['>=','Mayor o igual a'],['>','Mayor que'],['<=','Menor o igual a'],['<','Menor que'],['=','Igual a'],['!=','Distinto de'],['between','Entre']];
const structures=[['two_outcomes','Dos resultados'],['three_outcomes','Tres resultados · 1X2'],['double_chance','Doble oportunidad · 1X / X2 / 12']];
const examples={two_outcomes:[2,1.75],three_outcomes:[2.3,3,3.5],double_chance:[1.28,1.57,1.36]};
let instanceSequence=0;
export function mountPriceFormulaEditor(container,{onSave=()=>{},onCancel=()=>{}}={}){
  if(!container?.ownerDocument)throw new Error('El creador necesita un contenedor.');
  const instance=++instanceSequence;let sequence=0,state,editing=false,saving=false,fresh=true,expanded=new Set();
  let calculation={structure:'two_outcomes',budget:100,odds:[2,1.75],costRate:0,oddsDrop:0,probability:null,modified:false};
  const q=s=>container.querySelector(s);
  const nodes=(root=state.expression)=>[root,...(root.children||[]).flatMap(n=>nodes(n))];
  const find=id=>nodes().find(n=>n.id===id);
  const uid=prefix=>{let id;do{id=`${prefix}-${instance}-${++sequence}`;}while(find(id));return id;};
  const entries=(group=state.expression)=>group.children.flatMap(node=>node.type==='group'?entries(node):[{node,group}]);
  const groups=(group=state.expression,path='1')=>[{group,path},...group.children.flatMap((n,i)=>n.type==='group'?groups(n,`${path}.${i+1}`):[])];
  const groupChoices=()=>groups().map(({group,path})=>[group.id,group===state.expression?'Fórmula':`Grupo ${path}`]);
  const categoryFor=node=>PRICE_FORMULA_CATEGORIES.find(c=>c.fields.includes(node.field))||PRICE_FORMULA_CATEGORIES.find(c=>c.id===node.category);
  const opts=(list,value)=>list.map(([id,label])=>`<option value="${esc(id)}" ${String(id)===String(value??'')?'selected':''}>${esc(label)}</option>`).join('');
  const cell=(title,control)=>`<label>${esc(title)}${control}</label>`;
  const grid=content=>`<div class="entry-form record-filter-form wk-field-grid football-builder-fields">${content}</div>`;
  const read=(label,value,extra='')=>cell(label,`<input type="text" readonly value="${esc(value)}" aria-label="${esc(label)}" title="${esc(value)}" ${extra}>`);
  const action=(title,text,attrs)=>cell(title,`<button type="button" class="button button-neutral" ${attrs}>${esc(text)}</button>`);
  const select=(label,list,value,attrs)=>cell(label,`<select aria-label="${esc(label)}" ${attrs}>${opts(list,value)}</select>`);
  const input=(label,value,attrs)=>cell(label,`<input type="number" step="any" value="${esc(value??'')}" aria-label="${esc(label)}" ${attrs}>`);
  function panel(title,key,body){return `<details class="panel parking-registration-contract-vehicle collapsible-panel football-formula-mother" data-formula-panel="${key}" ${expanded.has(key)?'open':''}><summary class="panel-header collapsible-summary parking-registration-contract-vehicle-summary"><span class="collapsible-title"><span class="collapsible-heading">${esc(title)}</span></span><span class="collapsible-indicator" aria-hidden="true"></span></summary><div class="parking-registration-contract-vehicle-body parking-registration-contract-primary-vehicle-body">${body}</div></details>`;}
  function add(category){const node={...newPriceCondition(),id:uid('price-condition'),category:category.id};state.expression.children.push(node);return node;}
  function prepare(){fresh=true;expanded=new Set();for(const category of PRICE_FORMULA_CATEGORIES)if(!entries().some(({node})=>categoryFor(node)?.id===category.id))add(category);}
  function renderCondition(node,group,category){
    const attr=key=>`data-node-id="${esc(node.id)}" data-control="${key}"`,percent=percentages.has(node.field),factor=percent?100:1;
    let body=select('Condición',[['','Sin filtro'],...category.fields.map(f=>[f,PRICE_FIELD_LABELS[f]])],node.field,attr('field'));
    if(node.field){
      body+=select('Comparación',comparisons,node.operator,attr('operator'));
      if(node.operator==='between')body+=input(percent?'Desde (%)':'Desde',node.min==null?null:node.min*factor,attr('min'))+input(percent?'Hasta (%)':'Hasta',node.max==null?null:node.max*factor,attr('max'));
      else body+=input(percent?'Valor (%)':'Valor',node.value==null?null:node.value*factor,attr('value'));
      body+=select('Grupo',groupChoices(),group.id,attr('group'))+action('Condición','Quitar condición',`data-remove-node="${esc(node.id)}"`);
    }
    return grid(body);
  }
  function renderLogic(){return groups().map(({group,path})=>grid(select(group===state.expression?'Unir condiciones':`Unión del grupo ${path}`,[['Y','Y'],['O','O']],group.operator,`data-node-id="${esc(group.id)}" data-control="operator"`)+action(`Grupo ${path}`,'Agregar grupo',`data-add-group="${esc(group.id)}"`)+(group===state.expression?'':action(`Grupo ${path}`,'Quitar grupo',`data-remove-node="${esc(group.id)}"`)))).join('');}
  function calculator(){
    const names=calculation.structure==='two_outcomes'?['Sí / primero','No / segundo']:calculation.structure==='double_chance'?['1X','X2','12']:['Local','Empate','Visitante'];
    return grid(read('Origen de cuotas',calculation.modified?'Cuotas ingresadas · simulación':'Bet365 · ejemplo 31/10/2026','data-calc-source')+select('Estructura',structures,calculation.structure,'data-calc="structure"')+input('Importe total (u)',calculation.budget,'data-calc="budget" min="0.01"')+input('Costo (%)',calculation.costRate*100,'data-calc="costRate" min="0" max="99"')+input('Caída de cuota (%)',calculation.oddsDrop*100,'data-calc="oddsDrop" min="0" max="99"')+names.map((name,i)=>input(`Cuota ${name}`,calculation.odds[i],`data-calc="odds-${i}" min="1.01"`)).join('')+names.map((name,i)=>read(`Importe ${name} (u)`,'—',`data-calc-result="stake-${i}"`)).join('')+names.map((name,i)=>read(`Pago si ${calculation.structure==='double_chance'?['local','empate','visitante'][i]:name} (u)`,'—',`data-calc-result="payout-${i}"`)).join('')+read('Pago mínimo (u)','—','data-calc-result="minimum"')+read('Beneficio mínimo (u)','—','data-calc-result="profit"')+read('Retorno mínimo (%)','—','data-calc-result="return"')+read('EV del reparto (%)','—','data-calc-result="ev"')+read('Suma de inversas','—','data-calc-result="inverse"')+read('Resultado del cálculo','—','data-calc-result="status"')+input('Probabilidad de referencia (%)',calculation.probability==null?null:calculation.probability*100,'data-calc="probability" min="0" max="100"')+read('EV de la primera cuota (%)','—','data-calc-result="value-ev"')+read('Beneficio esperado primera cuota (u)','—','data-calc-result="value-profit"'));
  }
  function updateCalculation(){
    const out=(key,value)=>{const target=q(`[data-calc-result="${key}"]`);if(target){target.value=value;target.title=value;}};
    try{
      const result=calculatePaymentCoverage(calculation),payments=Object.values(result.roundedPayoutByOutcome);
      result.roundedStakes.forEach((v,i)=>out(`stake-${i}`,fmt(v)));payments.forEach((v,i)=>out(`payout-${i}`,fmt(v)));
      const minimum=Math.min(...payments),profit=result.roundedMinProfit,rate=profit/calculation.budget;
      out('minimum',fmt(minimum));out('profit',fmt(profit));out('return',fmt(rate*100));out('inverse',result.inverseSum.toLocaleString('es-AR',{maximumFractionDigits:6}));
      out('ev',Math.max(...payments)-minimum<1e-8?fmt(rate*100):'Sin probabilidad por resultado');
      out('status',profit>1e-8?'Retorno mínimo positivo · teórico':'Sin retorno mínimo positivo');
      const p=calculation.probability;
      if(p!=null&&p>=0&&p<=1){const ev=p*result.effectiveOdds[0]-1-calculation.costRate;out('value-ev',fmt(ev*100));out('value-profit',fmt(ev*calculation.budget));}
      else{out('value-ev','Sin referencia');out('value-profit','Sin referencia');}
    }catch(problem){for(const control of container.querySelectorAll('[data-calc-result]'))control.value='—';out('status',problem.message);}
  }
  function render(){
    if(!fresh)for(const section of container.querySelectorAll('[data-formula-panel]'))section.hasAttribute('open')?expanded.add(section.dataset.formulaPanel):expanded.delete(section.dataset.formulaPanel);fresh=false;
    const all=entries();
    container.innerHTML=grid(cell('Nombre de la fórmula',`<input type="text" maxlength="100" data-definition="name" aria-label="Nombre de la fórmula" value="${esc(state.name)}">`)+input('Importe total (u)',state.stake,'data-definition="stake" min="0.01"')+select('Cálculo',[['value','Pago frente a referencia · EV'],['coverage','Reparto entre resultados']],state.mode,'data-definition="mode"')+select('Selección',[['true','Una operación por partido'],['false','Todas las operaciones']],String(state.onePerMatch),'data-definition="onePerMatch"')+select('Estructura',structures,state.structure,`data-definition="structure" ${state.mode==='value'?'disabled':''}`)+select('Casas',[['same_book','Una misma casa'],['cross_book','Mejores cuotas entre casas']],state.bookPolicy,`data-definition="bookPolicy" ${state.mode==='value'?'disabled':''}`)+input('Costo (%)',state.costRate*100,'data-definition="costRate" min="0" max="99"')+input('Caída de cuota (%)',state.oddsDrop*100,'data-definition="oddsDrop" min="0" max="99"'))+
      '<div class="parking-registration-contract-vehicle-list">'+PRICE_FORMULA_CATEGORIES.map(category=>panel(category.name,category.id,all.filter(({node})=>categoryFor(node)?.id===category.id).map(({node,group})=>renderCondition(node,group,category)).join('')+grid(action(category.name,'Agregar condición',`data-add-category="${category.id}"`)))).join('')+panel('Uniones Y/O','logic',renderLogic())+panel('Probar cuotas y pagos','calculator',calculator())+'</div>'+
      grid(read('Fórmula','','data-preview')+cell('Guardar',`<button type="button" class="button primary" data-save-alert>${editing?'Guardar cambios':'Guardar fórmula'}</button>`)+(editing?action('Edición','Cancelar edición','data-cancel-alert'):''))+
      '<div class="entry-form record-filter-form wk-field-grid football-builder-fields" data-alert-error-grid hidden><label>Error<input type="text" readonly data-alert-error role="alert" aria-live="polite" aria-label="Error"></label></div>';
    preview();updateCalculation();
  }
  function capture(){
    for(const control of container.querySelectorAll('[data-definition]')){const key=control.dataset.definition;state[key]=key==='onePerMatch'?control.value==='true':['stake','costRate','oddsDrop'].includes(key)?numeric(control.value)/(['costRate','oddsDrop'].includes(key)?100:1):control.value;}
    for(const control of container.querySelectorAll('[data-node-id][data-control]')){const node=find(control.dataset.nodeId),key=control.dataset.control;if(!node||['field','group'].includes(key))continue;node[key]=['value','min','max'].includes(key)?numeric(control.value)==null?null:numeric(control.value)/(percentages.has(node.field)?100:1):control.value;}
  }
  function preview(){try{const value=formatPriceFormula(normalizePriceFormula({...state,name:state.name||'Fórmula'}));q('[data-preview]').value=value;q('[data-preview]').title=value;}catch{q('[data-preview]').value='';}}
  function error(problem){q('[data-alert-error]').value=problem?.message||String(problem||'');q('[data-alert-error-grid]').hidden=!q('[data-alert-error]').value;}
  function remove(id,group=state.expression){const i=group.children.findIndex(n=>n.id===id);if(i>=0){group.children.splice(i,1);return true;}return group.children.some(n=>n.type==='group'&&remove(id,n));}
  function getDefinition(){capture();return normalizePriceFormula(state);}
  container.addEventListener('submit',event=>event.preventDefault());
  container.addEventListener('input',event=>{
    const control=event.target;if(control.dataset.calc){const key=control.dataset.calc;if(key.startsWith('odds-')){calculation.odds[Number(key.slice(5))]=numeric(control.value);calculation.modified=true;q('[data-calc-source]').value='Cuotas ingresadas · simulación';q('[data-calc-source]').title='Cuotas ingresadas · simulación';}else calculation[key]=numeric(control.value)==null?null:numeric(control.value)/(['costRate','oddsDrop','probability'].includes(key)?100:1);updateCalculation();return;}
    if(control.tagName==='INPUT'&&!control.readOnly){capture();preview();error('');}
  });
  container.addEventListener('change',event=>{
    const control=event.target;
    if(control.dataset.calc==='structure'){calculation.structure=control.value;calculation.odds=[...examples[control.value]];calculation.modified=false;render();return;}
    if(control.dataset.definition){capture();if(control.dataset.definition==='mode'){
      const active=entries().filter(({node})=>node.field);
      if(active.length===1&&((state.mode==='coverage'&&active[0].node.field==='ev'&&active[0].node.value===.03)||(state.mode==='value'&&active[0].node.field==='min_return'&&active[0].node.value===.001))){active[0].node.field=state.mode==='coverage'?'min_return':'ev';active[0].node.value=state.mode==='coverage'?.001:.03;}
      render();
    }else preview();return;}
    const node=find(control.dataset.nodeId),key=control.dataset.control;if(!node||!key)return;const old=clone(node);capture();
    if(key==='field'){const category=node.category;Object.assign(node,newPriceCondition(control.value),{id:old.id,category});}
    if(key==='group'){const destination=find(control.value),source=entries().find(e=>e.node.id===node.id)?.group;if(destination?.type==='group'&&source&&destination!==source){source.children=source.children.filter(n=>n.id!==node.id);destination.children.push(node);}}
    if(key==='operator'&&node.type==='condition'){if(control.value==='between'){node.min=old.min??old.value??null;node.max=old.max??old.value??null;delete node.value;}else{node.value=old.value??old.min??null;delete node.min;delete node.max;}}
    error('');render();
  });
  container.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||!container.contains(button))return;
    try{
      if(button.hasAttribute('data-save-alert')&&!saving){const rule=getDefinition();saving=true;button.disabled=true;await onSave(rule);error('');}
      else if(button.hasAttribute('data-cancel-alert')){reset();onCancel();}
      else if(button.hasAttribute('data-add-category')){capture();if(nodes().length>=100)throw new Error('Máximo 100 condiciones y grupos.');add(PRICE_FORMULA_CATEGORIES.find(c=>c.id===button.dataset.addCategory));render();}
      else if(button.hasAttribute('data-add-group')){capture();if(nodes().length>=100)throw new Error('Máximo 100 condiciones y grupos.');find(button.dataset.addGroup)?.children.push({type:'group',id:uid('price-group'),operator:'Y',children:[]});render();}
      else if(button.hasAttribute('data-remove-node')){capture();remove(button.dataset.removeNode);render();}
    }catch(problem){error(problem);}finally{saving=false;if(button.isConnected)button.disabled=false;}
  });
  function edit(rule){state=clone(rule);editing=Boolean(rule.id);prepare();render();}
  function reset(){state=newPriceFormula();state.expression.children=[{...newPriceCondition('ev'),value:.03}];editing=false;prepare();render();}
  reset();return {edit,reset,getDefinition,setEntities(){}};
}
