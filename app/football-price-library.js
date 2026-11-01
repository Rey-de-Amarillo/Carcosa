/** Same-house payment recipes; exact migration retains edited historical rules. */
import {PRICE_FORMULA_KIND,normalizePriceFormula} from './football-price-engine.js';
import {buildFootballFormulaLibrary} from './football-formula-library.js';
import {STRATEGY_STORAGE_KEY,defaultScoreAlert} from './strategy-store.js';
import {DEFAULT_FORMULA,conditionsFromFormula} from './formula-builder.js';
export const PRICE_LIBRARY_COUNT=120;
export const PRICE_LIBRARY_BACKUP_KEY='workraken-football-strategies-price-backup-v2';
const pad=n=>String(n).padStart(3,'0');
const percent=n=>(n*100).toLocaleString('es-AR',{maximumFractionDigits:2})+'%';
export function buildReferencePriceFormulaLibrary(){
  let sequence=0;const result=[];
  const condition=(field,value,operator='>=')=>({type:'condition',id:`price-node-${++sequence}`,field,value,operator});
  const group=(operator,...children)=>({type:'group',id:`price-group-${++sequence}`,operator,children});
  function add(name,expression,overrides={}){const n=pad(result.length+1);result.push(normalizePriceFormula({kind:PRICE_FORMULA_KIND,version:1,id:`library-price-${n}`,name:`${n} · ${name}`,stake:100,mode:'value',structure:'two_outcomes',bookPolicy:'same_book',costRate:0,oddsDrop:0,onePerMatch:true,expression,...overrides}));}
  const bands=[[110,150],[150,190],[190,230],[230,300],[300,500],[500,1200]];
  const profiles=[{refs:3,dispersion:.03},{refs:5,dispersion:.02},{refs:7,dispersion:.01}];
  for(const [min,max] of bands)for(const ev of [.01,.02,.03,.05])for(const profile of profiles){
    const payout={...condition('gross_payout',null,'between'),min,max};delete payout.value;
    add(`Pago ${min}–${max} · EV ≥ ${percent(ev)} · ${profile.refs} refs`,group('Y',payout,condition('ev',ev),condition('references',profile.refs),condition('dispersion',profile.dispersion,'<=')));
  }
  const stress=[{bookPolicy:'same_book',costRate:0,oddsDrop:0,label:'misma casa'},{bookPolicy:'cross_book',costRate:0,oddsDrop:0,label:'entre casas'},{bookPolicy:'cross_book',costRate:.005,oddsDrop:0,label:'costo 0,5%'},{bookPolicy:'cross_book',costRate:.005,oddsDrop:.005,label:'costo y caída 0,5%'}];
  for(const [structure,label] of [['two_outcomes','Dos resultados'],['three_outcomes','Tres resultados'],['double_chance','Doble oportunidad']])for(const floor of [.001,.005,.01,.02])for(const profile of stress){
    const {label:stressLabel,...settings}=profile;
    add(`${label} · retorno ≥ ${percent(floor)} · ${stressLabel}`,group('Y',condition('min_return',floor),condition('min_profit',0,'>')),{mode:'coverage',structure,...settings});
  }
  if(result.length!==PRICE_LIBRARY_COUNT)throw new Error('La biblioteca debe contener 120 fórmulas matemáticas.');
  return result;
}
/** The live library uses only the payout of every possible result. */
export function buildPriceFormulaLibrary(){
  const result=[];let sequence=0;
  const leaf=(field,value,operator='>=')=>({type:'condition',id:`payment-node-${++sequence}`,field,operator,value});
  const structures=[['two_outcomes','Dos resultados'],['three_outcomes','Tres resultados'],['double_chance','Doble oportunidad']];
  const floors=[.001,.0025,.005,.01,.02];
  const stress=[[0,0],[.0025,0],[.005,0],[.01,0],[0,.0025],[0,.005],[0,.01],[.005,.005]];
  for(const [structure,label] of structures)for(const floor of floors)for(const [costRate,oddsDrop] of stress){
    const index=pad(result.length+1);
    result.push(normalizePriceFormula({
      kind:PRICE_FORMULA_KIND,version:1,id:`library-payment-${index}`,
      name:`${index} · ${label} · retorno ≥ ${percent(floor)} · costo ${percent(costRate)} · caída ${percent(oddsDrop)}`,
      stake:100,mode:'coverage',structure,bookPolicy:'same_book',costRate,oddsDrop,onePerMatch:true,
      expression:{type:'group',id:`payment-group-${++sequence}`,operator:'Y',children:[leaf('min_return',floor),leaf('min_profit',0,'>')]},
    }));
  }
  if(result.length!==PRICE_LIBRARY_COUNT)throw new Error('La biblioteca debe contener 120 fórmulas de pagos.');
  return result;
}
/** Existing pure payment rules can stay current without changing their meaning. */
export function isPaymentFormula(rule){
  if(rule?.kind!==PRICE_FORMULA_KIND||rule.mode!=='coverage'||rule.bookPolicy!=='same_book')return false;
  const allowed=new Set(['inverse_sum','min_payout','min_profit','min_return']);
  const pure=node=>node.type==='group'?node.children.every(pure):allowed.has(node.field);
  try{return pure(normalizePriceFormula(rule).expression);}catch{return false;}
}
const stable=value=>JSON.stringify(value,(key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b))):item);
export function seedPriceFormulaLibrary(existing,entities,storage=globalThis.localStorage){
  // Exact known definitions only: an ID, name, or formula kind alone is never
  // enough evidence that a user's saved rule can be replaced.
  const oldSeeds=new Map();
  const remember=rule=>{if(!oldSeeds.has(rule.id))oldSeeds.set(rule.id,new Set());oldSeeds.get(rule.id).add(stable(rule));};
  try{for(const rule of buildFootballFormulaLibrary(entities))remember(rule);}catch{}
  for(const rule of buildReferencePriceFormulaLibrary())remember(rule);
  remember(defaultScoreAlert());
  const originalEV=conditionsFromFormula(DEFAULT_FORMULA);
  for(const rule of [DEFAULT_FORMULA,originalEV]){remember(rule);remember({...rule,kind:'market-ev'});}
  const removed=[],retained=existing.filter(rule=>{const untouched=oldSeeds.get(rule.id)?.has(stable(rule));if(untouched)removed.push(rule);return !untouched;});
  const present=new Set(retained.map(rule=>rule.id)),additions=buildPriceFormulaLibrary().filter(rule=>!present.has(rule.id));
  if(!removed.length&&!additions.length)return existing;
  // Preserve the complete prior collection once, before persisting removals.
  // A failed backup write aborts migration and leaves the old store intact.
  if(removed.length&&storage?.getItem?.(PRICE_LIBRARY_BACKUP_KEY)==null)storage?.setItem?.(PRICE_LIBRARY_BACKUP_KEY,JSON.stringify(existing));
  const merged=[...retained,...additions];storage?.setItem?.(STRATEGY_STORAGE_KEY,JSON.stringify(merged));return merged;
}
