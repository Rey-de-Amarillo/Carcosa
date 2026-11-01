"""Check real available market keys for representative sports, within free quota."""
from pathlib import Path
import json
import sys
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import storage
from backend.providers import OddsAPI,flatten_odds


def main():
    provider=OddsAPI();now=datetime.now(timezone.utc);report=[]
    with storage.connect() as c:
        keys=[r[0] for r in c.execute("SELECT cache_key FROM snapshots WHERE cache_key LIKE 'odds:%:eu:h2h'")]
    events=[]
    for key in keys:
        snap=storage.cache_get(key)
        for e in snap['payload']:
            try:future=datetime.fromisoformat(e['commence_time'].replace('Z','+00:00'))>now
            except (ValueError,KeyError):future=False
            if future:events.append(e)
    priorities={'soccer':'soccer_epl','basketball':'basketball_nba','americanfootball':'americanfootball_nfl',
                'baseball':'baseball_mlb','icehockey':'icehockey_nhl','tennis':None,'cricket':None}
    wanted={'soccer':['btts','draw_no_bet','alternate_totals_corners'],
            'basketball':['player_points','player_rebounds','player_first_basket'],
            'americanfootball':['player_pass_yds','player_rush_yds','player_1st_td'],
            'baseball':['pitcher_strikeouts','batter_home_runs','h2h_1st_5_innings'],
            'icehockey':['player_shots_on_goal','player_goals','h2h_p1'],
            'tennis':['h2h_s1','totals_s1','spreads_s1'],'cricket':['h2h','totals','spreads']}
    for prefix,key in priorities.items():
        candidates=sorted([e for e in events if e['sport_key'].split('_')[0]==prefix and (key is None or e['sport_key']==key)],key=lambda e:e['commence_time'])
        if not candidates:continue
        e=candidates[0]
        try:
            snapshot=provider.event_markets(e['sport_key'],e['id'])
            available=sorted({m['key'] for x in snapshot['payload'] for b in x.get('bookmakers',[]) for m in b.get('markets',[])})
            selected=[m for m in wanted[prefix] if m in available][:3]
            price_count=0
            if selected:
                sample=provider.event_odds(e['sport_key'],e['id'],markets=','.join(selected))
                price_count=len(flatten_odds(sample))
            report.append({'sport':prefix,'sport_key':e['sport_key'],'event':e['home_team']+' — '+e['away_team'],
                           'event_id':e['id'],'commence_time':e['commence_time'],'markets':available,
                           'sampled_markets':selected,'sample_prices':price_count,'retrieved_at':snapshot['created_at'],
                           'model_status':'Market availability does not establish a validated forecasting model.'})
        except ValueError as exc:
            report.append({'sport':prefix,'sport_key':e['sport_key'],'status':'unavailable','error_type':type(exc).__name__})
    out={'generated_at':storage.utcnow(),'examples':report,'credits':provider.status(),
         'note':'Ejemplos observados, no cobertura universal; disponibilidad varía por evento y casa.'}
    path=storage.ROOT/'data/analysis/market_availability.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps({'sports':len(report),'available_keys':sum(len(r.get('markets',[])) for r in report),
                      'prices':sum(r.get('sample_prices',0) for r in report),'examples':[{k:r.get(k) for k in ('sport','sampled_markets','sample_prices')} for r in report],
                      'local_reserved_credits':out['credits']['local_reserved_credits']},ensure_ascii=False))


if __name__=='__main__':main()
