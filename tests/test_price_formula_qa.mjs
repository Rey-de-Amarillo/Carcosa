/** Independent mathematical, authoring and migration regressions. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PRICE_FORMULA_KIND,newPriceFormula,normalizePriceFormula,evaluatePriceFormula,calculatePaymentCoverage,PRICE_CONDITION_FIELDS} from '../app/football-price-engine.js';
import {mountPriceFormulaEditor,PRICE_FORMULA_CATEGORIES} from '../app/football-price-editor.js';
import {buildPriceFormulaLibrary,seedPriceFormulaLibrary,PRICE_LIBRARY_BACKUP_KEY} from '../app/football-price-library.js';
import {buildFootballFormulaLibrary} from '../app/football-formula-library.js';
import {STRATEGY_STORAGE_KEY,defaultScoreAlert,loadStrategies,saveStrategies} from '../app/strategy-store.js';
const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const VOID=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
const decode=value=>String(value).replace(/&(?:amp|quot|lt|gt|#39|apos);/g,s=>({'&amp;':'&','&quot;':'"','&lt;':'<','&gt;':'>','&#39;':"'",'&apos;':"'"}[s]));
const kebab=value=>value.replace(/[A-Z]/g,s=>'-'+s.toLowerCase());
class Element {
  constructor(tag='div',attrs={},doc=null){this.tagName=tag.toUpperCase();this.attrs={...attrs};this.ownerDocument=doc;this.childNodes=[];this.listeners=new Map();this.parentElement=null;this._value=undefined;}
  get children(){return this.childNodes.filter(n=>n instanceof Element);}
  get childElementCount(){return this.children.length;}
  get firstElementChild(){return this.children[0]||null;}
  get dataset(){return new Proxy({}, {get:(_,key)=>this.attrs['data-'+kebab(String(key))],set:(_,key,value)=>(this.attrs['data-'+kebab(String(key))]=String(value),true)});}
  get type(){return this.attrs.type||(this.tagName==='SELECT'?'select-one':'');}
  get value(){
    if(this._value!==undefined)return this._value;
    if(this.tagName==='SELECT'){const option=this.querySelectorAll('option').find(n=>n.hasAttribute('selected'))||this.querySelector('option');return option?.value??'';}
    if(this.tagName==='OPTION')return this.attrs.value??this.textContent;
    return this.attrs.value??'';
  }
  set value(value){this._value=String(value??'');}
  get valueAsNumber(){return this.value===''?NaN:Number(this.value);}
  get textContent(){return this.childNodes.map(n=>n instanceof Element?n.textContent:n).join('');}
  set textContent(value){this.childNodes=[String(value)];}
  get disabled(){return this.hasAttribute('disabled');}
  set disabled(value){value?this.setAttribute('disabled',''):this.removeAttribute('disabled');}
  get hidden(){return this.hasAttribute('hidden');}
  set hidden(value){value?this.setAttribute('hidden',''):this.removeAttribute('hidden');}
  get open(){return this.hasAttribute('open');}
  set open(value){value?this.setAttribute('open',''):this.removeAttribute('open');}
  get isConnected(){return this===documentRoot||Boolean(this.parentElement?.isConnected);}
  get classList(){return {contains:value=>(this.attrs.class||'').split(/\s+/).includes(value)};}
  hasAttribute(name){return Object.hasOwn(this.attrs,name);}
  getAttribute(name){return this.attrs[name]??null;}
  setAttribute(name,value){this.attrs[name]=String(value);}
  removeAttribute(name){delete this.attrs[name];}
  contains(node){return node===this||this.children.some(child=>child.contains(node));}
  append(...nodes){for(const node of nodes){if(node instanceof Element){node.parentElement=this;node.ownerDocument=this.ownerDocument;}this.childNodes.push(node);}}
  appendChild(node){this.append(node);return node;}
  replaceChildren(...nodes){for(const child of this.children)child.parentElement=null;this.childNodes=[];this.append(...nodes);}
  remove(){if(this.parentElement){const parent=this.parentElement;parent.childNodes=parent.childNodes.filter(n=>n!==this);this.parentElement=null;}}
  addEventListener(type,fn){this.listeners.set(type,[...(this.listeners.get(type)||[]),fn]);}
  removeEventListener(type,fn){this.listeners.set(type,(this.listeners.get(type)||[]).filter(n=>n!==fn));}
  matches(selector){
    return selector.split(',').some(part=>{
      let rest=part.trim();const tag=rest.match(/^[\w-]+/);if(tag){if(this.tagName!==tag[0].toUpperCase())return false;rest=rest.slice(tag[0].length);}
      for(const token of rest.matchAll(/(\.[\w-]+)|\[([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]+)))?\]/g)){
        if(token[1]){if(!this.classList.contains(token[1].slice(1)))return false;}
        else if(!this.hasAttribute(token[2])||(token[3]??token[4]??token[5])!==undefined&&this.getAttribute(token[2])!==(token[3]??token[4]??token[5]))return false;
      }
      return Boolean(tag)||/^[.\[]/.test(rest);
    });
  }
  closest(selector){return this.matches(selector)?this:this.parentElement?.closest(selector)||null;}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(child.matches(selector)?[child]:[]),...child.querySelectorAll(selector)]);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  set innerHTML(html){
    this.replaceChildren();const stack=[this];
    for(const token of String(html).match(/<!--[\s\S]*?-->|<(?:[^>"']|"[^"]*"|'[^']*')+>|[^<]+/g)||[]){
      if(token.startsWith('<!--'))continue;
      if(token.startsWith('</')){const tag=token.match(/^<\/\s*([\w-]+)/)?.[1];assert.equal(stack.at(-1).tagName,tag.toUpperCase(),'balanced generated markup');stack.pop();}
      else if(token.startsWith('<')){
        const tag=token.match(/^<\s*([\w-]+)/)?.[1];assert.ok(tag,'valid generated element');const attrs={};
        for(const m of token.slice(token.indexOf(tag)+tag.length).matchAll(/\s+([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))attrs[m[1]]=decode(m[2]??m[3]??m[4]??'');
        const node=new Element(tag,attrs,this.ownerDocument);stack.at(-1).append(node);if(!VOID.has(tag)&&!token.endsWith('/>'))stack.push(node);
      }else stack.at(-1).append(decode(token));
    }
    assert.equal(stack.length,1,'all generated elements closed');this._html=String(html);
  }
  get innerHTML(){return this._html||'';}
}
const document={createElement:tag=>new Element(tag,{},document)};
const documentRoot=new Element('main',{},document);
async function fire(type,target){assert.ok(target,`${type} target exists`);const event={type,target,preventDefault(){},stopPropagation(){}};for(let node=target;node;node=node.parentElement)for(const fn of node.listeners.get(type)||[])await fn(event);}
const walk=node=>[node,...(node.children||[]).flatMap(walk)];
const leaves=rule=>walk(rule.expression).filter(node=>node.type==='condition');
const strip=value=>value&&typeof value==='object'?Array.isArray(value)?value.map(strip):Object.fromEntries(Object.keys(value).filter(key=>!['id','name'].includes(key)).sort().map(key=>[key,strip(value[key])])):value;
const library=buildPriceFormulaLibrary();
assert.equal(library.length,120);assert.equal(library.filter(rule=>rule.mode==='value').length,72);assert.equal(library.filter(rule=>rule.mode==='coverage').length,48);
assert.equal(new Set(library.map(rule=>rule.id)).size,120);assert.equal(new Set(library.map(rule=>rule.name)).size,120);
assert.equal(new Set(library.map(rule=>JSON.stringify(strip(rule)))).size,120,'names and node IDs cannot manufacture different mathematical criteria');
assert.deepEqual(buildPriceFormulaLibrary(),library,'mathematical seed definitions are deterministic');
for(const rule of library){
  assert.equal(rule.kind,PRICE_FORMULA_KIND);assert.deepEqual(normalizePriceFormula(rule),rule);
  for(const node of leaves(rule))assert.ok(PRICE_CONDITION_FIELDS.includes(node.field),`${rule.id}: only mathematical price fields belong in the library`);
  assert.ok(!Object.hasOwn(rule,'context'),'no implicit team/league/player scope');
  if(rule.mode==='value')assert.ok(leaves(rule).some(node=>node.field==='ev'),'value recipe requires external reference EV');
  else assert.ok(leaves(rule).some(node=>node.field==='min_return'),'coverage recipe requires the minimum monetary return');
}

// Keep a self-contained minimal DOM so tests operate the actual rendered
// fields and delegated events, rather than searching editor source strings.
const container=new Element('div',{},document);documentRoot.append(container);let saved=[],cancelled=0;
const editor=mountPriceFormulaEditor(container,{onSave:rule=>saved.push(rule),onCancel:()=>cancelled++});
const q=selector=>container.querySelector(selector),qa=selector=>container.querySelectorAll(selector);
const control=(id,key)=>q(`[data-node-id="${id}"][data-control="${key}"]`);
const set=async(element,value,type='change')=>{assert.ok(element,'rendered editable control exists');element.value=value;await fire(type,element);};
const click=selector=>fire('click',q(selector));
const titles=()=>qa('[data-formula-panel]').filter(node=>PRICE_FORMULA_CATEGORIES.some(category=>category.id===node.dataset.formulaPanel)).map(node=>node.querySelector('.collapsible-heading').textContent);
assert.deepEqual(titles(),['Cuotas','Pagos','Valor esperado','Cobertura']);
assert.ok(qa('[data-formula-panel]').every(node=>!node.hasAttribute('open')),'all mothers begin closed');
assert.equal(q('[data-calc-result="minimum"]').value,'93,32','2.00/1.75 does not become a profitable cover');
assert.match(q('[data-calc-result="status"]').value,/Sin retorno mínimo positivo/);
assert.match(q('[data-calc-source]').value,/Bet365.*ejemplo/);
await set(q('[data-calc="odds-0"]'),2.1,'input');
assert.match(q('[data-calc-source]').value,/ingresadas.*simulación/);
assert.equal(q('[data-calc-source]').title,q('[data-calc-source]').value,'source tooltip must describe the modified quotes too');
await set(q('[data-calc="structure"]'),'double_chance');
assert.match(q('[data-calc-source]').value,/Bet365.*ejemplo/,'selecting a known example resets its attribution');

await set(q('[data-definition="name"]'),'Matemática propia','input');
let definition=editor.getDefinition();assert.equal(leaves(definition).length,1);assert.equal(leaves(definition)[0].field,'ev');assert.equal(leaves(definition)[0].value,.03);
await set(q('[data-definition="mode"]'),'coverage');definition=editor.getDefinition();assert.equal(leaves(definition)[0].field,'min_return');assert.equal(leaves(definition)[0].value,.001);
await set(q('[data-definition="mode"]'),'value');assert.equal(leaves(editor.getDefinition())[0].value,.03);
let evId=leaves(editor.getDefinition())[0].id;
await set(control(evId,'value'),5,'input');assert.equal(leaves(editor.getDefinition())[0].value,.05,'5 percent is .05 internally');
await set(control(evId,'operator'),'between');await set(control(evId,'max'),7.5,'input');
assert.deepEqual([leaves(editor.getDefinition())[0].min,leaves(editor.getDefinition())[0].max],[.05,.075]);
const customTree=structuredClone(editor.getDefinition().expression);
await set(q('[data-definition="mode"]'),'coverage');assert.deepEqual(editor.getDefinition().expression,customTree,'switching mode never erases an edited mathematical criterion');

// A prior session may have saved IDs with the current instance prefix. Draft
// preparation must skip those IDs, not corrupt a loaded user's expression.
const collisionRule=normalizePriceFormula({...newPriceFormula(),id:'collision',name:'Identidades persistidas',expression:{type:'group',id:'g',operator:'Y',children:[
  {type:'condition',id:'price-condition-1-4',field:'odds',operator:'>=',value:2},
  {type:'condition',id:'persisted-ev',field:'ev',operator:'>=',value:.03},
]}});
editor.edit(collisionRule);assert.deepEqual(editor.getDefinition(),collisionRule,'loaded user IDs cannot collide with new passive category rows');
for(const rule of library){editor.edit(rule);assert.deepEqual(editor.getDefinition(),rule,`${rule.id}: all120 definitions survive the actual editor`);}
editor.edit(collisionRule);
await click('[data-add-group="g"]');
const nestedId=qa('[data-add-group]').map(button=>button.dataset.addGroup).find(id=>id!=='g');
await set(control(nestedId,'operator'),'O');await set(control('persisted-ev','group'),nestedId);
let moved=editor.getDefinition();assert.equal(moved.expression.operator,'Y');assert.equal(moved.expression.children[1].operator,'O');assert.equal(moved.expression.children[1].children[0].id,'persisted-ev');
await set(control('persisted-ev','group'),'g');assert.deepEqual(editor.getDefinition(),collisionRule,'moving out of O retains the exact criterion and root Y');
await click('[data-save-alert]');assert.deepEqual(saved.at(-1),collisionRule);
q('[data-formula-panel="prices"]').setAttribute('open','');editor.reset();assert.ok(qa('[data-formula-panel]').every(node=>!node.hasAttribute('open')),'reset closes all mothers');
editor.edit(collisionRule);await click('[data-cancel-alert]');assert.equal(cancelled,1);

for(const element of qa('input,select,button')){
  assert.equal(element.parentElement.tagName,'LABEL','ordinary fields and actions stay inside their title');
  assert.ok(element.parentElement.parentElement.classList.contains('wk-field-grid'),'every field occupies the common Workraken grid');
  assert.ok(element.parentElement.childNodes.some(node=>typeof node==='string'&&node.trim()),'field title is present');
}
function verifyText(element){
  for(const child of element.childNodes)if(typeof child==='string'){
    if(!child.trim())continue;
    assert.ok(['LABEL','OPTION','BUTTON'].includes(element.tagName)||element.classList.contains('collapsible-heading'),`uncontained text: ${child}`);
  }else verifyText(child);
}
verifyText(container);

// Conservative monetary arithmetic: double chance is overlapping coverage,
// every actual state pays two tickets; cent rounding is applied before profit.
const dc=calculatePaymentCoverage({structure:'double_chance',odds:[1.5,3,4],budget:100});
const [oneX,xTwo,oneTwo]=dc.roundedStakes;
const down=value=>Math.floor((value+1e-10)*100)/100;
assert.equal(dc.roundedPayoutByOutcome.home,down(oneX*1.5)+down(oneTwo*4));
assert.equal(dc.roundedPayoutByOutcome.draw,down(oneX*1.5)+down(xTwo*3));
assert.equal(dc.roundedPayoutByOutcome.away,down(xTwo*3)+down(oneTwo*4));
assert.equal(dc.roundedEV,null,'unequal outcome payouts cannot invent a probability-weighted EV');
const fragile=calculatePaymentCoverage({odds:[2.01,1.9901],budget:100});assert.ok(fragile.minProfit>0&&fragile.roundedMinProfit<0,'continuous advantage may disappear after cents');

const condition=(field,value,operator='>=')=>({type:'condition',id:'c',field,value,operator});
const coverage={...newPriceFormula(),name:'QA sincronía',mode:'coverage',bookPolicy:'cross_book',expression:{type:'group',id:'root',operator:'Y',children:[condition('min_return',0,'>')]}};
const events=[{id:'fixture',date:'2026-10-31',home:'A',away:'B',home_score:1,away_score:0}];
const first={event:0,book:'A',market:'btts',period:'full',selection:'yes',odds:2.1,rulesId:'regulation-btts',capturedAt:'2026-10-31T10:00:00Z'};
const last={...first,book:'B',selection:'no',capturedAt:'2026-10-31T10:00:30Z'};
for(const state of [{active:false},{suspended:true}])for(const odds of [2.1,null]){
  const suspension={...first,...state,odds,capturedAt:'2026-10-31T10:00:10Z'};
  const result=evaluatePriceFormula({events,offers:[first,suspension,last]},coverage);
  assert.equal(result.alerts.length,0,'a later suspension invalidates the old quote even when its new odds are absent');
}
assert.equal(evaluatePriceFormula({events,offers:[first,last]},coverage).alerts.length,1,'an actually active aligned pair remains eligible');
const noTimes=[first,last].map(({capturedAt,...quote})=>quote);
assert.equal(evaluatePriceFormula({events,offers:noTimes},coverage).alerts.length,0,'matching event/day cannot manufacture simultaneous prices');
const ownReference={...newPriceFormula(),name:'QA referencia',expression:{type:'group',id:'root',operator:'Y',children:[condition('ev',0)]}};
assert.equal(evaluatePriceFormula({events,offers:[{...first,probability:.8,references:['A','EXTERNAL']}]},ownReference).alerts.length,0,'self-including reference cannot create EV');
const uniqueReferences={...first,probability:.8,references:['R1','R1','R2']};
assert.equal(evaluatePriceFormula({events,offers:[uniqueReferences]}, {...ownReference,expression:{type:'group',id:'root',operator:'Y',children:[condition('references',3)]}}).alerts.length,0,'repeated book IDs do not increase independent reference count');

// Safe migration only replaces untouched shipped recipes. User expressions,
// changed old examples, changed new examples and one original backup survive.
const old=buildFootballFormulaLibrary(entities),oldDefault=defaultScoreAlert(),editedOld=structuredClone(old[1]);
leaves(editedOld).find(node=>node.field==='odds').min+=.05;
const customOld={...structuredClone(old[2]),id:'my-team-criterion',name:'Mi regla anterior'};
const customAlert={...structuredClone(oldDefault),id:'my-legacy-alert',name:'Mi alerta anterior'};
const editedPrice={...structuredClone(library[0]),name:'Mi fórmula matemática',stake:250};
leaves(editedPrice).find(node=>node.field==='ev').value=.07;
const existing=[old[0],editedOld,customOld,oldDefault,customAlert,editedPrice],before=JSON.stringify(existing);
const values=new Map(),storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value))};
const merged=seedPriceFormulaLibrary(existing,entities,storage);
assert.equal(JSON.stringify(existing),before,'migration cannot mutate caller-owned criteria');
assert.equal(merged.length,123);assert.equal(merged.filter(rule=>rule.kind===PRICE_FORMULA_KIND).length,120);
assert.deepEqual(JSON.parse(values.get(PRICE_LIBRARY_BACKUP_KEY)),existing,'the complete original collection is backed up before replacement');
for(const original of [editedOld,customOld,customAlert,editedPrice])assert.deepEqual(merged.find(rule=>rule.id===original.id),original,'user definition is preserved exactly');
assert.ok(!merged.some(rule=>rule.id===old[0].id));assert.ok(!merged.some(rule=>rule.id===oldDefault.id));
assert.deepEqual(loadStrategies(storage),merged);
const backup=values.get(PRICE_LIBRARY_BACKUP_KEY),resaved=saveStrategies(merged,entities,storage);
assert.deepEqual(seedPriceFormulaLibrary(loadStrategies(storage),entities,storage),resaved,'reload never replaces edited mathematical or historical user formulas');
assert.equal(values.get(PRICE_LIBRARY_BACKUP_KEY),backup,'repeat seed never overwrites the original backup');
assert.equal(new Set(merged.map(rule=>rule.id)).size,merged.length);
console.log('Price formula QA: 120 math-only recipes, four canonical field mothers, exact editor/state/percent roundtrips, safe migration, conservative cents/DC and suspended-quote provenance passed.');
