/** Domain alerts coexist with the original EV rule; no legacy formula is erased. */
import {loadFormulas} from './formula-builder.js';
import {compileFormula} from './formula-engine.js';
import {newFootballAlert,normalizeFootballAlert} from './football-alert-builder.js';
import {canonicalSavedAlert} from './football-situations.js';
import {validateFootballStrategy} from './football-strategy-engine.js';
import {UNIFIED_FORMULA_KIND,normalizeUnifiedFormula} from './football-unified-formula.js';
export const STRATEGY_STORAGE_KEY='workraken-football-strategies-v2';
export function defaultScoreAlert(){const rule=newFootballAlert();rule.name='Cuotas 1,90 / 4,00 → 2–1';rule.id='odds-to-score-2-1';return normalizeFootballAlert(rule);}
export function loadStrategies(storage=globalThis.localStorage){
  try{const saved=JSON.parse(storage?.getItem(STRATEGY_STORAGE_KEY)||'null');if(Array.isArray(saved)&&saved.length){const valid=saved.filter(f=>f&&typeof f.id==='string'&&typeof f.name==='string'&&(f.kind===UNIFIED_FORMULA_KIND?f.expression?.type==='group'&&Array.isArray(f.expression.children):f.kind==='football-alert'?f.action&&Array.isArray(f.conditions):typeof f.expression==='string'));if(valid.length)return valid;}}catch{}
  return [defaultScoreAlert(),...loadFormulas(storage).map(f=>({...f,kind:'market-ev'}))];
}
export function saveStrategies(list,entities,storage=globalThis.localStorage){
  const validated=list.map(f=>{if(!f.id||!String(f.name||'').trim())throw new Error('La alerta necesita un nombre.');if(f.kind===UNIFIED_FORMULA_KIND)return normalizeUnifiedFormula(f,entities);if(f.kind==='football-alert'){const normalized=canonicalSavedAlert(f,entities);validateFootballStrategy(normalized);return normalized;}compileFormula(f.expression);return {...f,kind:'market-ev'};});
  storage.setItem(STRATEGY_STORAGE_KEY,JSON.stringify(validated));return validated;
}
