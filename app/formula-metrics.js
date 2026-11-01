/** Historical formula metrics, cached independently of grid order and search. */
import {UNIFIED_FORMULA_KIND,evaluateUnifiedFormula} from './football-unified-formula.js';
import {PRICE_FORMULA_KIND,evaluatePriceFormula} from './football-price-engine.js';
import {evaluateFootballStrategy,summarizeFootballAlerts} from './football-strategy-engine.js';
import {matchAndRank,summarize} from './formula-engine.js';
import {periodMatches} from './workspace-data.js';

const finite=value=>typeof value==='number'&&Number.isFinite(value);
const nullable=value=>finite(value)?value:null;
const canonicalMarket=value=>({h2h:'match_result',three_way:'match_result',correctScore:'correct_score',totals:'total_goals',totals25:'total_goals',both_teams_to_score:'btts'})[value]||value||'match_result';
export function normalizeMetricsScope(scope={}){
  return {period:['test','validation','all'].includes(scope.period)?scope.period:'test',league:String(scope.league||''),book:String(scope.book||'')};
}
export function formulaMetricsKey(rule,scope={}){
  // Names and saved IDs do not change a result. Everything else is retained,
  // including stake, contract identities, references and legacy configuration.
  const {id,name,...definition}=rule;
  return JSON.stringify([definition,normalizeMetricsScope(scope)]);
}
export function metricsFromSummary(summary,unknownCandidates=null){
  return Object.freeze({n:summary.n,meanEV:nullable(summary.meanEV),meanMinReturn:nullable(summary.meanMinReturn),expectedPriced:summary.expectedPriced??0,roi:nullable(summary.roi),profit:nullable(summary.profit),settledPriced:summary.settledPriced??0,winRate:nullable(summary.winRate),meanOdds:nullable(summary.meanOdds),unknownCandidates:nullable(unknownCandidates),scenario:Boolean(summary.isScenario)});
}
const hasSidePrices=node=>node?.type==='group'?(node.children||[]).some(hasSidePrices):['home_odds','draw_odds','away_odds'].includes(node?.field);

/** A conservative superset: outside it every valid contract is provably false.
 * An unrestricted OR branch (metadata, price or negation) forces a full scan.
 */
export function positiveMarketConstraint(node,weight=markets=>markets.size){
  if(node?.type==='group'){
    const restrictions=(node.children||[]).map(child=>positiveMarketConstraint(child,weight));
    if(node.operator==='O')return restrictions.length&&restrictions.every(Boolean)?new Set(restrictions.flatMap(set=>[...set])):null;
    if(node.operator!=='Y')return null;
    const bounded=restrictions.filter(Boolean);return bounded.length?bounded.reduce((best,set)=>weight(set)<weight(best)?set:best):null;
  }
  return node?.field==='market'&&['=','==',undefined].includes(node.operator)&&node.selection?.market?new Set([canonicalMarket(node.selection.market)]):null;
}
export function createOfferIndex(offers,scope={}){
  const view=normalizeMetricsScope(scope),books=view.book?new Set(view.book.split('|')):null,selected=[],byMarket=new Map();
  for(const offer of offers){
    if(!periodMatches(offer,view.period)||(view.league&&offer.league!==view.league)||(books&&!books.has(offer.book)))continue;
    selected.push(offer);const key=canonicalMarket(offer.market);
    if(!byMarket.has(key))byMarket.set(key,[]);byMarket.get(key).push(offer);
  }
  return {offers:selected,byMarket};
}
export function candidateOffers(index,rule){
  // Side-price predicates need the other 1X2 contracts from the same snapshot.
  // Passing only selected-market records would silently remove that context.
  if(hasSidePrices(rule.expression))return index.offers;
  const markets=positiveMarketConstraint(rule.expression,set=>[...set].reduce((n,key)=>n+(index.byMarket.get(key)?.length||0),0));
  if(!markets)return index.offers;
  if(markets.size===1)return index.byMarket.get([...markets][0])||[];
  return [...markets].flatMap(key=>index.byMarket.get(key)||[]);
}

export class FormulaMetricsEngine {
  constructor(data,{cacheLimit=512,scopeLimit=8}={}){this.data=data;this.cacheLimit=cacheLimit;this.scopeLimit=scopeLimit;this.cache=new Map();this.scopeIndexes=new Map();this.initializing=null;this.initialized=false;}
  async initialize(){
    if(this.initializing)return this.initializing;
    if(this.initialized)return this.data;
    // FootballData publishes manifest/entities before its events fetch ends.
    // Their presence cannot prove that initialization has actually finished.
    this.initializing=Promise.resolve().then(()=>this.data.initialize()).then(()=>{this.initialized=true;return this.data;}).finally(()=>{this.initializing=null;});
    return this.initializing;
  }
  remember(map,key,value,limit){map.delete(key);map.set(key,value);while(map.size>limit)map.delete(map.keys().next().value);return value;}
  async evaluate(rule,scope={}){
    await this.initialize();const view=normalizeMetricsScope(scope),key=formulaMetricsKey(rule,view);
    if(this.cache.has(key)){const cached=this.cache.get(key);return this.remember(this.cache,key,cached,this.cacheLimit);}
    let metrics;
    if(rule.kind===PRICE_FORMULA_KIND){
      const universe=await this.data.unifiedStrategyUniverse(),scopeKey=JSON.stringify(view);
      const index=this.scopeIndexes.get(scopeKey)||this.remember(this.scopeIndexes,scopeKey,createOfferIndex(universe.offers,view),this.scopeLimit);
      // Coverage needs all complementary contracts in the selected scope. A
      // single-market/branch optimization could silently remove a portfolio leg.
      const result=evaluatePriceFormula({events:universe.events,offers:index.offers},rule,{entities:this.data.entities,universe:universe.name,summaryOnly:true,immutableUniverse:true});
      metrics=metricsFromSummary(result.summary,result.coverage.unknownCandidates);
    }else if(rule.kind===UNIFIED_FORMULA_KIND){
      const universe=await this.data.unifiedStrategyUniverse(),scopeKey=JSON.stringify(view);
      const index=this.scopeIndexes.get(scopeKey)||this.remember(this.scopeIndexes,scopeKey,createOfferIndex(universe.offers,view),this.scopeLimit);
      const result=evaluateUnifiedFormula({events:universe.events,offers:candidateOffers(index,rule)},rule,{entities:this.data.entities,universe:universe.name,summaryOnly:true});
      metrics=metricsFromSummary(result.summary,result.coverage.unknownCandidates);
    }else if(rule.kind==='football-alert'){
      const universe=await this.data.strategyUniverse(rule),books=view.book?new Set(view.book.split('|')):null;
      // Legacy empirical estimates retain all earlier dates, exactly as Usar.
      const offers=universe.offers.filter(r=>(!view.league||r.league===view.league)&&(!books||books.has(r.book)));
      const result=evaluateFootballStrategy({events:universe.events,offers},rule,{entities:this.data.entities,universe:universe.name});
      metrics=metricsFromSummary(summarizeFootballAlerts(result.alerts.filter(r=>periodMatches(r,view.period))));
    }else {
      await this.data.ensureOffers(view.period);const books=view.book?new Set(view.book.split('|')):null;
      const offers=this.data.offers.filter(r=>periodMatches(r,view.period)&&(!view.league||r.league===view.league)&&(!books||books.has(r.book)));
      const rows=matchAndRank(offers,rule.expression,{onePerMatch:rule.onePerMatch}),summary=summarize(rows,rule.stake);
      metrics=metricsFromSummary({...summary,profit:summary.n?summary.profit:null,expectedPriced:rows.filter(r=>finite(r.ev)).length,settledPriced:rows.filter(r=>finite(r.profit)).length,isScenario:false});
    }
    return this.remember(this.cache,key,metrics,this.cacheLimit);
  }
}

/** Shared by the real worker and bounded tests. Messages never expose archives. */
export function createFormulaMetricsRunner(engine,post,{yieldTask=()=>new Promise(resolve=>setTimeout(resolve,0))}={}){
  let generation=0;
  return async message=>{
    if(message?.type==='cancel'){generation++;return;}
    if(message?.type!=='evaluate')return;
    const token=++generation,{requestId,formulas=[],scope={}}=message;let completed=0;
    try{await engine.initialize();}catch(error){if(token===generation){post({type:'error',requestId,message:error.message||String(error)});post({type:'complete',requestId});}return;}
    for(const rule of formulas){
      if(token!==generation)return;
      try{const metrics=await engine.evaluate(rule,scope);if(token!==generation)return;post({type:'metric',requestId,id:rule.id,metrics});}
      catch(error){if(token!==generation)return;post({type:'error',requestId,id:rule.id,message:error.message||String(error)});}
      completed++;post({type:'progress',requestId,completed,total:formulas.length});await yieldTask();
    }
    if(token===generation)post({type:'complete',requestId});
  };
}
