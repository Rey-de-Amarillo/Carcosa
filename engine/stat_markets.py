"""Prior-only models for half-time, corners and yellow-card counts.

These families have no matched historical betting prices in the ingested data.
They evaluate forecasts, never manufacture a betting ROI or a stake.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import groupby

from .models_v2 import score_grid


FAMILIES = {
    "period_half": {"columns": ("home_ht_score", "away_ht_score"), "prior": (.65,.50), "cap": 3.5,
                    "name": "Primer tiempo", "model": "half_time_empirical_bayes_poisson_v2"},
    "corners": {"columns": ("home_corners", "away_corners"), "prior": (5.,4.), "cap": 20.,
                "name": "Córners", "model": "corners_regularized_negative_binomial_v2"},
    "yellow_cards": {"columns": ("home_yellow", "away_yellow"), "prior": (1.7,1.9), "cap": 8.,
                     "name": "Tarjetas amarillas", "model": "yellow_cards_regularized_negative_binomial_v2"},
}


def _day(value):
    return date.fromisoformat(str(value)[:10])


def _count(value):
    if value is None or isinstance(value,bool) or str(value).strip()=="":
        return None
    try:
        value=float(value)
        return int(value) if math.isfinite(value) and value>=0 and int(value)==value else None
    except (TypeError,ValueError):
        return None


def observed_counts(row, family):
    cols=FAMILIES[family]["columns"]
    values=(_count(row.get(cols[0])),_count(row.get(cols[1])))
    return None if None in values else values


def count_over_probability(mean, line, alpha=0.):
    """P(count > line), with NB variance = mean + alpha * mean**2."""
    mean,alpha,line=float(mean),float(alpha),float(line)
    if not all(math.isfinite(x) for x in (mean,alpha,line)) or mean<0 or alpha<0:
        raise ValueError("Parámetros de conteo inválidos")
    if line<0:return 1.
    if mean==0:return 0.
    cutoff=math.floor(line)
    if cutoff>10000:raise ValueError("Línea fuera del dominio previsto")
    if alpha<1e-6:
        mass=math.exp(-mean);cdf=mass
        for k in range(1,cutoff+1):mass*=mean/k;cdf+=mass
    else:
        shape=1/alpha;q=mean/(shape+mean)
        mass=math.exp(-shape*math.log1p(mean/shape));cdf=mass
        for k in range(1,cutoff+1):mass*=(shape+k-1)*q/k;cdf+=mass
    return max(0.,min(1.,1-cdf))


@dataclass
class TeamCounts:
    games:float=0.
    scored:float=0.
    allowed:float=0.
    seen:int=0


class StatCountModel:
    """Separate count state for one league and one statistical target."""
    def __init__(self,family,half_life_days=365.,prior_games=20.):
        if family not in FAMILIES:raise ValueError("Familia de estadística desconocida")
        if half_life_days<=0 or prior_games<=0:raise ValueError("Regularización inválida")
        self.family=family;self.spec=FAMILIES[family]
        self.half_life_days=float(half_life_days);self.prior_games=float(prior_games)
        self.teams={};self.games=0.;self.home_sum=0.;self.away_sum=0.;self.seen=0
        self.dispersion_numerator=0.;self.dispersion_denominator=0.
        self.as_of=None;self.training_max_date=None;self.last_batch_date=None

    def advance(self,day):
        day=_day(day)
        if self.as_of is not None:
            if day<self.as_of:raise ValueError("No se puede retroceder la fecha")
            f=2**(-(day-self.as_of).days/self.half_life_days)
            self.games*=f;self.home_sum*=f;self.away_sum*=f
            self.dispersion_numerator*=f;self.dispersion_denominator*=f
            for t in self.teams.values():t.games*=f;t.scored*=f;t.allowed*=f
        self.as_of=day

    def _rates(self,home,away):
        ph,pa=self.spec["prior"]
        bh=(self.home_sum+20*ph)/(self.games+20)
        ba=(self.away_sum+20*pa)/(self.games+20)
        overall=(bh+ba)/2;k=self.prior_games
        h=self.teams.get(home,TeamCounts());a=self.teams.get(away,TeamCounts())
        ah=(h.scored+k*overall)/(h.games+k)/overall
        aa=(a.scored+k*overall)/(a.games+k)/overall
        dh=(h.allowed+k*overall)/(h.games+k)/overall
        da=(a.allowed+k*overall)/(a.games+k)/overall
        # Fixed shrinkage on the log-strength product, avoiding multiplication
        # of two noisy unshrunk team ratios as if they were known strengths.
        cap=self.spec["cap"]
        return min(cap,max(.05,bh*math.sqrt(ah*da))),min(cap,max(.05,ba*math.sqrt(aa*dh)))

    def dispersion(self):
        if self.family=="period_half":return 0.
        prior_mean=sum(self.spec["prior"])
        prior_denom=30*prior_mean*prior_mean
        alpha=(self.dispersion_numerator+.10*prior_denom)/(self.dispersion_denominator+prior_denom)
        return min(1.,max(0.,alpha))

    def predict(self,home,away,day,neutral=False):
        day=_day(day)
        if self.last_batch_date is not None and day<=self.last_batch_date:
            raise ValueError("La predicción sólo usa fechas anteriores")
        self.advance(day)
        lh,la=self._rates(home,away);mean=lh+la;alpha=self.dispersion()
        h=self.teams.get(home,TeamCounts());a=self.teams.get(away,TeamCounts())
        sample=min(h.seen,a.seen);effective=min(h.games,a.games)
        age=(day-self.training_max_date).days if self.training_max_date else None
        neutral=str(neutral).lower() in ("true","1","yes")
        reasons=[]
        if self.seen<120 or sample<8 or effective<6:reasons.append("Muestra previa insuficiente para esta estadística")
        if age is None or age>45:reasons.append("Historial de esta estadística desactualizado")
        if neutral:reasons.append("Cancha neutral sin validación específica")
        out={"model":self.spec["model"],"home_rate":lh,"away_rate":la,"mean_total":mean,
             "sample_size":sample,"effective_sample_size":effective,"league_sample_size":self.seen,
             "training_max_date":self.training_max_date.isoformat() if self.training_max_date else None,
             "model_age_days":age,"eligible":not reasons,"reasons":reasons,"alpha":alpha,
             "distribution":"poisson" if alpha<1e-6 else "negative_binomial",
             "execution_enabled":False,"odds_events":0,"roi":None,
             "uncertainty_label":"Sensibilidad heurística de la media; no es un intervalo de confianza validado"}
        radius=1.96*math.sqrt((mean+alpha*mean*mean)/max(1.,effective))
        out["mean_sensitivity"]={"low":max(0.,mean-radius),"high":mean+radius,
                                 "method":"heuristic_not_calibrated"}
        if self.family=="period_half":
            out.update(score_grid(lh,la))
            out["prob_over_0_5"]=1-out["grid"][0][0]
            out["prob_over_1_5"]=sum(p for h,row in enumerate(out["grid"]) for a,p in enumerate(row) if h+a>1)
        else:
            lines=(8.5,9.5,10.5) if self.family=="corners" else (3.5,4.5)
            for line in lines:
                key="prob_over_"+str(line).replace(".","_")
                out[key]=count_over_probability(mean,line,alpha)
                # Human/reference alias requested by callers; both spellings
                # refer to the same exact half-goal line, never an integer push.
                out["prob_over_"+str(line)]=out[key]
        return out

    def update_batch(self,rows):
        if not rows:return
        days={_day(r["date"]) for r in rows}
        if len(days)!=1:raise ValueError("El lote debe contener una fecha completa")
        day=next(iter(days))
        if self.last_batch_date is not None and day<=self.last_batch_date:raise ValueError("Resultados fuera de orden")
        self.advance(day)
        accepted=[]
        for row in rows:
            counts=observed_counts(row,self.family)
            if counts is None or str(row.get("neutral_venue","false")).lower() in ("true","1","yes"):continue
            h,a=row["home_team"],row["away_team"]
            if not h or not a or h==a:raise ValueError("Participantes inválidos")
            lh,la=self._rates(h,a)
            accepted.append((h,a,*counts,lh+la))
        # All residuals and intensities above use the state before this date.
        for h,a,hc,ac,prior_mean in accepted:
            ht=self.teams.setdefault(h,TeamCounts());at=self.teams.setdefault(a,TeamCounts())
            ht.games+=1;ht.scored+=hc;ht.allowed+=ac;ht.seen+=1
            at.games+=1;at.scored+=ac;at.allowed+=hc;at.seen+=1
            self.games+=1;self.home_sum+=hc;self.away_sum+=ac;self.seen+=1
            total=hc+ac
            self.dispersion_numerator+=(total-prior_mean)**2-total
            self.dispersion_denominator+=prior_mean*prior_mean
        if accepted:self.training_max_date=day
        self.last_batch_date=day


def _football_rows(rows):
    return sorted((r for r in rows if r.get("sport","football") in ("football","soccer")),
                  key=lambda r:(str(r["date"])[:10],r.get("league",""),str(r.get("id",""))))


def _metrics_item(identifier,name,family,line=None):
    return {"id":identifier,"name":name,"family":family,"line":line,"n":0,
            "brier":0.,"log_loss":0.,"accuracy":0.,"odds_events":0,"roi":None,
            "baseline_brier":0.,"baseline_log_loss":0.,"baseline_accuracy":0.,
            "baseline":"Frecuencia previa de resultados de la misma liga con regularización y decaimiento; no cuotas",
            "status":"research_without_historical_odds","model":FAMILIES[family]["model"],
            "note":"Evaluación retrospectiva ya inspeccionada; sin cuotas históricas equivalentes, EV, importe ni ROI.",
            "brier_definition":"Suma de errores cuadrados de 3 resultados (0–2)" if identifier=="half_time_1x2" else "Error cuadrático binario (0–1)"}


def run_stat_market_evaluation(rows,audit_start="2024-01-01"):
    specs=[("half_time_1x2","Primer tiempo · 1X2","period_half",None),
           ("half_time_over_0_5","Primer tiempo · más de 0,5 goles","period_half",.5),
           ("half_time_over_1_5","Primer tiempo · más de 1,5 goles","period_half",1.5),
           ("half_time_btts","Primer tiempo · ambos marcan","period_half","btts"),
           *[(f"corners_over_{str(x).replace('.','_')}",f"Córners · más de {str(x).replace('.',',')}","corners",x) for x in (8.5,9.5,10.5)],
           *[(f"yellow_cards_over_{str(x).replace('.','_')}",f"Amarillas · más de {str(x).replace('.',',')}","yellow_cards",x) for x in (3.5,4.5)]]
    result={s[0]:_metrics_item(*s) for s in specs};models={};missing=defaultdict(int);climatology={}
    def baseline(league,identifier,day):
        key=(league,identifier);nclasses=3 if identifier=="half_time_1x2" else 2
        if key not in climatology:climatology[key]=[_day(day),[0.]*nclasses]
        last,counts=climatology[key];f=2**(-(_day(day)-last).days/365.)
        if f!=1:
            counts[:]=[v*f for v in counts];climatology[key][0]=_day(day)
        total=sum(counts)+nclasses
        return [(v+1)/total for v in counts]
    def target_label(identifier,line,counts):
        hc,ac=counts
        if identifier=="half_time_1x2":return 0 if hc>ac else 1 if hc==ac else 2
        return int(hc>0 and ac>0) if line=="btts" else int(hc+ac>line)
    for day,day_rows in groupby(_football_rows(rows),lambda r:str(r["date"])[:10]):
        group=list(day_rows);batches=defaultdict(list)
        for row in group:
            league=row.get("league","")
            for family in FAMILIES:
                key=(league,family)
                if key not in models:models[key]=StatCountModel(family)
                model=models[key];batches[key].append(row)
                counts=observed_counts(row,family)
                if counts is None:
                    if day>=audit_start:missing[family]+=1
                    continue
                prediction=model.predict(row["home_team"],row["away_team"],day,row.get("neutral_venue",False))
                if day<audit_start or not prediction["eligible"]:continue
                hc,ac=counts
                for identifier,_,target,line in specs:
                    if target!=family:continue
                    entry=result[identifier]
                    base=baseline(league,identifier,day)
                    label=target_label(identifier,line,counts)
                    if identifier=="half_time_1x2":
                        probs=[prediction["home"],prediction["draw"],prediction["away"]]
                        truth=0 if hc>ac else 1 if hc==ac else 2
                        brier=sum((p-(i==truth))**2 for i,p in enumerate(probs))
                        loss=-math.log(max(1e-15,probs[truth]));correct=max(range(3),key=probs.__getitem__)==truth
                    else:
                        if line=="btts":p=prediction["btts_yes"];truth=hc>0 and ac>0
                        elif family=="period_half":p=prediction["prob_over_"+str(line).replace('.','_')];truth=hc+ac>line
                        else:p=prediction["prob_over_"+str(line).replace('.','_')];truth=hc+ac>line
                        brier=(p-truth)**2;loss=-math.log(max(1e-15,p if truth else 1-p));correct=(p>=.5)==truth
                    entry["n"]+=1;entry["brier"]+=brier;entry["log_loss"]+=loss;entry["accuracy"]+=correct
                    entry["baseline_brier"]+=(sum((v-(i==label))**2 for i,v in enumerate(base)) if identifier=="half_time_1x2" else (base[1]-label)**2)
                    entry["baseline_log_loss"]-=math.log(max(1e-15,base[label]))
                    entry["baseline_accuracy"]+=max(range(len(base)),key=base.__getitem__)==label
        for key,entries in batches.items():models[key].update_batch(entries)
        for row in group:
            if str(row.get("neutral_venue","false")).lower() in ("true","1","yes"):continue
            for identifier,_,family,line in specs:
                counts=observed_counts(row,family)
                if counts is None:continue
                league=row.get("league","");baseline(league,identifier,day)
                label=target_label(identifier,line,counts)
                climatology[(league,identifier)][1][label]+=1
    output=[]
    for item in result.values():
        n=item["n"]
        for key in ("brier","log_loss","accuracy","baseline_brier","baseline_log_loss","baseline_accuracy"):
            item[key]=item[key]/n if n else None
        item["missing_observations"]=missing[item["family"]]
        item["period"]={"audit_start":audit_start,"kind":"retrospective_already_inspected"}
        output.append(item)
    return output


def predict_stat_fixture(history,fixture):
    day=str(fixture["date"])[:10];league=fixture.get("league","")
    rows=[r for r in _football_rows(history) if r.get("league","")==league and str(r["date"])[:10]<day]
    models={family:StatCountModel(family) for family in FAMILIES}
    for _,batch in groupby(rows,lambda r:str(r["date"])[:10]):
        entries=list(batch)
        for model in models.values():model.update_batch(entries)
    return {family:model.predict(fixture["home_team"],fixture["away_team"],day,fixture.get("neutral_venue",False))
            for family,model in models.items()}
