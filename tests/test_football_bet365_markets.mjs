import assert from 'node:assert/strict';
import {FOOTBALL_MARKETS,settleFootballAction,validateFootballStrategy,evaluateFootballStrategy} from '../app/football-strategy-engine.js';

const event={id:'game',date:'2026-01-01',home:'Local',away:'Visitante',home_score:2,away_score:1,home_ht_score:0,away_ht_score:1,
  home_corners:6,away_corners:3,home_ht_corners:2,away_ht_corners:1,
  cardsRules:'bet365',home_cards:3,away_cards:2,
  home_shots:12,away_shots:8,home_ht_shots:5,away_ht_shots:4,
  home_shots_on_target:5,away_shots_on_target:3,home_offsides:2,away_offsides:1,
  firstTeamToScore:'away',lastTeamToScore:'home',firstGoalscorer:'p1',lastGoalscorer:'p2',
  playerStats:[{playerId:'p1',teamId:'h',starter:true,goals:1,shots:4,shotsOnTarget:2,assists:1},{playerId:'p2',teamId:'a',starter:true,goals:1}],
};
const entities={teams:[{id:'h',name:'Local'},{id:'a',name:'Visitante'}],players:[{id:'p1',name:'Delantero',teamId:'h'},{id:'p2',name:'Otro',teamId:'a'}]};
const action=(market,selection,rest={})=>({market,period:'full',selection,team:'home',stake:1,...rest});
const rule=a=>({conditions:[],action:a});
const settle=(a,e=event)=>settleFootballAction(e,a,{}, {entities});
const cases=[
  [action('double_chance','home_draw'),'win'],[action('double_chance','draw_away'),'loss'],[action('double_chance','home_away'),'win'],
  [action('draw_no_bet','home'),'win'],[action('draw_no_bet','away'),'loss'],
  [action('handicap_result','draw',{line:-1}),'win'],[action('handicap_result','home',{line:-1}),'loss'],
  [action('asian_handicap','home',{line:-1}),'push'],[action('asian_handicap','away',{team:'away',line:1.5}),'win'],
  [action('half_time_full_time','away_home'),'win'],[action('half_time_full_time','home_home'),'loss'],
  [action('odd_even','odd',{team:'total'}),'win'],[action('odd_even','even'),'win'],
  [action('team_to_score','yes',{team:'away'}),'win'],[action('clean_sheet','no'),'win'],[action('win_to_nil','yes'),'loss'],
  [action('result_btts','home_yes'),'win'],[action('result_btts','home_no'),'loss'],
  [action('first_team_to_score','away'),'win'],[action('last_team_to_score','home'),'win'],
  [action('cards','over',{team:'total',line:4.5}),'win'],[action('cards','exact',{line:3}),'win'],
  [action('shots','under',{team:'away',line:8.5}),'win'],[action('shots_on_target','over',{team:'total',line:7.5}),'win'],
  [action('offsides','at_least',{team:'total',line:3}),'win'],
  [action('player_shots','at_least',{playerId:'p1',teamId:'h',line:4}),'win'],
  [action('player_shots_on_target','over',{playerId:'p1',teamId:'h',line:2}),'push'],
  [action('player_assists','at_least',{playerId:'p1',teamId:'h',line:1}),'win'],
  [action('first_goalscorer','player',{playerId:'p1',teamId:'h'}),'win'],
  [action('last_goalscorer','player',{playerId:'p1',teamId:'h'}),'loss'],
];
for(const [a,outcome]of cases){assert.ok(FOOTBALL_MARKETS.includes(a.market));validateFootballStrategy(rule(a));assert.deepEqual(settle(a),{outcome,status:null},`${a.market}: ${a.selection}`);}
assert.equal(settle(action('draw_no_bet','home'),{...event,home_score:1}).outcome,'push');
assert.equal(settle(action('win_to_nil','yes'),{...event,away_score:0}).outcome,'win');
assert.equal(settle(action('clean_sheet','yes'),{...event,home_score:0,away_score:0}).outcome,'win');
assert.equal(settle(action('odd_even','even',{team:'total'}),{...event,home_score:0,away_score:0}).outcome,'win');
assert.equal(settle(action('first_team_to_score','none'),{...event,firstTeamToScore:undefined,home_score:0,away_score:0}).outcome,'win');
assert.equal(settle(action('shots','over',{team:'total',line:10.5,period:'second_half'})).outcome,'win');

// Neither score totals nor generic yellow-card counts prove special markets.
assert.equal(settle(action('cards','over',{team:'total',line:4.5}),{...event,cardsRules:undefined,home_yellow:5,away_yellow:5}).status,'cards_settlement_missing');
assert.equal(settle(action('first_team_to_score','home'),{...event,firstTeamToScore:undefined}).status,'goal_order_missing');
assert.equal(settle(action('half_time_full_time','away_home'),{...event,home_ht_score:undefined}).status,'half_time_result_missing');
assert.equal(settle(action('shots','over',{line:1.5}),{...event,home_shots:undefined}).outcome,null);
assert.equal(settle(action('first_goalscorer','player',{playerId:'p1',teamId:'h'}),{...event,firstGoalscorer:undefined}).status,'goalscorer_order_missing');
const nonstarter={...event,playerStats:[{...event.playerStats[0],starter:false,minutes:45}]};
assert.equal(settle(action('first_goalscorer','player',{playerId:'p1',teamId:'h'}),nonstarter).status,'player_participation_rules_missing');
assert.equal(settle(action('player_shots','over',{playerId:'p1',teamId:'h',line:1.5}),nonstarter).outcome,null);
const extraTime={...event,extraTimePlayed:true};
assert.equal(settle(action('player_shots','over',{playerId:'p1',teamId:'h',line:3.5}),extraTime).outcome,null);
assert.equal(settle(action('player_shots','over',{playerId:'p1',teamId:'h',line:3.5}),{...extraTime,playerStats:[{...event.playerStats[0],includesExtraTime:true}]}).outcome,'win');
assert.equal(settle(action('asian_handicap','home',{line:.25})).status,'asian_quarter_line_unsupported');
assert.throws(()=>validateFootballStrategy(rule(action('asian_handicap','home',{line:.25}))),/cuarto/);
assert.throws(()=>validateFootballStrategy(rule(action('handicap_result','home',{line:.5}))),/entera/);
assert.throws(()=>validateFootballStrategy(rule(action('shots','exact',{line:2.5}))),/entera/);
assert.throws(()=>validateFootballStrategy(rule(action('half_time_full_time','away_home',{period:'first_half'}))),/descanso/);
assert.throws(()=>validateFootballStrategy(rule(action('first_goalscorer','player',{playerId:'p1',period:'first_half'}))),/completo/);

const offers=[2,3,4].map((odds,side)=>({event:0,book:'B',side,odds}));
function evaluate(a,quotes=[],e=event){return evaluateFootballStrategy({events:[{...e,marketQuotes:quotes}],offers},rule({...a,oddsSource:'archive',probabilitySource:'manual',probability:.4}),{entities}).alerts[0];}
// A new contract can use only its own archived market, side, period and line.
for(const [a]of cases){
  const exact={...a,book:'B',odds:2.4};
  const wrongPeriod={...exact,period:'first_half',odds:90};
  const wrongSelection={...exact,selection:'not-this-selection',odds:95};
  const quotes=[{...exact,market:'match_result',odds:99},wrongPeriod,wrongSelection,exact];
  if(a.line!=null)quotes.unshift({...exact,line:a.line+1,odds:98});
  if(a.playerId)quotes.unshift({...exact,playerId:'wrong-player',odds:97});
  if(['cards','shots','shots_on_target','offsides','odd_even','team_to_score','clean_sheet','win_to_nil','asian_handicap'].includes(a.market))quotes.unshift({...exact,team:a.team==='away'?'home':'away',odds:96});
  const row=evaluate(a,quotes);assert.equal(row.odds,2.4,`quote identity: ${a.market}`);assert.ok(row.actionLabel&&!row.actionLabel.includes('undefined'));
  assert.equal(evaluate(a,quotes.filter(q=>q!==exact)).odds,null,`no substitute quote: ${a.market}`);
}
assert.equal(evaluate(action('double_chance','home_draw')).odds,null,'never manufacture double chance from 1X2');
const missingLine=action('asian_handicap','home',{line:0});
assert.equal(evaluate(missingLine,[{market:'asian_handicap',selection:'home',team:'home',period:'full',line:null,book:'B',odds:3}]).odds,null);
const equivalent=evaluate(action('shots','at_least',{team:'home',line:4}),[{market:'shots',selection:'over',team:'home',line:3.5,book:'B',odds:2.8}]);
assert.equal(equivalent.odds,2.8,'at least four and over 3.5 describe the same count contract');

// A draw refund has zero realized profit and must be present in EV assumptions.
const drawEvent={...event,home_score:1,away_score:1};
const dnb=action('draw_no_bet','home',{oddsSource:'manual',odds:2,probabilitySource:'manual',probability:.4});
let refunded=evaluateFootballStrategy({events:[drawEvent],offers},rule(dnb),{entities}).alerts[0];
assert.equal(refunded.outcome,'push');assert.equal(refunded.profit,0);assert.equal(refunded.ev,null);assert.ok(refunded.statuses.includes('push_probability_missing'));
refunded=evaluateFootballStrategy({events:[drawEvent],offers},rule({...dnb,pushProbability:.3}),{entities}).alerts[0];
assert.ok(Math.abs(refunded.ev-.1)<1e-12);assert.equal(refunded.breakEven,.35);
const explicitCards={market:'cards',period:'full',selection:'over',team:'total',line:4.5,outcome:'win'};
assert.equal(settle(action('cards','over',{team:'total',line:4.5}),{id:'settled',marketResults:[explicitCards]}).outcome,'win');
assert.equal(settle(action('cards','over',{team:'total',line:5.5}),{id:'settled',marketResults:[explicitCards]}).outcome,null);
console.log('Bet365 football markets: real contracts, exact quote matching, push accounting and missing-data guards passed.');
