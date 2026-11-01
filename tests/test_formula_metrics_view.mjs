/** Ranking and filters use only ready, finite metrics from the selected scope. */
import assert from 'node:assert/strict';
import {filterAndSortFormulas} from '../app/formula-metrics-view.js';

const formulas=[
  {id:'tie-b',name:'Tie'},
  {id:'loading',name:'Loading'},
  {id:'delta',name:'Delta'},
  {id:'missing',name:'Ausente'},
  {id:'zero',name:'Cero'},
  {id:'beta',name:'Beta'},
  {id:'null',name:'Nulos'},
  {id:'tie-a',name:'Tie'},
  {id:'partial',name:'Parcial'},
  {id:'error',name:'Error'},
  {id:'alpha',name:'Alpha'},
  {id:'nonfinite',name:'No finito'},
].map(Object.freeze);
Object.freeze(formulas);
const ready=(meanEV,roi,n,profit,winRate,meanOdds)=>Object.freeze({state:'ready',meanEV,roi,n,profit,winRate,meanOdds,unknownCandidates:0});
const metrics=new Map([
  ['alpha',ready(.03,.20,10,2,.50,2)],
  ['beta',ready(.10,-.10,100,-10,.55,5)],
  ['zero',ready(0,0,0,0,0,1.01)],
  ['delta',ready(-.05,.30,20,6,.80,3)],
  ['tie-a',ready(.03,.20,10,2,.50,2)],
  ['tie-b',ready(.03,.20,10,2,.50,2)],
  ['partial',ready(null,.15,7,1.05,.40,1.9)],
  ['null',ready(null,null,null,null,null,null)],
  ['nonfinite',ready(NaN,Infinity,Infinity,-Infinity,NaN,Infinity)],
  // Stale numbers from another calculation must not enter this scope's ranks.
  ['loading',Object.freeze({state:'loading',meanEV:99,roi:99,n:999,profit:999,winRate:1,meanOdds:999})],
  ['error',Object.freeze({state:'error',meanEV:88,roi:88,n:888,profit:888,winRate:1,meanOdds:888})],
]);
const originalFormulas=structuredClone(formulas),originalMetrics=structuredClone(metrics);
const ids=rows=>rows.map(rule=>rule.id);
const view=options=>filterAndSortFormulas(formulas,metrics,options);
const evKnown=['beta','alpha','tie-a','tie-b','zero','delta'];
const unknownEV=['error','loading','missing','nonfinite','null','partial'];

assert.deepEqual(ids(view()).slice(0,6),evKnown,'default ranking starts with the greatest actual EV');
assert.deepEqual(ids(view({sort:'ev_desc'})).slice(0,6),evKnown);
assert.deepEqual(ids(view({sort:'ev_asc'})).slice(0,6),['delta','zero','alpha','tie-a','tie-b','beta'],'negative EV and zero retain their numeric order');
for(const sort of ['ev_desc','ev_asc']){
  const result=ids(view({sort}));
  assert.deepEqual(result.slice(6).sort(),[...unknownEV].sort(),`${sort}: null, missing, invalid, loading and error values stay last`);
  assert.ok(result.indexOf('tie-a')<result.indexOf('tie-b'),`${sort}: identical metric/name sorts by stable identity`);
}
assert.deepEqual(ids(view({sort:'roi_desc'})).slice(0,7),['delta','alpha','tie-a','tie-b','partial','zero','beta'],'ROI uses real signed percentages');
assert.deepEqual(ids(view({sort:'roi_asc'})).slice(0,7),['beta','zero','partial','alpha','tie-a','tie-b','delta']);
assert.deepEqual(ids(view({sort:'profit_desc'})).slice(0,7),['delta','alpha','tie-a','tie-b','partial','zero','beta']);
assert.deepEqual(ids(view({sort:'n_desc'})).slice(0,7),['beta','delta','alpha','tie-a','tie-b','partial','zero']);
assert.deepEqual(ids(view({sort:'winRate_desc'})).slice(0,7),['delta','beta','alpha','tie-a','tie-b','partial','zero']);
assert.deepEqual(ids(view({sort:'odds_desc'})).slice(0,7),['beta','delta','alpha','tie-a','tie-b','partial','zero']);
for(const key of ['roi','profit','n','winRate','odds'])for(const direction of ['asc','desc']){
  const result=ids(view({sort:`${key}_${direction}`}));
  assert.deepEqual(result.slice(7).sort(),['error','loading','missing','nonfinite','null'].sort(),`${key}_${direction}: unavailable values never outrank real values`);
}
assert.deepEqual(ids(view({sort:'name_asc'})),['alpha','missing','beta','zero','delta','error','loading','nonfinite','null','partial','tie-a','tie-b']);
assert.deepEqual(ids(view({sort:'name_desc'})),['tie-b','tie-a','partial','null','nonfinite','loading','error','delta','zero','beta','missing','alpha']);

// Empty UI fields do not become zero thresholds. In particular, a blank
// filter cannot hide rows that are still loading or have no matching quotes.
for(const blank of ['',null,undefined,'   ']){
  const result=view({sort:'name_asc',minEV:blank,minROI:blank,minN:blank});
  assert.equal(result.length,formulas.length,`${String(blank)} does not filter metrics`);
}
assert.deepEqual(ids(view({sort:'name_asc',minEV:'3'})),['alpha','beta','tie-a','tie-b'],'3 in an EV percentage field means .03 and includes the boundary');
assert.deepEqual(ids(view({sort:'name_asc',minROI:'20'})),['alpha','delta','tie-a','tie-b'],'20 in an ROI percentage field means .20');
assert.deepEqual(ids(view({sort:'name_asc',minEV:3,minROI:20,minN:10})),['alpha','tie-a','tie-b'],'metric filters are conjunctive in one scope');
assert.deepEqual(ids(view({sort:'name_asc',minEV:' 3 ',minROI:' 20 ',minN:' 10 '})),['alpha','tie-a','tie-b'],'numeric UI strings preserve percentage units');
assert.deepEqual(ids(view({sort:'name_asc',minEV:'0'})),['alpha','beta','zero','tie-a','tie-b'],'zero EV is an active threshold, never an empty value');
assert.deepEqual(ids(view({sort:'name_asc',minROI:0})),['alpha','zero','delta','partial','tie-a','tie-b'],'zero ROI passes while negative or unavailable ROI does not');
assert.deepEqual(ids(view({sort:'name_asc',minN:0})),['alpha','beta','zero','delta','partial','tie-a','tie-b'],'zero samples is numeric, while missing/nonfinite samples are not');
assert.deepEqual(ids(view({sort:'name_asc',minEV:-5})),['alpha','beta','zero','delta','tie-a','tie-b'],'negative percentage boundaries retain their sign');
assert.deepEqual(ids(view({sort:'name_asc',minEV:-4.9})),['alpha','beta','zero','tie-a','tie-b']);
assert.deepEqual(ids(view({sort:'name_asc',minROI:-10})),['alpha','beta','zero','delta','partial','tie-a','tie-b']);
assert.deepEqual(ids(view({sort:'name_asc',minN:'10'})),['alpha','beta','delta','tie-a','tie-b'],'sample count is not divided by one hundred');
assert.deepEqual(view({minEV:11}),[],'a valid threshold may select no formulas');
assert.deepEqual(view({minN:101}),[],'unready stale sample counts cannot satisfy a filter');

const small=[{id:'above',name:'Above'},{id:'boundary',name:'Boundary'},{id:'below',name:'Below'}];
const precise=new Map([['above',ready(.0350001,.0750001,1,0,0,2)],['boundary',ready(.035,.075,1,0,0,2)],['below',ready(.0349999,.0749999,1,0,0,2)]]);
assert.deepEqual(ids(filterAndSortFormulas(small,precise,{minEV:3.5,minROI:7.5,sort:'name_asc'})),['above','boundary'],'decimal percentages use inclusive full-precision boundaries');
assert.deepEqual(filterAndSortFormulas([],new Map(),{minEV:0}),[]);
const uncalculated=filterAndSortFormulas(formulas,new Map(),{sort:'ev_desc'});
assert.equal(uncalculated.length,formulas.length,'loading a fresh metric scope does not remove its formulas');
assert.deepEqual(filterAndSortFormulas(formulas,new Map(),{minROI:0}),[],'a requested metric filter requires an actual metric');

assert.deepEqual(formulas,originalFormulas,'ranking cannot reorder or alter source formulas');
assert.deepEqual(metrics,originalMetrics,'ranking cannot rewrite the metric cache');
for(const formula of view())assert.ok(formulas.includes(formula),'results retain the saved formula identity');
console.log('Formula metrics view: percentage filters, zero/negative values, ready scope, nulls last, all numeric sorts, stable ties and immutable inputs passed.');
