/** Football alerts: pre-match conditions, a separate wager contract, and honest coverage.
 * No odds-derived score model, no multiplication of correlated selections, and no
 * current roster used as proof that a player represented a club in an old match.
 */
// A roster snapshot may support forecasts for at most two weeks by default;
// this is not a historical-membership interval and is not a UI filter.
export const DEFAULT_ROSTER_MAX_AGE_DAYS = 14;
export const FOOTBALL_CONDITION_FIELDS = Object.freeze([
  'home_odds','draw_odds','away_odds','home_implied','draw_implied','away_implied',
  'implied_gap','return_gap','odds_ratio','home_return','draw_return','away_return',
  'selected_odds','ev',...Array.from({length:8},(_,i)=>`leg_${i+1}_odds`),
  ...Array.from({length:40},(_,i)=>`situation_${i+1}_odds`),
]);
export const FOOTBALL_MARKETS = Object.freeze([
  'match_result','double_chance','draw_no_bet','handicap_result','asian_handicap',
  'half_time_full_time','correct_score','total_goals','team_goals','btts','result_btts',
  'odd_even','team_to_score','clean_sheet','win_to_nil','first_team_to_score','last_team_to_score',
  'corners','cards','shots','shots_on_target','offsides','player_goals','player_shots',
  'player_shots_on_target','player_assists','first_goalscorer','last_goalscorer','combination',
]);
const countMarkets = new Set(['total_goals','team_goals','corners','cards','shots','shots_on_target','offsides','player_goals','player_shots','player_shots_on_target','player_assists']);
const playerMarkets = new Set(['player_goals','player_shots','player_shots_on_target','player_assists','first_goalscorer','last_goalscorer']);
const teamCountMarkets = new Set(['team_goals','corners','cards','shots','shots_on_target','offsides']);
const teamBooleanMarkets = new Set(['team_to_score','clean_sheet','win_to_nil']);
const operators = new Set(['between','>=','>','<=','<','=','==','!=']);
const knownFields = new Set(FOOTBALL_CONDITION_FIELDS);
const numeric = value => typeof value === 'number' && Number.isFinite(value);
const positiveOdds = value => numeric(value) && value > 1;
const probability = value => numeric(value) && value >= 0 && value <= 1;
const normalize = value => String(value??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('es').replace(/[^a-z0-9]/g,'');
const asArray = value => Array.isArray(value)?value:value&&typeof value==='object'?Object.values(value):[];
const day = event => String(event.date||event.startDate||event.kickoff||'').slice(0,10);
const period = value => ({ft:'full',full_time:'full',ht:'first_half',half_time:'first_half','1h':'first_half','2h':'second_half'})[value]||value||'full';
const market = value => ({h2h:'match_result',three_way:'match_result',correctScore:'correct_score',totals:'total_goals',totals25:'total_goals',both_teams_to_score:'btts'})[value]||value;
const selection = value => ({H:'home',D:'draw',A:'away','1':'home',X:'draw','2':'away',Yes:'yes',No:'no',Over:'over',Under:'under'})[value]||String(value??'').toLowerCase();
const count = value => numeric(value)&&value>=0&&Number.isInteger(value);
const independentSituation = condition => /^situation_([1-9]|[1-3]\d|40)_odds$/.test(condition?.field||'');
const situationSelections = rule => rule.conditions.filter(independentSituation).map(condition=>condition.selection);
function requireCondition(condition){
  if(!knownFields.has(condition?.field))throw new Error(`La condición «${condition?.field||''}» no es un dato previo al partido.`);
  // A situation can observe a contract that is independent of the final wager.
  // Its archived price needs its own exact selection, never a result-price proxy.
  if(independentSituation(condition))validateAction(condition.selection,true);
  if(!operators.has(condition.operator))throw new Error('Elegí una comparación válida.');
  if(condition.operator==='between'){
    if(!numeric(condition.min)||!numeric(condition.max)||condition.min>condition.max)throw new Error('El rango de la condición no es válido.');
  }else if(!numeric(condition.value))throw new Error('La condición necesita un valor numérico.');
}
function validateAction(action, nested=false){
  if(!FOOTBALL_MARKETS.includes(action?.market))throw new Error('Elegí un mercado de fútbol válido.');
  if(!['full','first_half','second_half'].includes(period(action.period)))throw new Error('Elegí un período válido.');
  if(action.market==='combination'){
    if(nested||!Array.isArray(action.legs)||action.legs.length<2||action.legs.length>8)throw new Error('La combinada necesita entre dos y ocho selecciones.');
    action.legs.forEach(leg=>validateAction(leg,true));return;
  }
  if(action.market==='correct_score'&&(!count(action.homeGoals)||!count(action.awayGoals)))throw new Error('El marcador necesita goles enteros para local y visitante.');
  if(countMarkets.has(action.market)){
    if(!numeric(action.line)||action.line<0||!Number.isInteger(action.line*2))throw new Error('Usá una cantidad entera o una línea terminada en 0,5.');
    if(!['over','under','at_least','exact'].includes(selection(action.selection)))throw new Error('Elegí más, menos, al menos o exactamente.');
  }
  if(action.market==='match_result'&&!['home','draw','away'].includes(selection(action.selection)))throw new Error('Elegí local, empate o visitante.');
  if(action.market==='btts'&&!['yes','no'].includes(selection(action.selection)))throw new Error('Elegí ambos marcan: sí o no.');
  if(playerMarkets.has(action.market)&&!action.playerId)throw new Error('Elegí un jugador del equipo.');
  if(action.market==='double_chance'&&!['home_draw','home_away','draw_away'].includes(selection(action.selection)))throw new Error('Elegí una doble oportunidad válida.');
  if(action.market==='draw_no_bet'&&!['home','away'].includes(selection(action.selection)))throw new Error('Elegí local o visitante.');
  if(action.market==='handicap_result'){
    if(!numeric(action.line)||!Number.isInteger(action.line))throw new Error('El hándicap de tres opciones necesita una línea entera aplicada al local.');
    if(!['home','draw','away'].includes(selection(action.selection)))throw new Error('Elegí local, empate o visitante.');
  }
  if(action.market==='asian_handicap'){
    if(!numeric(action.line)||!Number.isInteger(action.line*2))throw new Error('El hándicap asiático admite líneas enteras o medias; las líneas de cuarto aún no están disponibles.');
    if(!['home','away','selected'].includes(action.team)||!['home','away'].includes(selection(action.selection))||['home','away'].includes(action.team)&&action.team!==selection(action.selection))throw new Error('Elegí el equipo del hándicap asiático.');
  }
  if(['first_goalscorer','last_goalscorer','player_shots','player_shots_on_target','player_assists'].includes(action.market)&&period(action.period)!=='full')throw new Error('Este mercado de jugador corresponde al partido completo.');
  if(['first_goalscorer','last_goalscorer'].includes(action.market)&&selection(action.selection)!=='player')throw new Error('Elegí el jugador que marcará.');
  if(action.market==='half_time_full_time'&&(period(action.period)!=='full'||! /^(home|draw|away)_(home|draw|away)$/.test(selection(action.selection))))throw new Error('Elegí una combinación válida de descanso/final.');
  if(action.market==='result_btts'&&! /^(home|draw|away)_(yes|no)$/.test(selection(action.selection)))throw new Error('Elegí resultado y ambos marcarán.');
  if(action.market==='odd_even'&&!['odd','even'].includes(selection(action.selection)))throw new Error('Elegí impar o par.');
  if(teamBooleanMarkets.has(action.market)&&!['yes','no'].includes(selection(action.selection)))throw new Error('Elegí sí o no.');
  if(['first_team_to_score','last_team_to_score'].includes(action.market)&&!['home','away','none'].includes(selection(action.selection)))throw new Error('Elegí local, visitante o ningún gol.');
  if((teamBooleanMarkets.has(action.market)||['team_goals','asian_handicap'].includes(action.market))&&action.team==='total')throw new Error('Elegí un equipo para ese mercado.');
  if(countMarkets.has(action.market)&&['at_least','exact'].includes(selection(action.selection))&&!Number.isInteger(action.line))throw new Error('La cantidad exacta o mínima debe ser entera.');
}
export function validateFootballStrategy(rule){
  if(!rule||!Array.isArray(rule.conditions))throw new Error('La alerta necesita condiciones.');
  if(rule.conditions.length>40)throw new Error('La alerta admite hasta cuarenta condiciones.');
  rule.conditions.forEach(requireCondition);validateAction(rule.action);
  const situationFields=rule.conditions.filter(independentSituation).map(condition=>condition.field);
  if(new Set(situationFields).size!==situationFields.length)throw new Error('Cada situación necesita un identificador distinto.');
  if(!(numeric(rule.action.stake??rule.stake??1)&&(rule.action.stake??rule.stake??1)>0))throw new Error('El importe debe ser mayor que cero.');
  if(rule.action.oddsSource==='manual'&&!positiveOdds(rule.action.odds))throw new Error('Ingresá la cuota de la apuesta, mayor que uno.');
  if(rule.action.probabilitySource==='manual'&&!probability(rule.action.probability))throw new Error('La probabilidad debe estar entre 0% y 100%.');
  if(rule.action.pushProbability!=null&&!probability(rule.action.pushProbability))throw new Error('La probabilidad de devolución no es válida.');
  if(probability(rule.action.probability)&&probability(rule.action.pushProbability)&&rule.action.probability+rule.action.pushProbability>1+1e-12)throw new Error('Las probabilidades de ganar y devolución no pueden sumar más de 100%.');
  return rule;
}
function entitiesFor(options){
  const rosterMaxAgeDays=options.rosterMaxAgeDays??DEFAULT_ROSTER_MAX_AGE_DAYS;
  if(!numeric(rosterMaxAgeDays)||rosterMaxAgeDays<=0)throw new Error('La vigencia del plantel debe ser un número positivo de días.');
  const entities=options.entities||{},teams=asArray(entities.teams),players=asArray(entities.players),byTeam=new Map(teams.map(t=>[String(t.id),t])),byPlayer=new Map(players.map(p=>[String(p.id),p]));
  const aliases=new Map(),global=new Map();
  for(const team of teams)for(const alias of [team.name,...asArray(team.aliases)]){
    const key=normalize(alias);if(!key)continue;
    for(const league of asArray(team.leagueIds))aliases.set(`${league}|${key}`,String(team.id));
    if(!global.has(key))global.set(key,String(team.id));else if(global.get(key)!==String(team.id))global.set(key,null);
  }
  return {entities,byTeam,byPlayer,rosterMaxAgeDays,resolve(event,side){
    const explicit=event[`${side}TeamId`]??event[`${side}_team_id`];if(explicit!=null)return String(explicit);
    const name=event[side]??event[`${side}_team`],key=normalize(name);
    return aliases.get(`${event.league||event.league_code}|${key}`)||global.get(key)||null;
  }};
}
function sameTeam(event,side,value,catalog){
  if(!value)return true;
  const target=String(value),resolved=catalog.resolve(event,side);
  if(resolved===target)return true;
  const team=catalog.byTeam.get(target),name=event[side]??event[`${side}_team`];
  return team?[team.name,...asArray(team.aliases)].some(alias=>normalize(alias)===normalize(name)):normalize(target)===normalize(name);
}
function actionTeam(action,rule,event,catalog){
  const team=action.team??(action.teamId?'selected':['corners','cards','shots','shots_on_target','offsides','odd_even'].includes(action.market)?'total':playerMarkets.has(action.market)?'selected':'home');if(team==='home'||team==='away'||team==='total')return team;
  const id=action.teamId||rule.context?.teamId||(catalog.byPlayer.get(String(action.playerId))?.teamId);
  if(!id)return null;
  return sameTeam(event,'home',id,catalog)?'home':sameTeam(event,'away',id,catalog)?'away':null;
}
function contextMatches(event,rule,catalog){
  const c=rule.context||{};
  if(c.league&&String(event.league??event.league_code)!==String(c.league))return false;
  if(c.homeTeam&&!sameTeam(event,'home',c.homeTeam,catalog))return false;
  if(c.awayTeam&&!sameTeam(event,'away',c.awayTeam,catalog))return false;
  if(c.teamId&&!sameTeam(event,'home',c.teamId,catalog)&&!sameTeam(event,'away',c.teamId,catalog))return false;
  const contracts=[...(rule.action.market==='combination'?rule.action.legs:[rule.action]),...situationSelections(rule)];
  for(const leg of contracts){
    if(leg.teamId&&!sameTeam(event,'home',leg.teamId,catalog)&&!sameTeam(event,'away',leg.teamId,catalog))return false;
    const player=catalog.byPlayer.get(String(leg.playerId||''));
    if(player&&!sameTeam(event,'home',player.teamId,catalog)&&!sameTeam(event,'away',player.teamId,catalog))return false;
    if(player&&['home','away'].includes(leg.team)&&!sameTeam(event,leg.team,player.teamId,catalog))return false;
  }
  return true;
}
function validatePlayers(rule,catalog){
  const c=rule.context||{},legs=[...(rule.action.market==='combination'?rule.action.legs:[rule.action]),...situationSelections(rule)];
  const checked=[...(c.playerId?[{playerId:c.playerId,teamId:c.teamId}]:[]),...legs.filter(l=>l.playerId)];
  for(const leg of checked){
    const player=catalog.byPlayer.get(String(leg.playerId));if(!player){if(catalog.entities.players!=null)throw new Error('El jugador elegido no está en la plantilla verificada.');continue;}
    const teamId=leg.teamId||(leg.playerId===c.playerId?c.teamId:null);
    if(teamId&&String(player.teamId)!==String(teamId))throw new Error('El jugador elegido no pertenece al equipo seleccionado.');
    if(['home','away'].includes(leg.team)){
      const fixed=c[leg.team==='home'?'homeTeam':'awayTeam'];
      if(fixed&&catalog.byTeam.has(String(fixed))&&String(player.teamId)!==String(fixed))throw new Error('El jugador no pertenece al equipo de esa selección.');
    }
  }
}
// Compare trustworthy, like-for-like season labels. A calendar-year label is
// not silently interpreted as either half of a cross-year European season.
function seasonIdentity(value){
  if(value==null)return null;
  const text=String(value).trim(),range=text.match(/^(\d{4})\s*[-/]\s*(\d{2}|\d{4})$/);
  if(range){const start=Number(range[1]),end=range[2].length===2?Math.floor(start/100)*100+Number(range[2]):Number(range[2]);return end===start+1?{kind:'range',key:`${start}/${end}`}:null;}
  if(/^\d{4}$/.test(text)&&Number(text)>=1800&&Number(text)<=2200)return {kind:'year',key:text};
  return null;
}
function snapshotSeasonMatches(player,event){
  const observed=seasonIdentity(player.season),target=seasonIdentity(event.season);
  return !observed||!target||observed.kind!==target.kind||observed.key===target.key;
}
function playerEvidence(event,playerId,teamId,catalog){
  const id=String(playerId),rows=[...asArray(event.playerStats),...asArray(event.players),...asArray(event.appearances)];
  const row=rows.find(p=>String(p.playerId??p.id)===id);
  if(row&&(teamId==null||String(row.teamId??row.team_id??teamId)===String(teamId)))return {verified:true,row};
  const lineups=asArray(event.lineups);
  for(const lineup of lineups){if(teamId&&String(lineup.teamId??lineup.team_id)!==String(teamId))continue;const found=asArray(lineup.players).find(p=>String(p.playerId??p.id??p)===id);if(found)return {verified:true,row:typeof found==='object'?found:null};}
  const historical=asArray(catalog.entities.historicalMemberships).find(m=>String(m.playerId)===id&&(!teamId||String(m.teamId)===String(teamId))&&(String(m.eventId??m.matchId??'')===String(event.id)||(m.date&&String(m.date).slice(0,10)===day(event))||(m.validFrom&&m.validTo&&m.validFrom<=day(event)&&m.validTo>=day(event))));
  if(historical)return {verified:true,row:null};
  const player=catalog.byPlayer.get(id),asOf=String(player?.asOf||'').slice(0,10);
  // A current snapshot may scope a current/future definition. It never proves
  // historical affiliation, participation, minutes, or a scored goal.
  const ageDays=(Date.parse(`${day(event)}T00:00:00Z`)-Date.parse(`${asOf}T00:00:00Z`))/86400000;
  if(player&&asOf&&Number.isFinite(ageDays)&&ageDays>=0&&ageDays<=catalog.rosterMaxAgeDays&&snapshotSeasonMatches(player,event)&&(!teamId||String(player.teamId)===String(teamId)))return {verified:true,row:null,snapshot:true};
  return {verified:false,row:null};
}
function membershipStatus(event,rule,catalog){
  const c=rule.context||{},legs=rule.action.market==='combination'?rule.action.legs:[rule.action];
  const players=[...(c.playerId?[{playerId:c.playerId,teamId:c.teamId}]:[]),...legs.filter(l=>l.playerId)];
  for(const leg of players){
    const player=catalog.byPlayer.get(String(leg.playerId)),teamId=leg.teamId||player?.teamId||c.teamId;
    if(!player&&!playerEvidence(event,leg.playerId,teamId,catalog).verified)return 'player_membership_missing';
    if(!playerEvidence(event,leg.playerId,teamId,catalog).verified)return 'player_history_missing';
  }
  return null;
}
function eventCount(event,subject,p){
  // The caller must choose the statistic. Yellow cards are not Bet365 cards.
  if(subject==='cards'&&!['bet365','bet365_cards'].includes(event.cardsRules??event.cards_rules))return null;
  const key=subject==='goals'?'score':subject;
  const full=[event[`home_${key}`],event[`away_${key}`]],half=[event[`home_ht_${key}`],event[`away_ht_${key}`]];
  if(p==='first_half')return half.every(count)?half:null;
  if(p==='second_half')return full.every(count)&&half.every(count)&&full.every((v,i)=>v>=half[i])?full.map((v,i)=>v-half[i]):null;
  return full.every(count)?full:null;
}
const resultFor=([home,away])=>home>away?'home':home===away?'draw':'away';
function playerCount(stats,stat,p){
  const capital=stat[0].toUpperCase()+stat.slice(1);
  if(p==='full')return stats?.[stat];
  if(p==='first_half')return stats?.[`firstHalf${capital}`];
  const second=stats?.[`secondHalf${capital}`];
  if(second!=null)return second;
  return count(stats?.[stat])&&count(stats?.[`firstHalf${capital}`])?stats[stat]-stats[`firstHalf${capital}`]:null;
}
function selectedCount(values,action,rule,event,catalog){
  const team=action.market==='total_goals'?'total':actionTeam(action,rule,event,catalog);
  if(!team)return null;
  return team==='total'?values[0]+values[1]:values[team==='home'?0:1];
}
function explicitSettlement(event,action,rule,catalog){
  // Optional bookmaker-settled results allow contracts with special rules to be
  // represented without reconstructing them from unrelated raw statistics.
  const result=asArray(event.marketResults).find(row=>['win','loss','push'].includes(row.outcome)&&quoteMatches(row,action,rule,event,catalog));
  return result?{outcome:result.outcome,status:null}:null;
}
function lineOutcome(value,action){
  const line=action.line,s=selection(action.selection);
  if(s==='at_least')return value>=line?'win':'loss';
  if(s==='exact')return value===line?'win':'loss';
  if(value===line)return 'push';
  return (s==='over'?value>line:value<line)?'win':'loss';
}
export function settleFootballAction(event,action,rule={},options={}){
  const catalog=options._catalog||entitiesFor(options),p=period(action.period),wanted=selection(action.selection);
  if(!FOOTBALL_MARKETS.includes(action.market))return {outcome:null,status:'market_rules_missing'};
  if(action.market==='combination'){
    const results=action.legs.map(leg=>settleFootballAction(event,leg,rule,{...options,_catalog:catalog}));
    if(results.some(r=>r.outcome==null))return {outcome:null,status:results.find(r=>r.outcome==null)?.status||'result_missing'};
    if(results.some(r=>r.outcome==='push'))return {outcome:null,status:'combination_void_rules_missing'};
    return {outcome:results.every(r=>r.outcome==='win')?'win':'loss',status:null};
  }
  const explicit=explicitSettlement(event,action,rule,catalog);if(explicit)return explicit;
  if(playerMarkets.has(action.market)){
    const player=catalog.byPlayer.get(String(action.playerId)),teamId=action.teamId||player?.teamId||rule.context?.teamId,evidence=playerEvidence(event,action.playerId,teamId,catalog);
    if(!evidence.verified)return {outcome:null,status:'player_history_missing'};
    const stats=evidence.row;
    if(action.market==='first_goalscorer'||action.market==='last_goalscorer'){
      // Pregame first/last scorer require a starter, and own goals are excluded.
      // These explicit result fields identify the eligible scorer, not merely
      // the first/last goal event in a feed that might include an own goal.
      if(stats?.starter!==true)return {outcome:null,status:'player_participation_rules_missing'};
      const key=action.market==='first_goalscorer'?'firstGoalscorer':'lastGoalscorer';
      const scorer=p==='full'?event[key]:event[p==='first_half'?'firstHalf':'secondHalf']?.[key];
      if(scorer==null)return {outcome:null,status:'goalscorer_order_missing'};
      return {outcome:String(scorer)===String(action.playerId)?'win':'loss',status:null};
    }
    const stat={player_goals:'goals',player_shots:'shots',player_shots_on_target:'shotsOnTarget',player_assists:'assists'}[action.market];
    let value=playerCount(stats,stat,p);
    // New Bet365 player-stat markets include extra time. Regulation-only totals
    // cannot settle a match known to have included it.
    if(action.market!=='player_goals'&&p==='full'&&event.extraTimePlayed===true&&!stats?.includesExtraTime){
      value=stats?.bet365?.[stat];
    }
    if(!count(value))return {outcome:null,status:'player_result_missing'};
    if(stats.played===false||stats.appeared===false||!(stats.played===true||stats.appeared===true||stats.starter===true||stats.minutes>0||action.market==='player_goals'&&value>0))return {outcome:null,status:'player_participation_rules_missing'};
    if(action.market!=='player_goals'&&stats.starter!==true)return {outcome:null,status:'player_participation_rules_missing'};
    return {outcome:lineOutcome(value,action),status:null};
  }
  if(['cards','shots','shots_on_target','offsides','corners'].includes(action.market)){
    const values=eventCount(event,action.market,p);
    if(!values)return {outcome:null,status:action.market==='cards'?'cards_settlement_missing':p!=='full'?`period_${action.market}_missing`:`${action.market}_result_missing`};
    const value=selectedCount(values,action,rule,event,catalog);
    return value==null?{outcome:null,status:'selected_team_missing'}:{outcome:lineOutcome(value,action),status:null};
  }
  if(['first_team_to_score','last_team_to_score'].includes(action.market)){
    const key=action.market==='first_team_to_score'?'firstTeamToScore':'lastTeamToScore';
    let value=p==='full'?event[key]:event[p==='first_half'?'firstHalf':'secondHalf']?.[key];
    if(value==null){const goals=eventCount(event,'goals',p);if(goals&&goals[0]+goals[1]===0)value='none';}
    if(!['home','away','none'].includes(selection(value)))return {outcome:null,status:'goal_order_missing'};
    return {outcome:selection(value)===wanted?'win':'loss',status:null};
  }
  const goals=eventCount(event,'goals',p);
  if(!goals)return {outcome:null,status:'result_missing'};
  const [home,away]=goals,result=resultFor(goals);
  let won;
  if(action.market==='correct_score')won=home===action.homeGoals&&away===action.awayGoals;
  else if(action.market==='match_result')won=result===wanted;
  else if(action.market==='double_chance')won=wanted.split('_').includes(result);
  else if(action.market==='draw_no_bet')return {outcome:result==='draw'?'push':result===wanted?'win':'loss',status:null};
  else if(action.market==='handicap_result')won=resultFor([home+action.line,away])===wanted;
  else if(action.market==='asian_handicap'){
    if(!numeric(action.line)||!Number.isInteger(action.line*2))return {outcome:null,status:'asian_quarter_line_unsupported'};
    const side=actionTeam(action,rule,event,catalog);
    if(!['home','away'].includes(side))return {outcome:null,status:'selected_team_missing'};
    const difference=(side==='home'?home-away:away-home)+action.line;
    return {outcome:difference===0?'push':difference>0?'win':'loss',status:null};
  }
  else if(action.market==='half_time_full_time'){
    const half=eventCount(event,'goals','first_half');if(!half)return {outcome:null,status:'half_time_result_missing'};
    won=`${resultFor(half)}_${result}`===wanted;
  }
  else if(action.market==='btts')won=(home>0&&away>0)===(wanted==='yes');
  else if(action.market==='result_btts')won=`${result}_${home>0&&away>0?'yes':'no'}`===wanted;
  else if(action.market==='odd_even'){
    const value=selectedCount(goals,action,rule,event,catalog);if(value==null)return {outcome:null,status:'selected_team_missing'};
    won=(value%2===1)===(wanted==='odd');
  }
  else if(teamBooleanMarkets.has(action.market)){
    const side=actionTeam(action,rule,event,catalog);if(!['home','away'].includes(side))return {outcome:null,status:'selected_team_missing'};
    const own=side==='home'?home:away,opponent=side==='home'?away:home;
    const truth=action.market==='team_to_score'?own>0:action.market==='clean_sheet'?opponent===0:own>0&&opponent===0;
    won=truth===(wanted==='yes');
  }
  else {
    const value=selectedCount(goals,action,rule,event,catalog);
    return value==null?{outcome:null,status:'selected_team_missing'}:{outcome:lineOutcome(value,action),status:null};
  }
  return {outcome:won?'win':'loss',status:null};
}
function targetSide(action){return ['home','draw','away'].indexOf(selection(action.selection));}
function quoteMatches(quote,action,rule,event,catalog){
  if(market(quote.market)!==action.market||period(quote.period)!==period(action.period))return false;
  if(action.market==='combination')return Array.isArray(quote.legs)&&quote.legs.length===action.legs.length&&quote.legs.every((q,i)=>quoteMatches(q,action.legs[i],rule,event,catalog));
  if(action.market==='correct_score'){
    let h=quote.homeGoals,a=quote.awayGoals;const score=String(quote.selection||'').match(/^(\d+)\s*[-:]\s*(\d+)$/);if(score){h??=Number(score[1]);a??=Number(score[2]);}
    return h===action.homeGoals&&a===action.awayGoals;
  }
  if(playerMarkets.has(action.market)&&String(quote.playerId)!==String(action.playerId))return false;
  if(countMarkets.has(action.market)){
    if(quote.line==null||String(quote.line).trim()==='')return false;
    const offeredLine=Number(quote.line),offeredSelection=selection(quote.selection),wantedSelection=selection(action.selection);
    const sameContract=offeredLine===action.line&&offeredSelection===wantedSelection;
    const equivalentAtLeast=wantedSelection==='at_least'&&Number.isInteger(action.line)&&offeredSelection==='over'&&offeredLine===action.line-.5;
    if(!sameContract&&!equivalentAtLeast)return false;
    if(teamCountMarkets.has(action.market)||playerMarkets.has(action.market)){
      const target=actionTeam(action,rule,event,catalog),quoted=actionTeam(quote,rule,event,catalog);if(quoted!==target)return false;
    }
    return true;
  }
  if(action.market==='asian_handicap'){
    return quote.line!=null&&String(quote.line).trim()!==''&&Number(quote.line)===action.line&&selection(quote.selection)===selection(action.selection)&&actionTeam(quote,rule,event,catalog)===actionTeam(action,rule,event,catalog);
  }
  if(action.market==='handicap_result'&&(quote.line==null||String(quote.line).trim()===''||Number(quote.line)!==action.line))return false;
  if((teamBooleanMarkets.has(action.market)||action.market==='odd_even')&&actionTeam(quote,rule,event,catalog)!==actionTeam(action,rule,event,catalog))return false;
  return selection(quote.selection)===selection(action.selection);
}
function quoteFor(group,action,rule,extra,catalog){
  if(action.market==='match_result'&&period(action.period)==='full'){
    const row=group.sides[targetSide(action)];if(row&&positiveOdds(row.odds))return {...row,market:'match_result',period:'full',selection:selection(action.selection),book:group.book};
  }
  const attached=asArray(group.event.marketQuotes),external=extra.get(String(group.event.id))||[];
  return [...attached,...external].filter(q=>(q.book!=null&&String(q.book)===group.book)&&positiveOdds(q.odds)&&quoteMatches(q,action,rule,group.event,catalog)).sort((a,b)=>b.odds-a.odds)[0]||null;
}
function conditionMatches(condition,values){
  const actual=values[condition.field];if(!numeric(actual))return false;
  switch(condition.operator){case 'between':return actual>=condition.min&&actual<=condition.max;case '>=':return actual>=condition.value;case '>':return actual>condition.value;case '<=':return actual<=condition.value;case '<':return actual<condition.value;case '!=':return actual!==condition.value;default:return actual===condition.value;}
}
function conditionsMatch(conditions,values,join){if(!conditions.length)return true;return join==='O'?conditions.some(c=>conditionMatches(c,values)):conditions.every(c=>conditionMatches(c,values));}
function requiresPushProbability(action){return action.market==='draw_no_bet'||action.market==='asian_handicap'&&Number.isInteger(action.line)||countMarkets.has(action.market)&&['over','under'].includes(selection(action.selection))&&Number.isInteger(action.line);}
function label(action,rule,event,catalog){
  if(action.market==='combination')return action.legs.map(leg=>label(leg,rule,event,catalog)).join(' + ');
  const team=actionTeam(action,rule,event,catalog),home=event.home??event.home_team??'Local',away=event.away??event.away_team??'Visitante',name=team==='home'?home:team==='away'?away:'Partido';
  const wanted=selection(action.selection),resultNames={home,draw:'Empate',away},yesNo=wanted==='yes'?'Sí':'No';
  const quantity=wanted==='at_least'?`${action.line}+`:wanted==='exact'?`Exactamente ${action.line}`:`${wanted==='over'?'Más de':'Menos de'} ${action.line}`;
  const player=catalog.byPlayer.get(String(action.playerId))?.name||action.playerId;
  let base;
  if(action.market==='correct_score')base=`Marcador ${action.homeGoals}–${action.awayGoals}`;
  else if(action.market==='match_result')base=resultNames[wanted];
  else if(action.market==='double_chance')base=`Doble oportunidad · ${wanted.split('_').map(v=>resultNames[v]).join(' o ')}`;
  else if(action.market==='draw_no_bet')base=`Empate, apuesta no válida · ${resultNames[wanted]}`;
  else if(action.market==='handicap_result')base=`Hándicap ${action.line>=0?'+':''}${action.line} al local · ${resultNames[wanted]}`;
  else if(action.market==='asian_handicap')base=`Hándicap asiático · ${name} ${action.line>=0?'+':''}${action.line}`;
  else if(action.market==='half_time_full_time')base=`Descanso/Final · ${wanted.split('_').map(v=>resultNames[v]).join(' / ')}`;
  else if(action.market==='btts')base=`Ambos marcan: ${yesNo}`;
  else if(action.market==='result_btts'){const [result,btts]=wanted.split('_');base=`${resultNames[result]} y ambos marcan: ${btts==='yes'?'Sí':'No'}`;}
  else if(action.market==='odd_even')base=`${name} · Goles ${wanted==='odd'?'impares':'pares'}`;
  else if(teamBooleanMarkets.has(action.market))base=`${name} · ${{team_to_score:'Marcará',clean_sheet:'Portería a cero',win_to_nil:'Ganará sin recibir goles'}[action.market]}: ${yesNo}`;
  else if(['first_team_to_score','last_team_to_score'].includes(action.market))base=`${action.market==='first_team_to_score'?'Primer':'Último'} equipo en marcar · ${wanted==='none'?'Ningún gol':resultNames[wanted]}`;
  else if(['first_goalscorer','last_goalscorer'].includes(action.market))base=`${action.market==='first_goalscorer'?'Primer':'Último'} goleador · ${player}`;
  else {
    const unit={total_goals:'goles',team_goals:'goles',player_goals:'goles',corners:'córners',cards:'tarjetas',shots:'remates',shots_on_target:'remates a puerta',offsides:'fueras de juego',player_shots:'remates',player_shots_on_target:'remates a puerta',player_assists:'asistencias'}[action.market];
    base=`${playerMarkets.has(action.market)?player:name} · ${quantity} ${unit}`;
  }
  return base+(period(action.period)==='first_half'?' · 1.er tiempo':period(action.period)==='second_half'?' · 2.º tiempo':'');
}
function numericMean(rows,key){const values=rows.map(r=>r[key]).filter(numeric);return values.length?values.reduce((a,b)=>a+b,0)/values.length:null;}
function summaryFor(alerts){
  const settled=alerts.filter(a=>a.won!==null),priced=alerts.filter(a=>positiveOdds(a.odds)),monetary=alerts.filter(a=>numeric(a.profit)),archive=monetary.filter(a=>a.quoteSource==='archive'),manual=monetary.filter(a=>a.quoteSource==='manual');
  const sum=(rows,key)=>rows.reduce((n,r)=>n+(numeric(r[key])?r[key]:0),0),roi=rows=>rows.length?sum(rows,'profit')/sum(rows,'stake'):null;
  const expected=alerts.filter(a=>numeric(a.expectedProfit));
  return {n:alerts.length,alerts:alerts.length,wins:settled.filter(a=>a.won===true).length,losses:settled.filter(a=>a.won===false).length,pushes:settled.filter(a=>a.won==='push').length,settled:settled.length,priced:priced.length,settledPriced:monetary.length,stake:monetary.length?sum(monetary,'stake'):null,profit:monetary.length?sum(monetary,'profit'):null,roi:roi(monetary),historicalROI:roi(archive),scenarioROI:roi(manual),isScenario:manual.length>0,resultBasis:manual.length?(archive.length?'mixed':'manual_scenario'):'archive',winRate:settled.length?settled.filter(a=>a.won===true).length/settled.length:null,meanEV:numericMean(alerts,'ev'),meanProbability:numericMean(alerts,'probability'),meanOdds:numericMean(alerts,'odds'),expectedProfit:expected.length?sum(expected,'expectedProfit'):null,expectedStake:expected.length?sum(expected,'stake'):null,expectedPriced:expected.length};
}
/** Aggregate a display subset without refitting its already calculated probabilities. */
export function summarizeFootballAlerts(alerts = []) {
  const summary=summaryFor(alerts),yearMap=new Map();
  for(const row of alerts){const year=String(row.date||'').slice(0,4);if(!yearMap.has(year))yearMap.set(year,[]);yearMap.get(year).push(row);}
  summary.years=[...yearMap].map(([year,rows])=>({year,...summaryFor(rows)}));
  return summary;
}
/** Evaluate one saved alert against one explicit historical universe.
 * Empirical estimates use only earlier dates and count a match once even if
 * several bookmakers triggered. Same-day scores never train another signal.
 */
export function evaluateFootballStrategy({events=[],offers=[],marketQuotes=[]},rule,options={}){
  validateFootballStrategy(rule);const catalog=entitiesFor(options);validatePlayers(rule,catalog);
  const eventById=new Map(events.map((event,index)=>[String(event.id),{event,index}])),groups=new Map(),extra=new Map();
  for(const quote of [...asArray(marketQuotes),...asArray(options.marketQuotes)]){const ref=quote.eventId??quote.matchId??quote.event;const id=Number.isInteger(ref)?events[ref]?.id:ref;if(id==null)continue;const key=String(id);if(!extra.has(key))extra.set(key,[]);extra.get(key).push(quote);}
  let contextEvents=0;const eligible=new Set();
  for(let i=0;i<events.length;i++)if(contextMatches(events[i],rule,catalog)){eligible.add(i);contextEvents++;}
  for(const offer of offers){
    let entry=Number.isInteger(offer.event)?{event:events[offer.event],index:offer.event}:eventById.get(String(offer.eventId??offer.event??offer.id));
    if(!entry?.event||!eligible.has(entry.index)||!positiveOdds(offer.odds)||![0,1,2].includes(Number(offer.side)))continue;
    if(offer.market&&market(offer.market)!=='match_result')continue;
    if(offer.period&&period(offer.period)!=='full')continue;
    const key=`${entry.index}|${offer.book}`;if(!groups.has(key))groups.set(key,{event:entry.event,eventIndex:entry.index,book:String(offer.book),sides:[]});
    const group=groups.get(key),i=Number(offer.side);if(!group.sides[i]||offer.odds>group.sides[i].odds)group.sides[i]=offer;
  }
  const ordered=[...groups.values()].filter(g=>g.sides.length===3&&[0,1,2].every(i=>g.sides[i])).sort((a,b)=>day(a.event).localeCompare(day(b.event))||String(a.event.id).localeCompare(String(b.event.id))||a.book.localeCompare(b.book));
  const action=rule.action,stake=action.stake??rule.stake??1,pSource=action.probabilitySource||'empirical',minimum=Math.max(1,Math.floor(action.minSample??30));
  const conditions=rule.conditions,baseConditions=conditions.filter(c=>c.field!=='ev'),hasModelCondition=baseConditions.length!==conditions.length;
  const history=new Map(),pending=new Map();let currentDay=null,wins=0,pushes=0,observations=0;
  const addPending=()=>{for(const [id,outcome]of pending)if(!history.has(id)){history.set(id,outcome);observations++;wins+=Number(outcome==='win');pushes+=Number(outcome==='push');}pending.clear();};
  const rawAlerts=[];let baseGroups=0,missingConditionValues=0;
  for(const group of ordered){
    const date=day(group.event);if(currentDay!==date){addPending();currentDay=date;}
    const [h,d,a]=group.sides.map(r=>r.odds),quote=quoteFor(group,action,rule,extra,catalog),values={home_odds:h,draw_odds:d,away_odds:a,home_implied:1/h,draw_implied:1/d,away_implied:1/a,implied_gap:1/h-1/a,return_gap:h-a,odds_ratio:h/a,home_return:h-1,draw_return:d-1,away_return:a-1};
    const odds=action.oddsSource==='manual'?action.odds:quote?.odds??null,quoteSource=action.oddsSource==='manual'?'manual':positiveOdds(odds)?'archive':null;values.selected_odds=odds;
    for(const [i,leg]of (action.legs||[]).entries())values[`leg_${i+1}_odds`]=quoteFor(group,leg,rule,extra,catalog)?.odds??null;
    for(const condition of conditions.filter(independentSituation))values[condition.field]=quoteFor(group,condition.selection,rule,extra,catalog)?.odds??null;
    const baseMatched=conditionsMatch(baseConditions,values,rule.join);
    const membership=membershipStatus(group.event,rule,catalog),settlement=membership?{outcome:null,status:membership}:settleFootballAction(group.event,action,rule,{...options,_catalog:catalog});
    let p=null,pushP=null,n=null,pStatus=null;
    if(pSource==='manual'){
      p=action.probability;pushP=action.pushProbability??(requiresPushProbability(action)?null:0);
    }else if(pSource==='reference'){
      // 'ownProbability' is never a substitute for an independent reference.
      const reference=quote?.referenceProbability??quote?.probability,refs=quote?.references;
      if(probability(reference)&&(!Array.isArray(refs)||refs.length>0)){p=reference;n=Array.isArray(refs)?refs.length:null;}
      pushP=quote?.pushProbability??(requiresPushProbability(action)?null:0);
    }else{
      n=observations;
      // This estimate is conditional on the pre-EV cohort. In an OR rule an
      // unrelated high price must not borrow that cohort's probability. With
      // no pre-EV clauses baseMatched is true, so EV-only rules use all history.
      if(!baseMatched)pStatus='probability_cohort_mismatch';
      else if(observations>=minimum){p=wins/observations;pushP=pushes/observations;}
      else pStatus='probability_history_insufficient';
    }
    if(membership){p=null;pushP=null;pStatus=membership;}
    const ambiguousCombinationVoids=action.market==='combination'&&action.legs.some(requiresPushProbability);
    const ev=!ambiguousCombinationVoids&&probability(p)&&positiveOdds(odds)&&probability(pushP)?p*odds+pushP-1:null;values.ev=ev;
    if(baseMatched){baseGroups++;if(settlement.outcome!=null)pending.set(String(group.event.id),settlement.outcome);}
    // With no model-derived clauses the conditions describe the empirical cohort.
    // With EV gates, bootstrap that cohort from the other pre-match clauses first.
    const matched=hasModelCondition?conditionsMatch(conditions,values,rule.join):baseMatched;
    if(!matched){if(conditions.some(c=>!numeric(values[c.field])))missingConditionValues++;continue;}
    const statuses=[];if(ambiguousCombinationVoids)statuses.push('combination_void_rules_missing');if(membership)statuses.push(membership);if(!positiveOdds(odds))statuses.push('market_quote_missing');if(!probability(p))statuses.push(pStatus||'probability_missing');else if(!probability(pushP))statuses.push('push_probability_missing');if(settlement.outcome==null)statuses.push(settlement.status||'result_missing');
    const outcome=settlement.outcome,won=outcome==='win'?true:outcome==='loss'?false:outcome==='push'?'push':null,profit=positiveOdds(odds)&&outcome!=null?(outcome==='win'?(odds-1)*stake:outcome==='loss'?-stake:0):null;
    rawAlerts.push({id:String(group.event.id),event:group.eventIndex,date,league:group.event.league??group.event.league_code,home:group.event.home??group.event.home_team,away:group.event.away??group.event.away_team,book:group.book,market:action.market,period:period(action.period),actionLabel:label(action,rule,group.event,catalog),contextOdds:{home:h,draw:d,away:a},contextValues:values,odds,probability:p,pushProbability:pushP,probabilityN:n,probabilitySource:pSource,ev,expectedProfit:numeric(ev)?stake*ev:null,stake,won,outcome,profit,quoteSource,isScenario:quoteSource==='manual',breakEven:!ambiguousCombinationVoids&&positiveOdds(odds)&&probability(pushP)?(1-pushP)/odds:null,reference:quote?.references||[],status:statuses[0]||'ready',statuses,triggered:true});
  }
  let alerts=rawAlerts;
  if(rule.onePerMatch!==false){
    const best=new Map();for(const row of rawAlerts){const old=best.get(row.id),value=numeric(row.ev)?row.ev:-Infinity,previous=numeric(old?.ev)?old.ev:-Infinity;if(!old||value>previous||(value===previous&&(row.odds??-Infinity)>(old.odds??-Infinity))||(value===previous&&row.odds===old.odds&&row.book>old.book))best.set(row.id,row);}alerts=[...best.values()];
  }
  const summary=summarizeFootballAlerts(alerts);
  const coverage={events:events.length,contextEvents,quoteGroups:ordered.length,conditionGroups:baseGroups,matchedGroups:rawAlerts.length,alerts:alerts.length,priced:alerts.filter(r=>positiveOdds(r.odds)).length,probability:alerts.filter(r=>probability(r.probability)).length,valued:alerts.filter(r=>numeric(r.ev)).length,settled:alerts.filter(r=>r.won!==null).length,missingQuote:alerts.filter(r=>r.statuses.includes('market_quote_missing')).length,missingProbability:alerts.filter(r=>!probability(r.probability)).length,missingConditionValues,playerHistoryMissing:alerts.filter(r=>r.statuses.some(s=>s==='player_history_missing'||s==='player_membership_missing')).length,universe:options.universe||null};
  return {alerts,summary,coverage};
}
