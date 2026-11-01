/** Filtering and ranking share one metric scope. Missing values are never zero. */
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const threshold=value=>value==null||String(value).trim()===''||!Number.isFinite(Number(value))?null:Number(value);
const names=(a,b)=>String(a.name||'').localeCompare(String(b.name||''),'es',{numeric:true,sensitivity:'base'})||String(a.id).localeCompare(String(b.id));
const fields={ev:'meanEV',minReturn:'meanMinReturn',roi:'roi',profit:'profit',n:'n',winRate:'winRate',odds:'meanOdds'};
export function filterAndSortFormulas(formulas,metricsMap,{sort='ev_desc',minEV='',minROI='',minN='',minReturn=''}={}){
  const limits={meanMinReturn:threshold(minReturn),meanEV:threshold(minEV),roi:threshold(minROI),n:threshold(minN)};
  if(limits.meanMinReturn!=null)limits.meanMinReturn/=100;
  if(limits.meanEV!=null)limits.meanEV/=100;
  if(limits.roi!=null)limits.roi/=100;
  const metrics=formula=>{const row=metricsMap.get(formula.id);return row?.state==='ready'?row:null;};
  const rows=formulas.filter(formula=>{
    const m=metrics(formula);
    return Object.entries(limits).every(([key,min])=>min==null||finite(m?.[key])&&m[key]>=min);
  });
  const [key,direction]=sort.split('_'),field=fields[key];
  return rows.sort((a,b)=>{
    if(!field)return direction==='desc'?-names(a,b):names(a,b);
    const av=metrics(a)?.[field],bv=metrics(b)?.[field],ak=finite(av),bk=finite(bv);
    if(ak!==bk)return ak?-1:1;
    if(ak&&av!==bv)return direction==='asc'?av-bv:bv-av;
    return names(a,b);
  });
}
