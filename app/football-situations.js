/** Situation authoring keeps price comparisons separate from the bets they trigger.
 * A price checked for the opposing team is never turned into a second bet.
 */
import {newFootballAlert,normalizeFootballAlert} from './football-alert-builder.js';
import {defaultMarketSelection} from './football-market-catalog.js';

const clone=value=>JSON.parse(JSON.stringify(value));
const blankPrice=()=>({operator:'around',value:null,margin:null});
const context=()=>({league:'',homeTeam:'',awayTeam:'',teamId:'',playerId:'',period:'full'});
const valuation=()=>({oddsSource:'archive',odds:null,stake:1,probabilitySource:'empirical',probability:null,pushProbability:null,minSample:30});
const valuationValues=raw=>({...valuation(),...Object.fromEntries(Object.keys(valuation()).filter(k=>raw?.[k]!==undefined).map(k=>[k,raw[k]]))});
const validResult=value=>['home','draw','away'].includes(value)?value:'home';
const opposite=value=>value==='draw'?'draw':value==='away'?'home':'away';
const priceDraft=condition=>condition?.ui?.operator==='around'?clone(condition.ui):condition?Object.fromEntries(['operator','value','margin','min','max'].filter(k=>condition[k]!==undefined).map(k=>[k,condition[k]])):null;
const stripValuation=selection=>Object.fromEntries(['market','period','selection','team','teamId','playerId','line','homeGoals','awayGoals'].filter(key=>selection?.[key]!==undefined).map(key=>[key,clone(selection[key])]));
const priceValues=price=>Object.fromEntries(['operator','value','margin','min','max'].filter(key=>price?.[key]!==undefined).map(key=>[key,clone(price[key])]));
const selectionKey=selection=>JSON.stringify(['market','period','selection','team','teamId','playerId','line','homeGoals','awayGoals'].map(k=>selection?.[k]??null));

export function newSituationSelection(market='match_result'){
  return defaultMarketSelection(market);
}

export function newSituationsDraft(){
  return {id:null,name:'',onePerMatch:true,context:context(),join:'Y',result:'home',valuation:valuation(),legacyConditions:[],situations:[
    {id:'bet-1',role:'bet',selection:newSituationSelection(),price:null},
  ]};
}

/** The shared Result field changes only the first two outcome comparisons. */
export function synchronizeSituationResults(raw){
  const draft=clone(raw),result=validResult(draft.result);draft.result=result;
  const comparisons=(draft.situations||[]).filter(s=>s.role==='condition'&&s.selection?.market==='match_result');
  if(comparisons[0])comparisons[0].selection.selection=result;
  if(comparisons[1])comparisons[1].selection.selection=opposite(result);
  return draft;
}

export function situationsDraftFromAlert(raw){
  if(!raw)return newSituationsDraft();
  if(Array.isArray(raw.situations))return clone(raw);
  const saved=raw.authoring;
  if(saved?.version===3&&Array.isArray(saved.situations))return {
    id:raw.id||null,name:raw.name||'',onePerMatch:raw.onePerMatch!==false,
    context:{...context(),...(raw.context||{})},join:raw.join==='O'?'O':'Y',result:validResult(saved.result),
    valuation:valuationValues(raw.action),
    legacyConditions:clone(saved.legacyConditions||[]),situations:clone(saved.situations),
  };
  const draft={...newSituationsDraft(),id:raw.id||null,name:raw.name||'',onePerMatch:raw.onePerMatch!==false,context:{...context(),...(raw.context||{})},join:raw.join==='O'?'O':'Y',situations:[],legacyConditions:[]};
  draft.valuation=valuationValues(raw.action);
  const action=raw.action||newFootballAlert().action;
  const bets=(action.market==='combination'?action.legs||[]:[action]).map((selection,index)=>({id:`bet-${index+1}`,role:'bet',selection:stripValuation(selection),price:null}));
  for(const [index,condition]of(raw.conditions||[]).entries()){
    const side=condition.field?.match(/^(home|draw|away)_odds$/);
    const leg=condition.field?.match(/^leg_([1-8])_odds$/);
    if(side)draft.situations.push({id:`comparison-${index+1}`,role:'condition',selection:{...newSituationSelection(),selection:side[1]},price:priceDraft(condition)});
    else if(condition.selection)draft.situations.push({id:`comparison-${index+1}`,role:'condition',selection:stripValuation(condition.selection),price:priceDraft(condition)});
    else if(condition.field==='selected_odds'&&bets.length===1&&!bets[0].price)bets[0].price=priceDraft(condition);
    else if(leg&&bets[Number(leg[1])-1]&&!bets[Number(leg[1])-1].price)bets[Number(leg[1])-1].price=priceDraft(condition);
    else draft.legacyConditions.push(clone(condition));
  }
  draft.situations.push(...bets);
  const first=draft.situations.find(s=>s.role==='condition'&&s.selection.market==='match_result');
  draft.result=validResult(first?.selection.selection);
  // Migration retains asymmetric legacy definitions; synchronization happens
  // only when the user changes the shared Result control.
  return draft;
}

function canonicalSelection(selection,draft,entities){
  const validation={...newFootballAlert(),name:draft.name||'Situación',context:draft.context,conditions:[{field:'selected_odds',operator:'>',value:1}],action:{...clone(selection),...valuation()}};
  return stripValuation(normalizeFootballAlert(validation,entities).action);
}

export function compileSituationsAlert(raw,entities={}){
  const draft=situationsDraftFromAlert(raw);
  if(!Array.isArray(draft.situations)||!draft.situations.length||draft.situations.length>40)throw new Error('Agregá entre 1 y 40 situaciones.');
  const situations=draft.situations.map((s,index)=>{
    if(!['condition','bet'].includes(s.role))throw new Error(`Elegí el uso de la situación ${index+1}.`);
    if(!s.selection?.market)throw new Error(`Elegí la apuesta de la situación ${index+1}.`);
    if(s.price!=null&&(typeof s.price!=='object'||Array.isArray(s.price)))throw new Error(`Ingresá una cuota válida en la situación ${index+1}.`);
    return {id:String(s.id||`situation-${index+1}`),role:s.role,selection:canonicalSelection(stripValuation(s.selection),draft,entities),price:s.price==null?null:priceValues(s.price)};
  });
  const bets=situations.filter(s=>s.role==='bet');
  if(!bets.length||bets.length>8)throw new Error('Elegí entre 1 y 8 situaciones para apostar.');
  const action={...(bets.length===1?bets[0].selection:{market:'combination',period:'full',legs:bets.map(s=>s.selection)}),...valuationValues(draft.valuation)};
  // Prices and probabilities are never multiplied to price a joint bet.
  if(bets.length>1&&action.oddsSource!=='manual')action.odds=null;
  const conditions=clone(draft.legacyConditions||[]).map(condition=>({...condition,...(condition.selection?{selection:canonicalSelection(stripValuation(condition.selection),draft,entities)}:{})}));
  for(const [index,situation]of situations.entries()){
    const {selection,role,price}=situation;
    if(price==null){if(role==='condition')throw new Error(`Ingresá la cuota de la situación ${index+1}.`);continue;}
    let field;
    if(role==='bet')field=bets.length===1?'selected_odds':`leg_${bets.indexOf(situation)+1}_odds`;
    else if(selection.market==='match_result'&&selection.period==='full')field=`${selection.selection}_odds`;
    else {
      const same=bets.findIndex(bet=>selectionKey(bet.selection)===selectionKey(selection));
      field=same>=0?(bets.length===1?'selected_odds':`leg_${same+1}_odds`):`situation_${index+1}_odds`;
    }
    conditions.push({field,...clone(price),...(field.startsWith('situation_')?{selection:clone(selection)}:{})});
  }
  const temporary=conditions.map(c=>({...c,field:c.field.startsWith('situation_')?'selected_odds':c.field}));
  const normalized=normalizeFootballAlert({...draft,kind:'football-alert',version:2,action,conditions:temporary.length?temporary:[{field:'selected_odds',operator:'>',value:1}]},entities);
  if(conditions.length)normalized.conditions=conditions.map((original,index)=>({...normalized.conditions[index],field:original.field,...(original.selection?{selection:original.selection}:{})}));
  normalized.authoring={version:3,result:validResult(draft.result),situations,legacyConditions:clone(normalized.conditions.slice(0,(draft.legacyConditions||[]).length))};
  return normalized;
}

/** The store uses this entry point so normalization cannot discard the editor. */
export function canonicalSavedAlert(raw,entities={}){
  if(raw?.authoring?.version===3||Array.isArray(raw?.situations))return compileSituationsAlert(raw,entities);
  return normalizeFootballAlert(raw,entities);
}
