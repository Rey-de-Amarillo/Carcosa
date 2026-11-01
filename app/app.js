import {FIELD_DICTIONARY,matchAndRank,summarize} from './formula-engine.js';
import {mountFootballAlertBuilder,ALERT_SIGNALS,ALERT_MARKETS,footballSelectionLabel} from './football-alert-builder.js';
import {loadStrategies,saveStrategies} from './strategy-store.js';
import {evaluateFootballStrategy,summarizeFootballAlerts} from './football-strategy-engine.js';
import {initEntityPresentation} from './entity-presentation.js';
import {FootballData,periodMatches} from './workspace-data.js';
import {UNIFIED_FORMULA_KIND,formatUnifiedFormula,evaluateUnifiedFormula} from './football-unified-formula.js';
import {seedFormulaLibrary} from './football-formula-library.js';
import {initExpandableFilterSearch,filterSearchMatches} from './vendor/workraken/search.js';
import {initDatePicker} from './vendor/workraken/date-picker.js';
import {initCommonSimpleSelects} from './vendor/workraken/single-select.js';
import {initFloatingDropdowns} from './vendor/workraken/floating-dropdowns.js';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(n,d=2)=>n==null||!Number.isFinite(n)?'—':n.toLocaleString('es-AR',{minimumFractionDigits:d,maximumFractionDigits:d});
const signed=n=>n==null?'—':`${n>0?'+':''}${num(n)}`;
const pct=(n,sign=false)=>n==null?'—':`${sign?signed(n*100):num(n*100)}%`;
const date=s=>s?s.split('-').reverse().join('/'):'—';
const cls=n=>n>0?'football-positive':n<0?'football-negative':'';
const pair=(e,a,b)=>e[a]==null||e[b]==null?'—':`${e[a]}–${e[b]}`;
const data=new FootballData();let ready=false,formulas=loadStrategies(),builder,active=formulas[0].id,selected=[],appliedFormula=formulas[0],tradeToken=0,offerToken=0,messageTimer,currentSummary,alertByKey=new Map(),goalToken=0,entityPresentation=null;
const tables={};
function notify(text){$('message').textContent=text;$('message').hidden=false;clearTimeout(messageTimer);messageTimer=setTimeout(()=>$('message').hidden=true,2800);}
function searchHTML(id,label,placeholder){return `<div class="expandable-filter-search is-expanded" data-filter-search data-filter-search-always-expanded role="search" aria-label="Buscar ${label}"><button class="expandable-filter-search-toggle" type="button" data-filter-search-toggle aria-label="Buscar ${label}" aria-expanded="true" aria-controls="${id}-search" title="Buscar ${label}"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m15.5 15.5 4.5 4.5"/></svg></button><span class="expandable-filter-search-field"><input id="${id}-search" type="search" data-filter-search-input aria-label="Buscar ${label}" aria-hidden="false" autocomplete="off" placeholder="${placeholder}" tabindex="0"><button class="expandable-filter-search-clear" type="button" data-filter-search-clear aria-label="Limpiar búsqueda de ${label}" title="Limpiar búsqueda" hidden><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m7 7 10 10"/><path d="m17 7-10 10"/></svg></button></span><span class="record-page-announcement" data-search-status role="status" aria-live="polite" aria-atomic="true"></span></div>`;}
// Markup retained from Workraken templates/_pagination.html. Domain callbacks only.
class Table {
  constructor(id,label,columns,render,searchText){
    Object.assign(this,{id,label,columns,renderRow:render,searchText,rows:[],filtered:[],page:1,pageSize:10,query:'',pageCount:0});
    $(`${id}-toolbar`).innerHTML=`<div class="record-pagination-controls"><label class="record-page-size-control"><span>Mostrar</span><select class="record-page-size-select" aria-label="Cantidad de ${label} por página" aria-controls="${id}-table">${[10,20,50,100,200].map(n=>`<option value="${n}">${n}</option>`).join('')}</select></label><span class="record-pagination" role="group" aria-label="Paginación de ${label}"><button class="mini-button record-page-button" type="button" data-prev hidden aria-label="Página anterior" title="Página anterior" aria-controls="${id}-table"><svg class="record-page-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m15 18-6-6 6-6"/></svg></button><label class="record-page-picker"><span>Página</span><select class="record-page-select" aria-label="Página de ${label}" aria-controls="${id}-table"><option value="1">1</option></select><span>de <span data-page-total>1</span></span></label><button class="mini-button record-page-button" type="button" data-next aria-label="Página siguiente" title="Página siguiente" aria-controls="${id}-table"><svg class="record-page-button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m9 18 6-6-6-6"/></svg></button><span class="record-page-announcement" data-page-status role="status" aria-live="polite" aria-atomic="true"></span></span></div>${searchHTML(id,label,id==='formulas'?'Nombre de la fórmula':'Equipo o partido')}`;
    this.root=$(`${id}-toolbar`);this.body=$(`${id}-table`).tBodies[0];
    this.size=this.root.querySelector('.record-page-size-select');this.picker=this.root.querySelector('.record-page-select');
    this.size.onchange=()=>{this.pageSize=Number(this.size.value);this.page=1;this.render();};
    this.picker.onchange=()=>{this.page=Number(this.picker.value);this.render();};
    this.root.querySelector('[data-prev]').onclick=()=>{this.page--;this.render();};this.root.querySelector('[data-next]').onclick=()=>{this.page++;this.render();};
    initExpandableFilterSearch(this.root.querySelector('[data-filter-search]'),{onSearch:query=>{this.query=query;this.page=1;clearTimeout(this.searchTimer);this.searchTimer=setTimeout(()=>this.filter(),160);}});
  }
  setRows(rows){this.busy=false;this.root.querySelectorAll('select,button,input').forEach(e=>e.disabled=false);this.rows=rows;this.page=1;this.filter();}
  filter(){if(this.busy)return;this.filtered=this.query?this.rows.filter(r=>filterSearchMatches(this.searchText(r),this.query)):this.rows;this.render();}
  loading(text='Cargando datos…'){this.busy=true;this.root.querySelectorAll('select,button,input').forEach(e=>e.disabled=true);this.body.innerHTML=`<tr><td colspan="${this.columns}"><div class="empty-state" role="status">${esc(text)}</div></td></tr>`;}
  render(){
    const total=this.filtered.length,pages=Math.max(1,Math.ceil(total/this.pageSize));this.page=Math.min(pages,Math.max(1,this.page));
    if(this.pageCount!==pages){this.picker.innerHTML=Array.from({length:pages},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join('');this.pageCount=pages;}
    this.picker.value=String(this.page);this.root.querySelector('[data-page-total]').textContent=num(pages,0);this.root.querySelector('[data-prev]').hidden=this.page===1;this.root.querySelector('[data-next]').hidden=this.page===pages;
    this.root.querySelector('[data-page-status]').textContent=`Página ${this.page} de ${pages}. ${total} ${this.label}.`;
    this.body.innerHTML=this.filtered.slice((this.page-1)*this.pageSize,this.page*this.pageSize).map(this.renderRow).join('')||`<tr><td colspan="${this.columns}"><div class="empty-state">No hay ${esc(this.label)} que coincidan con la búsqueda y los filtros.</div></td></tr>`;
    const count=$(`${this.id}-count`);if(count)count.textContent=`${num(total,0)} ${this.label}`;
  }
}
function scope(prefix){return {period:$(`${prefix}-period`).value,league:$(`${prefix}-league`).value,book:$(`${prefix}-book`).value};}
function offerMatches(r,s){return periodMatches(r,s.period)&&(!s.league||r.league===s.league)&&(!s.book||s.book.split('|').includes(r.book));}
const matchSearch=r=>[r.home,r.away,data.leagues?.get(r.league),r.book?data.books?.get(r.book):''];
const side=r=>r.side===0?'1 · '+r.home:r.side===1?'X · Empate':'2 · '+r.away;
function offerRow(r,stake=1){const e=data.events[r.event];return `<tr role="button" tabindex="0" data-trade="${r.event}|${esc(r.book)}|${r.side}" aria-label="Ver detalle de ${esc(r.home)} contra ${esc(r.away)}"><td>${date(r.date)}</td><td class="football-match">${matchHTML(r)}<span class="football-sub">${leagueHTML(r.league)}</span></td><td>${esc(side(r))}</td><td>${esc(data.books.get(r.book)||r.book)}</td><td data-number>${num(r.odds)}</td><td data-number>${pct(r.probability)}</td><td data-number class="${cls(r.ev)}">${pct(r.ev,true)}</td><td>${r.won?'Ganada':'Perdida'} · ${pair(e,'home_score','away_score')}</td><td data-number class="${cls(r.profit)}">${signed(r.profit*stake)} u</td></tr>`;}
const teamHTML=(name,league)=>entityPresentation?entityPresentation.teamHTML(name,league):esc(name);
const leagueHTML=id=>entityPresentation?entityPresentation.leagueHTML(id):esc(data.leagues?.get(id)||id);
const matchHTML=r=>`${teamHTML(r.home,r.league)} <span class="football-match-separator">—</span> ${teamHTML(r.away,r.league)}`;
function eventRow(e){return `<tr><td>${date(e.date)}</td><td>${teamHTML(e.home,e.league)}</td><td>${teamHTML(e.away,e.league)}</td><td>${leagueHTML(e.league)}</td>${[['home_score','away_score'],['home_ht_score','away_ht_score'],['home_corners','away_corners'],['home_shots','away_shots'],['home_shots_on_target','away_shots_on_target'],['home_yellow','away_yellow']].map(([a,b])=>`<td data-number>${pair(e,a,b)}</td>`).join('')}</tr>`;}
const stakeOf=f=>f.kind==='football-alert'?f.action.stake:f.stake;
function describeAction(action,context={}){return footballSelectionLabel(action,data.entities||{},context);}
function conditionLabel(condition){const signal=ALERT_SIGNALS.find(s=>s.id===condition.field),percent=signal?.unit==='percentage',value=v=>percent?pct(v):num(v),name=condition.selection?footballSelectionLabel(condition.selection,data.entities):signal?.name||condition.field;return `${name} ${condition.ui?.operator==='around'?value(condition.ui.value)+' ± '+value(condition.ui.margin):condition.operator==='between'?value(condition.min)+'–'+value(condition.max):condition.operator+' '+value(condition.value)}`;}
function formulaRow(f){const unified=f.kind===UNIFIED_FORMULA_KIND,domain=f.kind==='football-alert',trigger=unified?formatUnifiedFormula(f,data.entities||{}):domain?f.conditions.map(conditionLabel).join(' · '):'EV mínimo · referencias entre casas',bet=unified?'—':domain?describeAction(f.action,f.context):'Resultado 1X2 · mayor EV';return `<tr><td>${esc(f.name)}</td><td>${esc(trigger)}</td><td>${esc(bet)}</td><td>${num(stakeOf(f))} u</td><td><div class="football-row-actions"><button type="button" class="mini-button" data-use="${esc(f.id)}">Usar</button>${domain||unified?`<button type="button" class="mini-button" data-edit="${esc(f.id)}">Editar</button><button type="button" class="mini-button" data-duplicate="${esc(f.id)}">Duplicar</button>`:''}</div></td></tr>`;}
function refreshFormulaList(){tables.formulas.setRows(formulas);const value=$('trades-formula').value||active;$('trades-formula').innerHTML=formulas.map(f=>`<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('');$('trades-formula').value=formulas.some(f=>f.id===value)?value:formulas[0].id;}
function refreshEvents(){
  if(!ready)return;const from=$('events-from').value,to=$('events-to').value,league=$('events-league').value,result=$('events-result').value;
  const rows=data.events.filter(e=>(!from||e.date>=from)&&(!to||e.date<=to)&&(!league||e.league===league)&&(!result||Number(result)===(e.home_score>e.away_score?0:e.home_score===e.away_score?1:2))).sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id));
  tables.events.setRows(rows);$('events-export').disabled=false;
}
async function refreshOffers(){
  if(!ready)return;const token=++offerToken,s=scope('offers');tables.offers.loading('Cargando cuotas…');$('offers-export').disabled=true;
  try{await data.ensureOffers(s.period);if(token!==offerToken)return;const sideValue=$('offers-side').value;tables.offers.setRows(data.offers.filter(r=>offerMatches(r,s)&&(!sideValue||r.side===Number(sideValue))).sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id)||a.book.localeCompare(b.book)||a.side-b.side));$('offers-export').disabled=false;}catch(e){if(token===offerToken)tables.offers.loading(e.message);}
}
function metric(label,value,kind){return `<article class="kpi-card" ${kind?`data-availability-kpi="${kind}"`:''}><span data-kpi-label>${label}</span><strong data-kpi-value>${value}</strong></article>`;}
function setStrategyBooks(f){
  const old=$('trades-book').value,sg=f.kind==='football-alert'&&data.usesGoalArchive(f);
  const options=sg?[['SGP','Singapore Pools']]:[...new Set(data.manifest.books.map(b=>b.name))].map(name=>[data.manifest.books.filter(b=>b.name===name).map(b=>b.code).join('|'),name]);
  if(f.kind===UNIFIED_FORMULA_KIND&&!options.some(([key])=>key.split('|').includes('SGP')))options.push(['SGP','Singapore Pools']);
  $('trades-book').innerHTML='<option value="">Todas las casas</option>'+options.map(([key,name])=>`<option value="${esc(key)}">${esc(name)}</option>`).join('');
  $('trades-book').value=options.some(([key])=>key===old)?old:'';
}
function renderAlertRow(r){
  const pastResultMissing=r.won==null&&r.date<(data.entities?.asOf||new Date().toISOString()).slice(0,10);
  const missingHistory=pastResultMissing||r.statuses?.some(s=>/player_history|player_membership|period_corners|participation|combination_void/.test(s));
  const outcome=r.won===true?'Ganada':r.won===false?'Perdida':r.won==='push'?'Devuelta':missingHistory?'Sin dato':'Pendiente';
  const sample=r.probabilitySource==='manual'?'<span class="football-sub">Ingresada</span>':r.probabilityN!=null?`<span class="football-sub">${num(r.probabilityN,0)} ${r.probabilitySource==='reference'?'referencias':'previos'}</span>`:'';
  return `<tr role="button" tabindex="0" data-alert="${esc(r.id)}|${esc(r.book)}" aria-label="Ver alerta ${esc(r.home)} contra ${esc(r.away)}"><td>${date(r.date)}</td><td class="football-match">${matchHTML(r)}<span class="football-sub">${leagueHTML(r.league)}</span></td><td>${esc(r.actionLabel)}${r.contextOdds?`<span class="football-sub">1: ${num(r.contextOdds.home)} · X: ${num(r.contextOdds.draw)} · 2: ${num(r.contextOdds.away)}</span>`:''}</td><td>${esc(data.books.get(r.book)||r.book)}${r.isScenario?'<span class="football-sub">Cuota ingresada</span>':''}</td><td data-number>${num(r.odds)}</td><td data-number>${pct(r.probability)}${sample}</td><td data-number class="${cls(r.ev)}">${pct(r.ev,true)}</td><td data-number class="${cls(r.expectedProfit)}">${r.expectedProfit==null?'—':signed(r.expectedProfit)+' u'}</td><td>${outcome}</td><td data-number class="${cls(r.profit)}">${r.profit==null?'—':signed(r.profit)+' u'}</td></tr>`;
}
async function refreshTrades(){
  if(!ready)return;const token=++tradeToken,f=formulas.find(f=>f.id===$('trades-formula').value);if(!f)return;
  const unified=f.kind===UNIFIED_FORMULA_KIND;$('trades-coverage-field').hidden=!unified;$('trades-coverage').value=unified?'Buscando…':'';
  setStrategyBooks(f);initCommonSimpleSelects(document);const view=scope('trades');tables.trades.loading('Buscando coincidencias…');$('trades-export').disabled=true;$('trade-metrics').hidden=true;$('results-panel').hidden=true;
  try{
    let rows,summary;
    if(f.kind==='football-alert'||f.kind===UNIFIED_FORMULA_KIND){
      const universe=await data.strategyUniverse(f);if(token!==tradeToken)return;
      const offers=universe.offers.filter(r=>(f.kind!==UNIFIED_FORMULA_KIND||periodMatches(r,view.period))&&(!view.league||r.league===view.league)&&(!view.book||view.book.split('|').includes(r.book)));
      const evaluate=f.kind===UNIFIED_FORMULA_KIND?evaluateUnifiedFormula:evaluateFootballStrategy;
      const result=evaluate({events:universe.events,offers},f,{entities:data.entities,universe:universe.name});
      rows=result.alerts.filter(r=>periodMatches(r,view.period));summary=summarizeFootballAlerts(rows);
      if(unified){const coverage=result.coverage;$('trades-coverage').value=`${num(coverage.candidateCount??coverage.quoteGroups,0)} cuotas evaluadas · ${num(coverage.unknownCandidates,0)} sin datos`;}
    }else{
      await data.ensureOffers(view.period);if(token!==tradeToken)return;
      selected=matchAndRank(data.offers.filter(r=>offerMatches(r,view)),f.expression,{onePerMatch:f.onePerMatch});
      summary=summarize(selected,f.stake);summary.expectedProfit=selected.length?selected.reduce((total,r)=>total+r.ev*f.stake,0):null;summary.expectedPriced=selected.length;summary.isScenario=false;
      rows=selected.map(r=>({...r,actionLabel:side(r),contextOdds:null,stake:f.stake,profit:r.profit*f.stake,expectedProfit:r.ev*f.stake,probabilityN:r.references.length,probabilitySource:'reference',quoteSource:'archive',statuses:[],isScenario:false}));
    }
    appliedFormula={...f};active=f.id;currentSummary=summary;alertByKey=new Map(rows.map(r=>[`${r.id}|${r.book}`,r]));
    tables.trades.setRows(rows.toReversed());$('trades-export').disabled=false;$('trade-metrics').hidden=false;$('results-panel').hidden=false;
    const valued=summary.expectedPriced??summary.n;
    $('trade-metrics').innerHTML=metric('Alertas',num(summary.n,0))+metric(`EV estimado · ${num(valued,0)}`,pct(summary.meanEV,true))+metric('Ganancia esperada',summary.expectedProfit==null?'—':`${signed(summary.expectedProfit)} u`)+metric(summary.isScenario?'ROI simulado':'ROI histórico',pct(summary.roi,true));
    $('trades-count').textContent=`${num(summary.n,0)} alertas · ${num(valued,0)} con EV · ${summary.profit==null?'—':signed(summary.profit)+' u'} ${summary.isScenario?'simuladas':'realizadas'}`;
    $('years-table').tBodies[0].innerHTML=summary.years.map(y=>`<tr><td>${y.year}</td><td>${y.n}</td><td>${y.wins} · ${pct(y.winRate)}</td><td class="${cls(y.meanEV)}">${pct(y.meanEV,true)}</td><td class="${cls(y.roi)}">${pct(y.roi,true)}</td><td class="${cls(y.profit)}">${y.profit==null?'—':signed(y.profit)+' u'}</td></tr>`).join('');
  }catch(e){if(token===tradeToken){tables.trades.loading(e.message);if(unified)$('trades-coverage').value=e.message;}}
}
function showAlert(key){
  const r=alertByKey.get(key);if(!r)return;
  const cell=(label,value)=>`<div><span>${label}</span><strong>${value}</strong></div>`;
  const status={market_quote_missing:'Sin cuota para esta apuesta',probability_history_insufficient:'Muestra previa insuficiente',probability_missing:'Sin probabilidad',player_history_missing:'Sin historial del jugador en ese partido',player_result_missing:'Sin estadística individual',player_membership_missing:'Plantel histórico no verificado',result_missing:'Resultado pendiente',period_corners_missing:'Sin córners de ese período',push_probability_missing:'Sin probabilidad de devolución',combination_void_rules_missing:'Faltan reglas de devolución de la combinada',player_participation_rules_missing:'Falta participación del jugador',selected_team_missing:'Equipo no identificado en el partido',outside_empirical_cohort:'Fuera del filtro de la muestra',cards_settlement_missing:'Sin tarjetas liquidadas con las reglas del mercado',shots_result_missing:'Sin datos de remates',shots_on_target_result_missing:'Sin datos de remates al arco',offsides_result_missing:'Sin datos de fuera de juego',corners_result_missing:'Sin datos de córners',period_cards_missing:'Sin tarjetas de ese período',period_shots_missing:'Sin remates de ese período',period_shots_on_target_missing:'Sin remates al arco de ese período',period_offsides_missing:'Sin fuera de juego de ese período',half_time_result_missing:'Sin resultado del primer tiempo',goal_order_missing:'Sin orden de los goles',goalscorer_order_missing:'Sin orden de los goleadores',asian_quarter_line_unsupported:'Línea de hándicap no disponible',market_rules_missing:'Sin liquidación para este mercado'};
  $('trade-details').innerHTML=`<h3>${esc(r.home)} — ${esc(r.away)}</h3><p>${date(r.date)} · ${esc(r.actionLabel)}</p><div class="football-detail-grid">${r.contextOdds?cell('Cuota local',num(r.contextOdds.home))+cell('Cuota empate',num(r.contextOdds.draw))+cell('Cuota visitante',num(r.contextOdds.away)):''}${cell('Cuota de la apuesta',num(r.odds))}${cell('Probabilidad estimada',pct(r.probability))}${cell(r.probabilitySource==='reference'?'Referencias':'Partidos previos',r.probabilityN==null?'—':num(r.probabilityN,0))}${cell('Probabilidad de equilibrio',pct(r.breakEven===undefined?(r.odds?1/r.odds:null):r.breakEven))}${cell('Importe',num(r.stake)+' u')}${cell('EV estimado',pct(r.ev,true))}${cell('Ganancia esperada',r.expectedProfit==null?'—':signed(r.expectedProfit)+' u')}${cell(r.isScenario?'Beneficio simulado':'Beneficio histórico',r.profit==null?'—':signed(r.profit)+' u')}</div>${r.ev!=null?`<output>EV = ${pct(r.probability)} × ${num(r.odds)}${r.pushProbability?' + '+pct(r.pushProbability):''} − 1 = ${pct(r.ev,true)}<br>Ganancia esperada = ${num(r.stake)} × ${pct(r.ev)} = ${signed(r.expectedProfit)} u</output>`:''}${r.statuses?.length?`<ul>${r.statuses.map(key=>`<li>${esc(status[key]||'Dato no disponible')}</li>`).join('')}</ul>`:''}`;
  $('trade-dialog').showModal();
}
function showTrade(key){
  const [event,book,selection]=key.split('|'),rows=data.byEvent.get(Number(event))||[],r=rows.find(r=>r.book===book&&r.side===Number(selection));if(!r)return;
  const e=data.events[r.event],stake=$('formulas-view').hidden?1:appliedFormula.stake;
  const cell=(label,value)=>`<div><span>${label}</span><strong>${value}</strong></div>`;
  const refs=rows.filter(o=>o.side===r.side&&r.references.includes(o.book)).sort((a,b)=>a.ownProbability-b.ownProbability);
  $('trade-details').innerHTML=`<h3>${esc(r.home)} — ${esc(r.away)}</h3><p>${date(r.date)} · ${esc(side(r))} · ${esc(data.books.get(r.book))}</p><div class="football-detail-grid">${cell('Cuota',num(r.odds))}${cell('Probabilidad de equilibrio',pct(1/r.odds))}${cell('Probabilidad mínima',pct(r.probability))}${cell('EV estimado',pct(r.ev,true))}${cell('Otras casas',r.references.length)}${cell('Resultado final',pair(e,'home_score','away_score'))}${cell('Importe',`${num(stake)} u`)}${cell('Beneficio',`${signed(r.profit*stake)} u`)}</div><p>EV = ${num(r.probability,6)} × ${num(r.odds)} − 1 = ${pct(r.ev,true)}</p><div class="table-wrap"><table><thead><tr><th>Casa de referencia</th><th>Cuota</th><th>Probabilidad sin margen</th></tr></thead><tbody>${refs.map(o=>`<tr><td>${esc(data.books.get(o.book))}</td><td>${num(o.odds)}</td><td>${pct(o.ownProbability)}</td></tr>`).join('')}</tbody></table></div><p class="football-sub">Referencia mínima entre otras casas tras retirar el margen por potencia. Fuente: Football-Data.co.uk, archivo pre-cierre.</p>`;
  $('trade-dialog').showModal();
}
function exportCSV(table,columns,filename){
  const quote=x=>`"${String(x??'').replace(/"/g,'""')}"`,rows=table.filtered;
  const csv='\uFEFF'+[columns.map(([name])=>quote(name)).join(','),...rows.map(r=>columns.map(([,getter])=>quote(getter(r))).join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify(`${num(rows.length,0)} registros exportados`);
}
const offerColumns=[['id',r=>r.id],['fecha',r=>r.date],['liga',r=>r.league],['local',r=>r.home],['visitante',r=>r.away],['casa',r=>r.book],['seleccion',r=>['1','X','2'][r.side]],['cuota',r=>r.odds],['probabilidad_min',r=>r.probability],['referencias',r=>r.references.join('|')],['ev_estimado',r=>r.ev],['acierto',r=>r.won],['beneficio_1u',r=>r.profit]];
function setView(){const view=location.hash==='#formulas'?'formulas':'datos';$('datos-view').hidden=view!=='datos';$('formulas-view').hidden=view!=='formulas';document.querySelectorAll('[data-view]').forEach(a=>{const selected=a.dataset.view===view;a.classList.toggle('is-active',selected);if(selected)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});}
function playerStatus(p){return {a:'Disponible',i:'Lesionado',d:'En duda',s:'Suspendido'}[p.providerStatus]||'No indicado';}
function refreshPlayerTeams(){
  if(!ready)return;const league=$('players-league').value,old=$('players-team').value,ids=new Set(data.entities.players.filter(p=>!league||p.leagueId===league).map(p=>p.teamId));
  $('players-team').innerHTML='<option value="">Todos los equipos</option>'+data.entities.teams.filter(t=>ids.has(t.id)).map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');$('players-team').value=ids.has(old)?old:'';
}
function refreshPlayers(){
  if(!ready||!tables.players)return;refreshPlayerTeams();const league=$('players-league').value,team=$('players-team').value,position=$('players-position').value,status=$('players-status').value;
  tables.players.setRows(data.entities.players.filter(p=>(!league||p.leagueId===league)&&(!team||p.teamId===team)&&(!position||p.position===position)&&(!status||(status==='other'?!['a','i','d','s'].includes(p.providerStatus):p.providerStatus===status))).sort((a,b)=>a.name.localeCompare(b.name)));
}
function marketSelection(q){return q.market==='correct_score'?`${q.homeGoals}–${q.awayGoals}`:q.market==='btts'?(q.selection==='yes'?'Sí':'No'):q.market==='match_result'?({home:'Local',draw:'Empate',away:'Visitante'})[q.selection]:`${q.selection==='exact'?'Exactamente':q.selection==='over'?'Más de':'Menos de'} ${q.line}`;}
async function refreshGoals(){
  if(!ready||!tables.goals)return;const token=++goalToken;tables.goals.loading('Cargando cuotas…');$('goals-export').disabled=true;
  try{const universe=await data.ensureMarketHistory();if(token!==goalToken)return;
    const market=$('goals-market').value,period=$('goals-period').value,league=$('goals-league').value,min=Number($('goals-min-odds').value)||1;
    const rows=[];for(const event of universe.events)if(!league||event.league===league)for(const quote of event.marketQuotes)if(quote.market===market&&quote.period===period&&quote.odds>=min)rows.push({...event,quote});
    tables.goals.setRows(rows.sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id)));$('goals-export').disabled=false;
  }catch(e){if(token===goalToken)tables.goals.loading(e.message);}
}
function initializeEntityTables(){
  const teamName=id=>data.entities.teams.find(t=>t.id===id)?.name||id;
  tables.players=new Table('players','jugadores',6,p=>`<tr><td>${esc(p.name)}</td><td>${teamHTML(p.teamId,p.leagueId)}</td><td>${leagueHTML(p.leagueId)}</td><td>${esc(p.position)}</td><td>${playerStatus(p)}</td><td>${date(p.asOf?.slice(0,10))}</td></tr>`,p=>[p.name,teamName(p.teamId),p.position]);
  tables.goals=new Table('goals','cuotas',7,r=>`<tr><td>${date(r.date)}</td><td class="football-match">${matchHTML(r)}</td><td>${esc(ALERT_MARKETS.find(m=>m.id===r.quote.market)?.name)}</td><td>${marketSelection(r.quote)}</td><td>${num(r.quote.odds)}</td><td>Singapore Pools</td><td>${pair(r,'home_score','away_score')}</td></tr>`,matchSearch);
  const leagues=new Set(data.entities.players.map(p=>p.leagueId));$('players-league').innerHTML='<option value="">Todas las ligas con plantel</option>'+data.entities.leagues.filter(l=>leagues.has(l.id)).map(l=>`<option value="${esc(l.id)}">${esc(l.name)}</option>`).join('');
  $('players-position').innerHTML='<option value="">Todas</option>'+[...new Set(data.entities.players.map(p=>p.position).filter(Boolean))].sort().map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join('');
  $('goals-league').innerHTML='<option value="">Todas las ligas</option>'+data.entities.leagues.map(l=>`<option value="${esc(l.id)}">${esc(l.name)}</option>`).join('');refreshPlayerTeams();
  if($('players-panel').open)refreshPlayers();if($('goals-panel').open)refreshGoals();
}

async function initialize(){
  tables.events=new Table('events','partidos',10,eventRow,matchSearch);tables.offers=new Table('offers','cuotas',9,r=>offerRow(r),matchSearch);tables.trades=new Table('trades','alertas',10,renderAlertRow,matchSearch);tables.formulas=new Table('formulas','fórmulas',5,formulaRow,f=>f.name);
  builder=mountFootballAlertBuilder($('formula-builder'),{onSave:definition=>{
    const f={...definition,id:definition.id||crypto.randomUUID()},next=formulas.some(x=>x.id===f.id)?formulas.map(x=>x.id===f.id?f:x):[...formulas,f];
    formulas=saveStrategies(next,data.entities);active=f.id;refreshFormulaList();$('trades-formula').value=f.id;initCommonSimpleSelects(document);builder.reset();$('create-title').textContent='Crear fórmula';$('create-panel').open=false;$('formulas-panel').open=true;if($('trades-panel').open)refreshTrades();
  },onCancel:()=>{$('create-title').textContent='Crear fórmula';$('create-panel').open=false;}});
  refreshFormulaList();setView();initDatePicker({root:document});initCommonSimpleSelects(document);initFloatingDropdowns(document);
  try{
    await data.initialize();formulas=seedFormulaLibrary(formulas,data.entities);entityPresentation=initEntityPresentation(document,data.entities,data.badges);ready=true;builder.setEntities(data.entities);refreshFormulaList();initializeEntityTables();
    for(const id of ['events','offers','trades'])$(`${id}-league`).innerHTML='<option value="">Todas las ligas</option>'+data.entities.leagues.map(l=>`<option value="${esc(l.id)}">${esc(l.name)}</option>`).join('');
    const bookOptions=[...new Set(data.manifest.books.map(b=>b.name))].map(name=>`<option value="${esc(data.manifest.books.filter(b=>b.name===name).map(b=>b.code).join('|'))}">${esc(name)}</option>`).join('');
    for(const id of ['offers','trades'])$(`${id}-book`).innerHTML='<option value="">Todas las casas</option>'+bookOptions;
    $('events-from').value=data.manifest.date_range[0];$('events-to').value=data.manifest.date_range[1];
    $('dictionary-table').tBodies[0].innerHTML=FIELD_DICTIONARY.map(f=>`<tr><td>${esc(f.name)}<span class="football-sub">${esc(f.label)}</span></td><td>${esc(f.formula||f.description)}</td><td>${f.preMatch===false?'Resultado':'Condición'}</td></tr>`).join('')+'<tr><td>roi</td><td>Suma de beneficios históricos / importe total apostado</td><td>Resultado</td></tr>';
    if($('events-panel').open)refreshEvents();if($('offers-panel').open)refreshOffers();if($('trades-panel').open)refreshTrades();
  }catch(e){$('load-error').textContent=e.message;$('load-error').hidden=false;}
}
window.addEventListener('hashchange',setView);
for(const [id,refresh]of [['events',refreshEvents],['offers',refreshOffers],['trades',refreshTrades],['players',refreshPlayers],['goals',refreshGoals]]){
  $(`${id}-panel`).addEventListener('toggle',()=>{if($(`${id}-panel`).open)refresh();});$(`${id}-filters`).addEventListener('change',refresh);$(`${id}-filters`).addEventListener('submit',e=>e.preventDefault());
}
document.addEventListener('click',event=>{
  const use=event.target.closest('[data-use]'),edit=event.target.closest('[data-edit]'),duplicate=event.target.closest('[data-duplicate]'),row=event.target.closest('[data-trade]');
  if(use){$('trades-formula').value=use.dataset.use;$('trades-panel').open=true;refreshTrades();$('trades-panel').scrollIntoView({behavior:'smooth',block:'start'});}
  if(edit||duplicate){const f=formulas.find(f=>f.id===(edit?.dataset.edit||duplicate.dataset.duplicate));if(f?.kind==='football-alert'||f?.kind===UNIFIED_FORMULA_KIND){builder.edit(duplicate?{...f,id:null,name:f.name+' · copia'}:f);$('create-title').textContent='Crear fórmula';$('create-panel').open=true;$('create-panel').scrollIntoView({behavior:'smooth',block:'start'});}}
  const alert=event.target.closest('[data-alert]');if(alert)showAlert(alert.dataset.alert);if(row)showTrade(row.dataset.trade);
});
document.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)&&event.target.matches('[data-alert]')){event.preventDefault();showAlert(event.target.dataset.alert);}if(['Enter',' '].includes(event.key)&&event.target.matches('[data-trade]')){event.preventDefault();showTrade(event.target.dataset.trade);}});
$('close-dialog').onclick=()=>$('trade-dialog').close();$('trade-dialog').onclick=e=>{if(e.target===$('trade-dialog'))$('trade-dialog').close();};
$('goals-export').onclick=()=>exportCSV(tables.goals,[['fecha',r=>r.date],['local',r=>r.home],['visitante',r=>r.away],['mercado',r=>r.quote.market],['periodo',r=>r.quote.period],['seleccion',r=>marketSelection(r.quote)],['cuota',r=>r.quote.odds],['casa',()=> 'Singapore Pools']],'workraken-marcadores.csv');
$('events-export').onclick=()=>exportCSV(tables.events,data.manifest.tables.events.columns.map(key=>[key,r=>r[key]]),'workraken-partidos.csv');
$('offers-export').onclick=()=>exportCSV(tables.offers,offerColumns,'workraken-cuotas.csv');
$('trades-export').onclick=()=>exportCSV(tables.trades,[['fecha',r=>r.date],['local',r=>r.home],['visitante',r=>r.away],['casa',r=>r.book],['apuesta',r=>r.actionLabel],['cuota_apuesta',r=>r.odds],['probabilidad',r=>r.probability],['muestra_previa',r=>r.probabilityN],['probabilidad_fuente',r=>r.probabilitySource],['ev',r=>r.ev],['importe',r=>r.stake],['ganancia_esperada',r=>r.expectedProfit],['beneficio',r=>r.profit],['precio',r=>r.isScenario?'ingresado':'archivo'],['alerta',()=>appliedFormula.name]],'workraken-alertas.csv');
const shell=document.querySelector('[data-app-shell]');
document.querySelector('[data-sidebar-toggle]').onclick=event=>{const collapsed=shell.classList.toggle('is-sidebar-collapsed');event.currentTarget.setAttribute('aria-expanded',String(!collapsed));event.currentTarget.setAttribute('aria-label',collapsed?'Expandir módulos':'Contraer módulos');};
document.querySelector('[data-theme-toggle]').onclick=event=>{const dark=shell.classList.toggle('is-dark-mode');document.documentElement.dataset.theme=dark?'dark':'light';event.currentTarget.setAttribute('aria-pressed',String(dark));event.currentTarget.setAttribute('aria-label',dark?'Activar modo claro':'Activar modo oscuro');event.currentTarget.title=dark?'Modo claro':'Modo oscuro';event.currentTarget.querySelector('.sidebar-theme-toggle-label').textContent=dark?'Modo claro':'Modo oscuro';};
initialize();
