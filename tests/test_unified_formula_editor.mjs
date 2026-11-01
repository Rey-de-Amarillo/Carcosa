/** Test actual editor markup and delegated actions without browser dependencies. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mountUnifiedFormulaEditor} from '../app/football-formula-editor.js';
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
assert.equal(qa('[data-control="field"]').length,1,'new formula starts with one blank condition');
const fieldOptions=q('[data-control="field"]').querySelectorAll('option').map(o=>o.value);
for(const metadata of ['team','home_team','away_team','league','player','odds'])assert.ok(fieldOptions.includes(metadata),`actual ${metadata} field is available`);
for(const market of FOOTBALL_MARKET_CATALOG)assert.ok(fieldOptions.includes(`market:${market.id}`),`${market.name} is an actual selectable market`);
assert.equal(new Set(fieldOptions).size,fieldOptions.length,'condition dropdown has no duplicate choices');

// Build the user's complete example using only the rendered fields/actions.
const creationContainer=new Element('div',{},document);documentRoot.append(creationContainer);let created;
const creator=mountUnifiedFormulaEditor(creationContainer,{entities,onSave:value=>{created=value;}});
const cq=selector=>creationContainer.querySelector(selector),cqa=selector=>creationContainer.querySelectorAll(selector);
const cc=(id,key)=>cq(`[data-node-id="${id}"][data-control="${key}"]`);
const cclick=selector=>fire('click',cq(selector));
await set(cq('[data-definition="name"]'),'Equipo, jugador y alternativas','input');
await set(cq('[data-definition="stake"]'),3,'input');
const rootId=cq('[data-add-condition]').dataset.addCondition,clubId=cq('[data-control="field"]').dataset.nodeId;
await set(cc(clubId,'field'),'team');await set(cc(clubId,'value'),home.id);
await cclick(`[data-add-condition="${rootId}"]`);
const personId=cqa('[data-control="field"]').find(n=>n.value==='').dataset.nodeId;
await set(cc(personId,'field'),'player');await set(cc(personId,'teamId'),home.id);await set(cc(personId,'playerId'),player.id);
await cclick(`[data-add-group="${rootId}"]`);
const alternativeId=cqa('[data-add-condition]').map(n=>n.dataset.addCondition).find(id=>id!==rootId);
await set(cc(alternativeId,'operator'),'O');
const priceId=cqa('[data-control="field"]').find(n=>n.value==='').dataset.nodeId;
await set(cc(priceId,'field'),'odds');await set(cc(priceId,'operator'),'between');await set(cc(priceId,'min'),1.8,'input');await set(cc(priceId,'max'),2.2,'input');
await cclick(`[data-add-condition="${alternativeId}"]`);
const goalsId=cqa('[data-control="field"]').find(n=>n.value==='').dataset.nodeId;
await set(cc(goalsId,'field'),'market:player_goals');
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
const afterGroup=qa('[data-add-condition]').map(n=>n.getAttribute('data-add-condition'));
assert.equal(afterGroup.length,3,'a nested group is part of the same expression');
assert.deepEqual(editor.getDefinition(),normalized,'an entirely blank nested group is inactive');
const addedGroup=afterGroup.find(id=>!['root','alternatives'].includes(id));assert.ok(addedGroup);
await click(`[data-remove-node="${addedGroup}"]`);assert.deepEqual(editor.getDefinition(),normalized);
await click('[data-add-condition="root"]');
assert.equal(qa('[data-control="field"]').length,5,'a new condition joins the existing root');
assert.deepEqual(editor.getDefinition(),normalized,'entirely blank additional condition is inactive');
const addedId=qa('[data-control="field"]').map(n=>n.dataset.nodeId).find(id=>!['club','person','price','goals'].includes(id));
await set(control(addedId,'field'),'odds');
assert.throws(()=>editor.getDefinition(),/cuota|valor|n[uú]mero|complet/i,'selected but unfinished condition cannot disappear silently');
await click('[data-save-alert]');assert.equal(saved.length,2,'invalid formula never reaches save callback');
assert.ok(q('[data-alert-error]').value,'validation is shown inside error input');assert.equal(q('[data-alert-error-grid]').hidden,false);
await click(`[data-remove-node="${addedId}"]`);assert.deepEqual(editor.getDefinition(),normalized,'removing incomplete condition restores exact tree');

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
await click('[data-add-condition="root"]');
const extraPlayerId=qa('[data-control="field"]').find(n=>n.value==='').dataset.nodeId;
await set(control(extraPlayerId,'field'),'player');await set(control(extraPlayerId,'teamId'),home.id);await set(control(extraPlayerId,'playerId'),player.id);
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
assert.ok(wrapperContainer.querySelector('[data-control="field"]'),'canceling a legacy edit returns to the unified creator');
assert.throws(()=>wrapper.getDefinition(),/condici[oó]n|f[oó]rmula|nombre/i,'legacy cancel clears the old definition');
wrapper.edit(legacy);
wrapper.reset();assert.ok(wrapperContainer.querySelector('[data-control="field"]'),'reset from legacy opens unified creator');

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
assert.equal(qa('[data-control="field"]').length,1,'reset contains one blank condition');
console.log('Unified formula editor: nested Y/O, all market fields, exact edit/duplicate/save, empty and incomplete conditions, group actions, retry and reset passed.');
