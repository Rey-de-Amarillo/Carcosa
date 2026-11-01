/** Current payment formulas: pure money, connected creator and safe archives. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {newPriceFormula,normalizePriceFormula,evaluatePaymentFormula,evaluatePriceFormula,calculatePaymentCoverage} from '../app/football-price-engine.js';
import {mountPriceFormulaEditor,PRICE_FORMULA_CATEGORIES} from '../app/football-price-editor.js';
import {mountFootballAlertBuilder} from '../app/football-alert-builder.js';
import {buildPriceFormulaLibrary,buildReferencePriceFormulaLibrary,isPaymentFormula,seedPriceFormulaLibrary,PRICE_LIBRARY_BACKUP_KEY} from '../app/football-price-library.js';
import {STRATEGY_STORAGE_KEY,loadStrategies,saveStrategies} from '../app/strategy-store.js';
import {filterAndSortFormulas} from '../app/formula-metrics-view.js';
import {metricsFromSummary} from '../app/formula-metrics.js';
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

const near=(actual,expected,message)=>assert.ok(Math.abs(actual-expected)<1e-8,`${message||'cash amount'}: ${actual} != ${expected}`);
const down=value=>Math.floor((value+1e-10)*100)/100;
let sequence=0;
const c=(field,value,operator='>=')=>({type:'condition',id:`qa-c-${++sequence}`,field,operator,value});
const g=(operator,...children)=>({type:'group',id:`qa-g-${++sequence}`,operator,children});
const rule=overrides=>normalizePriceFormula({...newPriceFormula(),id:'qa-payment',name:'Pagos propios',...overrides});
const current=rule(),before=JSON.stringify(current),input={odds:[2.1,2.1],budget:100};
const one=evaluatePaymentFormula(current,{...input,book:'Bet365',probability:.001,references:[]});
const other=evaluatePaymentFormula(current,{...input,book:'Otra casa',probability:.999,references:['R1','R2']});
assert.deepEqual(one,other,'identical prices and budget give identical money independently of bookmaker names or reference probabilities');
assert.equal(JSON.stringify(current),before);assert.deepEqual(input,{odds:[2.1,2.1],budget:100});
assert.equal(one.match,true);near(one.minPayout,105);near(one.minProfit,5);near(one.minReturn,.05);
assert.equal(one.fields.reference_probability,null);assert.equal(one.fields.references,null);
assert.equal(one.probability,undefined,'no synthetic probability is attached to supplied odds');
const negative=evaluatePaymentFormula(current,{odds:[2,1.75]});
assert.deepEqual(negative.stakes,[46.67,53.33]);near(negative.minPayout,93.32);near(negative.minProfit,-6.68);near(negative.minReturn,-.0668);assert.equal(negative.match,false);
assert.equal(negative.ev,null,'different rounded outcome payments cannot manufacture an EV from inverse odds');
for(const structure of ['two_outcomes','three_outcomes','double_chance']){
 const size=structure==='two_outcomes'?2:3;
 for(const odds of [[],Array(size-1).fill(2),Array(size+1).fill(2),Array(size).fill(null),Array(size).fill(1)])assert.throws(()=>evaluatePaymentFormula(rule({structure}),{odds}),/cuotas|mayores/,'incomplete outcome coverage cannot demonstrate a result');
}
assert.throws(()=>evaluatePaymentFormula(current,{odds:[2,2],budget:100.006}),/dos decimales/);
const triple=evaluatePaymentFormula(rule({structure:'three_outcomes',stake:99}),{odds:[3.3,3.3,3.3]});
assert.deepEqual(triple.stakes,[33,33,33]);near(triple.minPayout,108.9);near(triple.ev,.1);assert.equal(triple.evBasis,'constant_payoff');
const dc=evaluatePaymentFormula(rule({structure:'double_chance',stake:100.01,costRate:.005,oddsDrop:.01}),{odds:[1.5,3,4]});
const [oneX,xTwo,oneTwo]=dc.stakes,[o0,o1,o2]=dc.effectiveOdds;
near(dc.sumStakes,100.01);near(dc.cost,100.01*.005);near(dc.totalCost,100.01*1.005);
near(dc.payoutByOutcome.home,down(oneX*o0)+down(oneTwo*o2));
near(dc.payoutByOutcome.draw,down(oneX*o0)+down(xTwo*o1));
near(dc.payoutByOutcome.away,down(xTwo*o1)+down(oneTwo*o2));
near(dc.minProfit,Math.min(...Object.values(dc.payoutByOutcome))-dc.totalCost);
assert.equal(dc.ev,null,'overlapping double-chance payouts need no invented probability weighting');
const costed=evaluatePaymentFormula(rule({costRate:.005,oddsDrop:.01}),{odds:[2.2,2.2]});
assert.deepEqual(costed.stakes,[50,50]);near(costed.minPayout,108.9);near(costed.minProfit,8.4);near(costed.minReturn,.084);
const fragile=calculatePaymentCoverage({odds:[2.01,1.9901],budget:100});
assert.ok(fragile.minProfit>0&&fragile.roundedMinProfit<0,'cent rounding must precede comparisons');
assert.equal(evaluatePaymentFormula(current,{odds:[2.01,1.9901]}).match,false);
const mixed=rule({expression:g('O',g('Y',c('min_return',.1),c('min_profit',10)),g('Y',c('inverse_sum',1,'<'),c('min_return',0,'>')))});
assert.equal(evaluatePaymentFormula(mixed,input).match,true);assert.equal(evaluatePaymentFormula(mixed,{odds:[2,1.75]}).match,false);
const unavailableEV=rule({structure:'double_chance',expression:g('Y',c('ev',0,'>'))});
assert.equal(evaluatePaymentFormula(unavailableEV,{odds:[2.2,2.2,1.01]}).match,null,'an exact EV condition cannot silently use a minimum-return bound');

const library=buildPriceFormulaLibrary();
assert.equal(library.length,120);assert.equal(new Set(library.map(item=>JSON.stringify(strip(item)))).size,120);
for(const item of library){
 assert.equal(isPaymentFormula(item),true);assert.equal(item.mode,'coverage');assert.equal(item.bookPolicy,'same_book');
 assert.ok(leaves(item).every(node=>['inverse_sum','min_payout','min_profit','min_return'].includes(node.field)));
}
const container=new Element('div',{},document);documentRoot.append(container);const saved=[];let cancelled=0;
const editor=mountPriceFormulaEditor(container,{onSave:item=>saved.push(item),onCancel:()=>cancelled++});
const q=selector=>container.querySelector(selector),qa=selector=>container.querySelectorAll(selector);
const set=async(element,value,type='change')=>{assert.ok(element,'control exists');element.value=value;await fire(type,element);};
const control=(id,key)=>q(`[data-node-id="${id}"][data-control="${key}"]`);
const titles=()=>qa('[data-formula-panel]').filter(node=>PRICE_FORMULA_CATEGORIES.some(category=>category.id===node.dataset.formulaPanel)).map(node=>node.querySelector('.collapsible-heading').textContent);
assert.deepEqual(titles(),['Cuotas','Pagos','Beneficio','Retorno']);
assert.ok(qa('[data-formula-panel]').every(node=>!node.open),'all mothers begin closed');
assert.doesNotMatch(container.textContent,/\bEV\b|probabilidad|referencia|entre casas/i,'current creator contains no reference-probability controls or labels');
assert.equal(q('[data-definition="mode"]'),null);assert.equal(q('[data-definition="bookPolicy"]'),null);assert.equal(q('[data-calc="probability"]'),null);
assert.ok(qa('option').every(option=>!['ev','expected_profit','expected_payout','reference_probability','references','dispersion','fair_payout','payout_edge'].includes(option.value)),'current creator offers only pure monetary conditions');
assert.equal(q('[data-calc-result="minimum"]').value,'93,32');assert.equal(q('[data-calc-result="profit"]').value,'-6,68');
assert.equal(q('[data-calc-result="match"]').value,'No cumple la fórmula');
assert.match(q('[data-calc-result="status"]').value,/Sin saldo positivo/);
await set(q('[data-definition="name"]'),'Pagos conectados','input');
let definition=editor.getDefinition();assert.equal(definition.mode,'coverage');assert.equal(definition.bookPolicy,'same_book');
assert.deepEqual(leaves(definition).map(({field,operator,value})=>({field,operator,value})),[{field:'min_return',operator:'>',value:0}]);
const minId=leaves(definition)[0].id;
await set(q('[data-calc="odds-0"]'),2.2,'input');await set(q('[data-calc="odds-1"]'),2.2,'input');
assert.equal(q('[data-calc-result="minimum"]').value,'110,00');assert.equal(q('[data-calc-result="match"]').value,'Cumple la fórmula');
assert.match(q('[data-calc-source]').value,/ingresadas.*simulación/);assert.equal(q('[data-calc-source]').title,q('[data-calc-source]').value);
await set(control(minId,'value'),11,'input');assert.equal(leaves(editor.getDefinition())[0].value,.11);
assert.equal(q('[data-calc-result="match"]').value,'No cumple la fórmula','calculator evaluates the current draft criteria rather than just positive profit');
await set(control(minId,'value'),5,'input');assert.equal(q('[data-calc-result="match"]').value,'Cumple la fórmula');
await set(q('[data-definition="costRate"]'),6,'input');assert.equal(editor.getDefinition().costRate,.06);assert.equal(q('[data-calc-result="match"]').value,'No cumple la fórmula');
await set(q('[data-definition="costRate"]'),0,'input');await set(q('[data-definition="oddsDrop"]'),6,'input');
assert.equal(editor.getDefinition().oddsDrop,.06);assert.equal(q('[data-calc-result="match"]').value,'No cumple la fórmula');
await set(q('[data-definition="oddsDrop"]'),0,'input');await set(q('[data-definition="stake"]'),200,'input');assert.equal(q('[data-calc-result="minimum"]').value,'220,00','calculator uses the same stake as the draft');
await set(q('[data-calc="odds-1"]'),'','input');assert.equal(q('[data-calc-result="minimum"]').value,'—');assert.match(q('[data-calc-result="match"]').value,/Completá/);
await set(q('[data-definition="structure"]'),'double_chance');assert.match(q('[data-calc-source]').value,/Bet365.*ejemplo/);assert.equal(qa('[data-calc]').length,3,'changing draft structure changes the supplied outcome set');
for(const item of library){editor.edit(item);assert.deepEqual(editor.getDefinition(),item,`${item.id} roundtrips through the actual creator`);}
const nested=rule({expression:g('Y',c('min_payout',100),g('O',c('min_return',.05),c('min_profit',1)))});
editor.edit(nested);assert.deepEqual(editor.getDefinition(),nested);await fire('click',q('[data-save-alert]'));assert.deepEqual(saved.at(-1),nested);
const rootId=nested.expression.id,childId=nested.expression.children[1].id,leafId=nested.expression.children[1].children[0].id;
await set(control(leafId,'group'),rootId);assert.equal(leaves(editor.getDefinition()).find(node=>node.id===leafId).field,'min_return');
await set(control(leafId,'group'),childId);assert.equal(editor.getDefinition().expression.children[1].operator,'O');
editor.edit(nested);q('[data-formula-panel="prices"]').open=true;await fire('click',q('[data-cancel-alert]'));assert.equal(cancelled,1);assert.ok(qa('[data-formula-panel]').every(node=>!node.open));
for(const element of qa('input,select,button')){assert.equal(element.parentElement.tagName,'LABEL');assert.ok(element.parentElement.parentElement.classList.contains('wk-field-grid'));}
function verifyText(element){for(const child of element.childNodes)if(typeof child==='string'){if(child.trim())assert.ok(['LABEL','OPTION','BUTTON'].includes(element.tagName)||element.classList.contains('collapsible-heading'),`uncontained text ${child}`);}else verifyText(child);}
verifyText(container);

// The archive is conservative: a complete, real same-house source can be
// evaluated, while an absent or another-house complement cannot be invented.
const events=[{id:'fixture',date:'2026-10-31',home:'A',away:'B',home_score:1,away_score:0}];
const first={event:0,book:'Bet365',market:'btts',period:'full',selection:'yes',odds:2.1,rulesId:'regulation',snapshotId:'capture-1'};
const second={...first,selection:'no'};
assert.equal(evaluatePriceFormula({events,offers:[first]},current).alerts.length,0);
assert.equal(evaluatePriceFormula({events,offers:[first,{...second,book:'Another'}]},current).alerts.length,0);
const archive=evaluatePriceFormula({events,offers:[first,second]},current);assert.equal(archive.alerts.length,1);near(archive.alerts[0].minProfit,one.minProfit);
const otherArchive=evaluatePriceFormula({events,offers:[{...first,book:'Another'},{...second,book:'Another'}]},current);
near(otherArchive.alerts[0].minProfit,archive.alerts[0].minProfit);near(otherArchive.alerts[0].minReturn,archive.alerts[0].minReturn);
const summaryMetric=metricsFromSummary(archive.summary,archive.coverage.unknownCandidates);near(summaryMetric.meanMinPayout,105);near(summaryMetric.meanMinProfit,5);near(summaryMetric.meanMinReturn,.05);
const sampleRules=['negative','zero','positive','missing','loading'].map(id=>({id,name:id}));
const metricMap=new Map([['negative',{state:'ready',meanMinReturn:-.01}],['zero',{state:'ready',meanMinReturn:0}],['positive',{state:'ready',meanMinReturn:.02}],['missing',{state:'ready',meanMinReturn:null}],['loading',{state:'loading',meanMinReturn:999}]]);
const ids=options=>filterAndSortFormulas(sampleRules,metricMap,options).map(item=>item.id);
assert.deepEqual(ids({sort:'minReturn_desc'}),['positive','zero','negative','loading','missing']);
assert.deepEqual(ids({sort:'minReturn_asc'}),['negative','zero','positive','loading','missing']);
assert.deepEqual(ids({sort:'minReturn_desc',minReturn:0}),['positive','zero'],'zero is an active percentage filter, missing is not zero');
assert.deepEqual(ids({sort:'minReturn_desc',minReturn:1}),['positive'],'UI return percentage is divided by100');
assert.deepEqual(ids({sort:'minReturn_desc',minReturn:-1}),['positive','zero','negative']);
const refs=buildReferencePriceFormulaLibrary(),customReference={...structuredClone(refs[0]),id:'my-reference',name:'Referencia propia'},customPayment={...structuredClone(library[0]),id:'my-payment',name:'Mis pagos'};
const original=[refs[1],customReference,customPayment],values=new Map(),storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value))};
const merged=seedPriceFormulaLibrary(original,entities,storage);
assert.deepEqual(JSON.parse(values.get(PRICE_LIBRARY_BACKUP_KEY)),original);assert.deepEqual(merged.find(item=>item.id===customReference.id),customReference);
assert.ok(!merged.filter(isPaymentFormula).some(item=>item.id===customReference.id),'reference custom remains stored but never belongs to current payment formulas');
assert.deepEqual(merged.filter(isPaymentFormula).find(item=>item.id===customPayment.id),customPayment);
assert.deepEqual(saveStrategies(loadStrategies(storage),entities,storage),merged);assert.deepEqual(JSON.parse(values.get(STRATEGY_STORAGE_KEY)),merged);
const wrapperContainer=new Element('div',{},document);documentRoot.append(wrapperContainer);const wrapper=mountFootballAlertBuilder(wrapperContainer,{entities});
wrapper.edit(customReference);assert.deepEqual(wrapper.getDefinition(),customReference,'archived custom keeps its exact historical criteria in its own editor');
assert.ok(wrapperContainer.querySelector('[data-calc="probability"]'),'reference fields belong only to the archived editor');
wrapper.reset();assert.equal(wrapperContainer.querySelector('[data-calc="probability"]'),null);assert.equal(wrapperContainer.querySelector('[data-definition="mode"]'),null,'new creator always returns to pure payments');
console.log('Payment QA: 120 pure same-house formulas, bookmaker independence, complete rounded payoff math, connected calculator/draft Y/O, canonical mothers and intact custom archives passed.');
