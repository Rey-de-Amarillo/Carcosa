/** Source-preserving archives. Load one bounded partition, never every price. */
const MANIFESTS=Object.freeze({expanded:'expanded-football-manifest.json',additional:'additional-market-manifest.json',research:'research-market-manifest.json'});
const LABELS={expanded:'Football-Data · archivo ampliado',additional:'SGodds · mercados adicionales',research:'Archivos de investigación'};
const records=table=>Array.isArray(table)?table:(table?.rows||[]).map(row=>Object.fromEntries(table.columns.map((key,i)=>[key,row[i]])));
export async function readArchiveJSON(path,gzip=false){
  if(!/^[a-zA-Z0-9_.-]+$/.test(path))throw new Error('Ruta de archivo no válida.');
  const response=await fetch(`data/${path}`);if(!response.ok)throw new Error(`No se pudo cargar ${path} (${response.status}).`);
  if(!gzip)return response.json();const buffer=await response.arrayBuffer();
  if(new Uint8Array(buffer)[0]!==31)return JSON.parse(new TextDecoder().decode(buffer));
  return new Response(new Blob([buffer]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
}
export function safeSourceURL(value){
  try{const url=new URL(String(value||''));if(!['https:','http:'].includes(url.protocol))return '';url.username='';url.password='';url.hash='';for(const key of [...url.searchParams.keys()])if(/key|token|secret|auth|signature|credential|password/i.test(key))url.searchParams.delete(key);return url.href;}catch{return '';}
}
const text=x=>String(x??'');
const workspaceSourceIndexes=new WeakMap();
export function sourceForWorkspaceEvent(data,event){
  const start=String(event?.season||'').match(/(\d{4})\D+(\d{2,4})/);let source;
  const manifest=data.manifest;
  if(start&&manifest){
    let index=workspaceSourceIndexes.get(manifest);
    if(!index){index=new Map();for(const item of manifest.sources?.files||[]){const match=safeSourceURL(item.url).match(/\/mmz4281\/([^/]+)\/([^/]+)\.csv$/);if(match)index.set(`${match[1]}|${match[2]}`,item);}workspaceSourceIndexes.set(manifest,index);}
    source=index.get(`${start[1].slice(-2)}${start[2].slice(-2)}|${event.league}`);
  }
  return {provider:data.manifest?.sources?.provider||'Football-Data.co.uk',url:safeSourceURL(source?.url||data.manifest?.sources?.provider_url),retrievedAt:source?.retrievedAt||source?.retrieved_at||null,sha256:source?.sha256||null,phase:'pre_closing',sourceRow:null,sourceColumn:null};
}
export function sourceForPlayer(data,player){
  const source=data.entities?.sources?.find(s=>s.id===player.source)||{},url=safeSourceURL(source.url);
  return {provider:url.includes('premierleague.com')?'Fantasy Premier League':url.includes('espn.com')?'ESPN':url?new URL(url).hostname:'Fuente no identificada',url,retrievedAt:source.asOf||player.asOf||null,sha256:source.sha256||null};
}
export class FootballDataArchive{
  constructor({read=readArchiveJSON,cacheLimit=2}={}){this.read=read;this.cacheLimit=cacheLimit;this.datasets=new Map();this.cache=new Map();this.pending=new Map();}
  async initialize(){
    if(this.initialized)return this;
    for(const [id,path]of Object.entries(MANIFESTS))if(!this.datasets.has(id))this.datasets.set(id,{id,path,name:LABELS[id]});
    if(!this.initializing)this.initializing=Promise.all(Object.entries(MANIFESTS).map(async([id,path])=>{try{const manifest=await this.read(path);this.datasets.set(id,{id,path,name:LABELS[id],manifest});}catch(error){this.datasets.set(id,{id,path,name:LABELS[id],error:error.message});}})).then(()=>{this.initialized=true;return this;}).finally(()=>this.initializing=null);
    return this.initializing;
  }
  selection(raw){
    if(!raw||!Object.hasOwn(MANIFESTS,raw.dataset))throw new Error('Elegí un archivo de datos válido.');
    const result={dataset:raw.dataset,partitionId:text(raw.partitionId),phase:text(raw.phase)};
    for(const key of ['book','market'])if(raw[key])result[key]=text(raw[key]);
    return result;
  }
  async partition(raw){await this.initialize();const selection=this.selection(raw),dataset=this.datasets.get(selection.dataset);if(dataset.error)throw new Error(dataset.error);const partition=dataset.manifest.partitions?.find(p=>text(p.id)===selection.partitionId);if(!partition)throw new Error('El archivo elegido no está en el catálogo.');if(!/^[a-zA-Z0-9_.-]+\.json(?:\.gz)?$/.test(partition.path))throw new Error('Ruta de datos no válida.');return {selection,dataset,partition};}
  async loadPartition(raw){
    const context=await this.partition(raw),key=`${context.selection.dataset}|${context.selection.partitionId}`;
    if(this.cache.has(key)){const hit=this.cache.get(key);this.cache.delete(key);this.cache.set(key,hit);return hit;}
    if(this.pending.has(key))return this.pending.get(key);
    const pending=this.read(context.partition.path,context.partition.path.endsWith('.gz')).then(payload=>{
      const {dataset,partition}=context,sourceMap=new Map((dataset.manifest.sources||[]).map(s=>[text(s.id),s]));
      const events=records(payload.events).map((event,index)=>({...event,id:`archive:${dataset.id}:${partition.id}:${event.id??index}`,sourceEventId:event.sourceEventId??event.id,date:event.date||'',home:event.home??event.home_team??event.eventName??'',away:event.away??event.away_team??'',league:event.league??partition.league??'',season:event.season??partition.season??'',sourceScope:event.scope??partition.quality??null}));
      const rawQuotes=payload.quotes?records(payload.quotes):(payload.events||[]).flatMap((event,index)=>(event.marketQuotes||[]).map(q=>({...q,event:index})));
      const offers=[];
      for(const [index,q]of rawQuotes.entries()){
        const event=events[Number(q.event)];if(!event)throw new Error('La cuota refiere a un partido que no está en el archivo.');
        const file=sourceMap.get(text(q.sourceFileId??event.sourceFileId))||partition.source||{},provider=q.sourceProvider??file.provider??dataset.manifest.provider;
        const row={...q,event:Number(q.event),eventId:event.id,id:event.id,quoteId:q.quoteId??`${dataset.id}:${partition.id}:${index}`,date:event.date,home:event.home,away:event.away,league:event.league,season:event.season,book:text(q.book??q.bookmaker),market:q.market,period:q.period||'full',phase:q.phase??q.quotePhase??event.quotePhase??'archive_timestamp_unknown',sourceProvider:provider,sourceUrl:safeSourceURL(q.sourceUrl??file.url??dataset.manifest.sourceUrl),sourceSha256:q.sourceSha256??file.sha256??null,retrievedAt:q.retrievedAt??file.retrievedAt??file.retrieved_at??null,sourceColumn:q.sourceColumn??q.sourceField??null,sourceRow:q.sourceRow??null,quality:q.quality??event.sourceScope??partition.quality??null};
        // A file download, fixture date, and pre/closing label are not a capture.
        // Original optional metadata is kept; absent timestamps stay absent.
        if(dataset.id==='expanded'&&row.book==='PS'&&event.date>='2025-07-23')row.quality=[row.quality,'Pinnacle: el proveedor advierte precios potencialmente desactualizados desde 23/07/2025'].filter(Boolean).join(' · ');
        if(!Object.hasOwn(q,'probability'))row.probability=null;if(!Array.isArray(q.references))row.references=[];
        offers.push(row);
      }
      const result={...context,events,offers,name:`${dataset.name} · ${partition.label||partition.id}`,books:dataset.manifest.books||[],leagues:dataset.manifest.leagues||[]};
      this.cache.set(key,result);while(this.cache.size>this.cacheLimit)this.cache.delete(this.cache.keys().next().value);return result;
    }).finally(()=>this.pending.delete(key));this.pending.set(key,pending);return pending;
  }
  async strategyUniverse(raw){
    const selection=this.selection(raw);if(selection.dataset==='research')throw new Error('Este archivo conserva mercados sin normalizar y se consulta en Datos.');
    const loaded=await this.loadPartition(selection),phases=[...new Set(loaded.offers.map(q=>q.phase))];
    if(selection.phase==='all'||!selection.phase&&phases.length>1)throw new Error('Elegí una fase para calcular sin mezclar precios iniciales y de cierre.');
    if(selection.phase&&!phases.includes(selection.phase))throw new Error('La fase elegida no existe en este archivo.');
    const offers=loaded.offers.filter(q=>(!selection.phase||q.phase===selection.phase)&&(!selection.book||q.book===selection.book)&&(!selection.market||q.market===selection.market));
    return {...loaded,offers,name:`${loaded.name} · ${selection.phase||phases[0]||'archivo'}`};
  }
  catalog(){
    const rows=[];
    for(const dataset of this.datasets.values())if(dataset.manifest)for(const partition of dataset.manifest.partitions||[]){const source=partition.source||{};rows.push({id:`${dataset.id}:${partition.id}`,dataset:dataset.id,partitionId:text(partition.id),name:dataset.name,label:partition.label||partition.id,provider:source.provider||dataset.manifest.provider,sourceUrl:safeSourceURL(source.url||dataset.manifest.sourceUrl),sha256:source.sha256||null,retrievedAt:source.retrievedAt||source.retrieved_at||dataset.manifest.generatedAt||null,events:partition.eventCount??null,quotes:partition.quoteCount??null,dateMin:partition.dateMin,dateMax:partition.dateMax,season:partition.season,league:partition.league,leagues:partition.leagues||[],books:partition.books||[],markets:partition.markets||[],phases:partition.phases||[],quality:partition.quality||dataset.manifest.quality||'Cuotas archivadas',path:partition.path});}
    return rows;
  }
}
