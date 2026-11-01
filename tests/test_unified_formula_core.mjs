import assert from 'node:assert/strict';
import {UNIFIED_FORMULA_KIND,newUnifiedFormula,newUnifiedCondition,normalizeUnifiedFormula,formatUnifiedFormula,evaluateUnifiedFormula,unifiedFormulaFromLegacy} from '../app/football-unified-formula.js';
import {defaultMarketSelection} from '../app/football-market-catalog.js';

const entities={
 teams:[{id:'h',name:'Boca',aliases:['Boca Juniors'],leagueIds:['ARG']},{id:'a',name:'River',aliases:['River Plate'],leagueIds:['ARG']},{id:'other',name:'Racing',leagueIds:['ARG']}],
 players:[{id:'p',name:'Jugador X',teamId:'h',asOf:'2026-10-30',season:'2026'},{id:'q',name:'Jugador Z',teamId:'a',asOf:'2026-10-30'}],
 leagues:[{id:'ARG',name:'Argentina'}],
};
let serial=0;
const c=(field,details={})=>({type:'condition',id:`c${++serial}`,field,operator:'=',...details});
const g=(operator,...children)=>({type:'group',id:`g${++serial}`,operator,children});
const rule=expression=>({kind:UNIFIED_FORMULA_KIND,version:1,id:'rule',name:'Fórmula única',stake:2,expression});
const e=(id='one',extra={})=>({id,date:'2026-10-01',league:'ARG',home:'Boca Juniors',away:'River Plate',home_score:2,away_score:1,home_ht_score:1,away_ht_score:0,...extra});
const offers=(event=0,book='B')=>[1.8,3.4,4.25].map((odds,side)=>({id:'shared-event-id',event,book,side,odds,probability:[.6,.3,.2][side],references:['REF1','REF2']}));
const evaluate=(expression,{events=[e()],quotes=offers(),...other}={})=>evaluateUnifiedFormula({events,offers:quotes},rule(expression),{entities,...other});
const market=(id='total_goals',extra={},operator='=')=>c('market',{operator,selection:{...defaultMarketSelection(id),...extra}});
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-12,`${actual} != ${expected}`);

assert.equal(newUnifiedFormula().kind,'football-formula');
assert.equal(newUnifiedFormula().expression.type,'group');
assert.equal(newUnifiedCondition().field,'');
assert.equal(newUnifiedCondition('odds').operator,'>=');

// Blank rows/groups have no hidden defaults; incomplete selected conditions fail.
const pure=rule(g('Y',c(''),g('O'),c('team',{value:'h'})));
const normalized=normalizeUnifiedFormula(pure,entities);
assert.equal(normalized.expression.children.length,1);
assert.equal(normalized.expression.children[0].value,'h');
assert.deepEqual(normalizeUnifiedFormula(JSON.parse(JSON.stringify(normalized)),entities),normalized);
assert.throws(()=>normalizeUnifiedFormula(rule(g('Y',c(''),g('O'))),entities),/al menos una/);
assert.throws(()=>normalizeUnifiedFormula(rule(g('Y',c('team'))),entities),/equipo/);
assert.throws(()=>normalizeUnifiedFormula(rule(g('Y',c('odds',{operator:'>=',value:''}))),entities),/cuota/);
assert.throws(()=>normalizeUnifiedFormula(rule(g('Y',c('typo',{value:1}))),entities),/condición válida/);
assert.throws(()=>normalizeUnifiedFormula(rule(g('X',c('team',{value:'h'}))),entities),/Y u O/);
assert.throws(()=>normalizeUnifiedFormula(rule(g('Y',c('odds',{operator:'between',min:3,max:2}))),entities),/mínima/);
const same=c('team',{value:'h'});assert.throws(()=>normalizeUnifiedFormula(rule(g('Y',same,same)),entities),/identificador/);
assert.throws(()=>normalizeUnifiedFormula({...rule(g('Y',c('team',{value:'h'}))),version:2},entities),/versión/);
assert.throws(()=>unifiedFormulaFromLegacy({kind:'football-alert',conditions:[],action:{market:'match_result'}}),/originales/);
const threshold=1.812345678901234;
assert.equal(normalizeUnifiedFormula(rule(g('Y',c('odds',{operator:'>=',value:threshold}))),entities).expression.children[0].value,threshold);
const around=c('odds',{operator:'around',value:1.9,margin:.1});
assert.deepEqual(normalizeUnifiedFormula(rule(g('Y',around)),entities).expression.children[0],{type:'condition',id:around.id,field:'odds',operator:'between',min:1.8,max:2});

// Every field participates inside the same logical tree, including OR branches.
const teamOrOdds=g('O',c('team',{value:'other'}),c('odds',{operator:'>=',value:4}));
assert.equal(evaluate(teamOrOdds).alerts.length,1);
const conjunction=g('Y',c('team',{value:'h'}),c('odds',{operator:'>=',value:3}));
assert.equal(evaluate(conjunction).alerts.length,2);
assert.equal(evaluate(g('Y',c('team',{value:'h'})),{events:[e('away',{home:'River Plate',away:'Boca Juniors'})]}).alerts.length,3,'Equipo matches either side');
assert.equal(evaluate(g('Y',c('home_team',{value:'h'})),{events:[e('away',{home:'River Plate',away:'Boca Juniors'})]}).alerts.length,0);
assert.equal(evaluate(g('Y',c('away_team',{value:'h'})),{events:[e('away',{home:'River Plate',away:'Boca Juniors'})]}).alerts.length,3);
const grouped=g('O',g('Y',c('team',{value:'h'}),c('odds',{operator:'>=',value:4})),g('Y',c('team',{value:'a'}),c('odds',{operator:'<=',value:2})));
assert.deepEqual(evaluate(grouped).alerts.map(row=>row.odds).sort((a,b)=>a-b),[1.8,4.25]);
const flat=g('Y',g('O',c('team',{value:'h'}),c('odds',{operator:'>=',value:4})),c('odds',{operator:'<=',value:2}));
assert.deepEqual(evaluate(flat).alerts.map(row=>row.odds),[1.8]);
const forbiddenGlobalScope={...rule(g('O',c('team',{value:'other'}),c('odds',{operator:'>=',value:4}))),context:{homeTeam:'other'}};
assert.equal(evaluateUnifiedFormula({events:[e()],offers:offers()},forbiddenGlobalScope,{entities}).alerts.length,1,'outer scopes never override an OR expression');

// Unknown is neither false nor true. A proven OR branch can still pass.
const unknown=c('player',{playerId:'p'});
assert.equal(evaluate(g('Y',unknown,c('odds',{operator:'>=',value:2}))).coverage.unknownCandidates,2);
assert.equal(evaluate(g('Y',c('team',{value:'other'}),unknown)).coverage.falseCandidates,3);
assert.equal(evaluate(g('O',unknown,c('team',{value:'h'}))).alerts.length,3);
assert.equal(evaluate(g('O',unknown,c('team',{value:'other'}))).alerts.length,0);
assert.equal(evaluate(g('Y',c('player',{playerId:'p',operator:'!='}))).alerts.length,0,'missing quoted player identity cannot be negated into a match');

// Concrete odds retain their archived contract, book, source precision and result.
const normal=evaluate(g('Y',c('odds',{operator:'>=',value:3})));
assert.equal(normal.alerts.length,2);assert.equal(new Set(normal.alerts.map(row=>row.id)).size,2);
assert.equal(normal.alerts.find(row=>row.selection==='draw').won,false);
assert.equal(normal.alerts.find(row=>row.selection==='away').odds,4.25);
close(normal.alerts.find(row=>row.selection==='draw').ev,.02);
assert.equal(normal.alerts.find(row=>row.selection==='draw').profit,-2);
const ownRefs=offers();ownRefs[2].references=['B'];
assert.equal(evaluate(g('Y',c('odds',{operator:'>=',value:4})),{quotes:ownRefs}).alerts[0].ev,null);
const precise=2.123456789012345;
assert.equal(evaluate(g('Y',c('odds',{operator:'=',value:precise})),{quotes:[{...offers()[0],odds:precise}]}).alerts[0].sourceQuote.odds,precise);

// Side quotes cannot borrow another bookmaker or a different snapshot.
assert.equal(evaluate(g('Y',c('home_odds',{operator:'between',min:1.7,max:1.9}))).alerts.length,3);
const books=[{...offers()[0],book:'A'},{...offers()[1],book:'B'},{...offers()[2],book:'B'}];
assert.deepEqual(evaluate(g('Y',c('home_odds',{operator:'>=',value:1.7})),{quotes:books}).alerts.map(row=>row.book),['A']);
const timed=offers().map((offer,index)=>({...offer,snapshotId:index===0?'early':'late'}));
assert.equal(evaluate(g('Y',c('home_odds',{operator:'>=',value:1.7})),{quotes:timed}).alerts.length,1);
const conflicting=[...offers(),{...offers()[0],odds:1.9}];
assert.equal(evaluate(g('Y',c('home_odds',{operator:'>=',value:1.7})),{quotes:conflicting}).alerts.length,0,'conflicting unversioned prices stay unknown');

// Repeated input rows deduplicate; distinct book, contract and price remain.
const repeated=[offers()[0],offers()[0],{...offers()[0],odds:1.9},{...offers()[0],book:'OTHER'},offers()[1]];
assert.equal(evaluate(g('Y',c('team',{value:'h'})),{quotes:repeated}).alerts.length,4);
assert.equal(evaluate(g('Y',c('team',{value:'h'})),{quotes:[{event:0,book:'B',market:'total_goals',selection:'over',odds:2}]}).alerts.length,0,'malformed quote cannot turn into a fabricated losing contract');

// Caller offer scope remains authoritative even when events carry other prices.
const attached=e('attached',{marketQuotes:[{book:'ATTACHED',market:'btts',period:'full',selection:'yes',odds:2.05}]});
const attachedRule=rule(g('Y',c('team',{value:'h'})));
assert.equal(evaluateUnifiedFormula({events:[attached],offers:[]},attachedRule,{entities}).alerts.length,0);
assert.equal(evaluateUnifiedFormula({events:[attached]},attachedRule,{entities}).alerts.length,1);
assert.equal(evaluateUnifiedFormula({events:[attached],offers:[{...offers()[0],book:'B'}]},attachedRule,{entities}).alerts[0].book,'B');

// Market conditions select the offered contract; outcomes only settle its return.
const oneXTwo=[1.8,3.4,4.2].map((price,index)=>({...offers()[index],odds:price}));
const homeOnly=g('Y',market('match_result',{selection:'home'}),c('odds',{operator:'>=',value:2}));
assert.equal(evaluate(homeOnly,{events:[e('home-wins',{home_score:2,away_score:0})],quotes:oneXTwo}).alerts.length,0,'the high-priced draw and away quotes are not a home bet');
for(const score of [{home_score:2,away_score:0},{home_score:0,away_score:2},{home_score:null,away_score:null}]){
  const selected=evaluate(g('Y',market('match_result',{selection:'home'})),{events:[e('result',score)],quotes:oneXTwo});
  assert.deepEqual(selected.alerts.map(row=>[row.selection,row.odds]),[['home',1.8]]);
  close(selected.alerts[0].probability,.6);close(selected.alerts[0].ev,.08);
  assert.ok(!selected.alerts[0].statuses.includes('retrospective_filter'));
  assert.equal(selected.coverage.retrospective,undefined);
}
assert.deepEqual(evaluate(g('Y',market('match_result',{selection:'home'},'!=')),{quotes:oneXTwo}).alerts.map(row=>row.selection).sort(),['away','draw']);
const bttsQuotes=[...offers(),{event:0,book:'B',market:'btts',period:'full',selection:'yes',odds:2.05,probability:.55,references:['REF1']},{event:0,book:'B',market:'btts',period:'full',selection:'no',odds:1.8}];
const btts=evaluate(g('Y',market('btts',{selection:'yes'})),{events:[e('lost-btts',{home_score:0,away_score:2})],quotes:bttsQuotes});
assert.equal(btts.alerts.length,1);assert.equal(btts.alerts[0].market,'btts');assert.equal(btts.alerts[0].selection,'yes');
assert.equal(btts.alerts[0].won,false);assert.equal(btts.alerts[0].profit,-2);close(btts.alerts[0].ev,.1275);
const countQuotes=[
 {event:0,book:'B',market:'total_goals',period:'full',selection:'over',line:2.5,odds:2.12},
 {event:0,book:'B',market:'total_goals',period:'full',selection:'under',line:2.5,odds:1.88},
 {event:0,book:'B',market:'total_goals',period:'first_half',selection:'over',line:2.5,odds:4},
 {event:0,book:'B',market:'total_goals',period:'full',selection:'over',line:3,odds:3},
 {event:0,book:'B',market:'total_goals',period:'full',selection:'at_least',line:3,odds:2.11},
];
const goals=evaluate(g('Y',market('total_goals',{selection:'over',line:2.5})),{quotes:countQuotes});
assert.deepEqual(goals.alerts.map(row=>row.odds).sort(),[2.11,2.12],'equivalent integer-count thresholds match without changing quoted prices');
const push=evaluate(g('Y',market('total_goals',{selection:'over',line:3})),{quotes:countQuotes});
assert.equal(push.alerts.length,1);assert.equal(push.alerts[0].won,'push');assert.equal(push.alerts[0].profit,0);
assert.equal(evaluate(g('Y',market('total_goals',{selection:'over',line:2.5})),{events:[e('pending',{home_score:null,away_score:null})],quotes:countQuotes}).alerts.length,2,'missing final scores do not hide matching quotes');
assert.equal(evaluate(g('Y',market('total_goals',{selection:'over',line:2.5}),market('total_goals',{selection:'under',line:2.5})),{quotes:countQuotes}).alerts.length,0,'mutually exclusive contracts never become a new combined bet');
const teamQuotes=[
 {event:0,book:'B',market:'team_goals',period:'full',selection:'over',line:1.5,team:'home',odds:2.25},
 {event:0,book:'B',market:'team_goals',period:'full',selection:'over',line:1.5,team:'away',odds:2.65},
 {event:0,book:'B',market:'team_goals',period:'full',selection:'over',line:1.5,team:'selected',teamId:'h',odds:2.3},
];
assert.deepEqual(evaluate(g('Y',market('team_goals',{team:'selected',teamId:'h'})),{quotes:teamQuotes}).alerts.map(row=>row.odds).sort(),[2.25,2.3]);
assert.deepEqual(evaluate(g('Y',market('team_goals',{team:'selected',teamId:'h'})),{events:[e('away-team',{home:'River Plate',away:'Boca Juniors'})],quotes:teamQuotes}).alerts.map(row=>row.odds).sort(),[2.3,2.65]);
const exactScoreQuotes=[{event:0,book:'B',market:'correct_score',period:'full',selection:'2-1',odds:8},{event:0,book:'B',market:'correct_score',period:'full',selection:'1-0',odds:7}];
assert.deepEqual(evaluate(g('Y',market('correct_score',{homeGoals:1,awayGoals:0})),{quotes:exactScoreQuotes}).alerts.map(row=>row.odds),[7]);

// A player is selected once; references bind that exact quoted player and market.
const person=c('player',{playerId:'p'}),stat=c('market',{playerRef:person.id,selection:{...defaultMarketSelection('player_goals'),playerId:'q',line:2}});
const playerFormula=normalizeUnifiedFormula(rule(g('Y',person,stat)),entities);
assert.equal(playerFormula.expression.children[1].selection.playerId,'p');
assert.equal(playerFormula.expression.children[1].selection.teamId,'h');
assert.equal(playerFormula.expression.children[1].selection.team,'selected');
assert.deepEqual(normalizeUnifiedFormula(playerFormula,entities),playerFormula);
assert.ok(formatUnifiedFormula(playerFormula,entities).includes('Jugador X'));
assert.ok(!formatUnifiedFormula(playerFormula,entities).includes(person.id));
assert.throws(()=>normalizeUnifiedFormula(rule(g('Y',c('market',{playerRef:'missing',selection:defaultMarketSelection('player_goals')}))),entities),/jugador que no existe/);
assert.throws(()=>normalizeUnifiedFormula(rule(g('Y',c('player',{playerId:'p',teamId:'a'}))),entities),/no pertenece/);
const playerQuotes=[
 {event:0,book:'B',market:'player_goals',period:'full',selection:'at_least',line:1,playerId:'p',team:'away',teamId:'h',odds:1.8},
 {event:0,book:'B',market:'player_goals',period:'full',selection:'over',line:1.5,playerId:'p',team:'away',teamId:'h',odds:4.2},
 {event:0,book:'B',market:'player_goals',period:'full',selection:'over',line:.5,playerId:'q',team:'home',teamId:'a',odds:3.5},
 {event:0,book:'B',market:'player_shots',period:'full',selection:'over',line:1.5,playerId:'p',team:'away',teamId:'h',odds:2.25},
 ...offers(),
];
const playerEvent=e('player',{home:'River Plate',away:'Boca Juniors',playerStats:[{playerId:'p',teamId:'h',goals:2,minutes:90}]});
const playerPrices=evaluate(g('Y',person,c('odds',{operator:'>=',value:2})),{events:[playerEvent],quotes:playerQuotes});
assert.deepEqual(playerPrices.alerts.map(row=>row.odds).sort(),[2.25,4.2],'player and price are evaluated on the same quote, never another player or 1X2');
assert.deepEqual(evaluateUnifiedFormula({events:[playerEvent],offers:playerQuotes},playerFormula,{entities}).alerts.map(row=>row.odds),[4.2],'a player reference compares identity, threshold and market on the away quote');
const anytime=g('Y',person,c('market',{playerRef:person.id,selection:{...defaultMarketSelection('player_goals')}}));
const equivalent=[{...playerQuotes[0],selection:'over',line:.5,odds:2.08}];
assert.deepEqual(evaluate(anytime,{events:[playerEvent],quotes:equivalent}).alerts.map(row=>row.odds),[2.08],'anytime scorer matches the archived over 0.5 contract');
assert.deepEqual(evaluate(g('Y',c('player',{playerId:'q',operator:'!='})),{quotes:playerQuotes}).alerts.map(row=>row.odds).sort(),[1.8,2.25,4.2],'known different quoted players match !=; generic markets remain unknown');
const playerOrHome=g('O',g('Y',person,c('odds',{operator:'>=',value:4})),g('Y',market('match_result',{selection:'home'}),c('odds',{operator:'<=',value:2})));
assert.deepEqual(evaluate(playerOrHome,{quotes:playerQuotes}).alerts.map(row=>row.odds).sort(),[1.8,4.2],'player and market branches have no hidden global scopes');
const oldClub={...playerQuotes[0],team:'away',teamId:'other'};
assert.equal(evaluate(g('Y',person),{events:[e('old-club',{home:'River Plate',away:'Racing',date:'2020-01-01'})],quotes:[oldClub]}).alerts.length,1,'current catalog membership is not an implicit historical team filter');
const referencedOldClub=normalizeUnifiedFormula(rule(anytime),entities);
assert.equal(evaluateUnifiedFormula({events:[e('old-club',{home:'River Plate',away:'Racing',date:'2020-01-01'})],offers:[oldClub]},referencedOldClub,{entities}).alerts.length,1,'playerRef does not silently add the picker club as a condition');
for(const extra of [
 {date:'2020-01-01'},
 {date:'2026-10-31',season:'2027-28'},
 {date:'2026-10-31',playerStatsComplete:true},
 {playerStats:[{playerId:'p',teamId:'h',played:false,goals:0}]},
 {lineups:[{teamId:'h',confirmed:true,players:[{playerId:'p',starter:false,minutes:0}]}]},
 {lineups:[{teamId:'h',confirmed:true,players:[{playerId:'p',starter:true,minutes:0}]}]},
]){
  const event=e('evidence',extra);
  assert.equal(evaluate(g('Y',person),{events:[event],quotes:offers()}).alerts.length,0,'rosters, seasons and lineup evidence cannot select a quote without playerId');
  assert.equal(evaluate(g('Y',person),{events:[event],quotes:[playerQuotes[0]]}).alerts.length,1,'quoted player identity does not depend on lineup or settlement evidence');
}
assert.ok(formatUnifiedFormula(rule(grouped),entities).includes(' O '));
assert.ok(formatUnifiedFormula(rule(grouped),entities).includes(' Y '));
console.log('Unified formula core: nested Y/O, exact quote scopes and prices, unknown data, player references, contract identity and settlement separation passed.');
