/** Verify that the app actually ships the canonical UI, not a restyled imitation. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=dirname(dirname(fileURLToPath(import.meta.url))),vendor=join(root,'app/vendor/workraken');
const manifest=JSON.parse(readFileSync(join(vendor,'provenance.json')));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
for(const item of manifest.files){
 const bytes=readFileSync(join(vendor,item.path));assert.equal(hash(bytes),item.sha256,item.path);
 if(item.url_roots_relocated){const original=bytes.toString().replaceAll('/vendor/workraken/static/','/static/').replaceAll('/vendor/workraken/assets/','/assets/');assert.equal(hash(original),item.source_sha256,item.path+' declarations changed');}
 else assert.equal(item.sha256,item.source_sha256,item.path+' is not an exact source copy');
}
const html=readFileSync(join(root,'app/index.html'),'utf8');
assert.ok(!/<textarea\b/i.test(html));
const details=[...html.matchAll(/<details\b([^>]*)>/gi)];assert.equal(details.length,9);
for(const [,attributes]of details){assert.ok(attributes.includes('panel table-panel collapsible-panel'));assert.ok(!/\sopen(?:\s|=|$)/.test(attributes),'mother panel defaults open');}
let previous=-1;
for(const path of manifest.css_order){const index=html.indexOf('vendor/workraken/'+path);assert.ok(index>previous,'stylesheet order');previous=index;}
for(const path of ['search.js','date-picker.js','single-select.js','floating-dropdowns.js'])assert.ok(manifest.files.some(f=>f.path===path));
const js=readFileSync(join(root,'app/app.js'),'utf8');
for(const token of ['record-pagination-controls','record-page-size-select','record-page-picker','record-page-select','record-page-button','expandable-filter-search is-expanded'])assert.ok(js.includes(token),token);
assert.ok(js.includes('initExpandableFilterSearch('));assert.ok(js.includes('initCommonSimpleSelects('));
console.log(`Exact Workraken UI verified: ${manifest.files.length} source assets, canonical stylesheet order, closed panels, original search/select/calendar controllers.`);
