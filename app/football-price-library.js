/** 120 price-only recipes. Seed migration preserves user changes and a backup. */
import {PRICE_FORMULA_KIND,normalizePriceFormula} from './football-price-engine.js';
import {buildFootballFormulaLibrary} from './football-formula-library.js';
import {STRATEGY_STORAGE_KEY,defaultScoreAlert} from './strategy-store.js';
export const PRICE_LIBRARY_COUNT=120;
export const PRICE_LIBRARY_BACKUP_KEY='workraken-football-strategies-price-backup-v1';
const pad=n=>String(n).padStart(3,'0');
const percent=n=>(n*100).toLocaleString('es-AR',{maximumFractionDigits:2})+'%';
export function buildPriceFormulaLibrary(){
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
const stable=value=>JSON.stringify(value,(key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b))):item);
export function seedPriceFormulaLibrary(existing,entities,storage=globalThis.localStorage){
  const oldSeeds=new Map();try{for(const f of buildFootballFormulaLibrary(entities))oldSeeds.set(f.id,f);}catch{}
  const originalDefault=defaultScoreAlert();oldSeeds.set(originalDefault.id,originalDefault);
  const removed=[],retained=existing.filter(f=>{const seed=oldSeeds.get(f.id),unchanged=seed&&stable(f)===stable(seed);if(unchanged)removed.push(f);return !unchanged;});
  const present=new Set(retained.map(f=>f.id)),additions=buildPriceFormulaLibrary().filter(f=>!present.has(f.id));
  if(!removed.length&&!additions.length)return existing;
  if(removed.length&&!storage?.getItem(PRICE_LIBRARY_BACKUP_KEY))storage?.setItem(PRICE_LIBRARY_BACKUP_KEY,JSON.stringify(existing));
  const merged=[...retained,...additions];storage?.setItem(STRATEGY_STORAGE_KEY,JSON.stringify(merged));return merged;
}
