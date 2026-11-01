/** Football contracts named after bet365's public football market and rules pages.
 * These are authoring choices, not a claim that a fixture has an archived price.
 * A market's exact period, line, player and settlement rules remain its identity.
 */
const ALL_PERIODS = Object.freeze(['full','first_half','second_half']);
const FULL = Object.freeze(['full']);
const entry = (id,name,group,kind,defaultSelection,defaultLine=null,teamScope=null,periods=ALL_PERIODS) =>
  Object.freeze({id,name,group,kind,defaultSelection,defaultLine,teamScope,periods});

export const FOOTBALL_MARKET_SOURCES = Object.freeze([
  Object.freeze({name:'bet365 · Mercados de fútbol',url:'https://help.bet365.com/s/en-bg/sports/football-betting-markets'}),
  Object.freeze({name:'bet365 · Resultado, eventos y descanso',url:'https://help.bet365.com/s/es/sportsrules/soccer/result-event-half-time'}),
  Object.freeze({name:'bet365 · Goles y hándicap de tres opciones',url:'https://help.bet365.com/s/es/sportsrules/soccer/goalscoring-markets'}),
  Object.freeze({name:'bet365 · Mercados de equipo',url:'https://help.bet365.com/s/es/sportsrules/soccer/team-markets'}),
  Object.freeze({name:'bet365 · Estadísticas de partido, equipo y jugador',url:'https://help.bet365.com/s/en/sportsrules/soccer/match-statistics'}),
  Object.freeze({name:'bet365 · Mercados del Crea tu apuesta',url:'https://news.bet365.com/en-gb/article/bet-builder-guide/2024082615115616537'}),
]);

/** Only actual single-market choices belong here. Combining selections is an
 * editor action, never another football outcome in the market dropdown.
 */
export const FOOTBALL_MARKET_CATALOG = Object.freeze([
  entry('match_result','Resultado final (1X2)','Resultado','result','home'),
  entry('double_chance','Doble oportunidad','Resultado','double_chance','home_draw'),
  entry('draw_no_bet','Empate, apuesta no válida','Resultado','team_result','home'),
  entry('handicap_result','Hándicap (3 opciones)','Resultado','handicap_result','home',-1),
  entry('asian_handicap','Hándicap asiático','Resultado','asian_handicap','home',0),
  entry('half_time_full_time','Descanso / Final','Resultado','htft','home_home',null,null,FULL),
  entry('correct_score','Marcador exacto','Goles','score',''),
  entry('total_goals','Total de goles','Goles','count','over',2.5,'match'),
  entry('team_goals','Goles del equipo','Goles','count','over',1.5,'team'),
  entry('btts','Ambos equipos marcarán','Goles','yes_no','yes'),
  entry('result_btts','Resultado / Ambos equipos marcarán','Goles','result_btts','home_yes'),
  entry('team_to_score','Equipo anotará','Goles','team_yes_no','yes',null,'team'),
  entry('clean_sheet','Equipo mantendrá su portería a cero','Goles','team_yes_no','yes',null,'team'),
  entry('win_to_nil','Equipo ganará a cero','Goles','team_yes_no','yes',null,'team'),
  entry('odd_even','Goles: impar / par','Goles','odd_even','odd',null,'both'),
  entry('first_team_to_score','Primer equipo en marcar','Goles','first_last_team','home',null,null,FULL),
  entry('last_team_to_score','Último equipo en marcar','Goles','first_last_team','home',null,null,FULL),
  entry('corners','Córners','Córners y tarjetas','count','over',9.5,'both'),
  entry('cards','Tarjetas','Córners y tarjetas','count','over',3.5,'both'),
  entry('shots','Remates','Estadísticas','count','over',19.5,'both',FULL),
  entry('shots_on_target','Remates al arco','Estadísticas','count','over',7.5,'both',FULL),
  entry('offsides','Fuera de juego','Estadísticas','count','over',3.5,'both',FULL),
  entry('player_goals','Jugador anotará','Jugadores','player_count','at_least',1,'team',FULL),
  entry('first_goalscorer','Primer goleador','Jugadores','player_scorer','player',null,'team',FULL),
  entry('last_goalscorer','Último goleador','Jugadores','player_scorer','player',null,'team',FULL),
  entry('player_shots','Remates del jugador','Jugadores','player_count','over',1.5,'team',FULL),
  entry('player_shots_on_target','Remates al arco del jugador','Jugadores','player_count','over',.5,'team',FULL),
  entry('player_assists','Asistencias del jugador','Jugadores','player_count','at_least',1,'team',FULL),
]);

const byId = new Map(FOOTBALL_MARKET_CATALOG.map(market=>[market.id,market]));
export const marketDefinition = id => byId.get(id) || null;
const resultChoices = (home,away) => [['home',`Gana ${home}`],['draw','Empate'],['away',`Gana ${away}`]];

export function marketSelectionChoices(id,{home='Local',away='Visitante'}={}) {
  const market=marketDefinition(id);
  if(!market)return [];
  if(['result','handicap_result'].includes(market.kind))return resultChoices(home,away);
  if(['team_result','asian_handicap'].includes(market.kind))return [['home',home],['away',away]];
  if(market.kind==='double_chance')return [
    ['home_draw',`${home} o empate (1X)`],['draw_away',`Empate o ${away} (X2)`],['home_away',`${home} o ${away} (12)`],
  ];
  if(market.kind==='htft'){
    const sides=[['home',home],['draw','Empate'],['away',away]];
    return sides.flatMap(([first,firstLabel])=>sides.map(([last,lastLabel])=>[`${first}_${last}`,`${firstLabel} / ${lastLabel}`]));
  }
  if(['yes_no','team_yes_no'].includes(market.kind))return [['yes','Sí'],['no','No']];
  if(market.kind==='result_btts')return resultChoices(home,away).flatMap(([side,label])=>[
    [`${side}_yes`,`${label} y ambos marcan`],[`${side}_no`,`${label} y no marcan ambos`],
  ]);
  if(market.kind==='odd_even')return [['odd','Impar'],['even','Par']];
  if(market.kind==='first_last_team')return [['home',home],['away',away],['none','Ningún equipo']];
  if(market.kind==='count')return [['over','Más de'],['under','Menos de'],['exact','Exactamente'],['at_least','Al menos']];
  if(market.kind==='player_count')return [
    ['at_least',id==='player_goals'?'Anotará':id==='player_assists'?'Dará una asistencia':'Al menos'],
    ['over','Más de'],['under','Menos de'],['exact','Exactamente'],
  ];
  return [];
}

/** Common quoted lines, rather than an unrestricted numeric input. A saved line
 * outside this list must be appended by the editor so editing stays lossless.
 * Quarter handicaps are omitted until split-stake returns are supported.
 */
export function marketLineChoices(id,selection) {
  const market=marketDefinition(id);
  if(!market)return [];
  if(market.kind==='handicap_result')return Array.from({length:11},(_,index)=>index-5);
  if(market.kind==='asian_handicap')return Array.from({length:21},(_,index)=>(index-10)/2);
  if(!['count','player_count'].includes(market.kind))return [];
  const chosen=selection||market.defaultSelection,whole=['exact','at_least'].includes(chosen);
  if(id==='player_goals'&&chosen==='at_least')return [1,2,3];
  const max=({corners:25,cards:15,shots:50,shots_on_target:25,offsides:15,player_shots:15,player_shots_on_target:10,player_assists:5})[id]||10;
  return Array.from({length:max},(_,index)=>whole?index+(chosen==='at_least'?1:0):index+.5);
}

export function defaultMarketSelection(id='match_result') {
  const market=marketDefinition(id);
  if(!market)throw new Error('Elegí un mercado de fútbol válido.');
  return {
    market:id,period:'full',selection:market.defaultSelection,
    team:market.teamScope==='both'||market.teamScope==='match'?'total':'home',
    teamId:'',playerId:'',line:market.defaultLine,
    homeGoals:market.kind==='score'?1:null,awayGoals:market.kind==='score'?0:null,
  };
}

const quantityLabel = action => action.selection==='exact'?`exactamente ${action.line}`:
  action.selection==='at_least'?`${action.line} o más`:
  `${action.selection==='under'?'menos de':'más de'} ${action.line}`;
const signed = value => Number(value)>0?`+${value}`:String(value??'');

export function footballMarketLabel(action={}, {home='Local',away='Visitante',player='Jugador'}={}) {
  const definition=marketDefinition(action.market);
  if(action.market==='combination')return (action.legs||[]).map(leg=>footballMarketLabel(leg,{home,away,player})).join(' + ');
  if(!definition)return 'Seleccionar mercado';
  const actor=action.team==='away'?away:action.team==='total'?'Partido':home;
  const yes=action.selection==='yes'?'Sí':'No';
  let label;
  if(definition.kind==='score')label=`${home} ${action.homeGoals??'–'}–${action.awayGoals??'–'} ${away}`;
  else if(definition.kind==='asian_handicap')label=`${action.selection==='away'?away:home} · Hándicap asiático ${signed(action.line)}`;
  else if(definition.kind==='handicap_result')label=`${marketSelectionChoices(action.market,{home,away}).find(([value])=>value===action.selection)?.[1]||''} · Hándicap ${home} ${signed(action.line)}`;
  else if(definition.kind==='htft')label=`Descanso / Final · ${marketSelectionChoices(action.market,{home,away}).find(([value])=>value===action.selection)?.[1]||''}`;
  else if(definition.kind==='yes_no')label=`Ambos marcan: ${yes.toLowerCase()}`;
  else if(definition.kind==='team_yes_no')label=`${actor} · ${action.market==='team_to_score'?'Anotará':action.market==='clean_sheet'?'Portería a cero':'Ganará a cero'}: ${yes.toLowerCase()}`;
  else if(definition.kind==='odd_even')label=`${actor} · Goles: ${action.selection==='even'?'par':'impar'}`;
  else if(definition.kind==='first_last_team')label=`${action.market==='first_team_to_score'?'Primer':'Último'} equipo en marcar · ${marketSelectionChoices(action.market,{home,away}).find(([value])=>value===action.selection)?.[1]||''}`;
  else if(definition.kind==='player_scorer')label=`${player} · ${definition.name.toLowerCase()}`;
  else if(definition.kind==='count'||definition.kind==='player_count'){
    const subject=action.market.includes('shots_on_target')?'remates al arco':action.market.includes('shots')?'remates':action.market==='cards'?'tarjetas':action.market==='corners'?'córners':action.market==='offsides'?'fueras de juego':action.market==='player_assists'?'asistencias':'goles';
    const person=definition.kind==='player_count'?player:actor;
    label=action.market==='player_goals'&&action.selection==='at_least'&&action.line===1?`${player} · Anotará en cualquier momento`:
      `${person} · ${quantityLabel(action)} ${subject}`;
  }else {
    label=marketSelectionChoices(action.market,{home,away}).find(([value])=>value===action.selection)?.[1]||definition.name;
    if(action.market==='draw_no_bet')label+=' · Empate, apuesta no válida';
  }
  return label+(action.period==='first_half'?' · Primer tiempo':action.period==='second_half'?' · Segundo tiempo':'');
}
