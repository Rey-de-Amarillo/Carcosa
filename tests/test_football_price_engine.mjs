import assert from 'node:assert/strict';
import {PRICE_FORMULA_KIND,PRICE_CONDITION_FIELDS,newPriceFormula,newPriceCondition,normalizePriceFormula,formatPriceFormula,calculatePaymentCoverage,evaluatePriceFormula} from '../app/football-price-engine.js';

let serial=0;
const c=(field,value,operator='>=')=>({type:'condition',id:`c${++serial}`,field,value,operator});
const g=(operator,...children)=>({type:'group',id:`g${++serial}`,operator,children});
const rule=(expression,extra={})=>({...newPriceFormula(),id:'r',name:'Pagos',expression,...extra});
const event=(id='e',extra={})=>({id,date:'2026-10-30',league:'L',home:'Cualquiera',away:'Otro',home_score:2,away_score:1,...extra});
const evaluate=(expression,quotes,extra={},events=[event()])=>evaluatePriceFormula({events,offers:quotes},rule(expression,extra));
const q=(selection,odds,extra={})=>({event:0,book:'B',market:'btts',period:'full',selection,odds,rulesId:'book-btts-regulation-v1',snapshotId:'one',...extra});
const close=(a,b,tolerance=1e-9)=>assert.ok(Math.abs(a-b)<tolerance,`${a} != ${b}`);

assert.equal(PRICE_FORMULA_KIND,'football-price');assert.equal(newPriceFormula().stake,100);assert.equal(newPriceCondition().field,'');
assert.equal(PRICE_CONDITION_FIELDS.includes('team'),false);assert.equal(PRICE_CONDITION_FIELDS.includes('player'),false);
const normalized=normalizePriceFormula(rule(g('Y',c('ev',.02),{...c('',null)},g('O'))));
assert.equal(normalized.expression.children.length,1);assert.deepEqual(normalizePriceFormula(normalized),normalized);
assert.match(formatPriceFormula(normalized),/EV ≥ 2 %/);
assert.throws(()=>normalizePriceFormula(rule(g('Y',c('team',1)))),/condición de pago/);
assert.throws(()=>normalizePriceFormula(rule(g('Y',c('ev',null)))),/valor/);
assert.throws(()=>normalizePriceFormula(rule(g('Y',c('ev',0)),{stake:0})),/mayor/);
assert.throws(()=>normalizePriceFormula(rule(g('Y',c('ev',0)),{oddsDrop:1})),/menos de uno/);
assert.throws(()=>normalizePriceFormula(rule(g('Y',c('min_return',0)),{mode:'coverage',stake:100.006})),/dos decimales/);
assert.equal(normalizePriceFormula(rule(g('Y',c('ev',0)),{stake:100.006})).stake,100.006,'single-bet units may retain arbitrary precision');
assert.throws(()=>normalizePriceFormula(rule(g('Y',{...c('odds',0),operator:'between',min:2,max:1}))),/mínimo/);
const duplicate=c('ev',0);assert.throws(()=>normalizePriceFormula(rule(g('Y',duplicate,duplicate))),/identificador/);

// Real numbers observed in the user's Bet365 tab are ordinary negative covers.
const btts=calculatePaymentCoverage({odds:[2,1.75]});
close(btts.stakes[0],46.6666666666667);close(btts.stakes[1],53.3333333333333);
close(btts.minPayout,93.3333333333333);close(btts.minReturn,-1/15);
close(btts.roundedMinPayout,93.32);close(btts.roundedMinReturn,-.0668);
assert.equal(calculatePaymentCoverage({odds:[2.30,3,3.5],structure:'three_outcomes'}).minReturn<0,true);
assert.equal(calculatePaymentCoverage({odds:[1.28,1.57,1.36],structure:'double_chance'}).minReturn<0,true);
assert.equal(evaluate(g('Y',c('min_return',0,'>')),[q('yes',2),q('no',1.75)],{mode:'coverage'}).alerts.length,0);

// Exhaustive complementary payoffs, not the sum of two winning ticket payments.
const pair=calculatePaymentCoverage({odds:[2.1,2.1]});
assert.deepEqual(pair.stakes,[50,50]);close(pair.minPayout,105);close(pair.minProfit,5);close(pair.ev,.05);
const three=calculatePaymentCoverage({odds:[3.3,3.3,3.3],structure:'three_outcomes'});
close(three.stakes.reduce((a,b)=>a+b),100);close(three.minReturn,.1);
close(three.roundedStakes.reduce((a,b)=>a+b),100);
const dc=calculatePaymentCoverage({odds:[1.6,1.6,1.6],structure:'double_chance'});
close(dc.minReturn,1.6*2/3-1);close(dc.payoutByOutcome.home,dc.payoutByOutcome.draw);
const unequal=calculatePaymentCoverage({odds:[2.2,2.2,1.01],structure:'double_chance'});
assert.equal(unequal.constantPayout,false);assert.equal(unequal.ev,null);
assert.equal(unequal.minReturn>0,true);
const stressed=calculatePaymentCoverage({odds:[2.1,2.1],costRate:.01,oddsDrop:.01});
close(stressed.minReturn,1.05*.99-1-.01);
assert.throws(()=>calculatePaymentCoverage({odds:[1,2]}),/mayores/);
assert.throws(()=>calculatePaymentCoverage({odds:[2,2],structure:'three_outcomes'}),/3 cuotas/);
assert.throws(()=>calculatePaymentCoverage({odds:[2,2],budget:100.006}),/dos decimales/);
const centBudget=calculatePaymentCoverage({odds:[2,2],budget:100.01});close(centBudget.roundedStakes.reduce((sum,x)=>sum+x,0),centBudget.totalCost);
assert.equal(calculatePaymentCoverage({odds:[2,2],budget:100-1e-11}).roundedMinProfit,0,'floating representation dust cannot create profit by understating the cash outlay');

// Monetary EV comes only from external reference probabilities, before filters.
const value=q('yes',2,{probability:.55,references:['R1','R2','R3'],referenceSd:.02});
let r=evaluate(g('Y',c('ev',.05),c('references',3),c('gross_payout',190)),[value]);
assert.equal(r.alerts.length,1);close(r.alerts[0].ev,.1);close(r.alerts[0].expectedProfit,10);
close(r.alerts[0].contextValues.expected_payout,110);close(r.alerts[0].contextValues.fair_payout,100/.55);
assert.equal(r.alerts[0].profit,100);assert.equal(r.alerts[0].quoteSource,'archive');assert.equal(r.alerts[0].isScenario,false);
r=evaluate(g('Y',c('ev',0)),[value],{costRate:.01,oddsDrop:.05});
close(r.alerts[0].ev,.035);close(r.alerts[0].profit,89);assert.equal(r.alerts[0].isScenario,true);
assert.equal(evaluate(g('Y',c('ev',0)),[{...value,references:['B','R1']}]).coverage.unknownCandidates,1);
assert.equal(evaluate(g('Y',c('ev',0)),[{...value,references:[]}]).alerts.length,0);
assert.equal(evaluate(g('Y',c('ev',0)),[{...value,probability:.8,pushProbability:.3}]).alerts.length,0);
assert.equal(evaluate(g('Y',c('ev',0)),[{...value,pushProbability:-.1}]).coverage.unknownCandidates,1,'an explicitly invalid push probability cannot become zero');
const push=q('home',2,{market:'draw_no_bet',probability:.5,references:['R'],pushProbability:.2});
close(evaluate(g('Y',c('ev',.1)),[push]).alerts[0].ev,.2);
assert.equal(evaluate(g('Y',c('ev',0)),[{...push,pushProbability:undefined}]).coverage.unknownCandidates,1);
assert.equal(evaluate(g('Y',c('odds',1.1)),[q('over',2,{market:'total_goals'})]).alerts.length,0,'incomplete count contract rejected');
assert.equal(evaluate(g('Y',c('ev',0)),[{...value,active:false}]).alerts.length,0);

// Kleene Y/O: a missing probability cannot become a positive comparison or !=.
const noProbability=q('no',2.2);
assert.equal(evaluate(g('Y',c('ev',0,'!=')),[noProbability]).coverage.unknownCandidates,1);
assert.equal(evaluate(g('O',g('Y',c('ev',.05),c('gross_payout',190)),g('Y',c('gross_payout',210),c('min_return',0,'>'))),[value,noProbability],{onePerMatch:false}).alerts.length,1);
assert.equal(evaluate(g('O',c('ev',.05),c('odds',2)),[noProbability]).alerts.length,1,'a proven OR price branch may pass without invented EV');
assert.equal(evaluate(g('Y',c('ev',0)),[value,{...value,book:'C',probability:.6}]).alerts.length,1);
close(evaluate(g('Y',c('ev',0)),[value,{...value,book:'C',probability:.6}]).alerts[0].ev,.2);

// One complete coverage produces one budget and one settlement in the grid.
const positive=[q('yes',2.1,{id:'q1'}),q('no',2.1,{id:'q2'})];
r=evaluate(g('Y',c('min_return',.01)),positive,{mode:'coverage'});
assert.equal(r.alerts.length,1);assert.equal(r.alerts[0].legs.length,2);assert.equal(r.summary.n,1);
close(r.summary.stake,100);close(r.summary.profit,5);close(r.summary.roi,.05);close(r.summary.meanEV,.05);
close(r.summary.meanMinReturn,.05);
assert.equal(r.alerts[0].quoteSource,'manual');assert.equal(r.alerts[0].isScenario,true);
assert.deepEqual(r.alerts[0].payoutByOutcome,{yes:105,no:105});assert.deepEqual(r.alerts[0].legs.map(l=>l.sourceId),['q1','q2']);
const full=evaluatePriceFormula({events:[event()],offers:positive},rule(g('Y',c('min_return',0)),{mode:'coverage'}));
const summaryOnly=evaluatePriceFormula({events:[event()],offers:positive},rule(g('Y',c('min_return',0)),{mode:'coverage'}),{summaryOnly:true});
assert.deepEqual(summaryOnly.summary,full.summary);assert.deepEqual(summaryOnly.coverage,full.coverage);assert.deepEqual(summaryOnly.alerts,[]);

// DC outcome labels are actual match outcomes; every state wins two tickets.
const dcQuotes=['home_draw','draw_away','home_away'].map(s=>q(s,1.6,{market:'double_chance'}));
r=evaluate(g('Y',c('min_return',0)),dcQuotes,{mode:'coverage',structure:'double_chance'});
assert.equal(r.alerts.length,1);assert.deepEqual(Object.keys(r.alerts[0].payoutByOutcome),['home','draw','away']);
close(r.alerts[0].profit,r.alerts[0].payoutByOutcome.home-100);
// A tiny continuous advantage erased by cent rounding is rejected.
assert.equal(evaluate(g('Y',c('min_return',0,'>')),[q('yes',2.00001),q('no',2.00001)],{mode:'coverage'}).alerts.length,0);

// Unknown snapshots, rules, missing outcomes and mismatched contracts stay unknown.
for(const quotes of [positive.map(x=>({...x,snapshotId:undefined})),positive.map(x=>({...x,rulesId:undefined})),[positive[0]],positive.map((x,i)=>({...x,snapshotId:String(i)})),positive.map((x,i)=>({...x,rulesId:String(i)})),positive.map((x,i)=>({...x,period:i?'first_half':'full'}))]){
  const result=evaluate(g('Y',c('min_return',0)),quotes,{mode:'coverage'});assert.equal(result.alerts.length,0);assert.ok(result.coverage.unknownCandidates>0);
}
assert.equal(evaluate(g('Y',c('min_return',0)),[positive[0],{...positive[1],book:'C'}],{mode:'coverage'}).alerts.length,0,'same-book policy cannot borrow another book');
assert.equal(evaluate(g('Y',c('min_return',0)),[positive[0],{...positive[1],book:'C'}],{mode:'coverage',bookPolicy:'cross_book'}).alerts.length,1);
const timed=positive.map((x,i)=>({...x,snapshotId:undefined,book:i?'C':'B',capturedAt:`2026-10-30T10:00:${i?'30':'00'}Z`}));
assert.equal(evaluate(g('Y',c('min_return',0)),timed,{mode:'coverage',bookPolicy:'cross_book'}).alerts.length,1);
assert.equal(evaluate(g('Y',c('min_return',0)),[timed[0],{...timed[1],capturedAt:'2026-10-30T10:01:01Z'}],{mode:'coverage',bookPolicy:'cross_book'}).alerts.length,0);
assert.equal(evaluate(g('Y',c('min_return',0)),[timed[0],{...timed[1],capturedAt:'2026-10-30T10:00:30'}],{mode:'coverage',bookPolicy:'cross_book'}).alerts.length,0,'timestamps require timezone');
// Old generous prices cannot survive their own recorded adverse update.
const updates=[{...timed[0],capturedAt:'2026-10-30T10:00:00Z'},{...timed[0],odds:1.5,capturedAt:'2026-10-30T10:00:10Z'},{...timed[1],capturedAt:'2026-10-30T10:00:30Z'}];
assert.equal(evaluate(g('Y',c('min_return',0)),updates,{mode:'coverage',bookPolicy:'cross_book'}).alerts.length,0);
for(const inactive of [{active:false},{suspended:true},{active:false,odds:null},{suspended:true,odds:0}]){
  const suspended=[timed[0],{...timed[0],...inactive,capturedAt:'2026-10-30T10:00:10Z'},timed[1]];
  assert.equal(evaluate(g('Y',c('min_return',0)),suspended,{mode:'coverage',bookPolicy:'cross_book'}).alerts.length,0,'a tombstone invalidates the preceding ticket price');
}
const conflict=[{...timed[0],odds:1.5},{...timed[0],odds:2.1},timed[1]];
assert.equal(evaluate(g('Y',c('min_return',0)),conflict,{mode:'coverage',bookPolicy:'cross_book'}).alerts.length,0,'same-time conflicts cannot select the favorable insertion order');
const simultaneousConflict=[{...timed[1],capturedAt:timed[0].capturedAt},{...timed[0],odds:2.1},{...timed[0],odds:1.5}];
assert.equal(evaluate(g('Y',c('min_return',0)),simultaneousConflict,{mode:'coverage',bookPolicy:'cross_book'}).alerts.length,0,'all same-time updates resolve before an interval is evaluated');
const mutable=[{...value}];assert.equal(evaluate(g('Y',c('ev',0)),mutable).alerts.length,1);mutable[0].probability=.1;
assert.equal(evaluate(g('Y',c('ev',0)),mutable).alerts.length,0,'direct live/mutable calls never cache stale prices');
const immutableUniverse={events:[event()],offers:positive},immutableRule=rule(g('Y',c('min_return',0)),{mode:'coverage'});
const immutableFirst=evaluatePriceFormula(immutableUniverse,immutableRule,{immutableUniverse:true});
assert.deepEqual(evaluatePriceFormula(immutableUniverse,immutableRule,{immutableUniverse:true}),immutableFirst,'prepared immutable coverage exactly matches a cold evaluation');

const empty=evaluate(g('Y',c('ev',0)),[]);assert.equal(empty.summary.n,0);assert.equal(empty.summary.meanEV,null);assert.equal(empty.summary.roi,null);
assert.equal(empty.summary.meanMinReturn,null);assert.equal(evaluate(g('Y',c('ev',0)),[value]).summary.meanMinReturn,null);
console.log('Football price engine: monetary EV, complete coverage, rounding, provenance, Y/O, and Bet365 prices verified.');
