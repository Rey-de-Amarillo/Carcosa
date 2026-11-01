/** Derived, indexed football tables. Prices and probabilities retain source precision. */
import {UNIFIED_FORMULA_KIND} from './football-unified-formula.js';
import {PRICE_FORMULA_KIND} from './football-price-engine.js';
import {FootballDataArchive,sourceForWorkspaceEvent} from './football-data-archive.js';
export const periodMatches=(row,period)=>period==='all'||(period==='test'?row.date>='2022-01-01':row.date<'2022-01-01');
export async function readData(path,gzip=false){
  const response=await fetch(`data/${path}`);if(!response.ok)throw new Error(`No se pudo cargar ${path} (${response.status}).`);
  if(!gzip)return response.json();
  const bytes=await response.arrayBuffer();if(new Uint8Array(bytes)[0]!==31)return JSON.parse(new TextDecoder().decode(bytes));
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
}
export class FootballData {
  constructor(){this.events=[];this.offers=[];this.byEvent=new Map();this.loaded=new Set();this.loading=new Map();this.archive=new FootballDataArchive({read:readData});}
  async initialize(){
    [this.manifest,this.entities,this.badges]=await Promise.all([readData('workspace.json'),readData('entities.json'),readData('entity-badges.json')]);const table=await readData(this.manifest.tables.events.path,true);
    // The helper resolves a recorded source file. Neither the fixture date nor
    // the file download date becomes a fabricated quote capture timestamp.
    this.events=table.rows.map(raw=>{
      const e=Object.fromEntries(table.columns.map((k,i)=>[k,raw[i]])),source=sourceForWorkspaceEvent(this,e);
      return {...e,home:e.home_team,away:e.away_team,sourceProvider:source.provider,sourceUrl:source.url||null,sourceSha256:source.sha256,sourceRetrievedAt:source.retrievedAt};
    });
    this.books=new Map(this.manifest.books.map(b=>[b.code,b.name]));this.books.set('SGP','Singapore Pools');this.leagues=new Map(this.entities.leagues.map(l=>[l.id,l.name]));return this;
  }
  async ensureOffers(period){
    const years=new Set(this.events.filter(e=>periodMatches(e,period)).map(e=>e.date.slice(0,4)));
    await Promise.all(this.manifest.tables.offers.parts.filter(p=>years.has(String(p.year))).map(part=>{
      if(this.loaded.has(part.year))return;
      if(this.loading.has(part.year))return this.loading.get(part.year);
      const pending=readData(part.path,true).then(table=>{
        const c=Object.fromEntries(table.columns.map((key,i)=>[key,i]));
        // Retain contract provenance verbatim; optional aliases only copy
        // source values. A date of the match is never a quote capture time.
        for(const r of table.rows){const raw=Object.fromEntries(table.columns.map((key,index)=>[key,r[index]])),e=this.events[raw.event];const row={...raw,id:e.id,event:raw.event,date:e.date,league:e.league,home:e.home,away:e.away,book:raw.book,side:raw.side,odds:raw.odds,probability:raw.probability,referenceMean:raw.referenceMean??raw.reference_mean,referenceSd:raw.referenceSd??raw.reference_sd,references:raw.references,ev:raw.ev,won:typeof raw.won==='boolean'?raw.won:null,profit:raw.profit,ownProbability:raw.ownProbability??raw.own_probability,bookmakerMargin:raw.bookmakerMargin??raw.bookmaker_margin};
          for(const key of ['sourceProvider','sourceUrl','sourceSha256','sourceRetrievedAt'])if(row[key]==null)row[key]=e[key]??null;
          row.sourceTable=part.path;
          if(raw.quoteId!=null||raw.id!=null)row.quoteId=raw.quoteId??raw.id;
          for(const [canonical,alias] of [['referenceProbability','reference_probability'],['pushProbability','push_probability'],['snapshotId','snapshot_id'],['rulesId','rules_id']])if(row[canonical]==null&&raw[alias]!=null)row[canonical]=raw[alias];
          this.offers.push(row);if(!this.byEvent.has(row.event))this.byEvent.set(row.event,[]);this.byEvent.get(row.event).push(row);}
        this.loaded.add(part.year);
      }).finally(()=>this.loading.delete(part.year));this.loading.set(part.year,pending);return pending;
    }));
  }
  async ensureMarketHistory(){
    if(this.marketHistory)return this.marketHistory;
    if(!this.marketLoading)this.marketLoading=readData('football-market-history.json.gz',true).then(payload=>{this.marketHistory=payload;for(const event of payload.events){event.sourceProvider??=payload.source?.name||null;event.sourceUrl??=payload.source?.url||null;for(const quote of event.marketQuotes||[]){quote.sourceProvider??=payload.source?.name||null;quote.sourceUrl??=event.sourceUrl;}}this.marketEventById=new Map(payload.events.map(e=>[e.id,e]));return payload;}).finally(()=>this.marketLoading=null);
    return this.marketLoading;
  }
  usesGoalArchive(rule){
    const a=rule.action,quotedMarkets=new Set(['correct_score','total_goals','btts']);
    if(!a)return false;
    // These new contracts can be settled from this archive's match/half scores.
    // They have no archived quote of their own: use this smaller universe only
    // when an explicitly observed goals price requires it.
    const scoreMarkets=new Set(['match_result',...quotedMarkets,'double_chance','draw_no_bet',
      'handicap_result','asian_handicap','half_time_full_time','odd_even',
      'team_to_score','clean_sheet','win_to_nil','result_btts']);
    const legacyCombination=a.market==='combination'&&a.legs.every(l=>quotedMarkets.has(l.market)||l.market==='match_result');
    const actionSupported=a.market==='combination'?a.legs.every(l=>scoreMarkets.has(l.market)):scoreMarkets.has(a.market);
    const observationNeedsArchive=(rule.conditions||[]).some(c=>c.selection&&(quotedMarkets.has(c.selection.market)||c.selection.market==='match_result'&&c.selection.period!=='full'));
    return quotedMarkets.has(a.market)||(a.market==='match_result'&&a.period!=='full')||legacyCombination||observationNeedsArchive&&actionSupported;
  }
  async strategyUniverse(rule){
    if([UNIFIED_FORMULA_KIND,PRICE_FORMULA_KIND].includes(rule.kind))return this.unifiedStrategyUniverse();
    if(this.usesGoalArchive(rule)){
      const payload=await this.ensureMarketHistory();return {...payload,name:'Archivo de marcadores y goles · Singapore Pools'};
    }
    await this.ensureOffers('all');return {events:this.events,offers:this.offers,name:'Archivo de cuotas comparadas · 1X2'};
  }
  async unifiedStrategyUniverse(){
    if(this.unifiedUniverse)return this.unifiedUniverse;
    if(!this.unifiedLoading)this.unifiedLoading=Promise.all([this.ensureOffers('all'),this.ensureMarketHistory()]).then(([,archive])=>{
      // Source identifiers describe different archives, not verified shared matches.
      // Keep both event identities and all actual quote contracts intact.
      const events=[...this.events],offers=[...this.offers],ids=new Set(events.map(e=>String(e.id)));
      for(const source of archive.events){
        const base=`market-history:${source.id}`;let id=base,suffix=1;while(ids.has(id))id=`${base}:${suffix++}`;ids.add(id);
        const event={...source,id,sourceEventId:source.id},index=events.length;events.push(event);
        for(const quote of source.marketQuotes||[])offers.push({probability:null,ev:null,references:[],...quote,id,event:index,eventId:id,date:event.date,league:event.league,home:event.home??event.home_team,away:event.away??event.away_team});
      }
      return this.unifiedUniverse={events,offers,name:'Archivos de cuotas comparadas y mercados de goles'};
    }).finally(()=>this.unifiedLoading=null);
    return this.unifiedLoading;
  }
}
