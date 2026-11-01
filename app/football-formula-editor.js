/** One editable boolean expression. Every visible value/action lives in a common field. */
import {newUnifiedFormula,newUnifiedCondition,normalizeUnifiedFormula,formatUnifiedFormula} from './football-unified-formula.js';
import {FOOTBALL_MARKET_CATALOG,marketDefinition,marketSelectionChoices,marketLineChoices,defaultMarketSelection} from './football-market-catalog.js';

const clone=value=>JSON.parse(JSON.stringify(value));
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=value=>String(value??'').trim()===''?null:Number(value);
const periods=[['full','Partido completo'],['first_half','Primer tiempo'],['second_half','Segundo tiempo']];
const metadata=[['team','Equipo'],['home_team','Local'],['away_team','Visitante'],['league','Liga'],['player','Jugador'],['odds','Cuota'],['home_odds','Cuota del local'],['draw_odds','Cuota del empate'],['away_odds','Cuota del visitante']];
const compare=[['>=','Mayor o igual a'],['>','Mayor que'],['<=','Menor o igual a'],['<','Menor que'],['=','Igual a'],['!=','Distinta de'],['between','Entre']];
const identities=[['=','Es'],['!=','No es']];
const marketNames={player_goals:'Goles del jugador',player_assists:'Asistencias del jugador',player_shots:'Remates del jugador',player_shots_on_target:'Remates al arco del jugador'};
export const unifiedFieldChoices=()=>[...metadata,...FOOTBALL_MARKET_CATALOG.map(m=>[`market:${m.id}`,marketNames[m.id]||m.name])];
const marketFields=test=>FOOTBALL_MARKET_CATALOG.filter(test).map(m=>`market:${m.id}`);
export const FORMULA_CATEGORIES=Object.freeze([
  {id:'teams',name:'Equipos',fields:['team','home_team','away_team'],initial:'team'},
  {id:'players',name:'Jugadores',fields:['player',...marketFields(m=>m.group==='Jugadores')],initial:'player'},
  {id:'odds',name:'Cuotas',fields:['odds','home_odds','draw_odds','away_odds'],initial:'odds'},
  {id:'results',name:'Resultados',fields:marketFields(m=>m.group==='Resultado')},
  {id:'goals',name:'Goles',fields:marketFields(m=>m.group==='Goles')},
  {id:'corners',name:'Córners',fields:['market:corners']},
  {id:'cards',name:'Tarjetas',fields:['market:cards']},
  {id:'shots',name:'Remates',fields:['market:shots','market:shots_on_target']},
  {id:'offsides',name:'Fuera de juego',fields:['market:offsides']},
  {id:'leagues',name:'Ligas',fields:['league'],initial:'league'},
]);
const playerMarket=a=>a?.market?.startsWith('player_')||['first_goalscorer','last_goalscorer'].includes(a?.market);
let editorSequence=0;

export function mountUnifiedFormulaEditor(container,{entities={},onSave=()=>{},onCancel=()=>{}}={}){
  if(!container?.ownerDocument)throw new Error('El creador necesita un contenedor.');
  const instance=++editorSequence;
  let catalog=entities,state=clone(newUnifiedFormula()),editing=false,saving=false,sequence=0;
  let inactive=new Set(),expanded=new Set(),fresh=true;
  const q=s=>container.querySelector(s);
  function nodes(root=state.expression){return root?[root,...(root.children||[]).flatMap(child=>nodes(child))]:[];}
  const find=id=>nodes().find(n=>n.id===id);
  const uid=prefix=>{let id;do{id=`${prefix}-${instance}-${++sequence}`;}while(find(id));return id;};
  const categoryFor=node=>FORMULA_CATEGORIES.find(c=>c.fields.includes(fieldValue(node)))||FORMULA_CATEGORIES.find(c=>c.id===node.category);
  function addDraft(category,passive=true){
    const node={...clone(newUnifiedCondition(category.initial||'')),id:uid('condition'),category:category.id};
    state.expression.children.push(node);if(passive)inactive.add(node.id);return node;
  }
  function prepare(){
    inactive=new Set();expanded=new Set();fresh=true;
    function clean(group){group.children=group.children.filter(n=>n.type==='group'||n.field);group.children.filter(n=>n.type==='group').forEach(clean);}
    clean(state.expression);
    for(const category of FORMULA_CATEGORIES)if(!nodes().some(n=>n.type==='condition'&&categoryFor(n)?.id===category.id))addDraft(category);
  }
  function definitionDraft(){
    const draft=clone(state);
    function clean(group){group.children=group.children.filter(n=>!inactive.has(n.id));group.children.filter(n=>n.type==='group').forEach(clean);}
    clean(draft.expression);return draft;
  }
  function groups(group=state.expression,path='1',parent=null){return [{group,path,parent},...(group.children||[]).flatMap((n,i)=>n.type==='group'?groups(n,`${path}.${i+1}`,group):[])];}
  const groupChoices=()=>groups().map(({group,path})=>[group.id,group===state.expression?'Fórmula':`Grupo ${path}`]);
  const parentOf=id=>groups().find(({group})=>group.children.some(n=>n.id===id))?.group;
  function conditionEntries(group=state.expression,path='1'){
    return group.children.flatMap((node,i)=>node.type==='group'?conditionEntries(node,`${path}.${i+1}`):[{node,path:`${path}.${i+1}`,group}]);
  }
  function panel(title,key,body,extra=''){
    return `<details class="panel parking-registration-contract-vehicle collapsible-panel football-formula-mother" ${extra} data-formula-panel="${esc(key)}" ${expanded.has(key)?'open':''}><summary class="panel-header collapsible-summary parking-registration-contract-vehicle-summary"><span class="collapsible-title"><span class="collapsible-heading">${esc(title)}</span></span><span class="collapsible-indicator" aria-hidden="true"></span></summary><div class="parking-registration-contract-vehicle-body parking-registration-contract-primary-vehicle-body">${body}</div></details>`;
  }
  const options=(list,value)=>list.map(([id,label])=>`<option value="${esc(id)}" ${String(id)===String(value??'')?'selected':''}>${esc(label)}</option>`).join('');
  const cell=(title,control)=>`<label>${esc(title)}${control}</label>`;
  const grid=content=>`<div class="entry-form record-filter-form wk-field-grid football-builder-fields">${content}</div>`;
  const attrs=(node,key)=>`data-node-id="${esc(node.id)}" data-control="${esc(key)}"`;
  const select=(node,key,list,value,label,extra='')=>`<select ${attrs(node,key)} aria-label="${esc(label)}" ${extra}>${options(list,value)}</select>`;
  const input=(node,key,value,label,extra='')=>`<input ${attrs(node,key)} type="number" step="any" data-number value="${esc(value??'')}" aria-label="${esc(label)}" ${extra}>`;
  const readonly=(value,label,extra='')=>`<input type="text" readonly value="${esc(value)}" aria-label="${esc(label)}" title="${esc(value)}" ${extra}>`;
  const action=(title,text,attributes)=>cell(title,`<button type="button" class="button button-neutral" ${attributes} aria-label="${esc(text)}">${esc(text)}</button>`);
  const teamName=id=>(catalog.teams||[]).find(t=>t.id===id)?.name||'';
  const playerName=id=>(catalog.players||[]).find(p=>p.id===id)?.name||'';
  const teams=()=>[['','Cualquier equipo'],...(catalog.teams||[]).map(t=>[t.id,t.name])];
  const playerBindings=()=>nodes().filter(n=>n.type==='condition'&&n.field==='player'&&n.playerId);
  function players(teamId){return teamId?(catalog.players||[]).filter(p=>p.teamId===teamId).sort((a,b)=>a.name.localeCompare(b.name)):[];}
  function fieldValue(node){return node.field==='market'?`market:${node.selection?.market||'match_result'}`:node.field||'';}
  function teamTargets(selection){
    const definition=marketDefinition(selection.market),list=definition?.teamScope==='both'?[['total','Ambos equipos']]:[];
    list.push(['home','Local'],['away','Visitante']);
    const selected=new Set(nodes().filter(n=>['team','home_team','away_team'].includes(n.field)&&n.value).map(n=>n.value));
    if(selection.team==='selected'&&selection.teamId)selected.add(selection.teamId);
    for(const id of selected)list.push([`named:${id}`,teamName(id)||id]);
    return list;
  }
  function countLines(selection){
    const values=marketLineChoices(selection.market,selection.selection).slice();
    if(selection.line!=null&&!values.includes(Number(selection.line)))values.push(Number(selection.line));
    return values.sort((a,b)=>a-b).map(n=>[n,selection.selection==='at_least'?`${n}+`:`${['asian_handicap','handicap_result'].includes(selection.market)&&n>0?'+':''}${String(n).replace('.',',')}`]);
  }
  function marketControls(node,path){
    const a=node.selection,d=marketDefinition(a.market),label=text=>`${text}, condición ${path}`;
    let fields='';
    if(playerMarket(a)){
      const bindings=playerBindings(),binding=bindings.find(p=>p.id===node.playerRef);
      fields+=cell('Jugador',bindings.length===1&&binding?readonly(playerName(binding.playerId),label('Jugador')):select(node,'playerRef',[['','Elegir jugador'],...bindings.map(p=>[p.id,playerName(p.playerId)])],node.playerRef,label('Jugador')));
    }else if(['team','both'].includes(d?.teamScope))fields+=cell('Equipo',select(node,'selection.team',teamTargets(a),a.team==='selected'?`named:${a.teamId}`:a.team,label('Equipo')));
    if(a.market==='correct_score'){
      const scores=[];for(let h=0;h<=6;h++)for(let v=0;v<=6;v++)scores.push([`${h}-${v}`,`${h} – ${v}`]);
      const value=a.homeGoals==null||a.awayGoals==null?'':`${a.homeGoals}-${a.awayGoals}`;
      if(value&&!scores.some(([id])=>id===value))scores.push([value,`${a.homeGoals} – ${a.awayGoals}`]);
      fields+=cell('Marcador',select(node,'score',[['','Elegir marcador'],...scores],value,label('Marcador')));
    }else {
      const choices=marketSelectionChoices(a.market);
      if(choices.length)fields+=cell('Selección',select(node,'selection.selection',choices,a.selection,label('Selección')));
      if(['count','player_count','asian_handicap','handicap_result'].includes(d?.kind))fields+=cell(['asian_handicap','handicap_result'].includes(a.market)?'Hándicap':'Cantidad',select(node,'selection.line',countLines(a),a.line,label('Cantidad'),'data-number'));
    }
    const allowed=periods.filter(([id])=>d?.periods.includes(id)||a.period===id);
    if(allowed.length>1)fields+=cell('Período',select(node,'selection.period',allowed,a.period,label('Período')));
    fields+=cell('Comparación',select(node,'operator',[['=','Es'],['!=','No es']],node.operator||'=',label('Comparación')));
    return fields;
  }
  function renderCondition(node,path,category){
    const label=text=>`${text}, condición ${path}`;
    const choices=unifiedFieldChoices().filter(([id])=>category.fields.includes(id));
    if(!node.field)choices.unshift(['','Elegir mercado']);
    let fields=category.fields.length>1||!node.field?cell(category.initial?'Tipo':'Mercado',select(node,'field',choices,fieldValue(node),label(category.initial?'Tipo':'Mercado'))):'';
    if(['team','home_team','away_team','league'].includes(node.field)){
      const list=node.field==='league'?[['','Elegir liga'],...(catalog.leagues||[]).map(l=>[l.id,l.name])]:[['','Elegir equipo'],...teams().slice(1)];
      fields+=cell('Comparación',select(node,'operator',identities,node.operator||'=',label('Comparación')))+cell(node.field==='league'?'Liga':'Equipo',select(node,'value',list,node.value,label('Valor')));
    }else if(node.field==='player'){
      fields+=cell('Equipo del jugador',select(node,'teamId',[['','Elegir equipo'],...teams().slice(1)],node.teamId,label('Equipo del jugador')))+
        cell('Jugador',select(node,'playerId',[['','Elegir jugador'],...players(node.teamId).map(p=>[p.id,p.name])],node.playerId,label('Jugador'),node.teamId?'':'disabled'))+
        cell('Comparación',select(node,'operator',identities,node.operator||'=',label('Comparación')));
    }else if(['odds','home_odds','draw_odds','away_odds'].includes(node.field)){
      const comparisons=compare.slice();if(node.operator==='around')comparisons.push(['around','Con margen']);
      fields+=cell('Comparación',select(node,'operator',comparisons,node.operator||'>=',label('Comparación')));
      if(node.operator==='between')fields+=cell('Desde',input(node,'min',node.min,label('Desde'),'min="1.01"'))+cell('Hasta',input(node,'max',node.max,label('Hasta'),'min="1.01"'));
      else fields+=cell('Cuota',input(node,'value',node.value,label('Cuota'),'min="1.01"'));
      if(node.operator==='around')fields+=cell('Margen',input(node,'margin',node.margin,label('Margen'),'min="0"'));
    }else if(node.field==='market'&&node.selection)fields+=marketControls(node,path);
    fields+=cell('Grupo',select(node,'group',groupChoices(),parentOf(node.id)?.id,label('Grupo')))+action(`Condición ${path}`,'Quitar condición',`data-remove-node="${esc(node.id)}"`);
    return grid(fields);
  }
  function renderGroup(group,path='1',root=true){
    let fields=cell(root?'Unir condiciones':`Unión del grupo ${path}`,select(group,'operator',[['Y','Y'],['O','O']],group.operator||'Y',root?'Unir condiciones':`Unión del grupo ${path}`))+
      action(`Grupo ${path}`,'Agregar grupo',`data-add-group="${esc(group.id)}"`);
    if(!root)fields+=action(`Grupo ${path}`,'Quitar grupo',`data-remove-node="${esc(group.id)}"`);
    return grid(fields)+(group.children||[]).map((node,index)=>node.type==='group'?renderGroup(node,`${path}.${index+1}`,false):'').join('');
  }
  function render(){
    if(!fresh)for(const section of container.querySelectorAll('[data-formula-panel]'))section.hasAttribute('open')?expanded.add(section.dataset.formulaPanel):expanded.delete(section.dataset.formulaPanel);
    fresh=false;
    const selectedTeams=[...new Set(nodes().filter(n=>!inactive.has(n.id)&&['team','home_team','away_team'].includes(n.field)&&n.operator!=='!='&&n.value).map(n=>n.value))];
    if(selectedTeams.length===1)for(const node of nodes())if(inactive.has(node.id)&&node.field==='player'&&!node.teamId)node.teamId=selectedTeams[0];
    const entries=conditionEntries();
    container.innerHTML=grid(cell('Nombre de la fórmula',`<input data-definition="name" type="text" maxlength="100" value="${esc(state.name||'')}" aria-label="Nombre de la fórmula" autocomplete="off">`)+
      cell('Importe (u)',`<input data-definition="stake" type="number" min="0.01" step="any" value="${esc(state.stake??1)}" aria-label="Importe por apuesta">`))+
      '<div class="parking-registration-contract-vehicle-list">'+FORMULA_CATEGORIES.map(category=>panel(category.name,category.id,entries.filter(({node})=>categoryFor(node)?.id===category.id).map(({node,path})=>renderCondition(node,path,category)).join('')+grid(action(category.name,'Agregar condición',`data-add-category="${category.id}"`)),`data-formula-category="${category.id}"`)).join('')+
      panel('Uniones Y/O','logic',renderGroup(state.expression),'data-formula-logic')+'</div>'+
      grid(cell('Fórmula',readonly('','Fórmula completa','data-preview'))+
        cell('Guardar',`<button type="button" class="button primary" data-save-alert aria-label="${editing?'Guardar cambios':'Guardar fórmula'}">${editing?'Guardar cambios':'Guardar fórmula'}</button>`)+
        (editing?action('Edición','Cancelar edición','data-cancel-alert'):''))+
      `<div class="entry-form record-filter-form wk-field-grid football-builder-fields" data-alert-error-grid hidden><label data-alert-error-field>Error<input type="text" data-alert-error readonly role="alert" aria-live="polite" aria-label="Error"></label></div>`;
    preview();
  }
  function capture(){
    for(const control of container.querySelectorAll('[data-definition]'))state[control.dataset.definition]=control.dataset.definition==='stake'?number(control.value):control.value;
    for(const control of container.querySelectorAll('[data-node-id][data-control]')){
      const node=find(control.dataset.nodeId),key=control.dataset.control;if(!node||key==='field'||key==='group')continue;
      if(key==='score'){
        const parts=control.value.split('-');node.selection.homeGoals=control.value?Number(parts[0]):null;node.selection.awayGoals=control.value?Number(parts[1]):null;continue;
      }
      let target=node;const keys=key.split('.');for(const part of keys.slice(0,-1)){target[part]??={};target=target[part];}
      target[keys.at(-1)]=control.hasAttribute('data-number')?number(control.value):control.value;
    }
    for(const node of nodes())if(node.selection&&String(node.selection.team).startsWith('named:')){node.selection.teamId=node.selection.team.slice(6);node.selection.team='selected';}
    return state;
  }
  function preview(){
    const target=q('[data-preview]');if(!target)return;
    try{const normalized=normalizeUnifiedFormula({...definitionDraft(),name:String(state.name||'').trim()||'Fórmula'},catalog);target.value=formatUnifiedFormula(normalized,catalog);target.title=target.value;}catch{target.value='';target.title='';}
  }
  function error(problem){const target=q('[data-alert-error]');if(!target)return;target.value=problem?.message||String(problem||'');target.title=target.value;q('[data-alert-error-grid]').hidden=!target.value;}
  function setField(node,value){
    const id=node.id,category=node.category,next=clone(newUnifiedCondition(value.startsWith('market:')?'market':value));
    for(const key of Object.keys(node))delete node[key];Object.assign(node,next,{id,type:'condition',category});
    if(value.startsWith('market:')){
      node.field='market';node.operator='=';node.selection=defaultMarketSelection(value.slice(7));
      if(playerMarket(node.selection)){
        const bindings=playerBindings();if(bindings.length===1)node.playerRef=bindings[0].id;
      }
    }else {node.field=value;node.operator=['odds','home_odds','draw_odds','away_odds'].includes(value)?'>=':'=';
      if(value==='player'){const selected=[...new Set(nodes().filter(n=>['team','home_team','away_team'].includes(n.field)&&n.operator!=='!='&&n.value).map(n=>n.value))];if(selected.length===1)node.teamId=selected[0];}
    }
  }
  function clearDanglingPlayers(){
    const ids=new Set(playerBindings().map(n=>n.id));
    for(const node of nodes())if(node.playerRef&&!ids.has(node.playerRef)){node.playerRef='';if(node.selection){node.selection.playerId='';node.selection.teamId='';}}
  }
  function remove(id,group=state.expression){
    const index=(group.children||[]).findIndex(n=>n.id===id);if(index>=0){group.children.splice(index,1);return true;}
    return (group.children||[]).some(n=>n.type==='group'&&remove(id,n));
  }
  const getDefinition=()=>{capture();return normalizeUnifiedFormula(definitionDraft(),catalog);};
  container.addEventListener('submit',e=>e.preventDefault());
  container.addEventListener('input',event=>{if(event.target.tagName==='INPUT'&&!event.target.readOnly){if(event.target.dataset.nodeId)inactive.delete(event.target.dataset.nodeId);capture();error('');preview();}});
  container.addEventListener('change',event=>{
    const control=event.target;if(!control.matches('[data-node-id][data-control]'))return;
    const node=find(control.dataset.nodeId);if(!node)return;
    const previous=clone(node),key=control.dataset.control,value=control.value;capture();
    if(key==='group'){
      const destination=find(value),source=parentOf(node.id);
      if(destination?.type==='group'&&source&&source!==destination){source.children=source.children.filter(n=>n.id!==node.id);destination.children.push(node);}
      error('');render();return;
    }
    if(node.type==='condition')inactive.delete(node.id);
    if(key==='field'){setField(node,value);clearDanglingPlayers();}
    if(node.field==='player'&&key==='teamId'&&node.playerId&&!(catalog.players||[]).some(p=>p.id===node.playerId&&(!node.teamId||p.teamId===node.teamId)))node.playerId='';
    if(node.field==='market'&&key==='selection.selection'){
      const lines=marketLineChoices(node.selection.market,node.selection.selection);if(lines.length&&!lines.includes(node.selection.line))node.selection.line=lines.includes(marketDefinition(node.selection.market).defaultLine)?marketDefinition(node.selection.market).defaultLine:lines[0];
    }
    if(node.field==='market'&&key==='playerRef'){node.selection.playerId='';node.selection.teamId='';node.selection.team='selected';}
    if(['odds','home_odds','draw_odds','away_odds'].includes(node.field)&&key==='operator'){
      const lo=previous.operator==='between'?previous.min:previous.operator==='around'&&previous.value!=null&&previous.margin!=null?previous.value-previous.margin:previous.value;
      const hi=previous.operator==='between'?previous.max:previous.operator==='around'&&previous.value!=null&&previous.margin!=null?previous.value+previous.margin:previous.value;
      delete node.value;delete node.min;delete node.max;delete node.margin;
      if(value==='between'){node.min=lo??null;node.max=hi??null;}
      else if(value==='around'){node.value=lo==null||hi==null?null:(lo+hi)/2;node.margin=lo==null||hi==null?null:(hi-lo)/2;}
      else node.value=['<=','<'].includes(value)?hi??null:lo??null;
    }
    error('');render();
  });
  container.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||!container.contains(button))return;
    try{
      if(button.hasAttribute('data-save-alert')&&!saving){const definition=getDefinition();saving=true;button.disabled=true;await onSave(definition);error('');}
      else if(button.hasAttribute('data-cancel-alert')){reset();onCancel();}
      else if(button.hasAttribute('data-add-category')){
        capture();if(nodes().length>=100)throw new Error('Máximo 100 condiciones y grupos.');
        const category=FORMULA_CATEGORIES.find(c=>c.id===button.dataset.addCategory);if(!category)throw new Error('Elegí una categoría válida.');
        addDraft(category,false);render();
      }
      else if(button.hasAttribute('data-add-group')){
        capture();if(nodes().length>=100)throw new Error('Máximo 100 condiciones y grupos.');
        const group=find(button.dataset.addGroup);if(group?.type!=='group')throw new Error('Elegí un grupo válido.');
        group.children.push({type:'group',id:uid('group'),operator:'Y',children:[]});
        render();
      }else if(button.hasAttribute('data-remove-node')){capture();remove(button.dataset.removeNode);clearDanglingPlayers();render();}
    }catch(problem){error(problem);}finally{saving=false;if(button.isConnected)button.disabled=false;}
  });
  function edit(rule){state=clone(rule);editing=Boolean(rule.id);prepare();render();}
  function reset(){state=clone(newUnifiedFormula());editing=false;prepare();render();}
  function setEntities(next){capture();catalog=next||{};render();}
  prepare();render();return {edit,reset,getDefinition,setEntities};
}
