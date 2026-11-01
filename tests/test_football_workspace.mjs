/** Cross-check the publishable data, expression engine, and original Python ledger. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
import {DEFAULT_EXPRESSION,matchAndRank,summarize} from '../app/formula-engine.js';
import {DEFAULT_FORMULA,formulaFromConditions} from '../app/formula-builder.js';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const data=join(root,'app/data');
const manifest=JSON.parse(readFileSync(join(data,'workspace.json')));
function readTable(meta){
  const bytes=readFileSync(join(data,meta.path));
  assert.ok(bytes.length<25*1024*1024,meta.path+' exceeds static file limit');
  assert.equal(createHash('sha256').update(bytes).digest('hex'),meta.sha256);
  const table=JSON.parse(gunzipSync(bytes));
  assert.equal(table.rows.length,meta.rows);
  return table.rows.map(raw=>Object.fromEntries(table.columns.map((key,i)=>[key,raw[i]])));
}
const events=readTable(manifest.tables.events),offers=[];
for(const part of manifest.tables.offers.parts){
  for(const raw of readTable(part)){
    const event=events[raw.event];
    assert.ok(event,'foreign event index');
    assert.equal(event.date.slice(0,4),String(part.year));
    assert.ok(raw.references.length>=3);
    assert.ok(!raw.references.includes(raw.book));
    if(event.date>='2025-07-23')assert.ok(raw.book!=='PS'&&!raw.references.includes('PS'));
    offers.push({...raw,id:event.id,date:event.date,referenceMean:raw.reference_mean,referenceSd:raw.reference_sd});
  }
}
assert.equal(offers.length,manifest.counts.offers);
assert.equal(events.length,manifest.counts.events);
const builderExpression=formulaFromConditions(DEFAULT_FORMULA);
assert.equal(builderExpression,DEFAULT_EXPRESSION);
const selected=matchAndRank(offers,builderExpression);
const original=readFileSync(join(root,'data/analysis/research_robust_reference_ev.trades.jsonl'),'utf8').trim().split('\n').map(JSON.parse).filter(r=>['validation_all_books_minimum','test_all_books_minimum'].includes(r.scenario));
const key=r=>`${r.id}|${r.book}|${r.side}`;
const expected=new Map(original.map(r=>[key(r),r]));
assert.equal(selected.length,295);
for(const row of selected){
  const reference=expected.get(key(row));assert.ok(reference,'selection absent in original research ledger');
  for(const field of ['odds','probability','ev','won'])assert.equal(row[field],reference[field],field);
  assert.deepEqual(row.references,reference.references);
}
const all=summarize(selected),test=summarize(selected.filter(r=>r.date>='2022-01-01'));
assert.equal(test.n,76);assert.equal(test.wins,39);
assert.ok(Math.abs(test.profit-12.78)<1e-10);
assert.ok(Math.abs(test.roi-0.1681578947368421)<1e-12);
assert.ok(Math.abs(all.profit-35.16)<1e-10);
assert.ok(Math.abs(all.roi-0.1191864406779661)<1e-12);
console.log(`Workspace verified: ${events.length} events, ${offers.length} offers, 295 exact ledger matches; test76 ROI ${(test.roi*100).toFixed(4)}%.`);
