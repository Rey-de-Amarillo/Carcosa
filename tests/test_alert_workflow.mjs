/** Integration across real entity catalogue, archived market quotes and saved alerts. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {defaultScoreAlert,loadStrategies,saveStrategies,STRATEGY_STORAGE_KEY} from '../app/strategy-store.js';
import {evaluateFootballStrategy,summarizeFootballAlerts} from '../app/football-strategy-engine.js';
import {normalizeFootballAlert,calculateManualPreview} from '../app/football-alert-builder.js';
import {FootballData} from '../app/workspace-data.js';
const entities=JSON.parse(readFileSync(new URL('../app/data/entities.json',import.meta.url)));
const source=JSON.parse(gunzipSync(readFileSync(new URL('../app/data/football-market-history.json.gz',import.meta.url))));
const rule=defaultScoreAlert();
const route=new FootballData();assert.equal(route.usesGoalArchive(rule),route.usesGoalArchive({...rule,action:{...rule.action,oddsSource:'manual',odds:8}}));
const result=evaluateFootballStrategy(source,rule,{entities});
assert.equal(result.alerts.length,52);assert.equal(result.summary.priced,52);assert.equal(result.summary.settled,51);assert.equal(result.summary.wins,6);
assert.ok(Math.abs(result.summary.profit-(-6.5))<1e-9);
assert.ok(Math.abs(result.summary.roi-(-6.5/51))<1e-12);
assert.equal(result.summary.expectedPriced,21);
for(const row of result.alerts){
 const event=source.events[row.event];
 assert.ok(event.marketQuotes.some(q=>q.book===row.book&&q.market==='correct_score'&&q.period==='full'&&q.homeGoals===2&&q.awayGoals===1&&q.odds===row.odds));
 if(row.won==null)assert.equal(row.profit,null);
}
const late=result.alerts.filter(r=>r.date>='2026-09-01');assert.equal(summarizeFootballAlerts(late).n,late.length);
const gapResult=evaluateFootballStrategy(source,{...rule,conditions:[...rule.conditions,{field:'return_gap',operator:'between',min:-2.3,max:-1.9}]},{entities});
assert.ok(gapResult.alerts.length>0);for(const r of gapResult.alerts)assert.ok(Math.abs(r.contextValues.return_gap-(r.contextOdds.home-r.contextOdds.away))<1e-12);
const values=new Map(),storage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};
const initial=loadStrategies(storage);assert.ok(initial.some(r=>r.kind==='market-ev'));
const persisted=saveStrategies(initial,entities,storage);assert.ok(values.has(STRATEGY_STORAGE_KEY));assert.equal(loadStrategies(storage).length,persisted.length);
const teams=entities.teams.filter(t=>t.playerIds.length&&t.currentLeagueIds?.includes('E0'));
const player=entities.players.find(p=>p.teamId===teams[0].id);
assert.throws(()=>normalizeFootballAlert({...rule,context:{league:'E0',homeTeam:teams[0].id,awayTeam:teams[1].id},action:{...rule.action,market:'player_goals',team:'away',teamId:teams[1].id,playerId:player.id,selection:'at_least',line:1}},entities));
const combo={...rule,conditions:[],action:{...rule.action,market:'combination',legs:[{market:'total_goals',period:'full',selection:'over',line:2},{market:'match_result',period:'full',selection:'home'}],oddsSource:'manual',odds:4,probabilitySource:'manual',probability:.3}};
const comboResult=evaluateFootballStrategy(source,combo,{entities});assert.ok(comboResult.alerts.length);assert.equal(comboResult.alerts[0].ev,null);assert.equal(comboResult.alerts[0].breakEven,null);assert.ok(comboResult.alerts[0].statuses.includes('combination_void_rules_missing'));
const preview=calculateManualPreview({...rule,action:{...rule.action,oddsSource:'manual',odds:4,probabilitySource:'manual',probability:.3,stake:10}});
assert.ok(Math.abs(preview.ev-.2)<1e-12);assert.ok(Math.abs(preview.expectedProfit-2)<1e-12);assert.equal(preview.profitIfWin,30);
console.log(`Alert workflow verified: ${result.alerts.length} signals, ${result.summary.settled} settled, ${result.summary.expectedPriced} prior-only estimates, target-market quotes, team/player guards and legacy storage.`);
