/** Price criteria and complete portfolios. No team/player/league selection. */
import {settleFootballAction,summarizeFootballAlerts,validateFootballStrategy} from './football-strategy-engine.js';
import {marketDefinition,footballMarketLabel} from './football-market-catalog.js';

export const PRICE_FORMULA_KIND='football-price';
export const PRICE_CONDITION_FIELDS=Object.freeze(['odds','gross_payout','profit_if_win','ev','expected_profit','expected_payout','reference_probability','references','dispersion','fair_payout','payout_edge','inverse_sum','min_payout','min_profit','min_return']);
export const PRICE_FIELD_LABELS=Object.freeze({odds:'Cuota',gross_payout:'Pago al acertar',profit_if_win:'Ganancia al acertar',ev:'EV',expected_profit:'Beneficio esperado',expected_payout:'Pago esperado',reference_probability:'Probabilidad de referencia',references:'Casas de referencia',dispersion:'Dispersión',fair_payout:'Pago de equilibrio',payout_edge:'Ventaja de pago',inverse_sum:'Suma inversa',min_payout:'Pago mínimo',min_profit:'Beneficio mínimo',min_return:'Retorno mínimo'});
const fields=new Set(PRICE_CONDITION_FIELDS),finite=x=>typeof x==='number'&&Number.isFinite(x),validOdds=x=>finite(x)&&x>1,prob=x=>finite(x)&&x>=0&&x<=1;
const clone=x=>JSON.parse(JSON.stringify(x)),list=x=>Array.isArray(x)?x:[],day=e=>String(e.date||e.startDate||e.kickoff||'').slice(0,10),EPS=1e-10;
const centAmount=x=>Number.isSafeInteger(Math.round(x*100))&&Math.abs(x*100-Math.round(x*100))<=1e-7;
let serial=0;
const number=(x,label)=>{if(x==null||String(x).trim()===''||!Number.isFinite(Number(x)))throw new Error(`Completá ${label}.`);return Number(x);};
export function newPriceCondition(field=''){return {type:'condition',id:`price-condition-${++serial}`,field,operator:'>=',value:null};}
export function newPriceFormula(){return {kind:PRICE_FORMULA_KIND,version:1,id:null,name:'',stake:100,mode:'coverage',structure:'two_outcomes',bookPolicy:'same_book',costRate:0,oddsDrop:0,onePerMatch:true,expression:{type:'group',id:'price-group-1',operator:'Y',children:[{...newPriceCondition('min_return'),operator:'>',value:0}]}};}
export function normalizePriceFormula(raw){
  if(!raw||raw.kind&&raw.kind!==PRICE_FORMULA_KIND)throw new Error('La fórmula no pertenece al editor de pagos.');
  if(raw.version!=null&&raw.version!==1)throw new Error('La versión de la fórmula no es compatible.');
  const name=String(raw.name||'').trim();if(!name)throw new Error('Poné un nombre a la fórmula.');
  let stake=number(raw.stake??100,'el importe');if(stake<=0)throw new Error('El importe debe ser mayor que cero.');
  const mode=raw.mode||'value',structure=raw.structure||'two_outcomes',bookPolicy=raw.bookPolicy||'same_book';
  if(!['value','coverage'].includes(mode))throw new Error('Elegí EV o cobertura.');
  if(mode==='coverage'){if(!centAmount(stake))throw new Error('El importe de cobertura debe tener hasta dos decimales.');stake=Math.round(stake*100)/100;}
  if(!['two_outcomes','three_outcomes','double_chance'].includes(structure))throw new Error('Elegí una estructura de pagos válida.');
  if(!['same_book','cross_book'].includes(bookPolicy))throw new Error('Elegí una política de casas válida.');
  const costRate=number(raw.costRate??0,'el costo'),oddsDrop=number(raw.oddsDrop??0,'la caída de cuota');
  if(costRate<0||costRate>=1||oddsDrop<0||oddsDrop>=1)throw new Error('El costo y la caída de cuota deben estar entre cero y menos de uno.');
  const ids=new Set();let count=0;
  function visit(node,path,depth){
    if(depth>12)throw new Error('Podés anidar hasta 12 niveles de grupos.');
    if(!node||typeof node!=='object'||Array.isArray(node))throw new Error('La condición no es válida.');
    if(node.type==='condition'&&!node.field)return null;
    const id=String(node.id||path);if(ids.has(id))throw new Error('Cada condición necesita un identificador distinto.');ids.add(id);
    if(node.type==='group'){
      if(!['Y','O'].includes(node.operator))throw new Error('Elegí Y u O.');
      if(!Array.isArray(node.children))throw new Error('El grupo necesita condiciones.');
      const children=node.children.map((n,i)=>visit(n,`${path}-${i+1}`,depth+1)).filter(Boolean);
      return children.length?{type:'group',id,operator:node.operator,children}:null;
    }
    if(node.type!=='condition'||!fields.has(node.field))throw new Error('Elegí una condición de pago válida.');
    if(++count>100)throw new Error('Podés usar hasta 100 condiciones.');
    const operator=node.operator==='=='?'=':node.operator||'>=';
    if(!['>=','>','<=','<','=','!=','between'].includes(operator))throw new Error('Elegí una comparación válida.');
    const result={type:'condition',id,field:node.field,operator};
    if(operator==='between'){result.min=number(node.min,'el mínimo');result.max=number(node.max,'el máximo');if(result.min>result.max)throw new Error('El mínimo debe ser menor o igual al máximo.');}
    else result.value=number(node.value,'el valor');
    return result;
  }
  let expression=visit(raw.expression,'price-root',0);if(!expression)throw new Error('Agregá al menos una condición.');
  if(expression.type!=='group')expression={type:'group',id:ids.has('price-root-group')?'price-root-outer':'price-root-group',operator:'Y',children:[expression]};
  return {kind:PRICE_FORMULA_KIND,version:1,id:raw.id||null,name:name.slice(0,100),stake,mode,structure,bookPolicy,costRate,oddsDrop,onePerMatch:raw.onePerMatch!==false,expression};
}
export function formatPriceFormula(raw){
  const n=x=>finite(x)?x.toLocaleString('es-AR',{maximumFractionDigits:8}):'';
  const percentages=new Set(['ev','reference_probability','dispersion','min_return']);
  function show(node){if(!node)return '';if(node.type==='group')return `(${node.children.map(show).filter(Boolean).join(` ${node.operator} `)})`;if(!node.field)return '';const label=PRICE_FIELD_LABELS[node.field]||node.field,display=x=>percentages.has(node.field)?`${n(x*100)} %`:n(x);return node.operator==='between'?`${label} entre ${display(node.min)} y ${display(node.max)}`:`${label} ${{'>=':'≥','<=':'≤','!=':'≠'}[node.operator]||node.operator} ${display(node.value)}`;}
  return show(raw.expression||raw);
}
function matches(node,values){
  if(node.type==='group'){let missing=false;for(const child of node.children){const result=matches(child,values);if(node.operator==='Y'&&result===false)return false;if(node.operator==='O'&&result===true)return true;if(result==null)missing=true;}return missing?null:node.operator==='Y';}
  const x=values[node.field];if(!finite(x))return null;
  if(node.operator==='between')return x>=node.min&&x<=node.max;
  switch(node.operator){case '>=':return x>=node.value;case '>':return x>node.value;case '<=':return x<=node.value;case '<':return x<node.value;case '=':return x===node.value;case '!=':return x!==node.value;default:return null;}
}
const matrixFor=(prices,structure)=>structure==='double_chance'?[[prices[0],0,prices[2]],[prices[0],prices[1],0],[0,prices[1],prices[2]]]:prices.map((p,i)=>prices.map((_,j)=>i===j?p:0));
const returns=(matrix,stakes)=>matrix.map(row=>row.reduce((sum,p,i)=>sum+p*stakes[i],0));
/** Complete declared outcomes only. Manual calculator output is theoretical. */
export function calculatePaymentCoverage({odds,budget=100,structure='two_outcomes',costRate=0,oddsDrop=0}){
  if(!['two_outcomes','three_outcomes','double_chance'].includes(structure))throw new Error('La estructura de pagos no es válida.');
  const size=structure==='two_outcomes'?2:3;
  if(!Array.isArray(odds)||odds.length!==size||!odds.every(validOdds))throw new Error(`Completá ${size} cuotas mayores que uno.`);
  if(!finite(budget)||budget<=0||!finite(costRate)||costRate<0||costRate>=1||!finite(oddsDrop)||oddsDrop<0||oddsDrop>=1)throw new Error('El importe, costo o caída de cuota no es válido.');
  if(!centAmount(budget))throw new Error('El importe de cobertura debe tener hasta dos decimales.');budget=Math.round(budget*100)/100;
  const effectiveOdds=odds.map(q=>q*(1-oddsDrop));
  const inverseSum=effectiveOdds.reduce((s,q)=>s+1/q,0),matrix=matrixFor(effectiveOdds,structure);
  const choices=[effectiveOdds.map(q=>1/q/inverseSum)];
  // All interior DC optima have equal ticket payments. Boundary optima are
  // two-ticket covers. Enumerating both solves this three-state maximin exactly.
  if(structure==='double_chance')for(let excluded=0;excluded<3;excluded++){
    const divisor=effectiveOdds.reduce((s,q,i)=>s+(i===excluded?0:1/q),0);
    choices.push(effectiveOdds.map((q,i)=>i===excluded?0:1/q/divisor));
  }
  let weights=choices[0],best=-Infinity;
  for(const w of choices){const floor=Math.min(...returns(matrix,w));if(floor>best+EPS){best=floor;weights=w;}}
  const stakes=weights.map(w=>w*budget),payouts=returns(matrix,stakes),cost=budget*costRate,totalCost=budget+cost;
  const labels=size===2?['first','second']:['home','draw','away'];
  const payoutByOutcome=Object.fromEntries(labels.map((label,i)=>[label,payouts[i]])),profitByOutcome=Object.fromEntries(labels.map((label,i)=>[label,payouts[i]-totalCost]));
  const minPayout=Math.min(...payouts),minProfit=minPayout-totalCost,minReturn=minProfit/budget,constantPayout=structure!=='double_chance'||weights.every(w=>w>0);
  const centBudget=Math.round(budget*100),cents=weights.map(w=>Math.floor(w*centBudget));
  const order=weights.map((w,i)=>({i,r:w*centBudget-cents[i]})).sort((a,b)=>b.r-a.r||a.i-b.i);
  const remainder=centBudget-cents.reduce((a,b)=>a+b,0);for(let i=0;i<remainder;i++)cents[order[i%size].i]++;
  const roundedStakes=cents.map(c=>c/100),roundedPayoutCents=matrix.map(row=>row.reduce((s,p,i)=>s+Math.floor((p*roundedStakes[i]+1e-10)*100),0)),roundedPayouts=roundedPayoutCents.map(c=>c/100);
  const roundedMinPayout=Math.min(...roundedPayouts),roundedMinProfit=roundedMinPayout-totalCost,roundedMinReturn=roundedMinProfit/budget,roundedConstantPayout=roundedPayoutCents.every(c=>c===roundedPayoutCents[0]);
  return {structure,budget,odds:[...odds],effectiveOdds,weights,stakes,cost,totalCost,matrix,payoutByOutcome,profitByOutcome,inverseSum,minPayout,minProfit,minReturn,constantPayout,
    ev:constantPayout?minReturn:null,expectedProfit:constantPayout?minProfit:null,expectedPayout:constantPayout?minPayout:null,isScenario:true,
    roundedStakes,roundedPayoutByOutcome:Object.fromEntries(labels.map((label,i)=>[label,roundedPayouts[i]])),roundedMinPayout,roundedMinProfit,roundedMinReturn,roundedConstantPayout,roundedEV:roundedConstantPayout?roundedMinReturn:null,
    rounded_min_payout:roundedMinPayout,rounded_min_profit:roundedMinProfit,rounded_min_return:roundedMinReturn,
    inverse_sum:inverseSum,min_payout:minPayout,min_profit:minProfit,min_return:minReturn};
}

const normalizePeriod=x=>({ft:'full',full_time:'full',ht:'first_half',half_time:'first_half','1h':'first_half','2h':'second_half'})[x]||x||'full';
const normalizeMarket=x=>({h2h:'match_result',three_way:'match_result',totals:'total_goals',totals25:'total_goals',both_teams_to_score:'btts'})[x]||x||'match_result';
const normalizeSelection=x=>({H:'home',D:'draw',A:'away','1':'home',X:'draw','2':'away',Yes:'yes',No:'no',Over:'over',Under:'under','1X':'home_draw',X2:'draw_away','2X':'draw_away','12':'home_away'})[x]||String(x??'').toLowerCase();
function actionFor(q){const a={market:normalizeMarket(q.market),period:normalizePeriod(q.period),selection:normalizeSelection(q.selection??['home','draw','away'][Number(q.side)])};for(const k of ['team','teamId','playerId','line','homeGoals','awayGoals'])if(q[k]!=null)a[k]=q[k];return a;}
const actionKey=a=>JSON.stringify(['market','period','selection','team','teamId','playerId','line','homeGoals','awayGoals'].map(k=>a[k]??null));
const rulesKey=q=>{const v=q.rulesId??q.rules_id??q.settlementRulesId??q.settlementRules??'';return typeof v==='object'?JSON.stringify(v):String(v);};
const quoteSnapshot=q=>String(q.snapshotId??q.quoteSnapshotId??q.snapshot_id??q.quote_snapshot_id??'');
function quoteTime(q){const value=q.capturedAt??q.captured_at??q.timestamp??q.createdAt;if(value==null||typeof value!=='string'||!/(Z|[+-]\d{2}:?\d{2})$/i.test(value))return null;const t=Date.parse(value);return Number.isFinite(t)?t:null;}
function referenceFor(q){
  const refs=list(q.references),book=String(q.book),names=refs.map(x=>typeof x==='string'?x:String(x?.book??x?.bookmaker??x?.code??''));
  const independent=names.length>0&&names.every(x=>x&&x!==book),p=q.referenceProbability??q.reference_probability??q.probability,sd=q.referenceSd??q.reference_sd;
  return {probability:independent&&prob(p)?p:null,references:independent?new Set(names).size:null,dispersion:independent&&finite(sd)&&sd>=0?sd:null,names};
}
function needsPush(a){return a.market==='draw_no_bet'||a.market==='asian_handicap'&&Number.isInteger(a.line)||['count','player_count'].includes(marketDefinition(a.market)?.kind)&&['over','under'].includes(a.selection)&&Number.isInteger(a.line);}
function valueFor(q,a,rule){
  const reference=referenceFor(q),p=reference.probability,rawPush=q.pushProbability??q.push_probability,push=rawPush==null?(needsPush(a)?null:0):prob(rawPush)?rawPush:null;
  const odds=q.odds*(1-rule.oddsDrop),gross=rule.stake*odds,cost=rule.stake*rule.costRate,valid=prob(p)&&prob(push)&&p+push<=1+EPS;
  const expected=valid?rule.stake*(p*odds+push):null,ev=valid?expected/rule.stake-1-rule.costRate:null;
  const fair=valid&&p>0?rule.stake*(1-push+rule.costRate)/p:null;
  return {odds,gross_payout:gross,profit_if_win:gross-rule.stake-cost,ev,expected_profit:ev==null?null:ev*rule.stake,expected_payout:expected,reference_probability:valid?p:null,references:reference.references,dispersion:reference.dispersion,fair_payout:fair,payout_edge:fair==null?null:gross-fair,pushProbability:push,reference};
}
function settlementCatalog(entities){
  const teams=new Map(list(entities.teams).map(x=>[String(x.id),x])),players=new Map(list(entities.players).map(x=>[String(x.id),x])),fold=x=>String(x??'').toLowerCase();
  const names=new Map();for(const t of teams.values())for(const n of [t.name,...list(t.aliases)]){const key=fold(n);names.set(key,names.has(key)&&names.get(key)!==String(t.id)?null:String(t.id));}
  return {entities,byTeam:teams,byPlayer:players,rosterMaxAgeDays:14,resolve(e,side){const explicit=e[`${side}TeamId`]??e[`${side}_team_id`];return explicit==null?names.get(fold(e[side]??e[`${side}_team`]))||null:String(explicit);}};
}
function baseRow(entry,book){const e=entry.event;return {eventId:String(e.id),event:entry.index,date:day(e),league:e.league??e.league_code,home:e.home??e.home_team,away:e.away??e.away_team,book};}
function selectionsFor(a,structure){
  if(a.playerId)return null;
  if(structure==='double_chance')return a.market==='double_chance'?['home_draw','draw_away','home_away']:null;
  if(structure==='three_outcomes'){
    if(['match_result','handicap_result'].includes(a.market))return ['home','draw','away'];
    if(['first_team_to_score','last_team_to_score'].includes(a.market))return ['home','away','none'];
    return null;
  }
  if(a.market==='btts')return ['yes','no'];
  if(a.market==='odd_even')return ['odd','even'];
  if(['total_goals','team_goals','corners','cards','shots','shots_on_target','offsides'].includes(a.market)&&finite(a.line)&&Math.abs(a.line%1)===.5)return ['over','under'];
  return null;
}
function coverageValues(payment){return {odds:null,gross_payout:null,profit_if_win:null,ev:payment.roundedEV,expected_profit:payment.roundedEV==null?null:payment.roundedMinProfit,expected_payout:payment.roundedEV==null?null:payment.roundedMinPayout,reference_probability:null,references:null,dispersion:null,fair_payout:null,payout_edge:null,inverse_sum:payment.inverseSum,min_payout:payment.roundedMinPayout,min_profit:payment.roundedMinProfit,min_return:payment.roundedMinReturn};}

/** The same supplied prices and budget always give the same calculation.
 * Bookmaker names, probabilities, references and historical results are not
 * inputs. Rounded ticket amounts/payments are used for every rule predicate.
 */
export function evaluatePaymentFormula(rawRule,{odds,budget}={}){
  const raw=rawRule||newPriceFormula(),rule=normalizePriceFormula({...raw,name:raw.name||'Cálculo de pagos',stake:budget??raw.stake??100,mode:raw.mode||'coverage'});
  if(rule.mode!=='coverage')throw new Error('La calculadora usa fórmulas de pagos.');
  const payment=calculatePaymentCoverage({odds,budget:rule.stake,structure:rule.structure,costRate:rule.costRate,oddsDrop:rule.oddsDrop}),values=coverageValues(payment),payoutByOutcome=payment.roundedPayoutByOutcome;
  const profitByOutcome=Object.fromEntries(Object.entries(payoutByOutcome).map(([key,payout])=>[key,payout-payment.totalCost]));
  const maxPayout=Math.max(...Object.values(payoutByOutcome)),maxProfit=maxPayout-payment.totalCost,maxReturn=maxProfit/payment.budget;
  return {...payment,...values,odds:[...payment.odds],fields:values,contextValues:values,match:matches(rule.expression,values),
    stakes:[...payment.roundedStakes],sumStakes:payment.roundedStakes.reduce((sum,x)=>sum+Math.round(x*100),0)/100,payoutByOutcome,profitByOutcome,
    minPayout:payment.roundedMinPayout,minProfit:payment.roundedMinProfit,minReturn:payment.roundedMinReturn,maxPayout,maxProfit,maxReturn,
    constantPayout:payment.roundedConstantPayout,ev:values.ev,expectedProfit:values.expected_profit,expectedPayout:values.expected_payout,
    evLowerBound:payment.roundedMinReturn,ev_lower_bound:payment.roundedMinReturn,evIsExact:payment.roundedConstantPayout,
    evBasis:payment.roundedConstantPayout?'constant_payoff':'minimum_return_bound',evLabel:payment.roundedConstantPayout?'EV exacto':'Piso del retorno',
    theoretical:{stakes:payment.stakes,payoutByOutcome:payment.payoutByOutcome,profitByOutcome:payment.profitByOutcome,minPayout:payment.minPayout,minProfit:payment.minProfit,minReturn:payment.minReturn,ev:payment.ev}};
}

// Workers explicitly opt in for their immutable archive. Direct evaluations of
// mutable/live inputs always prepare afresh, so updates cannot reuse stale data.
const preparedArchives=new WeakMap();
function prepareSource(events,source,immutable){
  const cached=immutable?preparedArchives.get(source):null;
  if(cached&&cached.events===events&&cached.sourceLength===source.length&&cached.eventLength===events.length)return cached;
  const entries=events.map((event,index)=>({event,index})),byId=new Map(entries.map(x=>[String(x.event.id),x])),entryIndices=new Int32Array(source.length),recordIndices=new Int32Array(source.length),actions=new Map(),records=[];
  entryIndices.fill(-1);recordIndices.fill(-1);
  for(let i=0;i<source.length;i++){
    const q=source[i],entry=Number.isInteger(q.event)?entries[q.event]:byId.get(String(q.eventId??q.matchId??q.event??q.id));
    if(!entry||q.book==null||!String(q.book))continue;
    const raw=[q.market??'',q.period??'',q.selection??q.side,q.team??'',q.teamId??'',q.playerId??'',q.line??'',q.homeGoals??'',q.awayGoals??''].join('\u001f');
    if(!actions.has(raw)){const a=actionFor(q);let index=-1;try{if(!marketDefinition(a.market))throw new Error();validateFootballStrategy({conditions:[],action:{...a,stake:1}});index=records.length;records.push({action:a,key:actionKey(a)});}catch{}actions.set(raw,index);}
    const recordIndex=actions.get(raw);if(recordIndex<0)continue;entryIndices[i]=entry.index;recordIndices[i]=recordIndex;
  }
  const prepared={events,sourceLength:source.length,eventLength:events.length,entries,entryIndices,recordIndices,records,coverageGroups:new Map()};
  if(immutable)preparedArchives.set(source,prepared);return prepared;
}

/** Returns one row per value bet or one row per complete multi-ticket operation. */
export function evaluatePriceFormula(universe,rawRule,options={}){
  const rule=normalizePriceFormula(rawRule),entities=options.entities||{},events=list(universe?.events);
  const source=Array.isArray(universe?.offers)?universe.offers:[...list(universe?.marketQuotes),...events.flatMap((event,index)=>list(event.marketQuotes).map(q=>({...q,event:index})))];
  const prepared=prepareSource(events,source,options.immutableUniverse===true),{entries,entryIndices,recordIndices,records:contractRecords}=prepared;
  const catalog=settlementCatalog(entities),settled=new Map(),alerts=[],seen=new Set();let candidateEvents=new Set(),candidates=0,unknown=0,failed=0;
  function outcome(entry,rec){const key=`${entry.index}\u001f${rec.key}`;if(!settled.has(key))settled.set(key,settleFootballAction(entry.event,rec.action,{}, {_catalog:catalog}));return settled.get(key);}
  const getOutcomeProfit=(entry,rec,odds,stake)=>{const result=outcome(entry,rec),won=result.outcome==='win'?true:result.outcome==='loss'?false:result.outcome==='push'?'push':null;return {result,won,profit:won==null?null:(won===true?(odds-1)*stake:won===false?-stake:0)-stake*rule.costRate};};
  if(rule.mode==='value'){
    for(let i=0;i<source.length;i++){const q=source[i];if(entryIndices[i]<0||!validOdds(q.odds)||q.active===false||q.suspended===true)continue;const entry=entries[entryIndices[i]],rec=contractRecords[recordIndices[i]];candidates++;candidateEvents.add(entry.index);
      // A known false price branch stays false after references arrive. This
      // early pass preserves three-valued Y/O while avoiding reference work for
      // quotes outside a requested payment band. Unknown is never rejected here.
      const cheapOdds=q.odds*(1-rule.oddsDrop),cheapGross=rule.stake*cheapOdds;
      if(matches(rule.expression,{odds:cheapOdds,gross_payout:cheapGross,profit_if_win:cheapGross-rule.stake*(1+rule.costRate)})===false){failed++;continue;}
      const values=valueFor(q,rec.action,rule),match=matches(rule.expression,values);if(match!==true){match==null?unknown++:failed++;continue;}
      const snapshot=quoteSnapshot(q)||quoteTime(q)||'',id=JSON.stringify([String(entry.event.id),String(q.book),snapshot,rec.key,q.odds]);if(seen.has(id))continue;seen.add(id);
      const {result,won,profit}=getOutcomeProfit(entry,rec,values.odds,rule.stake),scenario=rule.costRate>0||rule.oddsDrop>0,statuses=[];
      if(values.ev==null)statuses.push('probability_missing');if(won==null)statuses.push(result.status||'result_missing');
      const row={...baseRow(entry,String(q.book)),id,side:q.side,market:rec.action.market,period:rec.action.period,selection:rec.action.selection,actionLabel:options.summaryOnly?'':footballMarketLabel(rec.action,{home:entry.event.home??entry.event.home_team??'Local',away:entry.event.away??entry.event.away_team??'Visitante',player:'Jugador'}),contextOdds:null,contextValues:values,odds:values.odds,probability:values.reference_probability,pushProbability:values.pushProbability,probabilityN:values.references,probabilitySource:values.reference_probability==null?null:'reference',reference:values.reference.names,ev:values.ev,expectedProfit:values.expected_profit,stake:rule.stake,won,outcome:result.outcome,profit,quoteSource:scenario?'manual':'archive',isScenario:scenario,breakEven:prob(values.pushProbability)?(1-values.pushProbability+rule.costRate)/values.odds:null,status:statuses[0]||'ready',statuses,triggered:true};
      if(!options.summaryOnly)row.sourceQuote=clone(q);alerts.push(row);
    }
  }else{
    // A missing snapshot is not an implicit shared snapshot. Keep those groups
    // only to report unknown coverage, never to manufacture simultaneous odds.
    const preparationKey=`${rule.structure}|${rule.bookPolicy}`;let coverage=prepared.coverageGroups.get(preparationKey);
    if(!coverage){
      const groups=new Map(),missingGroups=new Set(),contextEvents=new Set();
      for(let i=0;i<source.length;i++){const q=source[i];if(entryIndices[i]<0)continue;const entry=entries[entryIndices[i]],rec=contractRecords[recordIndices[i]],selections=selectionsFor(rec.action,rule.structure);if(!selections||!selections.includes(rec.action.selection))continue;
        const live=validOdds(q.odds)&&q.active!==false&&q.suspended!==true,a=rec.action,snapshot=quoteSnapshot(q),time=quoteTime(q);
        // Invalid prices and suspensions remain in timed histories as tombstones.
        if(!live&&time==null&&!snapshot)continue;
        contextEvents.add(entry.index);const rules=rulesKey(q),base=JSON.stringify([entry.index,a.market,a.period,a.line??null,a.team??null,a.teamId??null,rules,rule.bookPolicy==='same_book'?String(q.book):null]),key=base+'\u001f'+(snapshot?`snapshot:${snapshot}`:time!=null?'time':'missing');
        if(!rules||!snapshot&&time==null){missingGroups.add(key);continue;}
        if(!groups.has(key))groups.set(key,{entry,selections,records:[],snapshot,timed:!snapshot&&time!=null});groups.get(key).records.push({q,rec,time,live});
      }
      coverage={groups,unknown:missingGroups.size,contextEvents};prepared.coverageGroups.set(preparationKey,coverage);
    }
    const {groups}=coverage;candidateEvents=coverage.contextEvents;candidates+=coverage.unknown;unknown+=coverage.unknown;
    for(const group of groups.values()){
      function* windows(){if(!group.timed){yield group.records;return;}const ordered=[...group.records].sort((a,b)=>a.time-b.time);let start=0,end=0;while(end<ordered.length){const at=ordered[end].time;while(end<ordered.length&&ordered[end].time===at)end++;while(at-ordered[start].time>60000)start++;yield ordered.slice(start,end);}}
      const batches=windows();
      for(const records of batches){
        const best=new Map(),conflicts=new Map();let ambiguous=false;
        for(const r of records){if(!r.live){if(!group.timed)ambiguous=true;continue;}const key=String(r.q.book)+'\u001f'+r.rec.action.selection;if(conflicts.has(key)&&conflicts.get(key)!==r.q.odds){if(!group.timed)ambiguous=true;}conflicts.set(key,r.q.odds);
          const previous=best.get(r.rec.action.selection);if(!previous||r.q.odds>previous.q.odds||r.q.odds===previous.q.odds&&(r.time??0)>(previous.time??0))best.set(r.rec.action.selection,r);
        }
        // A time window may have multiple updates of the same ticket. Only its
        // latest update was active at the end of that window.
        if(group.timed){best.clear();const latest=new Map();for(const r of records){const key=String(r.q.book)+'\u001f'+r.rec.action.selection,previous=latest.get(key);latest.set(key,previous&&previous.time===r.time?(!r.live||!previous.live?{...r,live:false}:r.q.odds<previous.q.odds?r:previous):r);}for(const r of latest.values()){if(!r.live)continue;const previous=best.get(r.rec.action.selection);if(!previous||r.q.odds>previous.q.odds)best.set(r.rec.action.selection,r);}}
        candidates++;if(ambiguous||!group.selections.every(s=>best.has(s))){unknown++;continue;}
        const legs=group.selections.map(s=>best.get(s)),times=legs.map(r=>r.time).filter(x=>x!=null);
        if(times.length>1&&Math.max(...times)-Math.min(...times)>60000){unknown++;continue;}
        const id=JSON.stringify([String(group.entry.event.id),...legs.map(r=>[r.q.book,quoteSnapshot(r.q),r.time,r.rec.key,r.q.odds])]);if(seen.has(id))continue;seen.add(id);
        const payment=calculatePaymentCoverage({odds:legs.map(r=>r.q.odds),budget:rule.stake,structure:rule.structure,costRate:rule.costRate,oddsDrop:rule.oddsDrop}),values=coverageValues(payment),match=matches(rule.expression,values);
        if(match!==true){match==null?unknown++:failed++;continue;}
        const outcomes=legs.map((r,i)=>{const x=getOutcomeProfit(group.entry,r.rec,payment.effectiveOdds[i],payment.roundedStakes[i]),stake=payment.roundedStakes[i];const payout=x.won==null?null:x.won===true?Math.floor((stake*payment.effectiveOdds[i]+1e-10)*100)/100:x.won==='push'?stake:0;return {...x,payout,profit:payout==null?null:payout-stake-stake*rule.costRate};}),hasResult=outcomes.every(x=>x.payout!=null),profit=hasResult?outcomes.reduce((sum,x)=>sum+x.payout,0)-payment.totalCost:null;
        // Per-ticket fees sum exactly to budget*costRate, never charged twice.
        const outcomeLabels=rule.structure==='double_chance'?['home','draw','away']:group.selections,payoutByOutcome=Object.fromEntries(Object.values(payment.roundedPayoutByOutcome).map((v,i)=>[outcomeLabels[i],v])),book=[...new Set(legs.map(r=>String(r.q.book)))].join('|');
        const row={...baseRow(group.entry,book),id,market:legs[0].rec.action.market,period:legs[0].rec.action.period,selection:'coverage',actionLabel:`Cobertura · ${group.selections.join(' / ')}`,contextOdds:null,contextValues:values,odds:null,probability:null,pushProbability:null,probabilityN:null,probabilitySource:payment.roundedConstantPayout?'constant_payoff':null,reference:[],ev:values.ev,expectedProfit:values.expected_profit,stake:rule.stake,won:profit==null?null:profit>EPS?true:profit<-EPS?false:'push',outcome:profit==null?null:profit>EPS?'win':profit<-EPS?'loss':'push',profit,quoteSource:'manual',isScenario:true,breakEven:null,status:profit==null?'result_missing':'ready',statuses:profit==null?['result_missing']:[],triggered:true,minPayout:payment.roundedMinPayout,minProfit:payment.roundedMinProfit,minReturn:payment.roundedMinReturn,inverseSum:payment.inverseSum,payoutByOutcome,
          legs:legs.map((r,i)=>({book:String(r.q.book),odds:r.q.odds,effectiveOdds:payment.effectiveOdds[i],stake:payment.roundedStakes[i],selection:r.rec.action.selection,market:r.rec.action.market,period:r.rec.action.period,line:r.rec.action.line??null,rulesId:rulesKey(r.q),snapshotId:quoteSnapshot(r.q)||null,capturedAt:r.q.capturedAt??r.q.captured_at??r.q.timestamp??r.q.createdAt??null,sourceId:r.q.quoteId??r.q.id??null,profit:outcomes[i].profit,...(!options.summaryOnly?{sourceQuote:clone(r.q)}:{})}))};
        alerts.push(row);
      }
    }
  }
  let result=alerts;
  if(rule.onePerMatch){const best=new Map();for(const row of alerts){const previous=best.get(row.eventId),score=rule.mode==='coverage'?row.minReturn:row.ev;if(!previous||(finite(score)?score:-Infinity)>(finite(rule.mode==='coverage'?previous.minReturn:previous.ev)?(rule.mode==='coverage'?previous.minReturn:previous.ev):-Infinity)||score===(rule.mode==='coverage'?previous.minReturn:previous.ev)&&row.id<previous.id)best.set(row.eventId,row);}result=[...best.values()];}
  result.sort((a,b)=>a.date.localeCompare(b.date)||a.eventId.localeCompare(b.eventId)||a.book.localeCompare(b.book)||a.id.localeCompare(b.id));
  const summary=summarizeFootballAlerts(result);
  for(const [field,key] of [['minReturn','meanMinReturn'],['minPayout','meanMinPayout'],['minProfit','meanMinProfit']]){const values=result.map(row=>row[field]).filter(finite);summary[key]=values.length?values.reduce((sum,x)=>sum+x,0)/values.length:null;}
  return {alerts:options.summaryOnly?[]:result,summary,coverage:{events:events.length,contextEvents:candidateEvents.size,quoteGroups:candidates,conditionGroups:result.length,matchedGroups:result.length,alerts:result.length,priced:result.length,probability:result.filter(r=>r.probability!=null).length,valued:result.filter(r=>r.ev!=null).length,settled:result.filter(r=>r.profit!=null).length,missingQuote:0,missingProbability:result.filter(r=>r.ev==null).length,missingConditionValues:unknown,unknownCandidates:unknown,falseCandidates:failed,universe:options.universe||null}};
}
