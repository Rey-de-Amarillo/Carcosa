import {mountUnifiedFormulaEditor} from './football-formula-editor.js';
import {mountPriceFormulaEditor} from './football-price-editor.js';
import {mountReferencePriceFormulaEditor} from './football-reference-price-editor.js';
import {isPaymentFormula} from './football-price-library.js';
import {PRICE_FORMULA_KIND} from './football-price-engine.js';
import {newSituationsDraft,newSituationSelection,situationsDraftFromAlert,compileSituationsAlert} from './football-situations.js';
import {FOOTBALL_MARKET_CATALOG,marketDefinition,marketSelectionChoices,marketLineChoices,defaultMarketSelection,footballMarketLabel} from './football-market-catalog.js';
/** Football alert authoring: entity context, price trigger, bet and valuation. */
export const ALERT_SIGNALS = Object.freeze([
  {id:'home_odds',name:'Cuota local · 1X2',unit:'odds'},
  {id:'draw_odds',name:'Cuota empate · 1X2',unit:'odds'},
  {id:'away_odds',name:'Cuota visitante · 1X2',unit:'odds'},
  {id:'home_return',name:'Ganancia neta local',unit:'percentage'},
  {id:'draw_return',name:'Ganancia neta empate',unit:'percentage'},
  {id:'away_return',name:'Ganancia neta visitante',unit:'percentage'},
  {id:'home_implied',name:'Probabilidad implícita local',unit:'percentage'},
  {id:'draw_implied',name:'Probabilidad implícita empate',unit:'percentage'},
  {id:'away_implied',name:'Probabilidad implícita visitante',unit:'percentage'},
  {id:'implied_gap',name:'Diferencia de probabilidades local − visitante',unit:'percentage'},
  {id:'return_gap',name:'Diferencia de ganancia neta local − visitante',unit:'percentage'},
  {id:'odds_ratio',name:'Relación cuota local / visitante',unit:'ratio'},
  {id:'selected_odds',name:'Cuota de la apuesta',unit:'odds'},
  {id:'ev',name:'EV de la apuesta',unit:'percentage'},
]);
export const ALERT_MARKETS = Object.freeze([...FOOTBALL_MARKET_CATALOG,{id:'combination',name:'Crear apuesta'}]);
const PERIODS=[['full','Partido completo'],['first_half','Primer tiempo'],['second_half','Segundo tiempo']];
const OPERATORS=[['around','Con margen'],['between','Entre'],['>=','Desde'],['<=','Hasta'],['=','Exacta'],['>','Mayor que'],['<','Menor que'],['!=','Distinta de']];
const clone=value=>JSON.parse(JSON.stringify(value));
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rounded=value=>Number(value.toPrecision(15));
const numeric=(value,label)=>{if(value==null||String(value).trim()===''||!Number.isFinite(Number(value)))throw new Error(`Completá ${label}.`);return Number(value);};
const optionalNumber=value=>value==null||String(value).trim()===''?null:Number(value);
const percentageField=field=>ALERT_SIGNALS.some(s=>s.id===field&&s.unit==='percentage');
const signalAllowed=field=>ALERT_SIGNALS.some(s=>s.id===field)||/^leg_([1-8])_odds$/.test(field);
export const inputToAlertValue=(field,value)=>{const number=numeric(value,'el valor');return percentageField(field)?number/100:number;};
export const alertValueToInput=(field,value)=>value==null?'':String(rounded(percentageField(field)?value*100:value));

/** The editor groups fields by the football decision they describe. Storage
 * remains the engine's field/operator schema so saved alerts keep their meaning. */
export function alertConditionMarket(field) {
  if(/^(home|draw|away)_odds$/.test(field))return 'result';
  if(field==='selected_odds')return 'selected';
  if(/^leg_[1-8]_odds$/.test(field))return 'combination';
  return 'mathematics';
}
export function footballSelectionLabel(action={},entities={},context={}) {
  const team=id=>(entities.teams||[]).find(item=>item.id===id)?.name||'';
  const home=team(context.homeTeam)||'Local',away=team(context.awayTeam)||'Visitante';
  const actor=(action.market?.startsWith('player_')||['first_goalscorer','last_goalscorer'].includes(action.market))?(entities.players||[]).find(item=>item.id===action.playerId)?.name||'Jugador':team(action.teamId||teamForAction(action,context))||(action.team==='total'?'Ambos equipos':action.team==='away'?away:home);
  const count=action.selection==='exact'?`exactamente ${action.line}`:action.selection==='at_least'?`${action.line} o más`:action.selection==='under'?`menos de ${action.line}`:`más de ${action.line}`;
  const period=action.period==='first_half'?' · Primer tiempo':action.period==='second_half'?' · Segundo tiempo':'';
  let title;
  if(!['correct_score','match_result','btts','combination','total_goals','team_goals','player_goals','corners'].includes(action.market))return footballMarketLabel(action,{home:action.team==='selected'?team(action.teamId)||home:home,away,player:actor});
  if(action.market==='correct_score')title=`${home} ${action.homeGoals}–${action.awayGoals} ${away}`;
  else if(action.market==='match_result')title=action.selection==='draw'?'Empate':`Gana ${action.selection==='away'?away:home}`;
  else if(action.market==='btts')title=`Ambos marcan: ${action.selection==='no'?'no':'sí'}`;
  else if(action.market==='combination')title='Combinada completa';
  else if(action.market==='total_goals')title=`Partido · ${count} goles`;
  else title=`${actor} · ${count} ${action.market==='corners'?'córners':'goles'}`;
  return title+period;
}
export function alertConditionChoices(market,{entities={},context={},action={}}={}) {
  const team=id=>(entities.teams||[]).find(item=>item.id===id)?.name||'';
  const home=team(context.homeTeam)||'local',away=team(context.awayTeam)||'visitante';
  if(market==='result')return [['home_odds',`Gana ${home}`],['draw_odds','Empate'],['away_odds',`Gana ${away}`]];
  if(market==='selected')return [['selected_odds',footballSelectionLabel(action,entities,context)]];
  if(market==='combination')return (action.legs||[]).map((leg,index)=>[`leg_${index+1}_odds`,footballSelectionLabel(leg,entities,context)]);
  const labels={home_return:`Ganancia neta · ${home}`,draw_return:'Ganancia neta · Empate',away_return:`Ganancia neta · ${away}`,home_implied:`Probabilidad implícita · ${home}`,draw_implied:'Probabilidad implícita · Empate',away_implied:`Probabilidad implícita · ${away}`,implied_gap:`Probabilidad · ${home} − ${away}`,return_gap:`Ganancia neta · ${home} − ${away}`,odds_ratio:`Relación de cuotas · ${home} / ${away}`,ev:'Valor esperado de la apuesta'};
  return ALERT_SIGNALS.filter(item=>labels[item.id]).map(item=>[item.id,labels[item.id]]);
}
export function alertConditionRangeLabel(condition) {
  const percent=percentageField(condition.field),suffix=percent?'%':'';
  const format=value=>Number(percentageField(condition.field)?value*100:value).toLocaleString('es-AR',{minimumFractionDigits:2,maximumFractionDigits:2})+suffix;
  try {
    const range=conditionRange(condition);
    if(['around','between'].includes(condition.operator))return `Entre ${format(range.min)} y ${format(range.max)}`;
    const word={'>=':'Desde','<=':'Hasta','>':'Mayor que','<':'Menor que','=':'Exactamente','!=':'Distinta de'}[condition.operator];
    return `${word} ${format(range.min)}`;
  } catch {return '';}
}

export function teamsForContext(entities={},context={}) {
  return (entities.teams||[]).filter(team=>!context.league||(team.leagueIds||[]).includes(context.league));
}
export function playersForTeam(entities={},teamId='',league='') {
  const team=(entities.teams||[]).find(t=>t.id===teamId);if(!team||team.playersCoverage?.status!=='verified_snapshot')return [];
  if(league&&Array.isArray(team.currentLeagueIds)&&!team.currentLeagueIds.includes(league))return [];
  const permitted=new Set(team.playerIds||[]);
  return (entities.players||[]).filter(p=>p.teamId===teamId&&permitted.has(p.id));
}
export function conditionRange(condition) {
  if(condition.operator==='around'){
    const value=numeric(condition.value,'el objetivo'),margin=numeric(condition.margin,'el margen');
    if(margin<0)throw new Error('El margen debe ser cero o mayor.');
    return {min:rounded(value-margin),max:rounded(value+margin)};
  }
  if(condition.operator==='between')return {min:numeric(condition.min,'el mínimo'),max:numeric(condition.max,'el máximo')};
  return {min:numeric(condition.value,'el valor'),max:numeric(condition.value,'el valor')};
}
export function normalizeAlertCondition(condition) {
  if(!signalAllowed(condition?.field))throw new Error('Elegí qué apuesta o cálculo comparar.');
  if(!OPERATORS.some(([op])=>op===condition.operator))throw new Error('Elegí una comparación.');
  if(condition.operator==='around'||condition.operator==='between'){
    const range=conditionRange(condition);if(range.min>range.max)throw new Error('El mínimo debe ser menor o igual al máximo.');
    if(condition.field.endsWith('_odds')&&range.min<=1)throw new Error('Las cuotas deben ser mayores que 1.');
    if(/^(home|draw|away)_implied$/.test(condition.field)&&(range.min<0||range.max>1))throw new Error('La probabilidad debe estar entre 0% y 100%.');
    const result={field:condition.field,operator:'between',...range};
    if(condition.operator==='around')result.ui={operator:'around',value:Number(condition.value),margin:Number(condition.margin)};
    else if(condition.ui?.operator==='around'){
      const candidate=conditionRange({...condition.ui,field:condition.field});
      if(candidate.min===range.min&&candidate.max===range.max)result.ui=clone(condition.ui);
    }
    return result;
  }
  return {field:condition.field,operator:condition.operator,value:numeric(condition.value,'el valor')};
}
function defaultAction(market='correct_score') {
  const base={market,period:'full',selection:'over',team:'home',teamId:'',playerId:'',homeGoals:2,awayGoals:1,line:2.5};
  if(market==='match_result')base.selection='home';
  if(market==='btts')base.selection='yes';
  if(market==='team_goals'||market==='player_goals'){base.selection='at_least';base.line=1;}
  if(market==='corners'){base.team='total';base.line=8.5;}
  if(market==='combination')base.legs=[{...defaultAction('team_goals'),team:'home',line:2},{...defaultAction('team_goals'),team:'away',line:1}];
  return base;
}
export function newFootballAlert() {
  return {kind:'football-alert',version:2,id:null,name:'',onePerMatch:true,context:{league:'',homeTeam:'',awayTeam:'',teamId:'',playerId:'',period:'full'},join:'Y',conditions:[{field:'home_odds',operator:'around',value:1.9,margin:.1},{field:'away_odds',operator:'around',value:4,margin:.2}],action:{...defaultAction(),oddsSource:'archive',odds:null,stake:1,probabilitySource:'empirical',probability:null,minSample:30}};
}
function teamForAction(action,context) {
  if(action.team==='total')return '';
  return action.team==='home'?context.homeTeam:action.team==='away'?context.awayTeam:action.teamId||context.teamId||'';
}
function normalizeSelection(raw,context,entities,leg=false) {
  if(!raw||typeof raw!=='object')throw new Error('Elegí una selección válida.');
  const action={...(raw.market==='combination'?defaultAction('combination'):defaultMarketSelection(raw.market)),...clone(raw)};
  const definition=marketDefinition(action.market);
  if(!definition&&action.market!=='combination'||leg&&action.market==='combination')throw new Error('Elegí un mercado válido.');
  if(!(action.market==='player_goals'?PERIODS.map(([id])=>id):definition?.periods||PERIODS.map(([id])=>id)).includes(action.period))throw new Error('Elegí el período de la apuesta.');
  const playerMarket=action.market.startsWith('player_')||['first_goalscorer','last_goalscorer'].includes(action.market);
  const countMarket=['count','player_count'].includes(definition?.kind);
  if(action.market==='correct_score'){
    action.homeGoals=numeric(action.homeGoals,'los goles del local');action.awayGoals=numeric(action.awayGoals,'los goles del visitante');
    if(!Number.isInteger(action.homeGoals)||!Number.isInteger(action.awayGoals)||action.homeGoals<0||action.awayGoals<0)throw new Error('El marcador debe contener goles enteros y positivos o cero.');
  }else if(countMarket){
    if(!['over','under','at_least','exact'].includes(action.selection))throw new Error('Elegí más, menos, al menos o exactamente.');
    action.line=numeric(action.line,'la cantidad');
    if(action.line<0||!Number.isInteger(action.line*2))throw new Error('Elegí una cantidad entera o una línea de medio punto.');
    if(['at_least','exact'].includes(action.selection)&&!Number.isInteger(action.line))throw new Error('La cantidad exacta o mínima debe ser entera.');
  }else if(['asian_handicap','handicap_result'].includes(action.market)){
    action.line=numeric(action.line,'el hándicap');
    if(!Number.isInteger(action.line*(action.market==='asian_handicap'?2:1)))throw new Error('Elegí una línea válida de hándicap.');
  }
  if(action.market==='asian_handicap'&&['home','away'].includes(action.selection))action.team=action.selection;
  const choices=marketSelectionChoices(action.market);
  if(choices.length&&!choices.some(([id])=>id===action.selection))throw new Error(action.market==='match_result'?'Elegí local, empate o visitante.':'Elegí una selección del mercado.');
  const needsTeam=['team','both'].includes(definition?.teamScope)||playerMarket;
  if(needsTeam){
    if(!['home','away','selected','total'].includes(action.team))throw new Error('Elegí el equipo de la selección.');
    if(action.team==='total'&&definition?.teamScope!=='both')throw new Error('Elegí un equipo para esa selección.');
    const teamId=teamForAction(action,context);
    if(action.team==='selected'&&!teamId)throw new Error('Elegí el equipo de la selección.');
    if(context.homeTeam&&context.awayTeam&&teamId&&![context.homeTeam,context.awayTeam].includes(teamId))throw new Error('El equipo de la selección debe ser local o visitante del partido.');
  }
  if(playerMarket){
    const teamId=teamForAction(action,context);
    if(!teamId)throw new Error('Elegí el equipo del jugador.');
    if(action.teamId&&['home','away'].includes(action.team)&&action.teamId!==teamId)throw new Error('El jugador debe pertenecer al equipo seleccionado.');
    if(!playersForTeam(entities,teamId,context.league).some(p=>p.id===action.playerId))throw new Error('Elegí un jugador del equipo seleccionado.');
    action.teamId=teamId;
  }else {action.playerId='';if(action.team!=='selected')action.teamId=teamForAction(action,context)||'';}
  if(action.team==='selected'&&action.teamId&&!(entities.teams||[]).some(t=>t.id===action.teamId))throw new Error('El equipo de la selección no está en el catálogo.');
  if(action.market==='combination'){
    if(!Array.isArray(action.legs)||action.legs.length<2||action.legs.length>8)throw new Error('La combinada necesita entre 2 y 8 selecciones.');
    action.legs=action.legs.map(item=>normalizeSelection(item,context,entities,true));
  }else delete action.legs;
  if(leg){for(const key of ['odds','oddsSource','stake','probability','probabilitySource','minSample'])delete action[key];}
  return action;
}
export function normalizeFootballAlert(raw,entities={}) {
  if(!raw||!String(raw.name||'').trim())throw new Error('Poné un nombre a la alerta.');
  const context={league:'',homeTeam:'',awayTeam:'',teamId:'',playerId:'',period:'full',...(raw.context||{})};
  if(context.league&&!(entities.leagues||[]).some(l=>l.id===context.league))throw new Error('La liga no está en el catálogo.');
  const teams=teamsForContext(entities,context);
  for(const key of ['homeTeam','awayTeam'])if(context[key]&&!teams.some(t=>t.id===context[key]))throw new Error('El equipo debe pertenecer a la liga elegida.');
  if(context.homeTeam&&context.homeTeam===context.awayTeam)throw new Error('Local y visitante deben ser equipos distintos.');
  if(context.teamId&&!(entities.teams||[]).some(t=>t.id===context.teamId))throw new Error('El equipo del jugador no está en el catálogo.');
  if(!Array.isArray(raw.conditions)||!raw.conditions.length||raw.conditions.length>40)throw new Error('Agregá entre 1 y 40 condiciones.');
  const conditions=raw.conditions.map(normalizeAlertCondition),action=normalizeSelection(raw.action||{},context,entities);
  action.stake=numeric(action.stake??1,'el importe');if(action.stake<=0)throw new Error('El importe debe ser mayor que cero.');
  action.oddsSource=action.oddsSource==='manual'?'manual':'archive';
  action.odds=action.oddsSource==='manual'?numeric(action.odds,'la cuota de la apuesta'):null;
  if(action.odds!=null&&action.odds<=1)throw new Error('La cuota de la apuesta debe ser mayor que 1.');
  action.probabilitySource=['reference','empirical','manual'].includes(action.probabilitySource)?action.probabilitySource:'empirical';
  if(action.probabilitySource==='reference'&&action.market!=='match_result')throw new Error('La referencia 1X2 corresponde al resultado del partido.');
  action.probability=action.probabilitySource==='manual'?numeric(action.probability,'la probabilidad'):null;
  if(action.probability!=null&&(action.probability<0||action.probability>1))throw new Error('La probabilidad debe estar entre 0% y 100%.');
  action.pushProbability=action.probabilitySource==='manual'?optionalNumber(action.pushProbability):null;
  if(action.pushProbability!=null&&(!Number.isFinite(action.pushProbability)||action.pushProbability<0||action.pushProbability>1||action.probability!=null&&action.pushProbability+action.probability>1))throw new Error('La probabilidad de acierto y devolución no debe superar 100%.');
  action.minSample=numeric(action.minSample??30,'la muestra mínima');if(!Number.isInteger(action.minSample)||action.minSample<1)throw new Error('La muestra mínima debe ser un entero mayor que cero.');
  context.period=action.period;
  if(action.playerId){context.teamId=action.teamId;context.playerId=action.playerId;}
  else {context.teamId='';context.playerId='';}
  for(const condition of conditions){const match=condition.field.match(/^leg_(\d+)_odds$/);if(match&&(action.market!=='combination'||Number(match[1])>action.legs.length))throw new Error('La condición se refiere a una selección que no existe en la combinada.');}
  return {kind:'football-alert',version:2,id:raw.id||null,name:String(raw.name).trim().slice(0,100),onePerMatch:raw.onePerMatch!==false,join:raw.join==='O'?'O':'Y',context,conditions,action};
}
export const validateFootballAlert=(raw,entities={})=>normalizeFootballAlert(raw,entities);
const conditionDraft=condition=>condition.ui?.operator==='around'?{field:condition.field,...clone(condition.ui)}:clone(condition);

export function selectionCanPush(action={}) {
  return action.market==='draw_no_bet'||action.market==='asian_handicap'&&Number.isInteger(Number(action.line))||['count','player_count'].includes(marketDefinition(action.market)?.kind)&&['over','under'].includes(action.selection)&&action.line!=null&&Number.isInteger(Number(action.line));
}
export function calculateManualPreview(raw={}) {
  const action=raw.action||raw;
  if(action.oddsSource!=='manual'||action.probabilitySource!=='manual')return null;
  const odds=optionalNumber(action.odds),probability=optionalNumber(action.probability),stake=optionalNumber(action.stake);
  if(!Number.isFinite(odds)||odds<=1||!Number.isFinite(probability)||probability<0||probability>1||!Number.isFinite(stake)||stake<=0)return null;
  if(action.market==='combination'&&(!Array.isArray(action.legs)||action.legs.length<2||action.legs.some(selectionCanPush)))return null;
  const explicitPush=action.pushProbability!=null&&String(action.pushProbability).trim()!=='';
  if(selectionCanPush(action)&&!explicitPush)return null;
  const push=explicitPush?Number(action.pushProbability):0;
  if(!Number.isFinite(push)||push<0||push>1||probability+push>1)return null;
  const ev=rounded(probability*odds+push-1),breakEven=(1-push)/odds;
  return {breakEven,breakEvenPercent:breakEven*100,ev,evPercent:ev*100,expectedProfit:stake*ev,profitIfWin:stake*(odds-1),pushProbability:push};
}

/** Direct market/selection rows; saved conditions retain their original meaning. */
export function mountLegacyFootballAlertBuilder(container,{entities={},onSave=()=>{},onCancel=()=>{}}={}) {
  if(!container?.ownerDocument)throw new Error('El creador necesita un contenedor.');
  let catalog=entities,state=newSituationsDraft(),editing=false,saving=false,sequence=0;
  const q=selector=>container.querySelector(selector);
  const options=(list,value)=>list.map(([key,label])=>`<option value="${esc(key)}" ${String(key)===String(value)?'selected':''}>${esc(label)}</option>`).join('');
  const field=(label,control)=>`<label>${esc(label)}${control}</label>`;
  const input=(key,value,label,type='number',extra='')=>`<input data-key="${esc(key)}" type="${type}" value="${esc(value??'')}" aria-label="${esc(label)}" ${type==='number'?'step="any"':''} ${extra}>`;
  const select=(key,list,value,label,extra='')=>`<select data-key="${esc(key)}" aria-label="${esc(label)}" ${extra}>${options(list,value)}</select>`;
  const grid=content=>`<div class="entry-form record-filter-form wk-field-grid football-builder-fields">${content}</div>`;
  const teamName=id=>(catalog.teams||[]).find(t=>t.id===id)?.name||'';
  const names=()=>({home:teamName(state.context.homeTeam)||'Local',away:teamName(state.context.awayTeam)||'Visitante'});
  const teamChoices=(exclude='',side='')=>[['',side?`Cualquier ${side}`:'Elegir equipo'],...teamsForContext(catalog,state.context).filter(t=>t.id!==exclude).map(t=>[t.id,t.name])];
  const isPlayer=a=>a.market.startsWith('player_')||['first_goalscorer','last_goalscorer'].includes(a.market);
  const targetValue=a=>isPlayer(a)&&['home','away'].includes(a.team)&&!state.context[a.team==='home'?'homeTeam':'awayTeam']?'':a.team==='selected'?'team:'+a.teamId:a.team;
  function targetChoices(a){
    const d=marketDefinition(a.market),{home,away}=names(),list=d?.teamScope==='both'?[['total','Ambos equipos']]:[];
    if(!isPlayer(a)||state.context.homeTeam)list.push(['home',home]);
    if(!isPlayer(a)||state.context.awayTeam)list.push(['away',away]);
    if(isPlayer(a)&&!(state.context.homeTeam&&state.context.awayTeam))list.unshift(['','Elegir equipo']);
    if(isPlayer(a)&&!(state.context.homeTeam&&state.context.awayTeam)){
      for(const team of teamsForContext(catalog,state.context))if(playersForTeam(catalog,team.id,state.context.league).length&&team.id!==state.context.homeTeam&&team.id!==state.context.awayTeam)list.push(['team:'+team.id,team.name]);
    }
    if(a.team==='selected'&&a.teamId&&!list.some(([id])=>id===targetValue(a)))list.push([targetValue(a),teamName(a.teamId)]);
    return list;
  }
  function priceFields(situation,index){
    const price=situation.price;if(!price)return '';
    const base=`situations.${index}.price`,op=price.operator||'between',name=label=>`${label}, fila ${index+1}`;
    const simple=[['between','Entre'],['>=','Como mínimo'],['<=','Como máximo'],['=','Exactamente']];
    if(!simple.some(([id])=>id===op))simple.push([op,OPERATORS.find(([id])=>id===op)?.[1]||op]);
    let fields=field('Cuota',select(base+'.operator',simple,op,name('Filtro de cuota')));
    if(op==='between')fields+=field('Desde',input(base+'.min',price.min,name('Cuota mínima'),'number','min="1.01" placeholder="1,80"'))+field('Hasta',input(base+'.max',price.max,name('Cuota máxima'),'number','min="1.01" placeholder="2,00"'));
    else fields+=field(op==='around'?'Cuota objetivo':'Valor',input(base+'.value',price.value,name('Cuota'),'number','min="1.01"'));
    if(op==='around')fields+=field('Margen',input(base+'.margin',price.margin,name('Margen'),'number','min="0"'));
    return fields;
  }
  function lineOptions(a){
    const values=marketLineChoices(a.market,a.selection).slice();
    if(a.line!=null&&!values.includes(Number(a.line)))values.push(Number(a.line));
    values.sort((x,y)=>x-y);
    return values.map(value=>[value,`${['asian_handicap','handicap_result'].includes(a.market)&&value>0?'+':''}${String(value).replace('.',',')}`]);
  }
  function renderSituation(situation,index){
    const a=situation.selection,d=marketDefinition(a.market),base=`situations.${index}.selection`,name=label=>`${label}, fila ${index+1}`;
    const markets=FOOTBALL_MARKET_CATALOG.map(m=>[m.id,m.name]);
    const bet=situation.role==='bet',number=state.situations.slice(0,index+1).filter(s=>s.role===situation.role).length;
    let controls=field(`Mercado de ${bet?'apuesta':'filtro'} ${number}`,select(base+'.market',markets,a.market,name('Mercado')));
    if(['team','both'].includes(d?.teamScope)||isPlayer(a))controls+=field('Equipo',select(base+'.team',targetChoices(a),targetValue(a),name('Equipo')));
    if(isPlayer(a)){
      const teamId=teamForAction(a,state.context),players=playersForTeam(catalog,teamId,state.context.league);
      controls+=field('Jugador',select(base+'.playerId',[['',players.length?'Elegir jugador':teamId?'Sin jugadores disponibles':'Elegí un equipo'],...players.map(p=>[p.id,p.name])],a.playerId,name('Jugador'),players.length?'':'disabled'));
    }
    if(a.market==='correct_score'){
      const scores=[];for(let h=0;h<=6;h++)for(let v=0;v<=6;v++)scores.push([`${h}-${v}`,`${h} – ${v}`]);
      const value=a.homeGoals==null||a.awayGoals==null?'':`${a.homeGoals}-${a.awayGoals}`;
      if(value&&!scores.some(([key])=>key===value))scores.push([value,`${a.homeGoals} – ${a.awayGoals}`]);
      controls+=field('Marcador (local – visitante)',`<select data-score-index="${index}" aria-label="${name('Marcador')}">${options([['','Elegir marcador'],...scores],value)}</select>`);
    }else if(a.market==='player_goals'&&a.selection==='at_least'){
      const choices=[[1,'Anotará en cualquier momento'],[2,'2 o más goles'],[3,'3 o más goles']];
      if(a.line!=null&&!choices.some(([v])=>v===a.line))choices.push([a.line,`${a.line} o más goles`]);
      controls+=field('Selección',select(base+'.line',choices,a.line,name('Selección'),'data-number'));
    }else {
      const choices=marketSelectionChoices(a.market,names());
      if(choices.length)controls+=field('Selección',select(base+'.selection',choices,a.selection,name('Selección')));
      if(['count','player_count','asian_handicap','handicap_result'].includes(d?.kind))controls+=field(a.market==='handicap_result'?'Hándicap del local':a.market==='asian_handicap'?'Hándicap':'Línea',select(base+'.line',lineOptions(a),a.line,name('Línea'),'data-number'));
    }
    const periods=PERIODS.filter(([id])=>d?.periods.includes(id)||id===a.period);
    if(periods.length>1)controls+=field('Período',select(base+'.period',periods,a.period,name('Período')));
    const last=state.situations.filter(s=>s.role==='bet').length===1&&bet;
    const remove=field(bet?'Selección':'Filtro',`<button type="button" class="button button-neutral" data-remove-situation="${index}" aria-label="Quitar ${bet?'selección':'filtro'} ${index+1}" ${last?'disabled':''}>Quitar ${bet?'selección':'filtro'}</button>`);
    const priceAction=bet?field('Cuota',`<button type="button" class="button button-neutral" data-toggle-price="${index}" aria-label="${situation.price?'Quitar filtro de cuota':'Filtrar cuota'}">${situation.price?'Quitar filtro de cuota':'Filtrar cuota'}</button>`):'';
    return `<div class="entry-form record-filter-form wk-field-grid football-builder-fields" data-situation-panel="${esc(situation.id)}" data-rule-index="${index}" ${situation.price?`data-price-index="${index}" data-render-operator="${esc(situation.price.operator||'between')}"`:''}>${controls}${priceFields(situation,index)}${priceAction}${remove}</div>`;
  }
  function legacyField(condition,index){
    const signal=ALERT_SIGNALS.find(item=>item.id===condition.field),title=signal?.name||`Condición ${index+1}`;
    const text=alertConditionRangeLabel(condition);
    return field(title,`<input type="text" readonly aria-label="${esc(title)}" value="${esc(text)}">`);
  }
  function render(){
    const conditions=state.situations.filter(s=>s.price).length+(state.legacyConditions?.length||0);
    container.innerHTML=grid(field('Nombre de la fórmula',input('name',state.name,'Nombre de la fórmula','text','maxlength="100" autocomplete="off"'))+
      field('Liga',select('context.league',[['','Todas las ligas'],...(catalog.leagues||[]).map(l=>[l.id,l.name])],state.context.league,'Liga'))+
      field('Local',select('context.homeTeam',teamChoices(state.context.awayTeam,'local'),state.context.homeTeam,'Equipo local'))+
      field('Visitante',select('context.awayTeam',teamChoices(state.context.homeTeam,'visitante'),state.context.awayTeam,'Equipo visitante')))+
      state.situations.map((s,index)=>renderSituation(s,index)).join('')+
      (state.legacyConditions?.length?grid(state.legacyConditions.map(legacyField).join('')):'')+
      grid(field('Importe (u)',input('valuation.stake',state.valuation.stake,'Importe por apuesta','number','min="0.01"'))+
        field('Muestra mínima',input('valuation.minSample',state.valuation.minSample,'Partidos previos mínimos','number','min="1"'))+
        (conditions>1?field('Cumplir filtros',select('join',[['Y','Todos'],['O','Cualquiera']],state.join,'Combinar filtros')):''))+
      grid(field('Selecciones',`<button type="button" class="button button-neutral" data-add-bet aria-label="Agregar selección">Agregar selección</button>`)+
        field('Filtros de cuota',`<button type="button" class="button button-neutral" data-add-condition aria-label="Agregar filtro">Agregar filtro</button>`)+
        field('Fórmula',`<button type="button" class="button primary" data-save-alert aria-label="${editing?'Guardar cambios':'Guardar fórmula'}">${editing?'Guardar cambios':'Guardar fórmula'}</button>`)+
        (editing?field('Edición',`<button type="button" class="button button-neutral" data-cancel-alert aria-label="Cancelar edición">Cancelar edición</button>`):''))+
      `<div class="entry-form record-filter-form wk-field-grid football-builder-fields" data-alert-error-grid hidden><label data-alert-error-field>Error<input type="text" data-alert-error readonly role="alert" aria-label="Error" aria-live="polite"></label></div>`;
  }
  function readDraft(){
    const result=clone(state);
    for(const control of container.querySelectorAll('[data-key]')){
      const keys=control.dataset.key.split('.');let target=result;
      for(const key of keys.slice(0,-1)){if(target[key]==null)target[key]={};target=target[key];}
      target[keys.at(-1)]=control.type==='number'||control.hasAttribute('data-number')?optionalNumber(control.value):control.value;
    }
    for(const control of container.querySelectorAll('[data-score-index]')){
      const a=result.situations[Number(control.dataset.scoreIndex)].selection,score=control.value.split('-');a.homeGoals=control.value?Number(score[0]):null;a.awayGoals=control.value?Number(score[1]):null;
    }
    for(const [index,situation]of result.situations.entries()){
      const price=situation.price,priceRow=q(`[data-price-index="${index}"]`);if(price)price.operator=priceRow?.dataset.renderOperator||price.operator;
      const a=situation.selection;
      if(String(a.team).startsWith('team:')){a.teamId=String(a.team).slice(5);a.team='selected';}
      else if(a.team==='home')a.teamId=result.context.homeTeam||'';
      else if(a.team==='away')a.teamId=result.context.awayTeam||'';
      else if(a.team==='total')a.teamId='';
    }
    return result;
  }
  function cleanPlayers(draft){
    for(const {selection:a}of draft.situations){
      if(a.team==='selected'&&draft.context.homeTeam&&draft.context.awayTeam&&![draft.context.homeTeam,draft.context.awayTeam].includes(a.teamId)){a.team='home';a.teamId=draft.context.homeTeam;a.playerId='';}
      const teamId=teamForAction(a,draft.context);a.teamId=teamId;
      if(!isPlayer(a)||!playersForTeam(catalog,teamId,draft.context.league).some(p=>p.id===a.playerId))a.playerId='';
    }
  }
  function error(problem){const el=q('[data-alert-error]');if(el){el.value=problem?.message||String(problem||'');el.title=el.value;q('[data-alert-error-grid]').hidden=!el.value;}}
  const getDefinition=()=>compileSituationsAlert(readDraft(),catalog);
  container.addEventListener('submit',event=>event.preventDefault());
  container.addEventListener('input',event=>{if(event.target.tagName==='INPUT'){error('');state=readDraft();}});
  container.addEventListener('change',event=>{
    error('');const key=event.target.dataset.key;
    if(event.target.hasAttribute('data-score-index')){state=readDraft();state.valuation={...state.valuation,oddsSource:'archive',odds:null,probabilitySource:'empirical',probability:null,pushProbability:null};render();return;}
    if(!key)return;
    let draft=readDraft();const match=key.match(/^situations\.(\d+)\./),index=match?Number(match[1]):null;
    if(key==='context.league'){
      const teams=teamsForContext(catalog,draft.context);
      for(const side of ['homeTeam','awayTeam'])if(!teams.some(t=>t.id===draft.context[side]))draft.context[side]='';
      for(const s of draft.situations)if(s.selection.team==='selected'&&!teams.some(t=>t.id===s.selection.teamId)){s.selection.teamId='';s.selection.playerId='';}
    }
    if(key.endsWith('.selection.market')){
      const s=draft.situations[index],previous=s.selection,next=newSituationSelection(previous.market);
      if(marketDefinition(previous.market)?.periods.includes(previous.period))next.period=previous.period;
      s.selection=next;s.price=s.role==='condition'?{operator:'between',min:null,max:null}:null;
    }
    if(key.endsWith('.selection.selection')){
      const a=draft.situations[index].selection,allowed=marketLineChoices(a.market,a.selection);
      if(allowed.length&&!allowed.includes(a.line))a.line=allowed.includes(marketDefinition(a.market)?.defaultLine)?marketDefinition(a.market).defaultLine:allowed[0];
    }
    if(key.endsWith('.price.operator')){
      const s=draft.situations[index],previous=s.price||{},op=event.target.value;let range;
      try{range=conditionRange(previous);}catch{range={min:null,max:null};}
      s.price=op==='around'?{operator:op,value:range.min==null?null:rounded((range.min+range.max)/2),margin:range.min==null?null:rounded((range.max-range.min)/2)}:op==='between'?{operator:op,min:range.min,max:range.max}:{operator:op,value:op==='<='||op==='<'?range.max:op==='>='||op==='>'?range.min:previous.value??previous.min??null};
    }
    if(key.startsWith('context.')||key.includes('.selection.')){
      cleanPlayers(draft);draft.valuation={...draft.valuation,oddsSource:'archive',odds:null,probabilitySource:'empirical',probability:null,pushProbability:null};
    }
    state=draft;if(event.target.tagName==='SELECT')render();
  });
  container.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||!container.contains(button))return;
    try{
      if(button.hasAttribute('data-save-alert')&&!saving){const definition=getDefinition();saving=true;button.disabled=true;await onSave(definition);error('');}
      else if(button.hasAttribute('data-cancel-alert')){reset();onCancel();}
      else if(button.hasAttribute('data-add-bet')||button.hasAttribute('data-add-condition')){
        state=readDraft();if(state.situations.length>=40)throw new Error('Máximo 40 filas.');
        const role=button.hasAttribute('data-add-bet')?'bet':'condition';
        if(role==='bet'&&state.situations.filter(s=>s.role==='bet').length>=8)throw new Error('Podés combinar hasta 8 selecciones.');
        state.situations.push({id:`row-${Date.now()}-${++sequence}`,role,selection:newSituationSelection(),price:role==='condition'?{operator:'between',min:null,max:null}:null});render();
      }else if(button.hasAttribute('data-remove-situation')){
        state=readDraft();const index=Number(button.dataset.removeSituation);
        if(state.situations[index].role==='bet'&&state.situations.filter(s=>s.role==='bet').length===1)return;
        state.situations.splice(index,1);render();
      }else if(button.hasAttribute('data-toggle-price')){state=readDraft();const s=state.situations[Number(button.dataset.togglePrice)];s.price=s.price?null:{operator:'between',min:null,max:null};render();}
    }catch(problem){error(problem);}finally{saving=false;if(button.isConnected)button.disabled=false;}
  });
  function edit(rule){state=situationsDraftFromAlert(rule);editing=Boolean(rule.id);cleanPlayers(state);render();}
  function reset(){state=newSituationsDraft();editing=false;render();}
  function setEntities(next){if(container.childElementCount)state=readDraft();catalog=next||{};cleanPlayers(state);render();}
  render();return {edit,reset,getDefinition,setEntities};
}

/** Saved rule kinds retain their editor; new formulas use payment mathematics. */
export function mountFootballAlertBuilder(container,options={}){
  let catalog=options.entities||{},current,mode;
  function activate(nextMode){
    mode=nextMode;
    const surface=container.ownerDocument.createElement('div');surface.className='football-builder-host';
    container.replaceChildren(surface);
    const mount=mode==='football-alert'?mountLegacyFootballAlertBuilder:mode==='football-formula'?mountUnifiedFormulaEditor:mode==='reference-price'?mountReferencePriceFormulaEditor:mountPriceFormulaEditor;
    current=mount(surface,{...options,entities:catalog,onCancel:()=>{if(mode!==PRICE_FORMULA_KIND)activate(PRICE_FORMULA_KIND);options.onCancel?.();}});
  }
  activate(PRICE_FORMULA_KIND);
  return {
    edit(rule){const next=rule.kind===PRICE_FORMULA_KIND&&!isPaymentFormula(rule)?'reference-price':rule.kind;if(next!==mode)activate(next);current.edit(rule);},
    reset(){if(mode!==PRICE_FORMULA_KIND)activate(PRICE_FORMULA_KIND);else current.reset();},
    getDefinition(){return current.getDefinition();},
    setEntities(next){catalog=next||{};current.setEntities(catalog);},
  };
}
