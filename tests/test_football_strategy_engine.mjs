import assert from 'node:assert/strict';
import {evaluateFootballStrategy,settleFootballAction,validateFootballStrategy,summarizeFootballAlerts} from '../app/football-strategy-engine.js';
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-12,`${a} != ${b}`);
const event=(id,date,home_score=2,away_score=1,extra={})=>({id,date,league:'E0',home:'Arsenal',away:'Chelsea',home_score,away_score,home_ht_score:1,away_ht_score:0,home_corners:6,away_corners:4,...extra});
const offersFor=(events,books=['A'])=>events.flatMap((e,index)=>books.flatMap(book=>[1.9,3.4,4].map((odds,side)=>({id:e.id,event:index,book,side,odds,probability:[.52,.27,.21][side],references:['X','Y','Z']}))));
const base=()=>({kind:'football-alert',version:2,id:'a',name:'Cuotas → 2–1',context:{},join:'Y',conditions:[{field:'home_odds',operator:'between',min:1.8,max:2},{field:'away_odds',operator:'between',min:3.8,max:4.2}],onePerMatch:true,action:{market:'correct_score',period:'full',homeGoals:2,awayGoals:1,oddsSource:'archive',stake:1,probabilitySource:'empirical',minSample:1}});
{
  const es=[event('a','2020-01-01'),event('b','2020-01-02',1,1),event('c','2020-01-03')],rule=base();
  const result=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule);
  assert.equal(result.alerts.length,3);
  assert.equal(result.alerts[0].probability,null);
  assert.equal(result.alerts[1].probability,1);
  assert.equal(result.alerts[2].probability,.5);
  assert.equal(result.alerts[2].probabilityN,2);
  const subset=summarizeFootballAlerts(result.alerts.slice(-1));assert.equal(subset.n,1);assert.equal(subset.meanProbability,.5);assert.equal(subset.years[0].n,1);
  assert.equal(result.alerts[2].odds,null,'1X2 price must never become correct-score price');
  assert.equal(result.alerts[2].ev,null);
  assert.equal(result.summary.profit,null);
  assert.equal(result.summary.roi,null);
  assert.equal(result.summary.wins,2);
  assert.ok(result.alerts[2].statuses.includes('market_quote_missing'));
}
{
  const es=[event('a','2020-01-01'),event('same-day','2020-01-01',1,1),event('next-day','2020-01-02')],result=evaluateFootballStrategy({events:es,offers:offersFor(es,['A','B'])},base());
  assert.equal(result.alerts.length,3,'one selection per match');
  assert.equal(result.alerts[0].probabilityN,0);
  assert.equal(result.alerts[1].probabilityN,0,'same-day score must not train another signal');
  assert.equal(result.alerts[2].probabilityN,2,'bookmakers must not duplicate training observations');
  assert.equal(result.alerts[2].probability,.5);
}
{
  const es=[event('a','2020-01-01')],rule=base();
  Object.assign(rule.action,{oddsSource:'manual',odds:4,probabilitySource:'manual',probability:.30,stake:10});
  const result=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule),r=result.alerts[0];
  close(r.ev,.2);close(r.expectedProfit,2);close(r.profit,30);close(r.breakEven,.25);
  assert.equal(r.isScenario,true);assert.equal(result.summary.historicalROI,null);close(result.summary.scenarioROI,3);
  assert.equal(result.summary.resultBasis,'manual_scenario');
}
{
  const es=[event('a','2020-01-01',2,1,{marketQuotes:[{book:'A',market:'correct_score',period:'full',homeGoals:2,awayGoals:1,odds:8.5}]})],rule=base();
  rule.action.probabilitySource='reference';
  const r=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0];
  assert.equal(r.odds,8.5);assert.equal(r.quoteSource,'archive');assert.equal(r.probability,null,'1X2 reference does not identify correct-score probability');assert.equal(r.ev,null);
  assert.equal(r.profit,7.5);
  rule.action.probabilitySource='manual';rule.action.probability=.2;
  const q=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0];close(q.ev,.7);
  es[0].marketQuotes[0].book='OTHER';assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0].odds,null,'do not mix books');
}
{
  const es=[event('a','2020-01-01')],rule=base();
  rule.conditions=[{field:'home_implied',operator:'between',min:.52,max:.53},{field:'implied_gap',operator:'between',min:.27,max:.28}];
  assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts.length,1);
  rule.conditions[0].max=.525;assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts.length,0);
  assert.throws(()=>validateFootballStrategy({...rule,conditions:[{field:'home_score',operator:'>=',value:2}]}),/previo/);
}
{
  const e=event('a','2020-01-01');
  assert.equal(settleFootballAction(e,{market:'correct_score',period:'first_half',homeGoals:1,awayGoals:0}).outcome,'win');
  assert.equal(settleFootballAction(e,{market:'correct_score',period:'second_half',homeGoals:1,awayGoals:1}).outcome,'win');
  assert.equal(settleFootballAction(e,{market:'corners',period:'full',team:'total',selection:'over',line:9.5}).outcome,'win');
  assert.equal(settleFootballAction(e,{market:'corners',period:'first_half',team:'total',selection:'over',line:4.5}).outcome,null,'full-time corners cannot settle first-half corners');
  assert.equal(settleFootballAction(e,{market:'team_goals',period:'full',team:'away',selection:'exact',line:1}).outcome,'win');
}
{
  const es=[event('a','2020-01-01',1,1),event('b','2020-01-02',2,1)],rule=base();
  Object.assign(rule.action,{market:'total_goals',selection:'over',line:2,oddsSource:'manual',odds:2});
  const r=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[1];
  assert.equal(r.probability,0);assert.equal(r.pushProbability,1);assert.equal(r.ev,0,'a past push refunds the stake');
  Object.assign(rule.action,{probabilitySource:'manual',probability:.5});
  const q=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0];assert.equal(q.ev,null);assert.ok(q.statuses.includes('push_probability_missing'));assert.equal(q.breakEven,null);
  Object.assign(rule.action,{odds:4,probability:.3,pushProbability:.2});
  const withPush=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0];close(withPush.ev,.4);close(withPush.breakEven,.2);
}
const entities={teams:[{id:'ars',name:'Arsenal',aliases:['Arsenal'],leagueIds:['E0']},{id:'che',name:'Chelsea',aliases:['Chelsea'],leagueIds:['E0']}],players:[{id:'saka',name:'Bukayo Saka',teamId:'ars',asOf:'2026-10-30',membershipScope:'snapshot_only'},{id:'palmer',name:'Cole Palmer',teamId:'che',asOf:'2026-10-30',membershipScope:'snapshot_only'}]};
{
  const es=[event('a','2020-01-01')],rule=base();rule.context={teamId:'ars',playerId:'saka'};
  Object.assign(rule.action,{market:'player_goals',playerId:'saka',team:'selected',selection:'at_least',line:1,oddsSource:'manual',odds:4,probabilitySource:'manual',probability:.3});
  const r=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule,{entities}).alerts[0];
  assert.equal(r.probability,null);assert.equal(r.won,null);assert.equal(r.profit,null);assert.ok(r.statuses.includes('player_history_missing'));
  rule.context.playerId='palmer';rule.action.playerId='palmer';assert.throws(()=>evaluateFootballStrategy({events:es,offers:offersFor(es)},rule,{entities}),/no pertenece/);
}
{
  const es=[event('a','2026-11-01',2,1,{playerStats:[{playerId:'saka',teamId:'ars',goals:1,minutes:90}]})],rule=base();rule.context={teamId:'ars'};
  Object.assign(rule.action,{market:'player_goals',playerId:'saka',teamId:'ars',team:'selected',selection:'at_least',line:1,oddsSource:'manual',odds:4,probabilitySource:'manual',probability:.3});
  const r=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule,{entities}).alerts[0];assert.equal(r.won,true);close(r.ev,.2);
  es[0].playerStats[0].goals=0;delete es[0].playerStats[0].minutes;
  assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule,{entities}).alerts[0].won,null,'a zero without participation evidence is not a losing player bet');
}
{
  const es=[event('a','2020-01-01',2,1,{marketQuotes:[{book:'A',market:'btts',period:'full',selection:'yes',odds:1.8}]})],rule=base();
  Object.assign(rule.action,{market:'combination',legs:[{market:'correct_score',period:'full',homeGoals:2,awayGoals:1},{market:'btts',period:'full',selection:'yes'}],oddsSource:'manual',odds:8,probabilitySource:'manual',probability:.2});
  rule.conditions.push({field:'leg_2_odds',operator:'between',min:1.7,max:1.9});
  const r=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0];assert.equal(r.won,true);close(r.ev,.6);assert.equal(r.odds,8,'joint price must be explicit');
  rule.action.oddsSource='archive';const q=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0];assert.equal(q.odds,null);assert.equal(q.ev,null,'do not multiply marginal prices');
  es[0].marketQuotes.push({book:'A',market:'combination',period:'full',legs:structuredClone(rule.action.legs),odds:9});
  assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0].odds,9);
}
{
  const es=[event('a','2020-01-01')],rule=base();
  Object.assign(rule.action,{market:'combination',legs:[{market:'team_goals',team:'home',period:'full',selection:'exact',line:2},{market:'player_goals',teamId:'che',team:'selected',playerId:'palmer',selection:'at_least',period:'full',line:1}],oddsSource:'manual',odds:8,probabilitySource:'manual',probability:.2});
  assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule,{entities}).alerts[0].won,null);
}
{
  const es=[event('a','2020-01-01',2,1,{marketQuotes:[{book:'A',market:'total_goals',period:'full',selection:'over',line:1.5,odds:1.6},{book:'A',market:'total_goals',period:'full',selection:'exact',line:3,odds:4}]})],rule=base();
  Object.assign(rule.action,{market:'total_goals',selection:'at_least',line:2,probabilitySource:'manual',probability:.8});
  const r=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0];assert.equal(r.odds,1.6,'2+ goals and over1.5 are identical integer-count contracts');assert.equal(r.won,true);
  rule.action.selection='over';rule.action.line=2;assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0].odds,null,'Asian over2 with a push cannot use over1.5');
  rule.action.selection='exact';rule.action.line=3;assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0].odds,4);
  rule.action.period='first_half';assert.equal(evaluateFootballStrategy({events:es,offers:offersFor(es)},rule).alerts[0].odds,null,'never substitute a full-time exact-goal price for a half');
}
{
  const rule=base();Object.assign(rule.action,{market:'player_goals',playerId:'not-in-roster',teamId:'ars',team:'selected',selection:'at_least',line:1});const es=[event('a','2026-11-01')];
  assert.throws(()=>evaluateFootballStrategy({events:es,offers:offersFor(es)},rule,{entities}),/plantilla verificada/);
}
{
  const rule=base();rule.context={teamId:'ars'};
  Object.assign(rule.action,{market:'player_goals',playerId:'saka',teamId:'ars',team:'selected',selection:'at_least',line:1,oddsSource:'manual',odds:4,probabilitySource:'manual',probability:.3});
  const check=(e,options={})=>evaluateFootballStrategy({events:[e],offers:offersFor([e])},rule,{entities,...options}).alerts[0];
  const tomorrow=check(event('tomorrow','2026-10-31'));close(tomorrow.ev,.2);assert.equal(tomorrow.won,null,'a current roster is not a player result');
  const boundary=check(event('boundary','2026-11-13'));close(boundary.ev,.2,'the14th day is inclusive');
  const expired=check(event('expired','2026-11-14'));assert.equal(expired.ev,null);assert.ok(expired.statuses.includes('player_history_missing'));
  const future=check(event('future','2029-10-31'));assert.equal(future.ev,null);assert.equal(future.won,null);
  const past=check(event('past','2026-10-29'));assert.equal(past.ev,null,'snapshots never backfill yesterday');
  const explicit=check(event('future-lineup','2029-10-31',2,1,{lineups:[{teamId:'ars',players:[{playerId:'saka',goals:1,minutes:90}]}]}));close(explicit.ev,.2);assert.equal(explicit.won,true,'event-specific evidence overrides snapshot expiry');
  const extended=check(event('extended','2026-11-20'),{rosterMaxAgeDays:30});close(extended.ev,.2);
  assert.throws(()=>check(event('invalid','2026-11-01'),{rosterMaxAgeDays:0}),/positivo/);
  const seasonal=structuredClone(entities);seasonal.players.find(p=>p.id==='saka').season='2026/27';
  const same=event('same-season','2026-11-01',2,1,{season:'2026/2027'}),different=event('wrong-season','2026-11-01',2,1,{season:'2027/2028'});
  close(evaluateFootballStrategy({events:[same],offers:offersFor([same])},rule,{entities:seasonal}).alerts[0].ev,.2);
  assert.equal(evaluateFootballStrategy({events:[different],offers:offersFor([different])},rule,{entities:seasonal}).alerts[0].ev,null,'reliable season mismatch rejects a current snapshot');
}
{
  const es=[event('cohort-a','2020-01-01'),event('cohort-b','2020-01-02',1,1),event('outside','2020-01-03'),event('cohort-d','2020-01-04')];
  for(const e of es)e.marketQuotes=[{book:'A',market:'correct_score',period:'full',homeGoals:2,awayGoals:1,odds:e.id==='outside'?50:8}];
  const offers=offersFor(es);for(const row of offers)if(row.id==='outside'){if(row.side===0)row.odds=3;if(row.side===2)row.odds=2;}
  const rule=base();rule.join='O';rule.conditions=[{field:'home_odds',operator:'between',min:1.8,max:2},{field:'ev',operator:'>=',value:.03}];
  const result=evaluateFootballStrategy({events:es,offers},rule);
  assert.ok(!result.alerts.some(r=>r.id==='outside'),'an out-of-cohort price50 must not activate the EV branch using conditional probability');
  const inside=result.alerts.find(r=>r.id==='cohort-d');assert.equal(inside.probability,.5);assert.equal(inside.probabilityN,2);close(inside.ev,3);
  Object.assign(rule.action,{oddsSource:'manual',odds:50,probabilitySource:'manual',probability:.3});
  assert.ok(evaluateFootballStrategy({events:es,offers},rule).alerts.some(r=>r.id==='outside'),'an independent manual probability may activate OR outside the historical cohort');
  Object.assign(rule.action,{market:'match_result',selection:'home',oddsSource:'archive',probabilitySource:'reference'});
  assert.ok(evaluateFootballStrategy({events:es,offers},rule).alerts.some(r=>r.id==='outside'),'a contract-specific independent reference may activate OR outside the cohort');
  Object.assign(rule.action,{market:'correct_score',homeGoals:2,awayGoals:1,oddsSource:'archive',probabilitySource:'empirical'});rule.conditions=[{field:'ev',operator:'>=',value:.03}];
  const global=evaluateFootballStrategy({events:es,offers},rule);assert.ok(global.alerts.some(r=>r.id==='outside'),'an EV-only empirical rule has a global cohort');assert.equal(global.alerts.find(r=>r.id==='outside').probability,.5);
}
{
  const goals={market:'total_goals',period:'full',selection:'over',line:1.5};
  const es=[event('independent-a','2020-01-01'),event('independent-b','2020-01-02')];
  for(const [i,e]of es.entries())e.marketQuotes=[{book:'A',...goals,odds:i?2.4:1.9},{book:'A',market:'correct_score',period:'full',homeGoals:2,awayGoals:1,odds:8.5}];
  const rule=base();rule.conditions=[{field:'situation_1_odds',selection:goals,operator:'between',min:1.8,max:2}];
  Object.assign(rule.action,{probabilitySource:'manual',probability:.2});
  const result=evaluateFootballStrategy({events:es,offers:offersFor(es)},rule);
  assert.deepEqual(result.alerts.map(row=>row.id),['independent-a']);
  assert.equal(result.alerts[0].contextValues.situation_1_odds,1.9);
  assert.equal(result.alerts[0].odds,8.5,'observed goals price is distinct from the final correct-score wager');
  close(result.alerts[0].ev,.7);assert.equal(result.alerts[0].profit,7.5);
  es[0].marketQuotes=es[0].marketQuotes.filter(q=>q.market!=='total_goals');
  assert.equal(evaluateFootballStrategy({events:es.slice(0,1),offers:offersFor(es.slice(0,1))},rule).alerts.length,0,'matching 1X2 odds cannot fill an absent goals quote');
  rule.join='O';rule.conditions.push({field:'home_odds',operator:'>=',value:1});
  const missing=evaluateFootballStrategy({events:es.slice(0,1),offers:offersFor(es.slice(0,1))},rule).alerts[0];
  assert.equal(missing.contextValues.situation_1_odds,null,'missing independent prices remain null');
}
{
  const firstHalf={market:'total_goals',period:'first_half',selection:'over',line:.5};
  const e=event('exact-period-book','2020-01-01',2,1,{marketQuotes:[{book:'A',...firstHalf,period:'full',odds:1.9},{book:'OTHER',...firstHalf,odds:1.9}]});
  const rule=base();rule.conditions=[{field:'situation_40_odds',selection:firstHalf,operator:'between',min:1.8,max:2}];
  assert.equal(evaluateFootballStrategy({events:[e],offers:offersFor([e])},rule).alerts.length,0,'a first-half situation cannot borrow full-time or other-book prices');
  e.marketQuotes.push({book:'A',...firstHalf,odds:1.95});
  const matched=evaluateFootballStrategy({events:[e],offers:offersFor([e])},rule).alerts[0];
  assert.equal(matched.contextValues.situation_40_odds,1.95);assert.equal(matched.odds,null,'independent condition prices never become final wager prices');
  assert.throws(()=>validateFootballStrategy({...rule,conditions:[{...rule.conditions[0],field:'situation_41_odds'}]}),/previo/);
  assert.throws(()=>validateFootballStrategy({...rule,conditions:[{...rule.conditions[0],selection:null}]}),/mercado/);
  assert.throws(()=>validateFootballStrategy({...rule,conditions:[...rule.conditions,...rule.conditions]}),/identificador/);
}
{
  const observedPlayer={market:'player_goals',period:'full',team:'selected',teamId:'ars',playerId:'saka',selection:'at_least',line:1};
  const e=event('player-price-only','2020-01-01',2,1,{marketQuotes:[{book:'A',...observedPlayer,odds:3.5},{book:'A',market:'correct_score',period:'full',homeGoals:2,awayGoals:1,odds:8}]});
  const rule=base();rule.conditions=[{field:'situation_1_odds',selection:observedPlayer,operator:'between',min:3,max:4}];Object.assign(rule.action,{probabilitySource:'manual',probability:.2});
  const r=evaluateFootballStrategy({events:[e],offers:offersFor([e])},rule,{entities}).alerts[0];
  assert.equal(r.won,true,'a player quote condition does not require player scoring statistics to settle a separate correct-score wager');close(r.ev,.6);
  rule.conditions[0].selection={...observedPlayer,playerId:'palmer'};
  assert.throws(()=>evaluateFootballStrategy({events:[e],offers:offersFor([e])},rule,{entities}),/no pertenece/);
}
console.log('Football alert engine: ranges, independent situation contracts, conditional chronology, market identity, roster integrity, settlement, combinations and expected returns passed.');
