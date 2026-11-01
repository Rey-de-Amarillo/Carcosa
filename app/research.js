'use strict';

(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const array = value => Array.isArray(value) ? value : [];
  const num = value => value === null || value === undefined || value === '' || typeof value === 'boolean' ? null : Number.isFinite(Number(value)) ? Number(value) : null;
  const count = value => num(value) === null ? '—' : Number(value).toLocaleString('es-AR');
  const dec = (value, digits=3) => num(value) === null ? '—' : Number(value).toLocaleString('es-AR',{minimumFractionDigits:digits,maximumFractionDigits:digits});
  const pct = (value, signed=false) => num(value) === null ? '—' : `${signed && Number(value)>0?'+':''}${(Number(value)*100).toLocaleString('es-AR',{minimumFractionDigits:1,maximumFractionDigits:1})}%`;
  const date = value => {
    if (!value) return '—';
    const raw = /^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? `${value}T12:00:00Z` : value;
    const parsed = new Date(raw);
    return Number.isFinite(parsed.getTime()) ? parsed.toLocaleDateString('es-AR',{day:'2-digit',month:'short',year:'numeric',timeZone:'America/Argentina/Salta'}) : String(value);
  };
  const icon = name => `<svg aria-hidden="true"><use href="#i-${esc(name)}"/></svg>`;
  const sports = {football:'Fútbol',soccer:'Fútbol',basketball:'Básquet',baseball:'Béisbol',hockey:'Hockey',tennis:'Tenis',american_football:'Fútbol americano',australian_football:'Fútbol australiano',rugby:'Rugby',cricket:'Críquet',mma:'MMA',boxing:'Boxeo',golf:'Golf',horse_racing:'Caballos',greyhounds:'Galgos',esports:'Esports',all_supported_sports:'Varios deportes'};
  const state = {report:null, catalog:[], mounted:false, loading:null};
  const text = value => typeof value === 'string' ? value : value && typeof value === 'object' ? value.message || value.summary || value.text || value.name || '' : '';

  function modelName(row) {
    if (row?.name) return row.name.replace(/\bpower\b/gi,'por potencia');
    const id = String(row?.id || '');
    const labels = {v1:'Poisson v1',v1_baseline:'Poisson v1',baseline_v1:'Poisson v1',structural:'Modelo estructural v2',consensus_proportional:'Consenso sin margen proporcional',consensus_power:'Consenso sin margen por potencia',selected:'Modelo seleccionado v2',market_proportional:'Mercado sin margen proporcional',market_power:'Mercado sin margen por potencia',market_shin:'Mercado sin margen de Shin',selected_v2:'Modelo seleccionado v2',v2:'Modelo seleccionado v2'};
    return labels[id] || id.replace(/_/g,' ') || 'Modelo sin nombre';
  }
  function periodLabel(value) { return value === 'selection' ? 'Selección' : value === 'audit' ? 'Revisión retrospectiva' : String(value || '—'); }
  function snapshotLabel(value) { return ({pre:'Anterior al cierre',pre_closing:'Anterior al cierre',closing:'Cierre',post:'Después del cierre'})[value] || String(value || 'Snapshot no informado'); }
  function marketLabel(value) { return ({h2h:'Ganador / 1X2','1x2':'Resultado 1X2',totals25:'Más / menos 2,5',totals:'Total',asian_handicap:'Hándicap asiático'})[value] || String(value || ''); }
  function statusForMarket(market) {
    const status = market.model_status || market.status || '';
    const evaluated=array(state.report?.market_evaluations).filter(item=>num(item.n)>0);
    if(market.key==='first_half' && evaluated.some(item=>/^half_time_/.test(item.id||''))) return {label:'Primer tiempo · exploratorio',type:'exploratory'};
    if(market.key==='corners_total' && evaluated.some(item=>/^corners_/.test(item.id||''))) return {label:'Conteos de córners · exploratorio',type:'exploratory'};
    if(market.key==='cards_total' && evaluated.some(item=>/^yellow_cards_/.test(item.id||''))) return {label:'Amarillas · exploratorio',type:'exploratory'};
    if (status === 'score_distribution_available_research') return {label:'Calculable desde marcador',type:'math'};
    if (/exploratory_count/.test(status)) return {label:'Modelo de conteos exploratorio',type:'exploratory'};
    if (/exploratory/.test(status)) return {label:'Exploratorio',type:'exploratory'};
    if (/period_specific/.test(status)) return {label:'Requiere modelo del período',type:'pending'};
    if (/separate_count/.test(status)) return {label:'Requiere modelo de conteos',type:'pending'};
    if (/sport_specific/.test(status)) return {label:'Requiere modelo del deporte',type:'pending'};
    if (/joint_distribution/.test(status)) return {label:'Dependencia por modelar',type:'pending'};
    if (/not_a_probability/.test(status)) return {label:'Gestión de posición',type:'pending'};
    if (/not_trained|pending/.test(status)) return {label:'Datos o modelo pendientes',type:'pending'};
    return {label:'Requiere validación propia',type:'pending'};
  }
  function comparisonRows() { return array(state.report?.comparison); }
  function auditedPair() {
    const rows = comparisonRows().filter(row => row.period === 'audit');
    const old = rows.find(row => row.id === 'v1');
    const next = rows.find(row => row.id === 'selected');
    return old && next && num(old.n)>0 && num(old.n)===num(next.n) && num(old.log_loss)!==null && num(next.log_loss)!==null ? {old,next} : null;
  }
  function cards() {
    const r=state.report, selected=r.selection?.selected || {}, pair=auditedPair();
    const reduction=pair && Number(pair.old.log_loss)>0 ? (Number(pair.old.log_loss)-Number(pair.next.log_loss))/Number(pair.old.log_loss) : null;
    const future=r.prospective || {};
    const values=[
      {label:'Reducción de log loss frente a v1',value:pct(reduction),className:reduction===null?'research-v2-neutral':reduction>=0?'research-v2-positive':'research-v2-negative',note:pair?`${dec(pair.old.log_loss)} → ${dec(pair.next.log_loss)} · mismos ${count(pair.old.n)} eventos de revisión`:'Se publica cuando ambos modelos tienen la misma muestra de revisión.'},
      {label:'Criterio para elegir el modelo',value:'Log loss',className:'research-v2-neutral',note:`${count(selected.n)} eventos de selección. El ROI de revisión no elige los parámetros.`},
      {label:'Tipos de apuesta estudiados',value:count(state.catalog.length),className:'research-v2-neutral',note:'Cada línea, período, participante y regla se verifica por separado.'},
      {label:'Eventos de validación prospectiva',value:count(future.events),className:'research-v2-neutral',note:`Desde ${date(future.start || r.protocol?.prospective_start)} · ${count(future.captured_events || 0)} pronósticos registrados, ${count(future.pending_events || 0)} pendientes.`}
    ];
    return values.map(item=>`<article class="research-v2-card"><span>${esc(item.label)}</span><strong class="${item.className}">${esc(item.value)}</strong><small>${esc(item.note)}</small></article>`).join('');
  }
  function modelTable() {
    const rows=comparisonRows();
    if (!rows.length) return '<div class="research-v2-empty">Todavía no se publicaron métricas comparables.</div>';
    return `<div class="table-scroll"><table class="research-v2-table"><thead><tr><th>MODELO</th><th>PERÍODO</th><th>EVENTOS</th><th>LOG LOSS ↓</th><th>BRIER ↓</th><th>ACIERTOS</th><th>CALIBRACIÓN ↓</th></tr></thead><tbody>${rows.map(row=>`<tr${row.id==='selected'?' class="selected-row"':''}><td><strong>${esc(modelName(row))}</strong>${row.id==='selected'?'<small>Elegido con el período de selección</small>':''}</td><td><span class="research-v2-period ${row.period==='audit'?'audit':''}">${esc(periodLabel(row.period))}</span></td><td class="numeric">${esc(count(row.n))}</td><td class="numeric">${esc(dec(row.log_loss))}</td><td class="numeric">${esc(dec(row.brier))}</td><td class="numeric">${esc(pct(row.accuracy))}</td><td class="numeric">${esc(pct(row.ece))}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function pairedComparisons() {
    const r=state.report?.improvement||{};
    const values=[['raw_v2_vs_v1','Estructural v2 frente a v1'],['selected_vs_v1','Seleccionado frente a v1'],['selected_vs_market','Seleccionado frente al consenso']].filter(([key])=>r[key]&&num(r[key].improvement)!==null);
    if(!values.length)return '';
    return `<article class="panel"><div class="panel-heading"><div><span class="eyebrow muted">COMPARACIÓN PAREADA</span><h2>Cuánto cambia el error en los mismos eventos</h2></div></div><p class="research-v2-subtitle">Diferencia de log loss de la referencia menos el candidato: positivo indica menor error del candidato. El intervalo describe esta revisión retrospectiva.</p><div class="table-scroll"><table class="research-v2-table"><thead><tr><th>COMPARACIÓN</th><th>EVENTOS</th><th>FECHAS</th><th>MEJORA LOG LOSS</th><th>INTERVALO</th></tr></thead><tbody>${values.map(([key,label])=>{const item=r[key];return `<tr><td><strong>${esc(label)}</strong><small>${esc(text(item.method))}</small></td><td>${esc(count(item.n))}</td><td>${esc(count(item.dates))}</td><td class="numeric ${Number(item.improvement)>=0?'research-v2-positive':'research-v2-negative'}">${esc(dec(item.improvement,4))}</td><td class="numeric">${num(item.low)!==null&&num(item.high)!==null?`${esc(dec(item.low,4))} a ${esc(dec(item.high,4))}`:'—'}</td></tr>`;}).join('')}</tbody></table></div></article>`;
  }
  function candidateTable() {
    const rows=array(state.report?.selection?.candidates);
    if (!rows.length) return '';
    const selected=state.report?.selection?.selected || {};
    return `<details class="research-v2-experiment"><summary>Ver candidatos y parámetros de selección (${esc(count(rows.length))})</summary><div class="table-scroll"><table class="research-v2-table"><thead><tr><th>CANDIDATO</th><th>REMOCIÓN DE MARGEN</th><th>PESO ESTRUCTURAL</th><th>EVENTOS</th><th>LOG LOSS ↓</th></tr></thead><tbody>${rows.map(row=>`<tr${row.id===selected.id?' class="selected-row"':''}><td><strong>${esc(modelName(row))}</strong></td><td>${esc(({proportional:'Proporcional',power:'Potencia',shin:'Shin'})[row.devig]||row.devig||'—')}</td><td>${esc(pct(row.structural_weight))}</td><td>${esc(count(row.n))}</td><td>${esc(dec(row.log_loss,4))}</td></tr>`).join('')}</tbody></table></div></details>`;
  }
  function strategyTable() {
    const rows=array(state.report?.strategies);
    if (!rows.length) return '<div class="research-v2-empty">Sin estrategias publicadas para comparar.</div>';
    return `<div class="table-scroll"><table class="research-v2-table"><thead><tr><th>ESTRATEGIA Y PRECIO</th><th>PERÍODO</th><th>APUESTAS</th><th>ROI</th><th>ROI CON ESTRÉS</th><th>INTERVALO ROI</th><th>CAPITAL FINAL</th><th>CAÍDA MÁXIMA</th></tr></thead><tbody>${rows.map(row=>{const bets=num(row.bets)||0;const roi=bets>0?num(row.roi):null;return `<tr><td><strong>${esc(row.name || row.id || 'Estrategia')}</strong><small>${esc(marketLabel(row.market))} · ${esc(snapshotLabel(row.snapshot))}</small>${row.note?`<small>${esc(text(row.note))}</small>`:''}</td><td><span class="research-v2-period ${row.period==='audit'?'audit':''}">${esc(periodLabel(row.period))}</span></td><td>${esc(count(row.bets))}</td><td class="numeric ${roi===null?'':roi>=0?'research-v2-positive':'research-v2-negative'}">${esc(pct(roi,true))}${bets===0?'<small>Sin exposición</small>':''}</td><td class="numeric">${esc(pct(bets>0?row.stressed_roi:null,true))}</td><td class="numeric">${num(row.ci?.low)!==null && num(row.ci?.high)!==null && bets>0?`${esc(pct(row.ci.low))} a ${esc(pct(row.ci.high))}`:'—'}</td><td class="numeric">${esc(dec(row.final_bankroll,2))}<small>Inicial ${esc(dec(row.initial_bankroll,0))} u.</small></td><td class="numeric">${esc(pct(row.max_drawdown))}</td></tr>`;}).join('')}</tbody></table></div>`;
  }
  function marketEvaluationTable() {
    const rows=array(state.report?.market_evaluations);
    if (!rows.length) return '<div class="research-v2-empty">Los mercados sin una evaluación publicada permanecen pendientes.</div>';
    return `<div class="table-scroll"><table class="research-v2-table"><thead><tr><th>MERCADO Y ALCANCE</th><th>EVENTOS</th><th>BRIER ↓</th><th>LOG LOSS ↓</th><th>ACIERTOS</th><th>BRIER MERCADO ↓</th><th>PRECIOS HISTÓRICOS</th><th>ROI</th></tr></thead><tbody>${rows.map(row=>`<tr><td><strong>${esc(row.name||row.id||'Mercado')}</strong><small>${esc(row.note||'Evaluación propia requerida.')}</small></td><td>${esc(count(row.n))}</td><td>${esc(dec(row.brier))}</td><td>${esc(dec(row.log_loss))}</td><td>${esc(pct(row.accuracy))}</td><td>${esc(dec(row.market_brier))}</td><td>${esc(count(row.odds_events))}</td><td>${esc(pct(row.roi,true))}${num(row.roi)===null?'<small>No se inventa retorno sin precios equivalentes</small>':''}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function protocol() {
    const p=state.report?.protocol||{};
    const stages=[
      ['01 · Desarrollo','Construir con el pasado',`Hasta ${date(p.development_end)}. Estimación de parámetros y construcción de los candidatos.`, ''],
      ['02 · Selección','Elegir por probabilidad',`${date(p.selection_start)} — ${date(p.selection_end)}. Comparación por log loss; parámetros elegidos antes de revisar el período siguiente.`, ''],
      ['03 · Revisión retrospectiva','Período ya inspeccionado',`${date(p.retrospective_audit_start)} — ${date(p.retrospective_audit_end)}. Sirve para comparar, sin llamarlo una prueba nueva o independiente.`, 'audit'],
      ['04 · Prospectiva','Registrar el futuro',`Desde ${date(p.prospective_start)}. Modelo registrado antes de incorporar los nuevos resultados.`, 'prospective']
    ];
    return stages.map(([label,title,copy,css])=>`<article class="research-v2-stage ${css}"><span class="stage-label">${esc(label)}</span><h3>${esc(title)}</h3><p>${esc(copy)}</p></article>`).join('');
  }
  function diagnosis() {
    const d=state.report?.diagnosis||{};
    const s=d.summary && typeof d.summary==='object' ? d.summary : {};
    const summary=text(d.summary)||(num(s.n)>0 ? `En las ${count(s.n)} selecciones simuladas de la corrida v1, la probabilidad media calculada fue ${pct(s.model_probability_mean)}, mientras que la frecuencia de aciertos fue ${pct(s.win_rate)}. La diferencia evidencia sobreconfianza en las selecciones elegidas por aquel modelo.` : 'La revisión separa el error de probabilidad, el precio disponible y la regla de selección. Una estimación extrema puede generar un EV atractivo y pérdidas si está mal calibrada.');
    const findings=array(d.findings||d.reasons||d.notes).map(text).filter(Boolean);
    const weight=num(state.report?.selection?.selected?.structural_weight);
    const stats=num(s.n)>0 ? `<div class="research-v2-diagnosis-stats"><div><span>Probabilidad media v1</span><strong>${esc(pct(s.model_probability_mean))}</strong></div><div><span>Aciertos de esas selecciones</span><strong>${esc(pct(s.win_rate))}</strong></div><div><span>Exceso de confianza medio</span><strong>${num(s.probability_optimism)!==null?`${esc(dec(Number(s.probability_optimism)*100,1))} p.p.`:'—'}</strong></div><div><span>ROI simulado de la corrida v1</span><strong class="research-v2-negative">${esc(pct(s.kelly_roi,true))}</strong></div></div>` : '';
    const blend=weight===null?'':weight===0?'<p><strong>La selección asignó peso cero al modelo estructural.</strong> La predicción elegida coincide con el consenso de mercado por potencia. Esto reduce el error frente a v1; no demuestra una ventaja independiente sobre ese consenso.</p>':`<p>Peso del modelo estructural elegido en selección: <strong>${esc(pct(weight))}</strong>. El resto corresponde a la referencia de mercado definida por el experimento.</p>`;
    return `<p>${esc(summary)}</p>${stats}${blend}${findings.length?`<ul>${findings.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`:''}${candidateTable()}`;
  }
  function viewHtml() {
    const r=state.report, reason=text(r.recommendation?.reason)||'La herramienta conserva el modo de investigación hasta reunir evidencia prospectiva y precios verificables.';
    return `<div class="page-heading"><div><div class="eyebrow">INVESTIGACIÓN V2 · COMPARACIONES REPRODUCIBLES</div><h1>Mejorar la predicción antes de exponer capital<span>.</span></h1><p>Modelos comparados con el mercado, reglas de apuesta transparentes y evaluación específica por familia.</p></div><span class="pill subtle">Versión ${esc(r.meta?.version||'v2')}</span></div><div class="research-v2-cards">${cards()}</div><div class="research-v2-note">${icon('shield')}<div><strong>Revisión retrospectiva; validación futura separada.</strong> ${esc(reason)} El período ya inspeccionado no se presenta como un holdout intacto.</div></div><article class="panel"><div class="panel-heading"><div><span class="eyebrow muted">PROTOCOLO REGISTRADO</span><h2>Cuatro etapas con fechas visibles</h2></div><span class="pill historical">Sin apuestas automáticas</span></div><div class="research-v2-protocol">${protocol()}</div></article><article class="panel"><div class="panel-heading"><div><span class="eyebrow muted">MODELOS Y BENCHMARK</span><h2>La misma muestra, el mismo criterio</h2></div><span class="pill subtle">Menor error es mejor</span></div><p class="research-v2-subtitle">El modelo se elige con el período de selección. Comparar precisión y calibración contra el mercado ayuda a evitar confundir un EV inflado con una ventaja.</p>${modelTable()}<div class="research-v2-footer">Las muestras y períodos están separados; el retorno no decide el ganador de esta comparación.</div></article>${pairedComparisons()}<div class="research-v2-model-grid"><article class="panel"><div class="panel-heading"><div><span class="eyebrow muted">DIAGNÓSTICO Y SELECCIÓN</span><h2>Qué cambió y por qué</h2></div></div><div class="research-v2-diagnosis">${diagnosis()}</div></article><article class="panel"><div class="panel-heading"><div><span class="eyebrow muted">VALIDACIÓN PROSPECTIVA</span><h2>Resultados nuevos, registro previo</h2></div></div><div class="research-v2-diagnosis"><div><span class="research-v2-state">Desde ${esc(date(r.prospective?.start||r.protocol?.prospective_start))}</span><div class="research-v2-prospective-stat">${esc(count(r.prospective?.events))}</div><p>eventos incorporados al registro prospectivo. Un período aún sin resultados no demuestra rentabilidad.</p></div><p>Registro del modelo: ${esc(date(r.prospective?.registered_at))}. Las nuevas predicciones deben conservarse antes de conocer sus resultados.</p></div></article></div><article class="panel"><div class="panel-heading"><div><span class="eyebrow muted">REGLAS ECONÓMICAS POR SEPARADO</span><h2>Precio, exposición y resultado simulado</h2></div></div><p class="research-v2-subtitle">Una política sin apuestas conserva el capital; no se etiqueta como una estrategia rentable. Los precios históricos no comprueban límites, aceptación o ejecutabilidad.</p>${strategyTable()}<div class="research-v2-footer">ROI = resultado neto / importe acumulado apostado. Capital final y caída máxima tienen otra escala. El estrés de precios y los intervalos se conservan cuando el experimento los publica. Las estrategias multicasa y Bet365 seleccionan cohortes diferentes: sus ROI no aíslan causalmente el efecto de comparar precios.</div></article><article class="panel"><div class="panel-heading"><div><span class="eyebrow muted">MERCADOS EVALUADOS</span><h2>Cada objetivo necesita su propia prueba</h2></div></div>${marketEvaluationTable()}</article><article class="panel"><div class="panel-heading"><div><span class="eyebrow muted">LIQUIDACIÓN MATEMÁTICA</span><h2>Empates, cuartos de línea y combinadas</h2></div></div><div class="research-v2-calculation"><div><h3>Valor esperado sobre los retornos</h3><code>EV = (cuota − 1) × W − L</code><p>W suma victoria completa y media victoria ponderada; L suma pérdida completa y media pérdida ponderada. Un empate reembolsable tiene retorno cero. Aplicar p × cuota − 1 a ese contrato puede dar un resultado incorrecto.</p></div><div><h3>La dependencia también se calcula</h3><code>P(local y ambos marcan) = Σ celdas compatibles</code><p>Se suman los marcadores que cumplen ambas condiciones. No se multiplican probabilidades marginales del mismo partido como si fueran independientes. Un bet builder necesita además su precio y reglas reales.</p></div></div></article><article class="panel research-v2-catalog"><div class="panel-heading"><div><span class="eyebrow muted">MAPA DE COBERTURA</span><h2>Explorar tipos de apuesta</h2></div><span class="pill subtle">${esc(count(state.catalog.length))} tipos</span></div><p class="research-v2-subtitle">Disponible para calcular, disponible para entrenar y disponible para apostar son estados distintos. Las variantes de cada casa se verifican dentro de su familia.</p><div class="research-v2-filter"><label>Buscar mercado, dato o regla<input id="research-market-search" type="search" placeholder="Primer goleador, córners, reembolso…"></label><label>Deporte<select id="research-market-sport"><option value="all">Todos los deportes</option></select></label><label>Familia<select id="research-market-family"><option value="all">Todas las familias</option></select></label><label>Estado de modelo<select id="research-market-status"><option value="all">Todos los estados</option><option value="math">Calculable desde marcador</option><option value="exploratory">Exploratorio</option><option value="pending">Pendiente de modelo o datos</option></select></label></div><p id="research-market-count" class="research-v2-catalog-count"></p><div id="research-market-table"></div><div class="research-v2-footer">Fuente del catálogo: documentación de los proveedores y reglas de liquidación consultadas. La cuota de un mercado puede existir aunque falten datos para estimar su probabilidad.</div></article>`;
  }
  function catalogFilters() {
    const sportValues=[...new Set(state.catalog.flatMap(item=>array(item.sports)))].sort((a,b)=>(sports[a]||a).localeCompare(sports[b]||b));
    const families=[...new Set(state.catalog.map(item=>item.family).filter(Boolean))].sort();
    $('#research-market-sport').innerHTML='<option value="all">Todos los deportes</option>'+sportValues.map(v=>`<option value="${esc(v)}">${esc(sports[v]||v)}</option>`).join('');
    $('#research-market-family').innerHTML='<option value="all">Todas las familias</option>'+families.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
    ['research-market-search','research-market-sport','research-market-family','research-market-status'].forEach(id=>$('#'+id).addEventListener(id.endsWith('search')?'input':'change',renderCatalog));
    renderCatalog();
  }
  function renderCatalog() {
    const query=$('#research-market-search').value.trim().normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    const chosenSport=$('#research-market-sport').value, family=$('#research-market-family').value, status=$('#research-market-status').value;
    const rows=state.catalog.filter(item=>{
      const haystack=[item.name,item.family,...array(item.requirements),...array(item.contract_fields)].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
      const sportMatches=chosenSport==='all'||array(item.sports).includes(chosenSport)||array(item.sports).includes('all_supported_sports');
      return (!query||haystack.includes(query))&&sportMatches&&(family==='all'||item.family===family)&&(status==='all'||statusForMarket(item).type===status);
    });
    $('#research-market-count').textContent=`${count(rows.length)} de ${count(state.catalog.length)} tipos · sin ejecución habilitada`;
    $('#research-market-table').innerHTML=rows.length?`<div class="table-scroll"><table class="research-v2-table"><thead><tr><th>MERCADO Y DEPORTE</th><th>ESTADO</th><th>HISTÓRICO Y PRECIOS</th><th>REQUISITOS Y CONTRATO</th></tr></thead><tbody>${rows.map(item=>{const status=statusForMarket(item);return `<tr><td><strong>${esc(item.name||item.key)}</strong><small>${esc(item.family||'')} · ${esc(array(item.sports).map(v=>sports[v]||v).join(' · '))}</small></td><td><span class="research-v2-state ${status.type==='pending'?'pending':''}">${esc(status.label)}</span><small>${item.settlement_engine===true?'Liquidación matemática implementada':typeof item.settlement_engine==='string'?'Depende de una distribución conjunta o del período':'Sin liquidación operativa verificada'}</small></td><td>${esc(item.history_status||'Historial pendiente')}<small>${esc(item.historical_price_status||'Precios históricos pendientes')}</small></td><td><details><summary>Revisar datos y reglas</summary><strong>Datos necesarios</strong><ul>${array(item.requirements).map(v=>`<li>${esc(v)}</li>`).join('')}</ul><strong>Contrato</strong><ul>${array(item.contract_fields).map(v=>`<li>${esc(v)}</li>`).join('')}</ul></details></td></tr>`;}).join('')}</tbody></table></div>`:'<div class="research-v2-empty">No hay tipos de apuesta que coincidan con estos filtros.</div>';
  }
  function activate(updateHash=true) {
    if (!state.mounted) return;
    $$('.page-view').forEach(view=>{view.hidden=view.id!=='view-research-v2';});
    $$('.nav-item').forEach(item=>{const active=item.id==='research-v2-nav';item.classList.toggle('active',active);if(active)item.setAttribute('aria-current','page');else item.removeAttribute('aria-current');});
    $('#breadcrumb-page').textContent='Investigación v2';
    $('#sidebar')?.classList.remove('open');
    if(updateHash){history.replaceState(null,'','#research-v2');window.scrollTo({top:0,behavior:'auto'});}
  }
  function banner() {
    const pair=auditedPair();
    const note=pair?`Revisión en los mismos ${count(pair.old.n)} eventos: log loss ${dec(pair.old.log_loss)} en v1 y ${dec(pair.next.log_loss)} en el candidato seleccionado.`:'Modelos, estrategias y mercados comparados con un protocolo temporal explícito.';
    let node=$('#research-v2-banner');
    if(!node){node=document.createElement('div');node.id='research-v2-banner';node.className='research-v2-banner';$('#overview-metrics').before(node);}
    node.innerHTML=`<div><div class="eyebrow">INVESTIGACIÓN V2</div><strong>Comparar la mejora y revisar los mercados.</strong><p>${esc(note)} La validación prospectiva se registra por separado.</p></div><button class="button secondary" id="research-v2-open">Ver investigación ${icon('arrow')}</button>`;
    $('#research-v2-open').addEventListener('click',()=>activate());
    let mini=$('#research-v2-model-mini');
    if(!mini){mini=document.createElement('article');mini.id='research-v2-model-mini';mini.className='panel research-v2-mini';$('#view-model').append(mini);}
    mini.innerHTML=`<div class="panel-heading"><div><span class="eyebrow muted">EXPERIMENTOS V2</span><h2>Modelos elegidos por precisión, revisión económica separada</h2></div><button class="text-link" id="research-v2-from-model">Ver comparación ${icon('arrow')}</button></div><p>${esc(note)} El período ya inspeccionado no se renombra como un test intacto.</p>`;
    $('#research-v2-from-model').addEventListener('click',()=>activate());
  }
  function mount(report) {
    if (!report || typeof report!=='object' || Array.isArray(report)) return false;
    if (!$('#dashboard-content') || !$('#overview-metrics')) return false;
    state.report=report;state.catalog=array(report.catalog?.markets || report.catalog);
    let nav=$('#research-v2-nav');
    if(!nav){nav=document.createElement('button');nav.id='research-v2-nav';nav.className='nav-item research-v2-nav';nav.innerHTML=`${icon('model')}Investigación v2<span class="count-badge">V2</span>`;$('.navigation').append(nav);nav.addEventListener('click',()=>activate());}
    let section=$('#view-research-v2');
    if(!section){section=document.createElement('section');section.id='view-research-v2';section.className='page-view research-v2-view';section.hidden=true;$('#dashboard-content').append(section);}
    section.innerHTML=viewHtml();catalogFilters();state.mounted=true;banner();
    if(location.hash==='#research-v2') activate(false);
    return true;
  }
  async function refresh() {
    try {
      const response=await fetch('/data/research.json',{cache:'no-store'});
      if(!response.ok) return false;
      const report=await response.json();
      return mount(report);
    } catch {return false;}
  }
  function afterBaseReady() {
    const base=$('#dashboard-content');
    if(!base) return;
    if(!base.hidden){refresh();return;}
    const observer=new MutationObserver(()=>{if(!base.hidden){observer.disconnect();refresh();}});
    observer.observe(base,{attributes:true,attributeFilter:['hidden']});
  }
  window.KrakenResearch={mount,refresh,activate};
  window.addEventListener('hashchange',()=>{if(location.hash==='#research-v2') activate(false);});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',afterBaseReady,{once:true});
  else afterBaseReady();
})();
