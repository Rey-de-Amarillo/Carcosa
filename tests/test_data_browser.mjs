/** Archive filters preserve price phase, raw identity and unknown activity. */
import assert from 'node:assert/strict';
import {filterArchiveOffers} from '../app/football-data-browser.js';
const rows=[
 {quoteId:'a',date:'2026-10-01',league:'E0',book:'B365',market:'match_result',phase:'pre_closing',odds:2.5,active:true},
 {quoteId:'b',date:'2026-10-02',league:'E0',book:'B365',market:'match_result',phase:'closing',odds:2.2,active:false},
 {quoteId:'c',date:'2026-10-03',league:'ARG1',book:'SGP',market:'btts',phase:'opening_archive_timestamp_unknown',odds:1.8,active:null},
 {quoteId:'d',date:'2026-10-04',league:'ARG1',book:'BFE-LTP',market:'betfair:ANYTIME_SCORE',phase:'historical_timestamp',odds:4.5,active:undefined,priceType:'last_traded_price',playerId:'runner-original'},
 {quoteId:'e',date:'2026-10-05',league:'E0',book:'B365',market:'match_result',phase:'pre_closing',odds:null,active:true,suspended:true},
].map(Object.freeze);
Object.freeze(rows);
const leagueName=id=>({E0:'Premier League',ARG1:'Liga Profesional Argentina'})[id]||id;
const ids=options=>filterArchiveOffers(rows,options,leagueName).map(row=>row.quoteId);
assert.deepEqual(ids({}),['e','d','c','b','a']);
assert.deepEqual(ids({book:'B365',market:'match_result',phase:'pre_closing'}),['e','a'],'closing prices never leak into the pre-closing view');
assert.deepEqual(ids({league:'argentina'}),['d','c'],'free-text league search matches the recorded league name');
assert.deepEqual(ids({league:'e0'}),['e','b','a']);
assert.deepEqual(ids({active:'active'}),['a'],'unknown activity and suspended quotes never become active');
assert.deepEqual(ids({active:'inactive'}),['e','b']);
assert.deepEqual(ids({sort:'odds_desc'}),['d','a','b','c','e'],'missing prices remain last');
assert.deepEqual(ids({sort:'odds_asc'}),['c','b','a','d','e']);
assert.deepEqual(ids({sort:'date_asc'}),['a','b','c','d','e']);
assert.deepEqual(ids({minOdds:'2.2',maxOdds:'2.5'}),['b','a'],'numeric boundaries remain inclusive at source precision');
assert.deepEqual(ids({minOdds:'',maxOdds:'   '}),['e','d','c','b','a'],'empty filters do not fabricate numeric thresholds');
assert.deepEqual(ids({phase:'historical_timestamp'}),['d'],'research price updates remain individual observations');
assert.equal(filterArchiveOffers(rows,{phase:'historical_timestamp'})[0],rows[3],'raw research labels, player IDs and LTP quality are retained');
assert.equal(rows[3].priceType,'last_traded_price');assert.equal(rows[3].playerId,'runner-original');
assert.equal(Object.hasOwn(rows[3],'capturedAt'),false,'the browser never fabricates a capture from a date');
assert.deepEqual(rows.map(row=>row.quoteId),['a','b','c','d','e'],'filtering never mutates cached archive order');
console.log('Data browser: bounded-view filters, exact phases, unknown activity, missing-price order and preserved research identity passed.');
