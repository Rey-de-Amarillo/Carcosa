/** Football badges decorate the original Workraken selectors without changing them. */
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normalize=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('es').replace(/[^a-z0-9]/g,'');
const safeAsset=src=>typeof src==='string'&&/^assets\/football\/[a-z0-9/_-]+\.png$/i.test(src)?src:null;
export function createEntityPresentation(entities={},badges={}){
  const teams=new Map((entities.teams||[]).map(t=>[t.id,t])),players=new Map((entities.players||[]).map(p=>[p.id,p]));
  const leagues=new Map((entities.leagues||[]).map(l=>[l.id,l]));const aliases=new Map(Object.entries(entities.teamAliasIndex||{})),globalAliases=new Map();
  for(const team of teams.values())for(const name of [team.name,...(team.aliases||[])]){const key=normalize(name);if(!globalAliases.has(key))globalAliases.set(key,team.id);else if(globalAliases.get(key)!==team.id)globalAliases.set(key,null);}
  function resolveTeam(value,league=''){
    if(teams.has(value))return value;
    if(String(value).startsWith('team:')&&teams.has(String(value).slice(5)))return String(value).slice(5);
    return aliases.get(`${league}|${normalize(value)}`)||globalAliases.get(normalize(value))||null;
  }
  function teamBadge(value,league=''){const id=resolveTeam(value,league);return id?badges.teams?.[id]||null:null;}
  function images(badge){if(!badge)return [];const list=[];if(safeAsset(badge.logoSrc))list.push({src:badge.logoSrc,kind:'crest'});if(safeAsset(badge.flagSrc))list.push({src:badge.flagSrc,kind:'flag'});return list;}
  function iconsHTML(badge){const files=images(badge);return files.length?`<span class="football-entity-icons" aria-hidden="true">${files.map(i=>`<img src="${esc(i.src)}" class="football-entity-${i.kind}" alt="" loading="lazy" decoding="async">`).join('')}</span>`:'';}
  function teamHTML(value,league=''){const id=resolveTeam(value,league),name=teams.get(id)?.name||value;return `<span class="football-entity-label">${iconsHTML(teamBadge(value,league))}<span>${esc(name)}</span></span>`;}
  function leagueHTML(id){return `<span class="football-entity-label">${iconsHTML(badges.leagues?.[id])}<span>${esc(leagues.get(id)?.name||id)}</span></span>`;}
  return {teams,players,leagues,resolveTeam,teamBadge,images,iconsHTML,teamHTML,leagueHTML,badges};
}
export function initEntityPresentation(root,entities,badges){
  const view=createEntityPresentation(entities,badges),doc=root.nodeType===9?root:root.ownerDocument,surface=root.nodeType===9?root.documentElement:root;
  let queued=false,stopped=false;
  function sideTeam(select,side){const builder=select.closest('#formula-builder');return builder?.querySelector(`select[data-key="context.${side}Team"]`)?.value||'';}
  function actionTeam(select,key){
    const builder=select.closest('#formula-builder'),field=name=>builder?.querySelector(`select[data-key="${key}.${name}"]`)?.value,market=field('market');
    if(!['match_result','team_goals','player_goals','corners'].includes(market))return '';
    const value=field(market==='match_result'?'selection':'team');
    if(value==='home'||value==='away')return sideTeam(select,value);
    return view.resolveTeam(value)||'';
  }
  function descriptor(select,option){
    const value=option?.value;if(!value)return null;
    if(view.badges.leagues?.[value])return view.badges.leagues[value];
    const direct=view.resolveTeam(value);if(direct)return view.teamBadge(direct);
    const player=view.players.get(value);if(player)return view.teamBadge(player.teamId);
    if(!select.closest('#formula-builder'))return null;
    if(value==='home'||value.startsWith('home_'))return view.teamBadge(sideTeam(select,'home'));
    if(value==='away'||value.startsWith('away_'))return view.teamBadge(sideTeam(select,'away'));
    const leg=value.match(/^leg_(\d+)_odds$/);if(leg)return view.teamBadge(actionTeam(select,`legs.${Number(leg[1])-1}`));
    if(value==='selected_odds')return view.teamBadge(actionTeam(select,'action'));
    return null;
  }
  function decorate(node,badge){
    if(!node)return;const files=view.images(badge),signature=JSON.stringify(files),existing=[...node.children].find(c=>c.classList.contains('football-entity-icons'));
    if(!files.length){existing?.remove();delete node.dataset.footballBadge;return;}
    if(existing&&node.dataset.footballBadge===signature)return;
    existing?.remove();const span=doc.createElement('span');span.className='football-entity-icons';span.setAttribute('aria-hidden','true');
    for(const file of files){const image=doc.createElement('img');image.src=file.src;image.alt='';image.className=`football-entity-${file.kind}`;image.loading='lazy';image.decoding='async';span.append(image);}
    node.prepend(span);node.dataset.footballBadge=signature;
  }
  function relevant(select){
    if(select.classList.contains('record-page-select')||select.classList.contains('record-page-size-select'))return false;
    const key=select.dataset.key||'';return /^(context\.(league|homeTeam|awayTeam)|result)$|\.(team|playerId)$/.test(key)||/\.selection\.selection$/.test(key)&&select.closest('[data-situation-panel]')?.querySelector('select[data-key$=".selection.market"]')?.value==='match_result'||select.hasAttribute('data-condition-field')||/(league|team)$/.test(select.id);
  }
  function refresh(){
    queued=false;if(stopped)return;
    for(const select of surface.querySelectorAll('select')){
      if(!relevant(select))continue;const wrapper=select.nextElementSibling;if(!wrapper?.classList.contains('currency-country-picker'))continue;
      decorate(wrapper.querySelector('.currency-country-trigger'),descriptor(select,select.selectedOptions[0]));
      for(const item of wrapper.querySelectorAll('.currency-country-option[data-index]'))decorate(item,descriptor(select,select.options[Number(item.dataset.index)]));
    }
  }
  function schedule(){if(!queued&&!stopped){queued=true;queueMicrotask(refresh);}}
  const observer=new MutationObserver(records=>{
    if(records.every(r=>r.target.closest?.('.football-entity-icons')||[...r.addedNodes,...r.removedNodes].every(n=>n.nodeType===1&&n.classList?.contains('football-entity-icons'))))return;
    schedule();
  });
  observer.observe(surface,{childList:true,subtree:true});
  const onChange=()=>schedule(),onError=event=>{if(event.target.matches?.('.football-entity-icons img'))event.target.hidden=true;};
  surface.addEventListener('change',onChange);surface.addEventListener('error',onError,true);refresh();
  return {...view,refresh,destroy(){stopped=true;observer.disconnect();surface.removeEventListener('change',onChange);surface.removeEventListener('error',onError,true);}};
}
