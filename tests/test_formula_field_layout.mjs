/** Creator text must live in ordinary fields, apart from their own titles. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mountFootballAlertBuilder,newFootballAlert,normalizeFootballAlert,playersForTeam} from '../app/football-alert-builder.js';
import {FOOTBALL_MARKET_CATALOG,defaultMarketSelection} from '../app/football-market-catalog.js';
import {newSituationsDraft,compileSituationsAlert} from '../app/football-situations.js';

const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const container={ownerDocument:{},innerHTML:'',querySelectorAll:()=>[],addEventListener(){}};
const editor=mountFootballAlertBuilder(container,{entities});
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
let checked=0;
function verifyFields(name){
  const nodes=flatten(parse(container.innerHTML)),elements=nodes.filter(node=>!node.tag.startsWith('#'));
  for(const node of elements){
    assert.ok(!['p','h1','h2','h3','h4','h5','h6','summary','details','section','span'].includes(node.tag),`${name}: stray ${node.tag} outside ordinary field structure`);
    if(controls.has(node.tag)){
      assert.equal(node.parent.tag,'label',`${name}: ${node.tag} must be directly inside its field label`);
      assert.ok((node.attrs['aria-label']||node.parent.children.some(n=>n.tag==='#text'&&n.text.trim())),`${name}: field has an accessible title`);
      if(node.tag==='button')assert.ok(node.children.some(n=>n.tag==='#text'&&n.text.trim()),`${name}: action has its text inside the control`);
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
    assert.ok(parent.tag==='label'||parent.tag==='option'||parent.tag==='button',`${name}: text outside a field: ${node.text.slice(0,100)}`);
    if(parent.tag==='option')assert.equal(parent.parent.tag,'select',`${name}: dropdown choice belongs to a field`);
  }
  const error=elements.find(node=>node.attrs['data-alert-error']!==undefined);
  assert.equal(error?.tag,'input',`${name}: validation errors are a field value`);
  assert.ok(error.attrs.readonly!==undefined,`${name}: validation field is readonly`);
  assert.equal(error.attrs.role,'alert',`${name}: validation field remains accessible`);
  assert.ok(error.parent.attrs['data-alert-error-field']!==undefined,`${name}: error field can be shown/hidden as a unit`);
  checked++;
}
verifyFields('new formula');
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
editor.reset();verifyFields('reset');
const css=readFileSync(new URL('../app/styles.css',import.meta.url),'utf8');
assert.ok(!/\.football-builder-fields[^}]*\bauto-fit\b/.test(css),'creator fields cannot stretch with an auto-fit grid');
assert.ok(!/\.football-builder-rule-heading[^}]*min-height\s*:\s*30px/.test(css),'no miniature creator controls');
const app=readFileSync(new URL('../app/app.js',import.meta.url),'utf8');
assert.ok(!app.includes("notify('Fórmula guardada')"),'saving cannot create text outside a standard field');
console.log(`Formula field layout: ${checked} real renders, field-contained text/actions/errors, common grids and legacy variants passed.`);
