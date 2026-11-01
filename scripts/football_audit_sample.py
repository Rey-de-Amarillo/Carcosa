"""Read-only, quota-bounded football market census and matched sport snapshots.

The free data subscription is already configured on the server. No bookmaker
account is opened and no wager, deposit, or other money movement is submitted.
"""
from pathlib import Path
import json
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import storage
from backend.providers import OddsAPI


MAX_NEW_RESERVATIONS=100
SPORTS=['soccer_epl','basketball_nba','americanfootball_nfl','icehockey_nhl',
        'baseball_mlb','tennis_atp_vienna_open','tennis_atp_swiss_indoors']
EXCHANGE_HINTS=('betfair_ex','betfair_exchange','matchbook','betdaq','smarkets')
DFS_HINTS=('prizepicks','underdog','pick6','sleeper','betr_dfs')


def timestamp(value):
    try:
        t=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (ValueError,TypeError):return None


def sport_group(key):
    prefix=key.split('_')[0]
    return {'soccer':'football','americanfootball':'american_football','icehockey':'hockey'}.get(prefix,prefix)


def flatten(snapshot,region):
    rows=[]
    for event in snapshot['payload']:
        for book in event.get('bookmakers',[]):
            key=book['key']
            for market in book.get('markets',[]):
                for outcome in market.get('outcomes',[]):
                    rows.append({'event_id':event['id'],'sport':sport_group(event['sport_key']),
                        'sport_key':event['sport_key'],'league':event.get('sport_title',event['sport_key']),
                        'home_team':event.get('home_team'),'away_team':event.get('away_team'),
                        'event':event.get('home_team','')+' — '+event.get('away_team',''),
                        'commence_time':event.get('commence_time'),'bookmaker':key,'bookmaker_title':book['title'],
                        'market_key':market['key'],'selection':outcome['name'],'description':outcome.get('description'),
                        'line':outcome.get('point'),'odds':outcome['price'],
                        'last_update':market.get('last_update') or book.get('last_update'),
                        'retrieved_at':snapshot['created_at'],'region':region,
                        'exchange':any(x in key for x in EXCHANGE_HINTS) or market['key'].endswith('_lay'),
                        'dfs':any(x in key for x in DFS_HINTS),'source':'The Odds API',
                        'verified_rules':False,'executable':False})
    return rows


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False));tmp.replace(path)


def main():
    provider=OddsAPI();initial=provider.status()['local_reserved_credits'];quotes=[];calls=[];failures=[];discoveries=[]
    def room(cost):
        return provider.status()['local_reserved_credits']-initial+cost<=MAX_NEW_RESERVATIONS
    def odds(sport,markets,region='eu',event=None):
        cost=len(markets.split(','))
        if not room(cost):
            failures.append({'stage':'budget','sport':sport,'markets':markets,'reason':'task_quota_cap'});return None
        try:
            snapshot=provider.event_odds(sport,event,markets=markets,regions=region,force=True) if event else provider.odds(sport,markets=markets,regions=region,force=True)
            rows=flatten(snapshot,region);quotes.extend(rows)
            calls.append({'sport':sport,'event_id':event,'region':region,'markets':markets.split(','),
                          'rows':len(rows),'retrieved_at':snapshot['created_at'],'quota':snapshot['quota']})
            return snapshot
        except ValueError:
            failures.append({'stage':'prices','sport':sport,'markets':markets,'reason':'provider_unavailable'});return None
    # All sports are queried in the SAME region, for the same three featured
    # market families. Not every sport has all three markets at every book.
    football=None
    for sport in SPORTS:
        snap=odds(sport,'h2h,spreads,totals')
        if sport=='soccer_epl':football=snap
    if football:
        clock=datetime.now(timezone.utc)
        upcoming=sorted([e for e in football['payload'] if (timestamp(e.get('commence_time')) or clock)>clock],key=lambda e:e['commence_time'])
        if upcoming:
            event=upcoming[0]
            for region in ['us','eu','uk']:
                if not room(1):break
                try:available=provider.event_markets('soccer_epl',event['id'],regions=region,force=True)
                except ValueError:
                    failures.append({'stage':'market_discovery','region':region,'reason':'unavailable'});continue
                keys=sorted({m['key'] for e in available['payload'] for b in e.get('bookmakers',[]) for m in b.get('markets',[]) if not m['key'].endswith('_lay')})
                selected=keys if region=='us' else [key for key in ['h2h','spreads','totals','double_chance','draw_no_bet','btts','correct_score','alternate_totals_corners','alternate_totals_cards'] if key in keys]
                discoveries.append({'event_id':event['id'],'event':event['home_team']+' — '+event['away_team'],
                                    'region':region,'available_keys':keys,'requested_keys':selected,
                                    'retrieved_at':available['created_at']})
                for i in range(0,len(selected),3):
                    odds('soccer_epl',','.join(selected[i:i+3]),region,event['id'])
    clock=datetime.now(timezone.utc);fresh=[];rejected=0
    # Retain all observations locally; only future events with independently
    # supplied, recent quote clocks enter comparisons.
    for q in quotes:
        start=timestamp(q.get('commence_time'));updated=timestamp(q.get('last_update'))
        if start and updated and start>clock and 0<=(clock-updated).total_seconds()<=900:
            fresh.append(q)
        else:rejected+=1
    result={'meta':{'generated_at':clock.isoformat(),'region_comparison':'eu','freshness_seconds':900,
                    'reserved_credits_before':initial,'reserved_credits_used':provider.status()['local_reserved_credits']-initial,
                    'task_credit_cap':MAX_NEW_RESERVATIONS,'execution_enabled':False},
            'quotes':quotes,'fresh_quotes':fresh,'calls':calls,'failures':failures,'discoveries':discoveries,
            'rejected_for_clock_or_started':rejected,'provider_status':provider.status(),
            'limitations':['Muestra de eventos, casas y regiones; no censo universal de todos los partidos.',
                           'Un timestamp reciente no prueba reglas idénticas, liquidez ni aceptación.',
                           'Reglas, cuenta, comisiones y límites no verificados; no se ejecuta ninguna operación.']}
    save(ROOT/'data/analysis/football_audit_sample.json',result)
    print(json.dumps({'observations':len(quotes),'fresh_quotes':len(fresh),'calls':len(calls),
                      'credit_reservations':result['meta']['reserved_credits_used'],'failures':failures,
                      'football_available_keys':{d['region']:len(d['available_keys']) for d in discoveries},
                      'quota':result['provider_status']['provider_quota']},ensure_ascii=False))


if __name__=='__main__':main()
