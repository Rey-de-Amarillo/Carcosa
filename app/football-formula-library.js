/** Editable criteria over real football contracts, never generated bet signals. */
import {defaultMarketSelection,FOOTBALL_MARKET_CATALOG,footballMarketLabel} from './football-market-catalog.js';
import {normalizeUnifiedFormula,UNIFIED_FORMULA_KIND} from './football-unified-formula.js';
import {STRATEGY_STORAGE_KEY} from './strategy-store.js';

export const FORMULA_LIBRARY_COUNT=120;
const clone=value=>JSON.parse(JSON.stringify(value));
const pad=value=>String(value).padStart(3,'0');
const decimal=value=>value.toLocaleString('es-AR',{minimumFractionDigits:2,maximumFractionDigits:2});

export function buildFootballFormulaLibrary(entities){
  let sequence=0;const formulas=[];
  const id=prefix=>`${prefix}-${++sequence}`;
  const group=(operator,...children)=>({type:'group',id:id('group'),operator,children});
  const value=(field,v)=>({type:'condition',id:id('condition'),field,operator:'=',value:v});
  const price=(min,max)=>({type:'condition',id:id('condition'),field:'odds',operator:'between',min,max});
  const market=(name,overrides={},playerRef)=>({type:'condition',id:id('condition'),field:'market',operator:'=',selection:{...defaultMarketSelection(name),...overrides},...(playerRef?{playerRef}:{} )});
  const player=p=>({type:'condition',id:id('condition'),field:'player',operator:'=',playerId:p.id,teamId:p.teamId});
  const add=(name,expression)=>{
    const number=pad(formulas.length+1);
    formulas.push(normalizeUnifiedFormula({kind:UNIFIED_FORMULA_KIND,version:1,id:`library-football-${number}`,name:`${number} · ${name}`,stake:1,expression},entities));
  };
  const range=(min,max)=>`cuota ${decimal(min)}–${decimal(max)}`;
  const selectionName=a=>footballMarketLabel(a,{home:'Local',away:'Visitante',player:'Jugador'});

  // 40 general recipes: all 22 non-player markets and 18 other contracts.
  const general=FOOTBALL_MARKET_CATALOG.filter(m=>m.group!=='Jugadores').map(m=>({name:m.id,overrides:{},min:1.5,max:3.5}));
  general.push(
    {name:'match_result',overrides:{selection:'draw'},min:2.8,max:4.5},
    {name:'match_result',overrides:{selection:'away'},min:1.8,max:3.2},
    {name:'double_chance',overrides:{selection:'draw_away'},min:1.3,max:2},
    {name:'double_chance',overrides:{selection:'home_away'},min:1.15,max:1.6},
    {name:'draw_no_bet',overrides:{selection:'away'},min:1.6,max:2.8},
    {name:'handicap_result',overrides:{selection:'away',line:1},min:1.7,max:3.5},
    {name:'asian_handicap',overrides:{selection:'away',line:.5},min:1.6,max:2.5},
    {name:'half_time_full_time',overrides:{selection:'draw_home'},min:3.5,max:7},
    {name:'half_time_full_time',overrides:{selection:'away_away'},min:2.5,max:6},
    {name:'correct_score',overrides:{homeGoals:1,awayGoals:0},min:4,max:12},
    {name:'correct_score',overrides:{homeGoals:1,awayGoals:1},min:4,max:10},
    {name:'total_goals',overrides:{selection:'under',line:2.5},min:1.6,max:2.5},
    {name:'total_goals',overrides:{selection:'over',line:3.5},min:2,max:3.5},
    {name:'total_goals',overrides:{selection:'over',line:.5,period:'first_half'},min:1.3,max:1.9},
    {name:'team_goals',overrides:{team:'away',selection:'over',line:1.5},min:1.8,max:3},
    {name:'btts',overrides:{selection:'no'},min:1.7,max:2.5},
    {name:'corners',overrides:{selection:'under',line:10.5},min:1.6,max:2.4},
    {name:'cards',overrides:{selection:'under',line:4.5},min:1.6,max:2.5},
  );
  for(const recipe of general){const bet=market(recipe.name,recipe.overrides);add(`${selectionName(bet.selection)} · ${range(recipe.min,recipe.max)}`,group('Y',bet,price(recipe.min,recipe.max)));}

  // 24 team recipes. Role and quoted selection always agree.
  const preferred=['Boca Juniors','River Plate','Arsenal','Liverpool','Man City','Real Madrid','Barcelona','Bayern Munich','Inter','Juventus','Chelsea','Tottenham'];
  const teams=preferred.map(name=>entities.teams.find(t=>t.name===name)).filter(Boolean);
  for(const team of entities.teams)if(teams.length<12&&!teams.some(t=>t.id===team.id)&&team.leagueIds?.length)teams.push(team);
  if(teams.length!==12)throw new Error('Faltan equipos para crear las 120 fórmulas.');
  for(const team of teams){
    add(`${team.name} local gana · ${range(1.5,2.75)}`,group('Y',value('home_team',team.id),market('match_result',{selection:'home'}),price(1.5,2.75)));
    add(`${team.name} visitante · empate no válido O X2`,group('Y',value('away_team',team.id),group('O',market('draw_no_bet',{selection:'away'}),market('double_chance',{selection:'draw_away'})),price(1.6,3)));
  }

  // 24 player recipes use verified catalog identities and explicit references.
  const playerIds=['player:espn:260812','player:fpl:223094','player:espn:231388','player:espn:219713'];
  const players=playerIds.map(key=>entities.players.find(p=>p.id===key));
  if(players.some(p=>!p))throw new Error('Faltan jugadores para crear las 120 fórmulas.');
  const bounds={player_goals:[1.7,4],first_goalscorer:[3,15],last_goalscorer:[3,15],player_shots:[1.4,2.6],player_shots_on_target:[1.5,3],player_assists:[2,12]};
  for(const person of players)for(const definition of FOOTBALL_MARKET_CATALOG.filter(m=>m.group==='Jugadores')){
    const who=player(person),bet=market(definition.id,{playerId:person.id,teamId:person.teamId,team:'selected'},who.id),[min,max]=bounds[definition.id];
    const label=footballMarketLabel(bet.selection,{player:person.name});
    add(`${label} · ${range(min,max)}`,group('Y',value('team',person.teamId),who,bet,price(min,max)));
  }

  // 16 leagues keep their own actual identity; no synthetic leagues are added.
  const leagueRecipes=[
    ['total_goals',{selection:'over',line:2.5},1.5,2.5],
    ['btts',{selection:'yes'},1.8,3.2],
    ['corners',{selection:'over',line:8.5},1.6,2.7],
    ['match_result',{selection:'draw'},2.7,4.5],
  ];
  if(entities.leagues.length<16)throw new Error('Faltan ligas para crear las 120 fórmulas.');
  entities.leagues.slice(0,16).forEach((league,index)=>{
    const [name,overrides,min,max]=leagueRecipes[index%leagueRecipes.length],bet=market(name,overrides);
    add(`${league.name} · ${selectionName(bet.selection)}`,group('Y',value('league',league.id),bet,price(min,max)));
  });

  // 16 nested OR recipes: each branch owns its contract and price criteria.
  const alternatives=[
    [['total_goals',{line:2.5},1.7,2.4],['btts',{selection:'yes'},1.8,2.8]],
    [['total_goals',{selection:'under',line:2.5},1.7,2.4],['btts',{selection:'no'},1.8,2.8]],
    [['match_result',{selection:'home'},1.8,2.6],['match_result',{selection:'draw'},3,4.2]],
    [['match_result',{selection:'away'},2,3.3],['double_chance',{selection:'draw_away'},1.4,2]],
    [['corners',{selection:'over',line:9.5},1.7,2.4],['cards',{selection:'over',line:3.5},1.7,2.6]],
    [['shots',{selection:'over',line:19.5},1.7,2.5],['shots_on_target',{selection:'over',line:7.5},1.8,2.8]],
    [['total_goals',{selection:'over',line:.5,period:'first_half'},1.4,2],['total_goals',{selection:'over',line:1.5,period:'second_half'},1.7,2.8]],
    [['correct_score',{homeGoals:2,awayGoals:1},6,14],['correct_score',{homeGoals:1,awayGoals:2},7,16]],
  ];
  for(const pair of alternatives){
    const branches=pair.map(([name,overrides,min,max])=>{const bet=market(name,overrides);return {bet,expression:group('Y',bet,price(min,max))};});
    add(`${selectionName(branches[0].bet.selection)} O ${selectionName(branches[1].bet.selection)}`,group('O',...branches.map(b=>b.expression)));
  }
  for(let index=0;index<8;index++){
    const a=teams[index],b=teams[(index+1)%teams.length];
    add(`${a.name} local O ${b.name} visitante`,group('O',
      group('Y',value('home_team',a.id),market('match_result',{selection:'home'}),price(1.7,3)),
      group('Y',value('away_team',b.id),market('draw_no_bet',{selection:'away'}),price(1.5,2.7)),
    ));
  }
  if(formulas.length!==FORMULA_LIBRARY_COUNT)throw new Error('La biblioteca debe contener exactamente 120 fórmulas.');
  return formulas;
}

/** Add only missing recipes, preserving every existing rule and user edit. */
export function seedFormulaLibrary(existing,entities,storage=globalThis.localStorage){
  const present=new Set(existing.map(f=>f.id));
  if(Array.from({length:FORMULA_LIBRARY_COUNT},(_,i)=>`library-football-${pad(i+1)}`).every(key=>present.has(key)))return existing;
  const additions=buildFootballFormulaLibrary(entities).filter(f=>!present.has(f.id));
  const merged=[...existing,...clone(additions)];
  storage.setItem(STRATEGY_STORAGE_KEY,JSON.stringify(merged));
  return merged;
}
