/** Bounded source/price exploration using the shared Workraken grids. */
import {safeSourceURL,sourceForWorkspaceEvent,sourceForPlayer} from './football-data-archive.js';
import {initCommonSimpleSelects} from './vendor/workraken/single-select.js';
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const text=x=>x==null?'':typeof x==='object'?JSON.stringify(x):String(x);
const fold=x=>text(x).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const unique=values=>[...new Set(values.filter(x=>x!=null&&x!==''))];
const phaseNames={pre_closing:'Previa al cierre',closing:'Cierre',opening_archive_timestamp_unknown:'Apertura archivada · hora no verificada',archive_timestamp_unknown:'Archivo · hora no verificada',archive_time_unknown:'Archivo · hora no verificada',historical_timestamp:'Actualización histórica de precio',pre_match_source_flag:'Prepartido según fuente',in_play_source_flag:'En vivo según fuente',phase_unknown:'Fase no informada'};
const periodNames={full:'Partido completo',first_half:'Primer tiempo',second_half:'Segundo tiempo',fulltime:'Partido completo',source_market_label:'Según el mercado original',full_match_source_label:'Partido según etiqueta original',regulation_duration_unverified:'Partido según etiqueta · duración sin verificar',research_format_and_regulation_duration_unverified:'Partido según etiqueta · duración sin verificar'};
const qualityNames={temporal_update_not_full_simultaneous_snapshot:'Actualización temporal · conjunto simultáneo sin verificar',message_publication_time_not_trade_or_executable_offer_time:'Hora de publicación · no acredita negociación ni oferta ejecutable',outright_question_or_unidentified_event:'Apuesta a largo plazo o evento sin identificar',snapshot_not_verified_executable_offer:'Captura · ejecución sin verificar',identified_fixture_no_imported_result:'Partido identificado · resultado sin importar',no_explicit_scope_flag_unverified:'Ámbito sin indicar · sin verificar',regulation_duration_unverified:'Duración reglamentaria sin verificar',research_format_and_regulation_duration_unverified:'Formato y duración reglamentaria sin verificar'};
const priceTypeNames={bookmaker_price_update:'Actualización de cuota de la casa',last_traded_price:'Último precio negociado',public_odds_snapshot:'Captura pública de cuotas',recorded_bookmaker_price:'Precio registrado de la casa'};
const selectionNames={home:'Local',draw:'Empate',away:'Visitante',yes:'Sí',no:'No',over:'Más de',under:'Menos de',odd:'Impar',even:'Par',exact:'Exactamente',at_least:'Al menos',none:'Ningún equipo',other:'Otro resultado',home_draw:'Local o empate',draw_away:'Empate o visitante',home_away:'Local o visitante'};
const phaseLabel=id=>phaseNames[id]||id||'No informada';
const threshold=value=>value==null||String(value).trim()===''||!Number.isFinite(Number(value))?null:Number(value);
export function filterArchiveOffers(offers,filter={},leagueName=x=>x){
  const min=threshold(filter.minOdds),max=threshold(filter.maxOdds),league=fold(filter.league);
  const rows=offers.filter(row=>(!filter.book||row.book===filter.book)&&(!filter.market||row.market===filter.market)&&(!filter.phase||row.phase===filter.phase)&&(!league||fold(`${row.league} ${leagueName(row.league)}`).includes(league))&&(min==null||finite(row.odds)&&row.odds>=min)&&(max==null||finite(row.odds)&&row.odds<=max)&&(!filter.active||filter.active==='active'&&row.active===true&&row.suspended!==true||filter.active==='inactive'&&(row.active===false||row.suspended===true)));
  const [key,direction]=(filter.sort||'date_desc').split('_'),sign=direction==='asc'?1:-1;
  return rows.sort((a,b)=>{
    if(key==='odds'){const av=finite(a.odds),bv=finite(b.odds);if(av!==bv)return av?-1:1;if(av&&a.odds!==b.odds)return sign*(a.odds-b.odds);}
    else {const order=text(a.date).localeCompare(text(b.date));if(order)return sign*order;}
    return text(a.quoteId).localeCompare(text(b.quoteId));
  });
}
export function mountFootballDataBrowser({data,Table,archive=data.archive,onApply=()=>{},onClear=()=>{},formatters={}}){
  const $=id=>document.getElementById(id),esc=formatters.esc||(value=>text(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const num=formatters.num||((value,d=0)=>finite(value)?value.toLocaleString('es-AR',{maximumFractionDigits:d}):'—');
  const date=formatters.date||(value=>value||'—'),pair=formatters.pair||((e,a,b)=>e[a]==null||e[b]==null?'—':`${e[a]}–${e[b]}`);
  let catalog=[],loaded=null,initialized=false,token=0,inputTimer,applied=null,eventSources=new Map(),catalogBookNames=new Map(),catalogMarketNames=new Map();
  const dataset=()=>archive.datasets.get($('archive-dataset').value),manifest=()=>dataset()?.manifest||{};
  const maps=()=>({books:new Map((manifest().books||[]).map(x=>[text(x.code??x.id),x.name])),markets:new Map((manifest().markets||[]).map(x=>[text(x.id),x.name])),leagues:new Map((manifest().leagues||[]).map(x=>[text(x.id),x.name]))});
  let names={books:new Map(),markets:new Map(),leagues:new Map()};
  const displayBrands={pinnacle:'Pinnacle',draftkings:'DraftKings',betfair:'Betfair',betfair_exchange:'Betfair Exchange'};
  const bookName=id=>{const name=names.books.get(text(id))||data.books?.get(text(id))||id;return displayBrands[text(name).toLowerCase()]||name||'No informada';};
  const marketName=id=>names.markets.get(text(id))||id||'No informado';
  const leagueName=id=>names.leagues.get(text(id))||data.leagues?.get(text(id))||id||'—';
  const cell=value=>`<div role="cell">${value}</div>`;
  const row=cells=>`<div role="row" class="wk-grid-row wk-row-outline wk-row-surface">${cells.map(cell).join('')}</div>`;
  const field=(id,value)=>{if($(id))$(id).value=value??'';};
  const stamp=value=>{if(!value)return 'No informada';if(/^\d{4}-\d{2}-\d{2}$/.test(text(value)))return date(value);if(!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(text(value)))return text(value);const parsed=new Date(value);return Number.isNaN(parsed.valueOf())?text(value):parsed.toLocaleString('es-AR',{timeZone:'America/Argentina/Salta',dateStyle:'short',timeStyle:'short'});};
  function link(url,label,sha){const safe=safeSourceURL(url);return safe?`<a href="${esc(safe)}" target="_blank" rel="noopener noreferrer" title="${esc([safe,sha?`SHA-256: ${sha}`:''].filter(Boolean).join(' · '))}">${esc(label||new URL(safe).hostname)}</a>`:'—';}
  const quality=value=>value?qualityNames[value]||text(value).replaceAll('source_fixture_no_imported_score','Fixture de la fuente · marcador no importado').replaceAll('_',' '):'Sin clasificación adicional';
  const priceType=value=>priceTypeNames[value]||value||'';
  const sourceCell=r=>`${esc(r.sourceProvider||r.provider||'Fuente no informada')}<span class="football-sub">${link(r.sourceUrl,'Archivo de origen',r.sourceSha256||r.sha256)}</span><span class="football-sub" title="${esc(r.retrievedAt||'')}">${esc(stamp(r.retrievedAt))}</span>`;
  const catalogBooks=r=>r.books?.length?r.books:r.dataset==='additional'?['SGP']:[];
  const catalogMarkets=r=>r.markets?.length?r.markets:r.dataset==='additional'?(archive.datasets.get('additional')?.manifest.markets||[]).map(m=>m.id):[];
  function sourceRow(r){
    const ds=archive.datasets.get(r.dataset)?.manifest,bookIds=r.books?.length?r.books:(r.dataset==='additional'?(ds?.books||[]).map(x=>x.code):[]);
    const bookLabels=bookIds.map(id=>ds?.books?.find(x=>text(x.code??x.id)===text(id))?.name||data.books?.get(id)||id),marketLabels=(r.markets||[]).map(id=>ds?.markets?.find(x=>text(x.id)===text(id))?.name||id);
    const compact=(labels,noun,fallback)=>labels.length>3?[...labels.slice(0,3),`${labels.length} ${noun}`].join(' · '):labels.join(' · ')||fallback;
    const books=bookLabels.join(' · ')||r.bookLabel||'No desglosadas',markets=marketLabels.join(' · ')||r.marketLabel||'Varios';
    const action=r.partitionId?`<button type="button" class="mini-button" data-open-archive="${esc(r.id)}">Abrir archivo</button>`:`<button type="button" class="mini-button" data-open-existing="${esc(r.target||'events-panel')}">Ver registros</button>`;
    return row([esc(r.provider),`<span title="${esc(books)}">${esc(compact(bookLabels,'casas',books))}</span>`,`<span title="${esc(r.path||r.label)}">${esc(r.name)}<span class="football-sub">${esc(r.label)}</span></span>`,`<span title="${esc(markets)}">${esc(compact(marketLabels,'mercados',markets))}</span>`,num(r.events,0),num(r.quotes,0),esc(date(r.dateMin)),esc(date(r.dateMax)),`<span title="${esc(r.retrievedAt||'')}">${esc(stamp(r.retrievedAt))}</span>`,link(r.sourceUrl,'Fuente original',r.sha256),action]);
  }
  function priceRow(r){
    let displayedSelection=r.selection;if(loaded.dataset.id!=='research'){displayedSelection=selectionNames[r.selection]||r.selection;if(r.market==='half_time_full_time')displayedSelection=text(r.selection).split('_').map(part=>selectionNames[part]||part).join(' / ');}
    const e=loaded.events[r.event]||{},selection=[displayedSelection,r.line!=null?`Línea ${text(r.line)}`:'',r.playerId!=null&&text(r.playerId)!=='0'&&text(r.playerId)!==''?`Jugador ${text(r.playerId)}`:'',r.rawSelectionId!=null?`ID ${text(r.rawSelectionId)}`:''].filter(x=>x!==''&&x!=null).join(' · ');
    const activity=r.priceType==='last_traded_price'?(r.active===true?'Participante activo según fuente':r.active===false?'Participante inactivo según fuente':'Estado del participante no informado'):r.suspended===true?'Suspendida':r.active===true?'Activa según fuente':r.active===false?'Inactiva según fuente':'Actividad no informada';
    const details=[quality(r.quality),activity,priceType(r.priceType),r.marketStatus?`Mercado: ${r.marketStatus}`:'',r.runnerStatus?`Participante: ${r.runnerStatus}`:'',r.limit!=null?`Límite ${text(r.limit)}`:''].filter(Boolean).join(' · '),rawDetails=[r.quality,r.priceType,r.marketStatus,r.runnerStatus,r.limit].filter(x=>x!=null).map(text).join(' · ');
    return row([esc(e.sourceStartTime||r.rawStartTime||e.date||r.date),`${esc(r.home||e.eventName||'Evento')}<span class="football-sub">${esc(r.away||'')}</span>`,esc(leagueName(r.league)),`<span title="${esc(r.rawMarketId??r.market)}">${esc(r.rawMarketName||marketName(r.market))}</span>`,`<span title="${esc(r.period)}">${esc(periodNames[r.period]||r.period)}</span>`,esc(selection||'No informada'),esc(bookName(r.book)),`<span title="${esc([r.phase,r.priceType].filter(Boolean).join(' · '))}">${esc(`${phaseLabel(r.phase)}${r.priceType?' · '+priceType(r.priceType):''}`)}</span>`,num(r.odds,3),`<span title="${esc(r.rawTimeLabel||'')}">${esc(r.capturedAt||r.rawTimestamp||'No informada')}</span>`,sourceCell(r),esc([r.sourceColumn,r.sourceRow!=null?`Fila ${r.sourceRow}`:''].filter(Boolean).join(' · ')||'—'),`<span title="${esc(rawDetails)}">${esc(details)}</span>`]);
  }
  function eventRow(e){
    const eventSource=e.sourceFileId==null?null:(loaded.dataset.manifest.sources||[]).find(source=>text(source.id)===text(e.sourceFileId));
    const source=eventSource||eventSources.get(e.id)||loaded.partition.source||{},r={sourceProvider:source.sourceProvider||source.provider||loaded.dataset.manifest.provider,sourceUrl:source.sourceUrl??source.url,sourceSha256:source.sourceSha256??source.sha256,retrievedAt:source.retrievedAt??source.retrieved_at};
    return row([esc(date(e.date)),esc(e.home||e.eventName),esc(e.away||'—'),esc(leagueName(e.league)),esc(e.season||'—'),pair(e,'home_score','away_score'),pair(e,'home_ht_score','away_ht_score'),pair(e,'home_corners','away_corners'),pair(e,'home_shots','away_shots'),pair(e,'home_shots_on_target','away_shots_on_target'),pair(e,'home_yellow','away_yellow'),sourceCell(r),`<span title="${esc(e.sourceScope||loaded.partition.quality||'')}">${esc(quality(e.sourceScope||loaded.partition.quality))}</span>`]);
  }
  const sourcesTable=new Table('sources','archivos',11,sourceRow,r=>[r.provider,r.name,r.label,r.sourceUrl,r.league,...catalogBooks(r),...catalogBooks(r).map(id=>catalogBookNames.get(id)),...catalogMarkets(r),...catalogMarkets(r).map(id=>catalogMarketNames.get(id))].join(' '),'Fuente, casa, mercado o archivo');
  const pricesTable=new Table('archive','registros de cuota',13,priceRow,r=>[r.date,r.home,r.away,r.league,leagueName(r.league),r.market,r.rawMarketName,r.selection,r.playerId,r.rawSelectionId,bookName(r.book),r.sourceProvider,r.sourceColumn,r.phase,r.quality,r.capturedAt].join(' '),'Partido, jugador, mercado, casa o fuente');
  const eventsTable=new Table('archive-events','registros de partido',13,eventRow,e=>[e.date,e.home,e.away,e.eventName,e.league,leagueName(e.league),e.season,e.sourceEventId,e.sourceScope].join(' '),'Equipo, evento, liga o identificador');
  function options(id,entries,{empty='Todos',value}={}){const select=$(id),previous=value??select.value;select.innerHTML=(empty==null?'':`<option value="">${esc(empty)}</option>`)+entries.map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join('');select.value=[...select.options].some(o=>o.value===text(previous))?text(previous):entries[0]?.[0]||'';if(empty!=null&&previous==='')select.value='';}
  const refreshSelects=()=>initCommonSimpleSelects(document);
  function legacyCatalog(){
    const rows=[],eventCounts=new Map(),dates=new Map();
    for(const event of data.events||[]){const source=event.sourceUrl?{url:event.sourceUrl}:sourceForWorkspaceEvent(data,event),url=safeSourceURL(source.url);eventCounts.set(url,(eventCounts.get(url)||0)+1);const range=dates.get(url)||[event.date,event.date];range[0]=range[0]<event.date?range[0]:event.date;range[1]=range[1]>event.date?range[1]:event.date;dates.set(url,range);}
    for(const [i,file]of(data.manifest?.sources?.files||[]).entries()){const url=safeSourceURL(file.url),range=dates.get(url)||[];rows.push({id:`workspace:${i}`,dataset:'workspace',name:'Archivo original',label:url.split('/').slice(-2).join('/'),provider:data.manifest.sources.provider,sourceUrl:url,sha256:file.sha256,retrievedAt:file.retrievedAt||file.retrieved_at,events:eventCounts.get(url)??null,quotes:null,dateMin:range[0],dateMax:range[1],books:[],markets:['match_result'],bookLabel:'Casas del archivo original',target:'events-panel'});}
    const provenance=data.sgoddsProvenance,counts=new Map();for(const entry of Object.values(provenance?.events||{}))counts.set(entry.sourceId,(counts.get(entry.sourceId)||0)+1);
    for(const source of provenance?.sources||[])rows.push({id:`legacy:${source.id}`,dataset:'legacy-sgodds',name:'SGodds · archivo original',label:source.url?.split('/').at(-1)||source.id,provider:source.provider,sourceUrl:safeSourceURL(source.url),sha256:source.sha256,retrievedAt:source.retrievedAt,events:counts.get(source.id)||0,quotes:null,books:['SGP'],markets:['match_result','correct_score','total_goals','btts'],target:'goals-panel'});
    const playersBySource=new Map();for(const player of data.entities?.players||[])playersBySource.set(player.source,(playersBySource.get(player.source)||0)+1);
    for(const [i,source]of(data.entities?.sources||[]).entries()){const info=sourceForPlayer(data,{source:source.id});rows.push({id:`players:${i}`,dataset:'players',name:'Jugadores y planteles',label:`${source.id} · ${num(playersBySource.get(source.id)||0,0)} jugadores`,provider:info.provider,sourceUrl:info.url,sha256:info.sha256,retrievedAt:info.retrievedAt,events:null,quotes:0,books:[],bookLabel:'No corresponde',markets:['player_statistics'],target:'players-panel'});}
    return rows;
  }
  function catalogLists(){
    const providers=unique(catalog.map(r=>r.provider)).sort(),bookMap=new Map(),marketMap=new Map();
    for(const ds of archive.datasets.values()){for(const b of ds.manifest?.books||[])bookMap.set(text(b.code??b.id),b.name);for(const m of ds.manifest?.markets||[])marketMap.set(text(m.id),m.name);}
    for(const b of data.manifest?.books||[])bookMap.set(b.code,b.name);bookMap.set('SGP','Singapore Pools');marketMap.set('player_statistics','Jugadores y planteles');
    catalogBookNames=bookMap;catalogMarketNames=marketMap;
    options('sources-provider',providers.map(x=>[x,x]),{empty:'Todas'});options('sources-book',[...bookMap],{empty:'Todas'});options('sources-market',[...marketMap],{empty:'Todos'});
    options('sources-dataset',[...archive.datasets.values()].map(x=>[x.id,x.name]).concat([['workspace','Archivo original'],['legacy-sgodds','SGodds original'],['players','Jugadores y planteles']]),{empty:'Todas'});
  }
  function refreshCatalog(){
    const provider=$('sources-provider').value,book=$('sources-book').value,market=$('sources-market').value,collection=$('sources-dataset').value;
    sourcesTable.setRows(catalog.filter(r=>(!provider||r.provider===provider)&&(!collection||r.dataset===collection)&&(!book||catalogBooks(r).includes(book))&&(!market||catalogMarkets(r).includes(market))));
  }
  function filteredParts(){const season=$('archive-season').value,league=fold($('archive-league').value);return(manifest().partitions||[]).filter(p=>(!season||text(p.season)===season)&&(!league||fold([p.league,names.leagues.get(text(p.league)),...(p.leagues||[])].join(' ')).includes(league)));}
  function partitionOptions(preferred){const parts=filteredParts();options('archive-partition',parts.map(p=>[text(p.id),`${p.season||p.dateMax?.slice(0,4)||''} · ${p.label||names.leagues.get(text(p.league))||p.league||p.id} · ${num(p.quoteCount,0)} registros`]),{empty:null,value:preferred});return parts;}
  function selectedFilters(){return{book:$('archive-book').value,market:$('archive-market').value,phase:$('archive-phase').value,league:$('archive-league').value,minOdds:$('archive-min-odds').value,maxOdds:$('archive-max-odds').value,active:$('archive-active').value,sort:$('archive-sort').value};}
  function eligibility(){
    const phases=loaded?unique(loaded.offers.map(r=>r.phase)):[],selected=$('archive-phase').value,research=$('archive-dataset').value==='research';
    const allowed=Boolean(loaded&&!research&&(selected||phases.length===1));
    $('archive-use').disabled=!allowed;
    field('archive-eligibility',!loaded?'Elegí un archivo':research?'Consulta de investigación · mercados originales sin normalizar':!allowed?'Elegí una fase única para fórmulas':'Fórmulas: archivo, fase, casa y mercado seleccionados');
    return allowed;
  }
  function refresh(){
    if(!loaded)return;const filters=selectedFilters(),rows=filterArchiveOffers(loaded.offers,filters,leagueName);pricesTable.setRows(rows);
    const league=fold(filters.league),events=loaded.events.filter(e=>!league||fold(`${e.league} ${leagueName(e.league)}`).includes(league)).sort((a,b)=>text(b.date).localeCompare(text(a.date))||text(a.id).localeCompare(text(b.id)));eventsTable.setRows(events);
    field('archive-status',`${num(rows.length,0)} registros filtrados · ${num(loaded.offers.length,0)} observaciones en el archivo`);$('archive-export').disabled=!rows.length;eligibility();
  }
  async function load(){
    const request=++token,selection={dataset:$('archive-dataset').value,partitionId:$('archive-partition').value};loaded=null;$('archive-use').disabled=true;$('archive-export').disabled=true;
    if(!selection.partitionId){pricesTable.setRows([]);eventsTable.setRows([]);field('archive-status','No hay archivos para esos filtros');eligibility();return;}
    pricesTable.loading('Cargando un archivo…');eventsTable.loading('Cargando registros…');field('archive-status','Cargando un archivo…');
    try{const result=await archive.loadPartition(selection);if(request!==token)return;loaded=result;names=maps();
      eventSources=new Map();for(const quote of loaded.offers){const id=loaded.events[quote.event]?.id;if(id!=null&&!eventSources.has(id))eventSources.set(id,quote);}
      const books=unique(loaded.offers.map(r=>r.book)).sort(),markets=unique(loaded.offers.map(r=>r.market)).sort(),phases=unique(loaded.offers.map(r=>r.phase)).sort();
      options('archive-book',books.map(x=>[x,bookName(x)]),{empty:'Todas',value:''});options('archive-market',markets.map(x=>[x,marketName(x)]),{empty:'Todos',value:''});options('archive-phase',phases.map(x=>[x,phaseLabel(x)]),{empty:'Todas las fases',value:phases.includes('pre_closing')?'pre_closing':phases[0]||''});
      field('archive-provider',loaded.partition.source?.provider||loaded.dataset.manifest.provider);field('archive-source-url',safeSourceURL(loaded.partition.source?.url));field('archive-retrieved',stamp(loaded.partition.source?.retrievedAt));field('archive-sha',loaded.partition.source?.sha256||'No informado');refresh();refreshSelects();
    }catch(error){if(request!==token)return;loaded=null;pricesTable.setRows([]);eventsTable.setRows([]);field('archive-status',error.message||String(error));eligibility();}
  }
  async function chooseDataset(preferred){
    names=maps();const parts=manifest().partitions||[],chosen=parts.find(p=>text(p.id)===preferred)||[...parts].sort((a,b)=>text(b.dateMax).localeCompare(text(a.dateMax))).find(p=>$('archive-dataset').value!=='expanded'||p.league==='E0')||parts[0];
    options('archive-season',unique(parts.map(p=>text(p.season))).sort().reverse().map(x=>[x,x]),{empty:'Todas',value:chosen?.season||''});field('archive-league','');partitionOptions(chosen?.id);await load();
  }
  async function openCatalog(id){const item=catalog.find(r=>r.id===id);if(!item?.partitionId)return;$('archive-dataset').value=item.dataset;$('archive-panel').open=true;await chooseDataset(item.partitionId);$('archive-panel').scrollIntoView?.({block:'start',behavior:'smooth'});}
  function exportCSV(){
    if(!loaded)return;const columns=['date','home','away','league','season','book','market','rawMarketName','period','selection','line','playerId','rawSelectionId','phase','priceType','odds','capturedAt','rawTimestamp','active','suspended','limit','marketStatus','runnerStatus','quality','sourceProvider','sourceUrl','retrievedAt','sourceSha256','sourceColumn','sourceRow','quoteId'];
    const quote=value=>'"'+text(value).replaceAll('"','""')+'"',rows=pricesTable.filtered||[];
    const csv='\uFEFF'+[columns,...rows.map(r=>columns.map(key=>key==='sourceUrl'?safeSourceURL(r[key]):r[key]))].map(values=>values.map(quote).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=`workraken-${$('archive-dataset').value}-${$('archive-partition').value}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),0);
  }
  $('sources-filters').addEventListener('submit',e=>e.preventDefault());$('archive-filters').addEventListener('submit',e=>e.preventDefault());
  $('sources-filters').addEventListener('change',refreshCatalog);
  $('sources-table').addEventListener('click',event=>{const open=event.target.closest('[data-open-archive]'),existing=event.target.closest('[data-open-existing]');if(open)openCatalog(open.dataset.openArchive);if(existing){const panel=$(existing.dataset.openExisting);if(panel){panel.open=true;panel.scrollIntoView?.({block:'start',behavior:'smooth'});}}});
  $('archive-filters').addEventListener('change',event=>{const id=event.target.id;if(id==='archive-dataset')chooseDataset();else if(id==='archive-season'){partitionOptions();load();}else if(id==='archive-partition')load();else if(id!=='archive-league')refresh();});
  $('archive-filters').addEventListener('input',event=>{clearTimeout(inputTimer);inputTimer=setTimeout(()=>{if(event.target.id==='archive-league'){const previous=$('archive-partition').value;partitionOptions(previous);if($('archive-partition').value!==previous)load();else refresh();}else refresh();},160);});
  $('archive-export').addEventListener('click',exportCSV);
  $('archive-use').addEventListener('click',async()=>{if(!eligibility())return;const phase=$('archive-phase').value||unique(loaded.offers.map(r=>r.phase))[0],book=$('archive-book').value,market=$('archive-market').value,selection={dataset:$('archive-dataset').value,partitionId:$('archive-partition').value,phase,...(book?{book}:{}),...(market?{market}:{})},label=[loaded.name,phaseLabel(phase),book?bookName(book):'Todas las casas',market?marketName(market):'Todos los mercados'].join(' · ');try{await onApply(selection,label);applied=selection;field('archive-applied',label);}catch(error){field('archive-status',error.message||String(error));}});
  $('archive-clear').addEventListener('click',async()=>{try{await onClear();applied=null;field('archive-applied','Archivo original');}catch(error){field('archive-status',error.message||String(error));}});
  async function initialize(){if(initialized)return;await archive.initialize();catalog=[...archive.catalog(),...legacyCatalog()];catalogLists();refreshCatalog();const expanded=archive.datasets.get('expanded')?.manifest;field('archive-total-quotes',num(expanded?.quoteCount,0));field('archive-total-events',num(expanded?.eventCount,0));options('archive-dataset',[...archive.datasets.values()].filter(x=>x.manifest).map(x=>[x.id,x.name]),{empty:null,value:archive.datasets.get('expanded')?.manifest?'expanded':archive.datasets.keys().next().value});initialized=true;await chooseDataset();refreshSelects();}
  return {initialize,refresh,refreshCatalog,load,openCatalog,getSelection:()=>applied?{...applied}:null,tables:{sources:sourcesTable,archive:pricesTable,events:eventsTable}};
}
