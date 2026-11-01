"""Coherent multi-book probability references and bounded structural blending.

Odds are observations of prices. Removing margin is an assumption, not proof
of knowing the event's true probability or having a profitable strategy.
"""
import math


def devig(odds, method='power'):
    values = [float(x) for x in odds]
    if len(values) < 2 or any(not math.isfinite(o) or o <= 1 for o in values):
        raise ValueError('Cuotas completas, finitas y mayores que uno requeridas.')
    q = [1/o for o in values]
    margin = sum(q)-1
    if method == 'proportional':
        p = [x/sum(q) for x in q]
        exponent = 1.0
    elif method == 'power':
        low, high = 0.0, 2.0
        while sum(x**high for x in q) > 1 and high < 1024:
            high *= 2
        for _ in range(64):
            middle = (low+high)/2
            if sum(x**middle for x in q) > 1:
                low = middle
            else:
                high = middle
        exponent = (low+high)/2
        p = [x**exponent for x in q]
        total = sum(p)
        p = [x/total for x in p]
    else:
        raise ValueError('Método de margen desconocido')
    return {'probabilities':p,'overround':margin,'method':method,'exponent':exponent}


def consensus(books, method='power', max_overround=.15):
    """Equal-book arithmetic pooling preserves a valid probability simplex.

    Only actual bookmaker vectors of the same complete market/snapshot belong
    here. Average/maximum columns and exchange lay prices are never books.
    """
    valid, rejected = [], []
    size = None
    for name, prices in sorted(books.items()):
        if name.lower() in ('avg','max','bbav','bbmx','bfe','betfair_exchange'):
            rejected.append(name); continue
        try:
            result = devig(prices,method)
            if not -.02 <= result['overround'] <= max_overround:
                rejected.append(name);continue
            if size is None:size=len(prices)
            if len(prices)!=size:
                rejected.append(name);continue
            valid.append((name,result['probabilities']))
        except (TypeError, ValueError, OverflowError):
            rejected.append(name)
    if not valid:
        return {'probabilities':None,'books':[],'count':0,'dispersion':None,'rejected':rejected,'method':method}
    p = [sum(v[i] for _,v in valid)/len(valid) for i in range(size)]
    dispersion = [math.sqrt(sum((v[i]-p[i])**2 for _,v in valid)/len(valid)) for i in range(size)]
    return {'probabilities':p,'books':[name for name,_ in valid],'count':len(valid),
            'dispersion':dispersion,'rejected':rejected,'method':method,
            'note':'Dispersión entre casas; no es un intervalo de confianza independiente.'}


def blend(structural, market, weight):
    if not math.isfinite(weight) or not 0 <= weight <= 1:
        raise ValueError('Peso fuera de rango')
    def simplex(vector):
        values=[float(x) for x in vector]
        if len(values)<2 or any(not math.isfinite(x) or not 0<=x<=1 for x in values) or abs(sum(values)-1)>1e-6:
            raise ValueError('Distribución inválida')
        return values
    if market is None:
        return simplex(structural) if structural is not None and weight == 1 else None
    if structural is None:
        return simplex(market) if weight == 0 else None
    structural,market=simplex(structural),simplex(market)
    if len(structural)!=len(market):
        raise ValueError('Resultados incompatibles')
    p = [weight*a+(1-weight)*b for a,b in zip(structural,market)]
    if any(not math.isfinite(x) or x<0 for x in p) or abs(sum(p)-1)>1e-6:
        raise ValueError('Distribución inválida')
    return p


def multiclass_logloss(p, outcome):
    return -math.log(max(1e-15,min(1.,p[outcome])))


def select_candidate(records,candidates,start='2022-01-01',end='2023-12-31'):
    """Selection sees only the declared interval, never later audit outcomes."""
    selected_records=[r for r in records if start<=r['date']<=end]
    table=[]
    for candidate in candidates:
        losses=[]
        for row in selected_records:
            market=row['consensus_'+candidate['devig']]
            if market is None or row.get('structural') is None:continue
            p=blend(row['structural'],market,candidate['structural_weight'])
            losses.append(multiclass_logloss(p,row['outcome']))
        table.append({**candidate,'n':len(losses),'log_loss':sum(losses)/len(losses) if losses else None})
    valid=[r for r in table if r['log_loss'] is not None]
    winner=min(valid,key=lambda x:(x['log_loss'],x['structural_weight'],x['id'])) if valid else None
    return {'selected':winner,'candidates':table,'start':start,'end':end,
            'criterion':'log_loss','audit_outcomes_used':False,'roi_used':False}
