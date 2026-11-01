/** Test actual editor markup and delegated actions without browser dependencies. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {FORMULA_CATEGORIES,mountUnifiedFormulaEditor} from '../app/football-formula-editor.js';
import {mountFootballAlertBuilder,newFootballAlert,normalizeFootballAlert} from '../app/football-alert-builder.js';
import {normalizeUnifiedFormula} from '../app/football-unified-formula.js';
import {FOOTBALL_MARKET_CATALOG,defaultMarketSelection} from '../app/football-market-catalog.js';

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
const container=new Element('div',{},document);documentRoot.append(container);
let saved=[],cancelled=0;
const editor=mountUnifiedFormulaEditor(container,{entities,onSave:definition=>saved.push(structuredClone(definition)),onCancel:()=>cancelled++});
const q=selector=>container.querySelector(selector);
const qa=selector=>container.querySelectorAll(selector);
const control=(id,name)=>q(`[data-node-id="${id}"][data-control="${name}"]`);
const click=selector=>fire('click',q(selector));
const set=async(element,value,type='change')=>{assert.ok(element,'editable control exists');element.value=value;await fire(type,element);};
const home=entities.teams.find(team=>team.currentLeagueIds?.includes('E0')&&team.playerIds?.length);
const player=entities.players.find(item=>home.playerIds.includes(item.id));
assert.ok(home&&player,'real team/player fixtures');
const condition=(id,field,operator,value)=>({type:'condition',id,field,operator,...(value===undefined?{}:{value})});
const rule=normalizeUnifiedFormula({kind:'football-formula',version:1,id:'nested-rule',name:'Equipo Y jugador Y (cuota O goles)',stake:2,expression:{type:'group',id:'root',operator:'Y',children:[
  condition('club','team','=',home.id),condition('person','player','=',player.id),
  {type:'group',id:'alternatives',operator:'O',children:[condition('price','odds','>=',2),{type:'condition',id:'goals',field:'market',operator:'=',playerRef:'person',selection:{...defaultMarketSelection('player_goals'),playerId:player.id}}]},
]}},entities);

assert.throws(()=>editor.getDefinition(),/condici[oó]n|f[oó]rmula|nombre/i,'blank editor cannot become a match-all formula');
const categoryIds=['teams','players','odds','results','goals','corners','cards','shots','offsides','leagues'];
assert.deepEqual(qa('[data-formula-category]').map(n=>n.dataset.formulaCategory),categoryIds,'all mother dropdowns are available directly in the creator');
assert.deepEqual(FORMULA_CATEGORIES.map(c=>c.id),categoryIds);
assert.equal(q('[data-add-condition]'),null,'there is no global choose-condition action');
assert.equal(q('dialog'),null,'mother fields belong to the creator, not a modal');
assert.ok(q('[data-formula-logic]'),'one logic editor controls the complete expression');
const offeredFields=[];
for(const category of FORMULA_CATEGORIES){
  const mother=q(`[data-formula-category="${category.id}"]`),field=mother.querySelector('[data-control="field"]');
  assert.equal(mother.tagName,'DETAILS');
  assert.equal(mother.querySelector('summary').textContent.trim(),category.name);
  assert.equal(mother.querySelectorAll('[data-control="group"]').length,1,'each mother starts with one pending row');
  assert.equal(mother.querySelector('[data-add-category]').dataset.addCategory,category.id);
  const choices=field?field.querySelectorAll('option').map(o=>o.value).filter(Boolean):[category.initial];
  assert.deepEqual(choices,category.fields,`${category.name} offers only its own fields`);
  assert.equal(new Set(choices).size,choices.length,'family choices have no duplicates');
  offeredFields.push(...choices);
}
for(const market of FOOTBALL_MARKET_CATALOG)assert.ok(offeredFields.includes(`market:${market.id}`),`${market.name} is offered in a mother dropdown`);
assert.equal(offeredFields.length,new Set(offeredFields).size,'each actual field belongs to one family');
assert.ok(qa('option').every(option=>option.textContent!=='Elegir condición'),'the flat choose-condition list is absent');
await set(q('[data-definition="name"]'),'Sólo filas pendientes','input');
assert.throws(()=>editor.getDefinition(),/condici[oó]n/i,'all untouched mother rows are inactive, including preset team/player/odds fields');

// Build the user's complete example using only the rendered fields/actions.
const creationContainer=new Element('div',{},document);documentRoot.append(creationContainer);let created;
const creator=mountUnifiedFormulaEditor(creationContainer,{entities,onSave:value=>{created=value;}});
const cq=selector=>creationContainer.querySelector(selector),cqa=selector=>creationContainer.querySelectorAll(selector);
const cc=(id,key)=>cq(`[data-node-id="${id}"][data-control="${key}"]`);
const cclick=selector=>fire('click',cq(selector));
await set(cq('[data-definition="name"]'),'Equipo, jugador y alternativas','input');
await set(cq('[data-definition="stake"]'),3,'input');
const cmother=id=>cq(`[data-formula-category="${id}"]`);
const rootId=cq('[data-formula-logic]').querySelector('[data-add-group]').dataset.addGroup;
const clubId=cmother('teams').querySelector('[data-control="value"]').dataset.nodeId;
cmother('teams').open=true;cmother('players').open=true;
await set(cc(clubId,'value'),home.id);
assert.equal(cmother('teams').open,true,'changing a mother value preserves its expanded state');
const personId=cmother('players').querySelector('[data-control="playerId"]').dataset.nodeId;
await set(cc(personId,'teamId'),home.id);await set(cc(personId,'playerId'),player.id);
assert.equal(cmother('players').open,true,'player changes preserve the open mother');
await cclick(`[data-add-group="${rootId}"]`);
const alternativeId=cq('[data-formula-logic]').querySelectorAll('[data-add-group]').map(n=>n.dataset.addGroup).find(id=>id!==rootId);
await set(cc(alternativeId,'operator'),'O');
const priceId=cmother('odds').querySelector('[data-control="field"]').dataset.nodeId;
await set(cc(priceId,'operator'),'between');await set(cc(priceId,'min'),1.8,'input');await set(cc(priceId,'max'),2.2,'input');
await set(cc(priceId,'group'),alternativeId);
await cclick('[data-add-category="players"]');
const goalsId=cmother('players').querySelectorAll('[data-control="field"]').map(n=>n.dataset.nodeId).find(id=>id!==personId);
await set(cc(goalsId,'field'),'market:player_goals');
await set(cc(goalsId,'group'),alternativeId);
const built=creator.getDefinition();
assert.equal(built.stake,3);assert.equal(built.expression.operator,'Y');assert.equal(built.expression.children.length,3);
assert.equal(built.expression.children[0].value,home.id);assert.equal(built.expression.children[1].playerId,player.id);
assert.equal(built.expression.children[2].operator,'O');assert.equal(built.expression.children[2].children[0].min,1.8);assert.equal(built.expression.children[2].children[0].max,2.2);
assert.equal(built.expression.children[2].children[1].playerRef,personId,'market automatically references the single selected player');
assert.ok(cqa('input').some(n=>n.hasAttribute('readonly')&&n.value===player.name),'player statistic displays the selected identity without another player dropdown');
await cclick('[data-save-alert]');assert.deepEqual(created,built,'creating through controls saves one complete expression');

editor.edit(rule);
const normalized=normalizeUnifiedFormula(rule,entities);
assert.deepEqual(editor.getDefinition(),normalized,'editing preserves nested tree, player reference, identity, stake and prices');
assert.equal(control('root','operator').value,'Y');assert.equal(control('alternatives','operator').value,'O');
assert.equal(control('price','group').value,'alternatives');assert.equal(control('goals','group').value,'alternatives');
assert.equal(control('club','value').closest('[data-formula-category]').dataset.formulaCategory,'teams');
assert.equal(control('goals','field').closest('[data-formula-category]').dataset.formulaCategory,'players','editing derives the mother from the saved market');
assert.ok(q('[data-preview]').value.includes('('),'expression field displays parentheses for nested logic');
assert.equal(control('goals','field').value,'market:player_goals');
assert.deepEqual(control('goals','operator').querySelectorAll('option').map(option=>option.textContent),['Es','No es'],'market comparison identifies the quoted contract');
assert.match(control('goals','operator').getAttribute('aria-label'),/Comparación/);
await click('[data-save-alert]');assert.deepEqual(saved.at(-1),normalized,'save callback receives exact canonical expression');

// A duplicate changes only its identity/name, retaining the exact logical tree.
const duplicate={...structuredClone(rule),id:null,name:'Copia'};editor.edit(duplicate);
assert.deepEqual(editor.getDefinition(),normalizeUnifiedFormula(duplicate,entities),'duplicate retains nested OR and selected-player reference');
await click('[data-save-alert]');assert.equal(saved.at(-1).id,null);assert.deepEqual(saved.at(-1).expression,normalized.expression);

// Add/remove must not rewrite sibling IDs or leave a second independent formula.
editor.edit(rule);await click('[data-add-group="alternatives"]');
const afterGroup=q('[data-formula-logic]').querySelectorAll('[data-add-group]').map(n=>n.dataset.addGroup);
assert.equal(afterGroup.length,3,'a nested group is part of the same expression');
assert.deepEqual(editor.getDefinition(),normalized,'an entirely blank nested group is inactive');
const addedGroup=afterGroup.find(id=>!['root','alternatives'].includes(id));assert.ok(addedGroup);
await click(`[data-remove-node="${addedGroup}"]`);assert.deepEqual(editor.getDefinition(),normalized);
const oddsMother=()=>q('[data-formula-category="odds"]');
await click('[data-add-category="odds"]');
assert.equal(oddsMother().querySelectorAll('[data-control="group"]').length,2,'a category action adds a row to the existing formula');
const addedId=oddsMother().querySelectorAll('[data-control="field"]').map(n=>n.dataset.nodeId).find(id=>id!=='price');
assert.equal(control(addedId,'group').value,'root','new category rows start in the root group');
assert.throws(()=>editor.getDefinition(),/cuota|valor|n[uú]mero|complet/i,'selected but unfinished condition cannot disappear silently');
await click('[data-save-alert]');assert.equal(saved.length,2,'invalid formula never reaches save callback');
assert.ok(q('[data-alert-error]').value,'validation is shown inside error input');assert.equal(q('[data-alert-error-grid]').hidden,false);
await click(`[data-remove-node="${addedId}"]`);assert.deepEqual(editor.getDefinition(),normalized,'removing incomplete condition restores exact tree');

// Category layout does not change the tree: a condition can move freely across
// nested groups, and an untouched pending row stays inactive when moved.
await set(control('goals','group'),'root');
let moved=editor.getDefinition();
assert.ok(moved.expression.children.some(n=>n.id==='goals'));
assert.deepEqual(moved.expression.children.find(n=>n.id==='alternatives').children.map(n=>n.id),['price']);
assert.equal(moved.expression.children.find(n=>n.id==='alternatives').operator,'O');
assert.equal(moved.expression.children.find(n=>n.id==='goals').playerRef,'person','moving a leaf preserves its selected-player reference');
await set(control('goals','group'),'alternatives');assert.deepEqual(editor.getDefinition(),normalized,'moving a leaf back preserves the original logical tree');
const passiveId=q('[data-formula-category="goals"]').querySelector('[data-control="group"]').dataset.nodeId;
await set(control(passiveId,'group'),'alternatives');assert.deepEqual(editor.getDefinition(),normalized,'moving a passive mother row does not create a predicate');

// Y/O edits affect the stored expression rather than a separate global filter.
await set(control('root','operator'),'O');assert.equal(editor.getDefinition().expression.operator,'O');
assert.equal(editor.getDefinition().expression.children[0].field,'team');
await set(control('alternatives','operator'),'Y');assert.equal(editor.getDefinition().expression.children[2].operator,'Y');
editor.setEntities(structuredClone(entities));assert.equal(editor.getDefinition().expression.operator,'O','entity refresh preserves draft logic');

// Changing a player updates referenced statistics; multiple players require an
// explicit reference, and deleting that identity cannot silently pick another.
editor.edit(rule);
const secondPlayer=entities.players.find(item=>home.playerIds.includes(item.id)&&item.id!==player.id);assert.ok(secondPlayer);
await set(control('person','playerId'),secondPlayer.id);
assert.equal(editor.getDefinition().expression.children[2].children[1].selection.playerId,secondPlayer.id);
await click('[data-add-category="players"]');
const extraPlayerId=q('[data-formula-category="players"]').querySelectorAll('[data-control="playerId"]').map(n=>n.dataset.nodeId).find(id=>id!=='person');
await set(control(extraPlayerId,'teamId'),home.id);await set(control(extraPlayerId,'playerId'),player.id);
assert.equal(control('goals','playerRef').tagName,'SELECT','multiple selected players expose one reference choice');
await set(control('goals','playerRef'),extraPlayerId);
assert.equal(editor.getDefinition().expression.children[2].children[1].selection.playerId,player.id);
await click(`[data-remove-node="${extraPlayerId}"]`);
assert.throws(()=>editor.getDefinition(),/jugador/i,'deleted player reference cannot silently attach to remaining player');

// Switching between legacy and unified editors must leave a single active
// event handler and retain the saved meaning of each format.
const wrapperContainer=new Element('div',{},document);documentRoot.append(wrapperContainer);const wrapperSaves=[];let wrapperCancelled=0;
const wrapper=mountFootballAlertBuilder(wrapperContainer,{entities,onSave:value=>wrapperSaves.push(value),onCancel:()=>wrapperCancelled++});
const legacy=normalizeFootballAlert({...newFootballAlert(),id:'legacy-editor',name:'Alerta existente'},entities);
for(const next of [rule,legacy,rule,legacy]){wrapper.edit(next);await fire('click',wrapperContainer.querySelector('[data-save-alert]'));}
assert.deepEqual(wrapperSaves.map(value=>value.kind),['football-formula','football-alert','football-formula','football-alert'],'one save fires after every editor switch');
assert.deepEqual(wrapperSaves[0],normalized);assert.deepEqual(wrapperSaves[2],normalized);
assert.deepEqual(wrapperSaves[1],wrapperSaves[3],'legacy alert remains unchanged across editor switches');
await fire('click',wrapperContainer.querySelector('[data-cancel-alert]'));
assert.equal(wrapperCancelled,1,'legacy cancel invokes the configured callback once');
const priceMotherTitles=()=>wrapperContainer.querySelectorAll('[data-formula-panel]').filter(panel=>['prices','payments','value','coverage'].includes(panel.dataset.formulaPanel)).map(panel=>panel.querySelector('.collapsible-heading').textContent);
assert.deepEqual(priceMotherTitles(),['Cuotas','Pagos','Valor esperado','Cobertura'],'canceling a legacy edit returns to the four mathematical mothers');
assert.throws(()=>wrapper.getDefinition(),/condici[oó]n|f[oó]rmula|nombre/i,'legacy cancel clears the old definition');
wrapper.edit(legacy);
wrapper.reset();assert.deepEqual(priceMotherTitles(),['Cuotas','Pagos','Valor esperado','Cobertura'],'reset from legacy opens the four mathematical mothers');

// Failed asynchronous saves remain retryable and report through the same field.
const failureContainer=new Element('div',{},document);documentRoot.append(failureContainer);let calls=0;
const failing=mountUnifiedFormulaEditor(failureContainer,{entities,onSave:async()=>{calls++;if(calls===1)throw new Error('Error de almacenamiento');}});
failing.edit(rule);await fire('click',failureContainer.querySelector('[data-save-alert]'));
assert.match(failureContainer.querySelector('[data-alert-error]').value,/almacenamiento/);
assert.equal(failureContainer.querySelector('[data-save-alert]').disabled,false);
await fire('click',failureContainer.querySelector('[data-save-alert]'));assert.equal(calls,2,'save may be retried after storage failure');

editor.edit(rule);await click('[data-cancel-alert]');assert.equal(cancelled,1,'cancel callback fires');
assert.throws(()=>editor.getDefinition(),/condici[oó]n|f[oó]rmula|nombre/i,'cancel returns to a blank formula');
editor.edit(rule);editor.reset();assert.throws(()=>editor.getDefinition(),/condici[oó]n|f[oó]rmula|nombre/i,'reset cannot retain an old expression');
assert.equal(qa('[data-formula-category]').length,categoryIds.length,'reset restores every mother dropdown');
for(const category of FORMULA_CATEGORIES)assert.equal(q(`[data-formula-category="${category.id}"]`).querySelectorAll('[data-control="group"]').length,1,'reset restores one inactive row per mother');
console.log('Unified formula editor: mother categories, filtered markets, passive rows, open-state retention, nested Y/O group moves, exact edit/duplicate/save, retry and reset passed.');
