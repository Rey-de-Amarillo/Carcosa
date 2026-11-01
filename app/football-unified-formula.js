/** One boolean expression over concrete archived betting contracts.
 * Team metadata scopes the event; player, market and odds belong to the same
 * offered contract. Results are used only after matching, for settlement.
 */
import {defaultMarketSelection,marketDefinition,marketSelectionChoices,footballMarketLabel} from './football-market-catalog.js';
import {settleFootballAction,summarizeFootballAlerts,validateFootballStrategy,DEFAULT_ROSTER_MAX_AGE_DAYS} from './football-strategy-engine.js';

export const UNIFIED_FORMULA_KIND='football-formula';
export const UNIFIED_CONDITION_FIELDS=Object.freeze(['team','home_team','away_team','league','player','odds','home_odds','draw_odds','away_odds','market']);
const fields=new Set(UNIFIED_CONDITION_FIELDS);
const priceFields=new Set(['odds','home_odds','draw_odds','away_odds']);
const playerMarkets=new Set(['player_goals','player_shots','player_shots_on_target','player_assists','first_goalscorer','last_goalscorer']);
const identities=new Set(['team','home_team','away_team','league']);
const numeric=value=>typeof value==='number'&&Number.isFinite(value);
const odds=value=>numeric(value)&&value>1;
const probability=value=>numeric(value)&&value>=0&&value<=1;
const list=value=>Array.isArray(value)?value:value&&typeof value==='object'?Object.values(value):[];
const fold=value=>String(value??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('es').replace(/[^a-z0-9]/g,'');
const day=event=>String(event.date||event.startDate||event.kickoff||'').slice(0,10);
const clone=value=>JSON.parse(JSON.stringify(value));
const period=value=>({ft:'full',full_time:'full',ht:'first_half',half_time:'first_half','1h':'first_half','2h':'second_half'})[value]||value||'full';
const market=value=>({h2h:'match_result',three_way:'match_result',correctScore:'correct_score',totals:'total_goals',totals25:'total_goals',both_teams_to_score:'btts'})[value]||value;
const selection=value=>({H:'home',D:'draw',A:'away','1':'home',X:'draw','2':'away',Yes:'yes',No:'no',Over:'over',Under:'under'})[value]||String(value??'').toLowerCase();
const rounded=value=>Number(value.toPrecision(15));
const number=(value,label)=>{if(value==null||String(value).trim()===''||!Number.isFinite(Number(value)))throw new Error(`Completá ${label}.`);return Number(value);};
const nameFor=(items,id,fallback)=>id==null||id===''?fallback:list(items).find(item=>String(item.id)===String(id))?.name||fallback;
let sequence=0;

export function newUnifiedCondition(field=''){
  const node={type:'condition',id:`condition-${++sequence}`,field,operator:priceFields.has(field)?'>=':'='};
  if(field==='market')node.selection=defaultMarketSelection('match_result');
  else if(field==='player'){node.playerId='';node.teamId='';}
  else node.value=priceFields.has(field)?null:'';
  return node;
}
export function newUnifiedFormula(){
  return {kind:UNIFIED_FORMULA_KIND,version:1,id:null,name:'',stake:1,expression:{type:'group',id:'group-1',operator:'Y',children:[newUnifiedCondition()]}};
}

function requireIdentity(value,items,label){
  if(value==null||!String(value).trim())throw new Error(`Elegí ${label}.`);
  const id=String(value);
  if(Array.isArray(items)&&!items.some(item=>String(item.id)===id))throw new Error(`El ${label} no está en el catálogo.`);
  return id;
}
function normalizeMarket(raw,entities,reference){
  if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new Error('Elegí un mercado.');
  const definition=marketDefinition(raw.market);
  if(!definition)throw new Error('Elegí un mercado válido.');
  const defaults=defaultMarketSelection(raw.market),result={};
  for(const key of ['market','period','selection','team','teamId','playerId','line','homeGoals','awayGoals'])result[key]=raw[key]===undefined?defaults[key]:raw[key];
  result.period=period(result.period);result.selection=selection(result.selection);
  const periods=result.market==='player_goals'?['full','first_half','second_half']:definition.periods;
  if(!periods.includes(result.period))throw new Error('Elegí un período válido para ese mercado.');
  if(reference){
    if(!playerMarkets.has(result.market))throw new Error('La referencia de jugador corresponde a un mercado de jugador.');
    result.playerId=reference.playerId;result.teamId=reference.teamId||'';result.team='selected';
  }
  if(result.market==='asian_handicap')result.team=result.selection;
  const choices=marketSelectionChoices(result.market);
  if(choices.length&&!choices.some(([id])=>id===result.selection))throw new Error('Elegí una selección del mercado.');
  if(['count','player_count','asian_handicap','handicap_result'].includes(definition.kind))result.line=number(result.line,'la cantidad');
  if(result.market==='correct_score'){
    result.homeGoals=number(result.homeGoals,'los goles del local');result.awayGoals=number(result.awayGoals,'los goles del visitante');
  }
  if(['team','both'].includes(definition.teamScope)||playerMarkets.has(result.market)||result.market==='asian_handicap'){
    if(!['home','away','selected','total'].includes(result.team))throw new Error('Elegí el equipo del mercado.');
    if(result.team==='total'&&definition.teamScope!=='both')throw new Error('Elegí un equipo para ese mercado.');
  }
  if(playerMarkets.has(result.market)){
    result.playerId=requireIdentity(result.playerId,entities.players,'jugador');
    const player=list(entities.players).find(item=>String(item.id)===result.playerId);
    result.teamId=result.teamId?requireIdentity(result.teamId,entities.teams,'equipo'):player?.teamId?String(player.teamId):'';
    if(player&&result.teamId&&String(player.teamId)!==result.teamId)throw new Error('El jugador no pertenece al equipo seleccionado.');
  }else {
    result.playerId='';
    result.teamId=result.team==='selected'?requireIdentity(result.teamId,entities.teams,'equipo'):'';
  }
  validateFootballStrategy({conditions:[],action:{...result,stake:1}});
  return result;
}

/** Canonicalization is deliberately independent of legacy alert authoring. */
export function normalizeUnifiedFormula(raw,entities={}){
  if(!raw||raw.kind&&raw.kind!==UNIFIED_FORMULA_KIND)throw new Error('La fórmula no pertenece a este editor.');
  if(raw.version!=null&&raw.version!==1)throw new Error('La versión de esta fórmula no es compatible con este editor.');
  const name=String(raw.name||'').trim();if(!name)throw new Error('Poné un nombre a la fórmula.');
  const stake=number(raw.stake??1,'el importe');if(stake<=0)throw new Error('El importe debe ser mayor que cero.');
  const ids=new Set(),players=new Map(),pending=[];let total=0;
  function visit(node,path,depth){
    if(depth>12)throw new Error('Podés anidar hasta 12 niveles de grupos.');
    if(!node||typeof node!=='object'||Array.isArray(node))throw new Error('La condición no es válida.');
    if(node.type==='condition'&&!node.field)return null;
    const id=String(node.id||path);if(ids.has(id))throw new Error('Cada condición y grupo necesita un identificador distinto.');ids.add(id);
    if(node.type==='group'){
      if(!['Y','O'].includes(node.operator))throw new Error('Elegí Y u O para unir las condiciones.');
      if(!Array.isArray(node.children))throw new Error('El grupo necesita una lista de condiciones.');
      const children=node.children.map((child,index)=>visit(child,`${path}-${index+1}`,depth+1)).filter(Boolean);
      return children.length?{type:'group',id,operator:node.operator,children}:null;
    }
    if(node.type!=='condition'||!fields.has(node.field))throw new Error('Elegí una condición válida.');
    if(++total>100)throw new Error('Podés usar hasta 100 condiciones.');
    const operator=node.operator==='=='?'=':node.operator||'=',result={type:'condition',id,field:node.field,operator};
    if(identities.has(node.field)){
      if(!['=','!='].includes(operator))throw new Error('Elegí Es o No es para esa condición.');
      result.value=requireIdentity(node.value??node.teamId,node.field==='league'?entities.leagues:entities.teams,node.field==='league'?'liga':'equipo');
    }else if(node.field==='player'){
      if(!['=','!='].includes(operator))throw new Error('Elegí Es o No es para el jugador.');
      result.playerId=requireIdentity(node.playerId||node.value,entities.players,'jugador');
      const player=list(entities.players).find(item=>String(item.id)===result.playerId);
      result.teamId=node.teamId?requireIdentity(node.teamId,entities.teams,'equipo'):player?.teamId?String(player.teamId):'';
      if(player&&result.teamId&&String(player.teamId)!==result.teamId)throw new Error('El jugador no pertenece al equipo seleccionado.');
      players.set(id,result);
    }else if(priceFields.has(node.field)){
      if(!['>=','>','<=','<','=','!=','between','around'].includes(operator))throw new Error('Elegí una comparación de cuota.');
      if(operator==='between'){
        result.min=number(node.min,'la cuota mínima');result.max=number(node.max,'la cuota máxima');
      }else if(operator==='around'){
        const value=number(node.value,'la cuota'),margin=number(node.margin,'el margen');
        if(margin<0)throw new Error('El margen debe ser cero o mayor.');
        result.operator='between';result.min=rounded(value-margin);result.max=rounded(value+margin);
      }else result.value=number(node.value,'la cuota');
      if(result.operator==='between'&&result.min>result.max)throw new Error('La cuota mínima debe ser menor o igual a la máxima.');
      if((result.operator==='between'?[result.min,result.max]:[result.value]).some(value=>value<1))throw new Error('La cuota del filtro debe ser 1 o mayor.');
    }else if(node.field==='market'){
      if(!['=','!='].includes(operator))throw new Error('Elegí Es o No es para el mercado.');
      if(node.playerRef)result.playerRef=String(node.playerRef);
      pending.push({result,selection:node.selection});
    }
    return result;
  }
  let expression=visit(raw.expression,'group-1',0);
  if(!expression)throw new Error('Agregá al menos una condición.');
  if(expression.type!=='group')expression={type:'group',id:ids.has('root')?'root-group':'root',operator:'Y',children:[expression]};
  for(const item of pending){
    const reference=item.result.playerRef?players.get(item.result.playerRef):null;
    if(item.result.playerRef&&!reference)throw new Error('La condición se refiere a un jugador que no existe en la fórmula.');
    item.result.selection=normalizeMarket(item.selection,entities,reference);
  }
  return {kind:UNIFIED_FORMULA_KIND,version:1,id:raw.id||null,name:name.slice(0,100),stake,expression};
}

export function unifiedFormulaFromLegacy(raw,entities={}){
  if(raw?.kind===UNIFIED_FORMULA_KIND)return normalizeUnifiedFormula(raw,entities);
  throw new Error('Esta fórmula guardada conserva su editor y motor originales.');
}

const fieldNames={team:'Equipo',home_team:'Local',away_team:'Visitante',league:'Liga',player:'Jugador',odds:'Cuota',home_odds:'Cuota local',draw_odds:'Cuota empate',away_odds:'Cuota visitante'};
const comparisonNames={'>=':'≥','>':'>','<=':'≤','<':'<','=':'=','!=':'≠'};
const displayNumber=value=>numeric(value)?value.toLocaleString('es-AR',{maximumFractionDigits:10}):'';
export function formatUnifiedFormula(rule,entities={}){
  function format(node){
    if(!node)return '';
    if(node.type==='group'){
      const children=(node.children||[]).map(format).filter(Boolean);return children.length?`(${children.join(` ${node.operator==='O'?'O':'Y'} `)})`:'';
    }
    if(!node.field)return '';
    const name=fieldNames[node.field]||'Condición',op=comparisonNames[node.operator]||'=';
    if(identities.has(node.field))return `${name} ${op} ${nameFor(node.field==='league'?entities.leagues:entities.teams,node.value??node.teamId,node.field==='league'?'Liga seleccionada':'Equipo seleccionado')}`;
    if(node.field==='player')return `${name} ${op} ${nameFor(entities.players,node.playerId||node.value,'Jugador seleccionado')}`;
    if(node.field==='market'){
      const a=node.selection||{},team=nameFor(entities.teams,a.teamId,'Equipo'),person=nameFor(entities.players,a.playerId,'Jugador');
      const label=footballMarketLabel(a,{home:a.team==='selected'?team:'Local',away:'Visitante',player:person});
      return node.operator==='!='?`NO (${label})`:label;
    }
    if(node.operator==='between')return `${name} entre ${displayNumber(node.min)} y ${displayNumber(node.max)}`;
    if(node.operator==='around')return `${name} ${displayNumber(node.value)} ± ${displayNumber(node.margin)}`;
    return `${name} ${op} ${displayNumber(node.value)}`;
  }
  return format(rule?.expression||rule);
}

function createCatalog(entities,rosterMaxAgeDays){
  const byTeam=new Map(list(entities.teams).map(item=>[String(item.id),item])),byPlayer=new Map(list(entities.players).map(item=>[String(item.id),item]));
  const scoped=new Map(),global=new Map();
  for(const team of byTeam.values())for(const value of [team.name,...list(team.aliases)]){
    const key=fold(value);if(!key)continue;
    for(const league of list(team.leagueIds))scoped.set(`${league}|${key}`,String(team.id));
    if(!global.has(key))global.set(key,String(team.id));else if(global.get(key)!==String(team.id))global.set(key,null);
  }
  return {entities,byTeam,byPlayer,rosterMaxAgeDays,resolve(event,side){
    const explicit=event[`${side}TeamId`]??event[`${side}_team_id`];if(explicit!=null)return String(explicit);
    const key=fold(event[side]??event[`${side}_team`]);return scoped.get(`${event.league||event.league_code}|${key}`)||global.get(key)||null;
  }};
}
function teamMatches(event,side,id,catalog){
  const explicit=event[`${side}TeamId`]??event[`${side}_team_id`],name=event[side]??event[`${side}_team`];
  if(explicit!=null)return String(explicit)===String(id);
  const resolved=catalog.resolve(event,side);if(resolved)return resolved===String(id);
  if(name==null||String(name).trim()==='')return null;
  const team=catalog.byTeam.get(String(id));
  return team?[team.name,...list(team.aliases)].some(alias=>fold(alias)===fold(name)):fold(name)===fold(id);
}
function or(values){return values.includes(true)?true:values.includes(null)?null:false;}
function invert(value,operator){return value==null?null:operator==='!='?!value:value;}
function compare(actual,node){
  if(!numeric(actual))return null;
  if(node.operator==='between')return actual>=node.min&&actual<=node.max;
  return ({'>=':()=>actual>=node.value,'>':()=>actual>node.value,'<=':()=>actual<=node.value,'<':()=>actual<node.value,'=':()=>actual===node.value,'!=':()=>actual!==node.value})[node.operator]();
}
function contract(raw){
  const m=market(raw.market||'match_result'),s=raw.selection??(['home','draw','away'][Number(raw.side)]);
  const result={market:m,period:period(raw.period),selection:selection(s)};
  for(const key of ['team','teamId','playerId','line','homeGoals','awayGoals'])if(raw[key]!=null)result[key]=raw[key];
  if(m==='correct_score'){
    const score=String(raw.selection||'').match(/^(\d+)\s*[-:]\s*(\d+)$/);if(score){result.homeGoals??=Number(score[1]);result.awayGoals??=Number(score[2]);}
  }
  for(const key of ['line','homeGoals','awayGoals'])if(result[key]!=null&&String(result[key]).trim()!=='')result[key]=Number(result[key]);
  return result;
}
const contractKey=action=>JSON.stringify(['market','period','selection','team','teamId','playerId','line','homeGoals','awayGoals'].map(key=>action[key]??null));
const snapshotKey=quote=>String(quote.snapshotId??quote.quoteSnapshotId??quote.capturedAt??quote.timestamp??'');

function contractTeam(action,event,catalog){
  if(['home','away','total'].includes(action.team))return action.team;
  if(action.teamId){
    const id=String(action.teamId);
    for(const side of ['home','away'])if(teamMatches(event,side,id,catalog)===true)return side;
    return `team:${id}`;
  }
  const scope=marketDefinition(action.market)?.teamScope;
  return scope==='match'||scope==='both'?'total':null;
}
function sameContract(actual,wanted,event,catalog){
  if(!actual?.market||!wanted?.market)return null;
  if(actual.market!==wanted.market||actual.period!==wanted.period)return false;
  if(actual.market==='correct_score')return actual.homeGoals===wanted.homeGoals&&actual.awayGoals===wanted.awayGoals;
  if(playerMarkets.has(actual.market)){
    if(!actual.playerId)return null;
    if(String(actual.playerId)!==String(wanted.playerId))return false;
    // The picker team identifies the player. It is not an implicit historical
    // club filter. Literal home/away targets still require that quoted side.
    if(['home','away'].includes(wanted.team)){
      const actor=contractTeam(actual,event,catalog);if(actor==null)return null;if(actor!==wanted.team)return false;
    }
  }
  const definition=marketDefinition(actual.market);
  if(['count','player_count'].includes(definition?.kind)){
    if(!numeric(actual.line)||!numeric(wanted.line))return null;
    const direct=actual.selection===wanted.selection&&actual.line===wanted.line;
    const wantedMinimum=wanted.selection==='at_least'&&actual.selection==='over'&&Number.isInteger(wanted.line)&&actual.line===wanted.line-.5;
    const actualMinimum=actual.selection==='at_least'&&wanted.selection==='over'&&Number.isInteger(actual.line)&&wanted.line===actual.line-.5;
    if(!direct&&!wantedMinimum&&!actualMinimum)return false;
  }else {
    if(actual.selection!==wanted.selection)return false;
    if(['handicap_result','asian_handicap'].includes(actual.market)){
      if(!numeric(actual.line)||!numeric(wanted.line))return null;
      if(actual.line!==wanted.line)return false;
    }
  }
  if(!playerMarkets.has(actual.market)&&(['team','both'].includes(definition?.teamScope)||actual.market==='asian_handicap')){
    const target=contractTeam(wanted,event,catalog),offered=contractTeam(actual,event,catalog);
    if(target==null||offered==null)return null;
    return target===offered;
  }
  return true;
}

/** Matching is one expression. No global scope can override an OR branch. */
export function evaluateUnifiedFormula(universe,rawRule,options={}){
  const {events=[],marketQuotes=[]}=universe||{},entities=options.entities||{},rule=normalizeUnifiedFormula(rawRule,entities);
  const rosterMaxAgeDays=options.rosterMaxAgeDays??DEFAULT_ROSTER_MAX_AGE_DAYS;
  if(!numeric(rosterMaxAgeDays)||rosterMaxAgeDays<=0)throw new Error('La vigencia del plantel debe ser mayor que cero.');
  const catalog=createCatalog(entities,rosterMaxAgeDays),entries=events.map((event,index)=>({event,index})),eventById=new Map(entries.map(entry=>[String(entry.event.id),entry]));
  const leaves=[];function gather(node){if(node.type==='group')node.children.forEach(gather);else leaves.push(node);}gather(rule.expression);
  const needsSidePrices=leaves.some(node=>['home_odds','draw_odds','away_odds'].includes(node.field));
  const explicitOffers=Array.isArray(universe?.offers),expand=!explicitOffers||options.expandAttached===true;
  const source=explicitOffers&&!expand?universe.offers:explicitOffers?[...universe.offers]:[];
  if(expand){
    events.forEach((event,index)=>list(event.marketQuotes).forEach(quote=>source.push({...quote,event:index,eventId:String(event.id)})));
    source.push(...list(marketQuotes));
  }
  const resolve=quote=>Number.isInteger(quote.event)?entries[quote.event]||null:eventById.get(String(quote.eventId??quote.matchId??quote.event??quote.id));
  // Most offers repeat the same small set of contracts. Intern those objects;
  // never retain an extra full-universe candidate array or source-array copy.
  const rawContracts=new Map(),contracts=new Map();let contractSequence=0;
  function recordFor(quote){
    const signature=[quote.market||'match_result',quote.period||'full',quote.selection??['home','draw','away'][Number(quote.side)],quote.team??'',quote.teamId??'',quote.playerId??'',quote.line??'',quote.homeGoals??'',quote.awayGoals??''].join('\u001f');
    if(rawContracts.has(signature))return rawContracts.get(signature);
    const action=contract(quote),key=contractKey(action);let record=contracts.get(key);
    if(!record){
      try{if(!marketDefinition(action.market))throw new Error();validateFootballStrategy({conditions:[],action:{...action,stake:1}});}
      catch{rawContracts.set(signature,null);return null;}
      record={id:++contractSequence,key,action};contracts.set(key,record);
    }
    rawContracts.set(signature,record);return record;
  }
  const sidePrices=new Map(),groupKey=(entry,book,snapshot)=>`${entry.index}\u001f${book}\u001f${snapshot}`;
  if(needsSidePrices)for(const quote of source){
    const entry=resolve(quote);if(!entry||!odds(quote.odds)||quote.book==null)continue;
    const record=recordFor(quote);if(record?.action.market!=='match_result'||record.action.period!=='full')continue;
    const key=groupKey(entry,String(quote.book),snapshotKey(quote));if(!sidePrices.has(key))sidePrices.set(key,{});
    const prices=sidePrices.get(key),side=record.action.selection;
    if(prices[side]===undefined)prices[side]=quote.odds;else if(prices[side]!==quote.odds)prices[side]=null;
  }
  const eventCache=new Map(),settlementCache=new Map(),alerts=[],seen=new Set(),candidateEvents=new Set();let unknown=0,failed=0,candidateCount=0;
  const settled=(entry,record)=>{
    if(!settlementCache.has(entry.index))settlementCache.set(entry.index,new Map());
    const cache=settlementCache.get(entry.index);if(!cache.has(record.id))cache.set(record.id,settleFootballAction(entry.event,record.action,{}, {entities,_catalog:catalog}));return cache.get(record.id);
  };
  function evaluate(node,entry,values,actual){
    if(node.type==='group'){
      let missing=false;
      for(const child of node.children){const value=evaluate(child,entry,values,actual);if(node.operator==='O'&&value===true)return true;if(node.operator==='Y'&&value===false)return false;if(value==null)missing=true;}
      return missing?null:node.operator==='Y';
    }
    if(priceFields.has(node.field))return compare(values[node.field],node);
    if(node.field==='player')return actual.playerId?invert(String(actual.playerId)===String(node.playerId),node.operator):null;
    if(node.field==='market')return invert(sameContract(actual,node.selection,entry.event,catalog),node.operator);
    if(!eventCache.has(entry.index))eventCache.set(entry.index,new Map());
    const cache=eventCache.get(entry.index);if(cache.has(node.id))return cache.get(node.id);
    let result=null;
    if(node.field==='team')result=invert(or(['home','away'].map(side=>teamMatches(entry.event,side,node.value,catalog))),node.operator);
    else if(node.field==='home_team'||node.field==='away_team')result=invert(teamMatches(entry.event,node.field==='home_team'?'home':'away',node.value,catalog),node.operator);
    else if(node.field==='league'){const actual=entry.event.league??entry.event.league_code;result=actual==null?null:invert(String(actual)===node.value,node.operator);}
    cache.set(node.id,result);return result;
  }
  for(const quote of source){
    const entry=resolve(quote);if(!entry||!odds(quote.odds)||quote.book==null||!String(quote.book))continue;
    const record=recordFor(quote);if(!record)continue;candidateCount++;candidateEvents.add(entry.index);
    const action=record.action,book=String(quote.book),snapshot=snapshotKey(quote),group=needsSidePrices?sidePrices.get(groupKey(entry,book,snapshot)):null;
    const sideValue=side=>needsSidePrices?(group?.[side]??null):(action.market==='match_result'&&action.period==='full'&&action.selection===side?quote.odds:null);
    const values={odds:quote.odds,home_odds:sideValue('home'),draw_odds:sideValue('draw'),away_odds:sideValue('away')};
    const matched=evaluate(rule.expression,entry,values,action);if(matched!==true){if(matched==null)unknown++;else failed++;continue;}
    const dedup=JSON.stringify([entry.index,book,snapshot,record.id,quote.odds]);if(seen.has(dedup))continue;seen.add(dedup);
    const outcome=settled(entry,record),won=outcome.outcome==='win'?true:outcome.outcome==='loss'?false:outcome.outcome==='push'?'push':null;
    const refs=list(quote.references),independent=refs.length>0&&!refs.some(item=>String(item)===book),rawP=quote.referenceProbability??quote.probability;
    const p=independent&&probability(rawP)?rawP:null;
    const pushing=action.market==='draw_no_bet'||action.market==='asian_handicap'&&Number.isInteger(action.line)||['count','player_count'].includes(marketDefinition(action.market)?.kind)&&['over','under'].includes(action.selection)&&Number.isInteger(action.line);
    const pushP=probability(quote.pushProbability)?quote.pushProbability:pushing?null:0;
    const ev=probability(p)&&probability(pushP)&&p+pushP<=1?p*quote.odds+pushP-1:null;
    const statuses=[];if(outcome.outcome==null)statuses.push(outcome.status||'result_missing');if(p==null)statuses.push('probability_missing');
    const person=nameFor(entities.players,action.playerId,'Jugador'),team=nameFor(entities.teams,action.teamId,'Equipo');
    alerts.push({id:`${entry.event.id}|${snapshot}|${record.key}|${quote.odds}`,eventId:String(entry.event.id),event:entry.index,date:day(entry.event),league:entry.event.league??entry.event.league_code,home:entry.event.home??entry.event.home_team,away:entry.event.away??entry.event.away_team,book,side:quote.side,market:action.market,period:action.period,selection:action.selection,actionLabel:footballMarketLabel(action,{home:action.team==='selected'?team:entry.event.home??entry.event.home_team??'Local',away:entry.event.away??entry.event.away_team??'Visitante',player:person}),contextOdds:{home:values.home_odds,draw:values.draw_odds,away:values.away_odds},contextValues:values,odds:quote.odds,probability:p,pushProbability:pushP,probabilityN:p==null?null:refs.length,probabilitySource:p==null?null:'reference',ev,expectedProfit:ev==null?null:ev*rule.stake,stake:rule.stake,won,outcome:outcome.outcome,profit:outcome.outcome==null?null:won===true?(quote.odds-1)*rule.stake:won===false?-rule.stake:0,quoteSource:'archive',isScenario:false,breakEven:probability(pushP)?(1-pushP)/quote.odds:null,reference:refs,status:statuses[0]||'ready',statuses,triggered:true,sourceQuote:clone(quote)});
  }
  alerts.sort((a,b)=>a.date.localeCompare(b.date)||a.eventId.localeCompare(b.eventId)||a.book.localeCompare(b.book)||a.id.localeCompare(b.id));
  const summary=summarizeFootballAlerts(alerts);
  return {alerts,summary,coverage:{events:events.length,contextEvents:candidateEvents.size,quoteGroups:candidateCount,conditionGroups:alerts.length,matchedGroups:alerts.length,alerts:alerts.length,priced:alerts.length,probability:alerts.filter(row=>row.probability!=null).length,valued:alerts.filter(row=>row.ev!=null).length,settled:alerts.filter(row=>row.won!==null).length,missingQuote:0,missingProbability:alerts.filter(row=>row.probability==null).length,missingConditionValues:unknown,unknownCandidates:unknown,falseCandidates:failed,universe:options.universe||null}};
}
