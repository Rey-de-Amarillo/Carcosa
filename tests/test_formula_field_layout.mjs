/** Creator text belongs to ordinary fields or canonical native panel titles. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mountLegacyFootballAlertBuilder,newFootballAlert,normalizeFootballAlert,playersForTeam} from '../app/football-alert-builder.js';
import {FOOTBALL_MARKET_CATALOG,defaultMarketSelection} from '../app/football-market-catalog.js';
import {newSituationsDraft,compileSituationsAlert} from '../app/football-situations.js';
import {mountUnifiedFormulaEditor} from '../app/football-formula-editor.js';
import {normalizeUnifiedFormula} from '../app/football-unified-formula.js';

const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const container={ownerDocument:{},innerHTML:'',querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}};
const editor=mountLegacyFootballAlertBuilder(container,{entities});
const voidTags=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
const controls=new Set(['input','select','button']);

// The creator emits deliberately simple HTML. Parse its actual output rather
// than asserting that implementation strings happen to occur in the source.
function parse(html){
  const root={tag:'#root',attrs:{},children:[]},stack=[root];
  const tokens=html.match(/<!--[\s\S]*?-->|<(?:[^>"']|"[^"]*"|'[^']*')+>|[^<]+/g)||[];
  for(const token of tokens){
    if(token.startsWith('<!--'))continue;
    if(token.startsWith('</')){
      const tag=token.match(/^<\/\s*([\w-]+)/)?.[1]?.toLowerCase();
      assert.equal(stack.at(-1)?.tag,tag,`well-formed closing ${tag}`);stack.pop();continue;
    }
    if(token.startsWith('<')){
      const tag=token.match(/^<\s*([\w-]+)/)?.[1]?.toLowerCase();assert.ok(tag,'valid element');
      const attrs={};
      for(const match of token.slice(token.indexOf(tag)+tag.length).matchAll(/\s+([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))attrs[match[1]]=match[2]??match[3]??match[4]??'';
      const node={tag,attrs,children:[],parent:stack.at(-1)};node.parent.children.push(node);
      if(!voidTags.has(tag)&&!token.endsWith('/>'))stack.push(node);
    }else stack.at(-1).children.push({tag:'#text',text:token,parent:stack.at(-1)});
  }
  assert.equal(stack.length,1,'all creator containers are closed');return root;
}
function flatten(node){return [node,...node.children?.flatMap(flatten)||[]];}
const classes=node=>(node?.attrs.class||'').split(/\s+/);
const hasClass=(node,name)=>classes(node).includes(name);
const panel=node=>node?.tag==='details'&&(node.attrs['data-formula-category']!==undefined||node.attrs['data-formula-logic']!==undefined);
const summary=node=>node?.tag==='summary'&&panel(node.parent);
const title=node=>node?.tag==='span'&&hasClass(node,'collapsible-title')&&summary(node.parent);
const heading=node=>node?.tag==='span'&&hasClass(node,'collapsible-heading')&&title(node.parent);
const indicator=node=>node?.tag==='span'&&hasClass(node,'collapsible-indicator')&&summary(node.parent);
const textContent=node=>node.tag==='#text'?node.text:(node.children||[]).map(textContent).join('');
const categoryTitles=['Equipos','Jugadores','Cuotas','Resultados','Goles','Córners','Tarjetas','Remates','Fuera de juego','Ligas'];
let checked=0;
function verifyFields(name,html=container.innerHTML){
  const nodes=flatten(parse(html)),elements=nodes.filter(node=>!node.tag.startsWith('#'));
  for(const node of elements){
    assert.ok(!['p','h1','h2','h3','h4','h5','h6','section'].includes(node.tag),`${name}: stray ${node.tag} outside ordinary field structure`);
    if(node.tag==='details'){
      assert.ok(panel(node),`${name}: only formula category/logic mothers may use a native panel`);
      assert.ok(hasClass(node,'panel')&&hasClass(node,'collapsible-panel'),`${name}: mother uses the official native panel classes`);
      const headers=node.children.filter(child=>child.tag==='summary');
      assert.equal(headers.length,1,`${name}: native panel owns one summary`);
      assert.equal(node.children.find(child=>!child.tag.startsWith('#')),headers[0],`${name}: summary is the panel's first element`);
    }
    if(node.tag==='summary'){
      assert.ok(summary(node),`${name}: summary belongs directly to a native formula mother`);
      assert.ok(hasClass(node,'panel-header')&&hasClass(node,'collapsible-summary'),`${name}: summary uses official header classes`);
      assert.equal(node.children.filter(title).length,1,`${name}: header has one canonical title`);
      assert.equal(node.children.filter(indicator).length,1,`${name}: header has one canonical caret`);
    }
    if(node.tag==='span'){
      assert.ok(title(node)||heading(node)||indicator(node),`${name}: span is restricted to the official native header structure`);
      if(title(node))assert.equal(node.children.filter(heading).length,1,`${name}: canonical title contains its heading`);
      if(indicator(node)){
        assert.equal(node.attrs['aria-hidden'],'true',`${name}: decorative native caret is hidden from assistive technology`);
        assert.equal(textContent(node).trim(),'',`${name}: caret cannot contain explanatory text`);
      }
    }
    if(controls.has(node.tag)){
      assert.equal(node.parent.tag,'label',`${name}: ${node.tag} must be directly inside its field label`);
      assert.ok((node.attrs['aria-label']||node.parent.children.some(n=>n.tag==='#text'&&n.text.trim())),`${name}: field has an accessible title`);
      if(node.tag==='button')assert.ok(node.children.some(n=>n.tag==='#text'&&n.text.trim()),`${name}: action has its text inside the control`);
      if(node.attrs['data-node-id']!==undefined){
        let mother=node.parent;while(mother&&!panel(mother))mother=mother.parent;
        assert.ok(mother,`${name}: each condition/group field belongs inside a canonical mother`);
      }
    }
    if(node.tag==='label'){
      const cells=node.children.filter(child=>controls.has(child.tag));
      assert.equal(cells.length,1,`${name}: every field title owns exactly one ordinary control`);
      assert.ok(node.children.some(n=>n.tag==='#text'&&n.text.trim()),`${name}: every field has its title`);
      assert.ok((node.parent.attrs.class||'').split(/\s+/).includes('wk-field-grid'),`${name}: every field uses the common field grid`);
    }
    if(node.tag==='div'&&(node.attrs.class||'').split(/\s+/).includes('football-builder-fields')){
      for(const required of ['entry-form','record-filter-form','wk-field-grid'])assert.ok(node.attrs.class.split(/\s+/).includes(required),`${name}: grid uses canonical ${required}`);
    }
  }
  for(const node of nodes.filter(n=>n.tag==='#text'&&n.text.trim())){
    const parent=node.parent;
    assert.ok(parent.tag==='label'||parent.tag==='option'||parent.tag==='button'||heading(parent),`${name}: text outside a field or canonical panel title: ${node.text.slice(0,100)}`);
    if(parent.tag==='option')assert.equal(parent.parent.tag,'select',`${name}: dropdown choice belongs to a field`);
  }
  const error=elements.find(node=>node.attrs['data-alert-error']!==undefined);
  assert.equal(error?.tag,'input',`${name}: validation errors are a field value`);
  assert.ok(error.attrs.readonly!==undefined,`${name}: validation field is readonly`);
  assert.equal(error.attrs.role,'alert',`${name}: validation field remains accessible`);
  assert.ok(error.parent.attrs['data-alert-error-field']!==undefined,`${name}: error field can be shown/hidden as a unit`);
  checked++;
  return elements;
}
verifyFields('legacy new formula');
const base=normalizeFootballAlert({...newFootballAlert(),id:'legacy',name:'Legacy price ranges'},entities);
editor.edit(base);verifyFields('legacy around price');
editor.edit({...base,id:'calculations',conditions:[{field:'ev',operator:'>=',value:.03},{field:'home_implied',operator:'>=',value:.6}]});verifyFields('legacy calculation conditions');
editor.edit({...base,id:'combination',action:{...base.action,market:'combination',period:'full',legs:[defaultMarketSelection('total_goals'),defaultMarketSelection('btts')]}});verifyFields('multiple selections');
const home=entities.teams.find(team=>team.currentLeagueIds?.includes('E0')&&playersForTeam(entities,team.id,'E0').length);
const player=playersForTeam(entities,home.id,'E0')[0];
const context={...base.context,league:'E0',homeTeam:home.id};
for(const definition of FOOTBALL_MARKET_CATALOG){
  const draft={...newSituationsDraft(),id:`market-${definition.id}`,name:definition.name,context,situations:[{id:'bet-1',role:'bet',price:null,selection:defaultMarketSelection(definition.id)}]};
  if(definition.id.startsWith('player_')||definition.kind==='player_scorer')draft.situations[0].selection.playerId=player.id;
  editor.edit(compileSituationsAlert(draft,entities));verifyFields(definition.id);
}
editor.edit(normalizeFootballAlert({...base,id:'player-half',context,action:{...base.action,...defaultMarketSelection('player_goals'),period:'first_half',playerId:player.id,teamId:home.id}},entities));verifyFields('legacy first-half player');
editor.reset();verifyFields('legacy reset');
// Category mothers use the official native details/summary structure. Their
// bodies retain the common field contract and one arbitrary logical tree.
const unifiedContainer={ownerDocument:{},innerHTML:'',querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}};
const unified=mountUnifiedFormulaEditor(unifiedContainer,{entities});
const editUnified=rule=>unified.edit(normalizeUnifiedFormula(rule,entities));
const verifyUnified=(name,{closed=false}={})=>{
  const elements=verifyFields(name,unifiedContainer.innerHTML),mothers=elements.filter(panel);
  const categories=mothers.filter(node=>node.attrs['data-formula-category']!==undefined);
  assert.equal(categories.length,categoryTitles.length,`${name}: each football family has one mother`);
  assert.equal(new Set(categories.map(node=>node.attrs['data-formula-category'])).size,categories.length,`${name}: category identifiers are unique`);
  assert.deepEqual(categories.map(node=>textContent(flatten(node).find(heading)).trim()).sort(),[...categoryTitles].sort(),`${name}: mothers name the actual football families`);
  for(const node of categories){
    assert.ok(node.attrs['data-formula-category'],`${name}: category has an identity`);
    assert.ok(flatten(node).some(child=>child.attrs?.['data-add-category']===node.attrs['data-formula-category']),`${name}: add action stays inside its own mother`);
  }
  const logic=mothers.filter(node=>node.attrs['data-formula-logic']!==undefined);
  assert.equal(logic.length,1,`${name}: one logic mother edits the shared formula`);
  assert.equal(textContent(flatten(logic[0]).find(heading)).trim(),'Uniones Y/O',`${name}: shared logical groups have their canonical mother`);
  if(closed)for(const node of mothers)assert.equal(node.attrs.open,undefined,`${name}: all mothers begin closed`);
  for(const node of elements.filter(node=>node.tag==='select')){
    const choices=node.children.filter(child=>child.tag==='option');
    assert.ok(!choices.some(option=>textContent(option).trim()==='Elegir condición'),`${name}: no generic condition selector remains`);
    const values=new Set(choices.map(option=>option.attrs.value));
    assert.ok(!['team','player','odds'].every(value=>values.has(value)),`${name}: one generic list cannot mix the separate football families`);
  }
};
verifyUnified('unified blank formula',{closed:true});
const metadata=(id,field,value)=>({type:'condition',id,field,operator:'=',value});
const unifiedRule={kind:'football-formula',version:1,id:'unified-layout',name:'Una fórmula',stake:1,expression:{type:'group',id:'root',operator:'Y',children:[
  metadata('club','team',home.id),metadata('player','player',player.id),
  {type:'group',id:'alternatives',operator:'O',children:[{type:'condition',id:'price',field:'odds',operator:'between',min:1.8,max:2.2},{type:'condition',id:'stat',field:'market',operator:'=',playerRef:'player',selection:{...defaultMarketSelection('player_goals'),playerId:player.id}}]},
]}};
editUnified(unifiedRule);verifyUnified('nested team Y player Y (price O player goals)');
for(const definition of FOOTBALL_MARKET_CATALOG){
  const selection=defaultMarketSelection(definition.id),isPlayer=definition.id.startsWith('player_')||definition.kind==='player_scorer';
  if(isPlayer)selection.playerId=player.id;
  editUnified({...unifiedRule,expression:{type:'group',id:'root',operator:'O',children:[
    metadata('club','team',home.id),...(isPlayer?[metadata('player','player',player.id)]:[]),
    {type:'condition',id:'market',field:'market',operator:'=',selection,...(isPlayer?{playerRef:'player'}:{})},
  ]}});verifyUnified(`unified ${definition.id}`);
}
for(const field of ['home_team','away_team','league']){
  editUnified({...unifiedRule,expression:{type:'group',id:'root',operator:'Y',children:[metadata('metadata',field,field==='league'?'E0':home.id)]}});verifyUnified(`unified ${field}`);
}
editUnified({...unifiedRule,expression:{type:'group',id:'root',operator:'Y',children:[metadata('player1','player',player.id),metadata('player2','player',playersForTeam(entities,home.id,'E0')[1].id),{type:'condition',id:'stat',field:'market',operator:'=',playerRef:'player2',selection:{...defaultMarketSelection('player_shots'),playerId:playersForTeam(entities,home.id,'E0')[1].id}}]}});verifyUnified('unified multiple player references');
unified.reset();verifyUnified('unified reset',{closed:true});
const css=readFileSync(new URL('../app/styles.css',import.meta.url),'utf8');
assert.ok(!/\.football-builder-fields[^}]*\bauto-fit\b/.test(css),'creator fields cannot stretch with an auto-fit grid');
assert.ok(!/\.football-builder-rule-heading[^}]*min-height\s*:\s*30px/.test(css),'no miniature creator controls');
const app=readFileSync(new URL('../app/app.js',import.meta.url),'utf8');
assert.ok(!app.includes("notify('Fórmula guardada')"),'saving cannot create text outside a standard field');
console.log(`Formula field layout: ${checked} real renders, canonical category mothers, field-contained bodies/actions/errors, common grids and legacy variants passed.`);
