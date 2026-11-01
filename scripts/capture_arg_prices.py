"""Transcribe dated Bet365 DOM observations; this script never connects or bets."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/analysis/bet365_arg_quotes.json'
URL='https://www.bet365.bet.ar/#/AC/B1/C1/D8/E202426204/F3/I1/'
quotes=[]
def add(label,market,selection,odds,**details):
    quotes.append({'id':f'q{len(quotes)+1:04}','label':label,'market':market,'selection':selection,'odds':odds,
        'period':'full_time','statistic':'goals','source_url':URL,'bookmaker':'bet365_argentina',
        'captured_at':'2026-10-30T16:36:46+00:00','last_update':None,'verified_rules':False,
        'executable':False,**details})
for s,o in [('home',4.2),('draw',3.3),('away',1.95)]:add('Full Time Result','1x2',s,o)
for line,over,under in [(.5,1.083,8),(1.5,1.4,2.75),(2.5,2.25,1.61),(3.5,4,1.22),(4.5,10,1.062),(5.5,21,1.015),(6.5,51,1.002)]:
    for s,o in [('over',over),('under',under)]:add('Goals Over/Under','totals',s,o,line=line)
for s,o in [('yes',2),('no',1.75)]:add('Both Teams to Score','btts',s,o)
for s,o in [('home',3),('away',1.36)]:add('Draw No Bet','dnb',s,o)
for result,yes,no in [('home',9.5,6.5),('away',4.75,3),('draw',4.75,7.5)]:
    for s,o in [('yes',yes),('no',no)]:
        add('Result/Both Teams to Score','combo','and',o,legs=[{'market':'1x2','selection':result},{'market':'btts','selection':s}],mapping_status='binary_score_intersection')
for s,o in [('yes',1.57),('no',2.25)]:add('Match Goals Range 2–4','goal_range',s,o,min_goals=2,max_goals=4)
add('Correct Score 0–0','correct_score','score',7.5,score=[0,0])
add('Half Time Correct Score 0–0','correct_score','score',2.5,score=[0,0],period='first_half')
# Three exclusive corner results. Over10 is 11+, Under10 is0..9: no push.
for s,o in [('over',2.2),('exact',8),('under',2)]:add('Corners 10','count_total_3way',s,o,line=10,statistic='corners')
for line,over,exact,under in [(2,1.002,51,67),(3,1.008,34,51),(4,1.02,21,29),(5,1.05,15,19),(6,1.12,12,11),(7,1.25,9.5,6)]:
    for s,o in [('over',over),('exact',exact),('under',under)]:add('Alternative Corners','count_total_3way',s,o,line=line,statistic='corners')
# Correct score All view: away scores displayed from the winning team's perspective.
for home,away,odds in [(1,0,10),(2,0,21),(2,1,15),(3,0,41),(3,1,41),(3,2,41),(4,0,126),(4,1,81),(4,2,126),(4,3,201),(5,0,501),(5,1,351),(5,2,501),(1,1,6),(2,2,17),(3,3,67),(4,4,451),(0,1,6),(0,2,8.5),(1,2,9),(0,3,17),(1,3,17),(2,3,34),(0,4,41),(1,4,41),(2,4,51),(3,4,151),(0,5,81),(1,5,81),(2,5,151),(3,5,401),(0,6,201),(1,6,251),(2,6,501)]:
    add('Correct Score · All','correct_score','score',odds,score=[home,away],captured_at='2026-10-30T16:40:07+00:00')
for name,goal,assist,either in [('Agustin Auzmendi',2.37,9,2.05),('Marcelo Torres',2.62,7,2.1),('Ignacio Fernandez',4.33,5,2.5),('Nicolas Barros Schelotto',4.33,5.5,2.62),('Gabriel Alanis',5.5,6.5,3.2),('Martín Garnerone',5.5,7.5,3.4)]:
    for market,odds in [('player_goal',goal),('player_assist',assist),('player_goal_or_assist',either)]:add('Score or Assist',market,'yes',odds,participant=name,statistic='player_event',substitute_plus=True)
for name,last5,odds in [('Lucas Gonzalez',[0,0,0,0],[1.33,2.62,6.5,19]),('Maximiliano Zalazar',[1,0,1,0,1],[1.53,3.5,11]),('Gabriel Alanis',[1,0,0,2,1],[1.57,3.75,11]),('Javier Ferreira',[0,0,0,0,1],[1.61,4,13]),('Agustin Auzmendi',[2,0,0,2,0],[1.66,4.33,15]),('Agustin Quiroga',[0,1,0,0,0],[1.72,4.5,15])]:
    for count,o in enumerate(odds,1):add('Shots On Target','player_count','over',o,line=count-.5,participant=name,statistic='shots_on_target',last_matches_displayed=last5,substitute_plus=True)
for name,last5,odds in [('Lucas Gonzalez',[1,0,2,0],[1.03,1.18,1.57,2.37,4,7,15,21]),('Javier Ferreira',[0,0,1,0,1],[1.04,1.2,1.61,2.5,4.33,8,15]),('Agustin Quiroga',[2,2,0,0,0],[1.062,1.33,1.9,3.4,6.5,13,21]),('Benjamin Moyano',[],[1.071,1.36,2.1,3.75,7,15]),('Gabriel Alanis',[2,0,0,3,4],[1.083,1.44,2.25,4,8,17]),('Ibrahim Hesar',[0,1,1,3,2],[1.083,1.4,2.2,3.75,8,17])]:
    for count,o in enumerate(odds,1):add('Shots','player_count','over',o,line=count-.5,participant=name,statistic='shots',last_matches_displayed=last5,substitute_plus=True)
for count,yes,no in [(1,1.16,5),(2,1.83,1.83)]:
    for s,o in [('yes',yes),('no',no)]:add('Both Teams to Receive Cards','both_teams_count',s,o,min_count=count,statistic='cards')
# Offered boosts: no independent probabilities assigned without participant/joint history.
boosts=[
 ('Marcelo Torres from outside box',11,[{'market':'player_goal_method','selection':'outside_box','participant':'Marcelo Torres'}]),
 ('Marcelo Torres header',11,[{'market':'player_goal_method','selection':'header','participant':'Marcelo Torres'}]),
 ('Auzmendi 1+ SOT / Torres 1+ SOT / Gimnasia win',6.5,[{'market':'player_count','statistic':'shots_on_target','participant':'Agustin Auzmendi','selection':'over','line':.5},{'market':'player_count','statistic':'shots_on_target','participant':'Marcelo Torres','selection':'over','line':.5},{'market':'1x2','selection':'away'}]),
 ('Gimnasia win / Gimnasia most corners / Over2 goals',7,[{'market':'1x2','selection':'away'},{'market':'most_corners','selection':'away'},{'market':'totals','selection':'over','line':2.5,'source_label':'Over2Goals; strict2+ threshold assumed, BB settlement unverified'}]),
 ('Auzmendi1+SOT / Hesar2+SOT / BTTS',15,[{'market':'player_count','statistic':'shots_on_target','participant':'Agustin Auzmendi','selection':'over','line':.5},{'market':'player_count','statistic':'shots_on_target','participant':'Ibrahim Hesar','selection':'over','line':1.5},{'market':'btts','selection':'yes'}]),
 ('Auzmendi goal / Ignacio Fernandez assist / Gimnasia win',12,[{'market':'player_goal','participant':'Agustin Auzmendi','selection':'yes'},{'market':'player_assist','participant':'Ignacio Fernandez','selection':'yes'},{'market':'1x2','selection':'away'}]),
 ('Auzmendi goal / Over2 goals / Gimnasia win',5,[{'market':'player_goal','participant':'Agustin Auzmendi','selection':'yes'},{'market':'totals','selection':'over','line':2.5,'source_label':'Over2Goals strict threshold assumed; BB settlement unverified'},{'market':'1x2','selection':'away'}])]
for label,odds,legs in boosts:add(label,'combo','and',odds,legs=legs,offered_boost=True,mapping_status='rules_unverified',substitute_plus='player legs unresolved')
# Additional priced rows read in the Goals category at13:45:09 Salta.
for result,over,under in [('home',8.5,7),('away',3.6,3.75),('draw',15,3.75)]:
    for selection,odds in [('over',over),('under',under)]:
        add('Result/Total Goals2.5','combo','and',odds,legs=[{'market':'1x2','selection':result},{'market':'totals','selection':selection,'line':2.5}],mapping_status='binary_score_intersection',captured_at='2026-10-30T16:45:09+00:00',source_url=URL.replace('/I1/','/I6/'))
for total,btts,odds in [('over','yes',2.75),('over','no',10),('under','yes',6),('under','no',2)]:
    add('Total Goals/BTTS2.5','combo','and',odds,legs=[{'market':'totals','selection':total,'line':2.5},{'market':'btts','selection':btts}],mapping_status='binary_score_intersection',captured_at='2026-10-30T16:45:09+00:00',source_url=URL.replace('/I1/','/I6/'))
for period,yes,no in [('first_half',5.5,1.14),('second_half',4,1.22)]:
    for selection,odds in [('yes',yes),('no',no)]:add('Half BTTS','btts',selection,odds,period=period,captured_at='2026-10-30T16:45:09+00:00',source_url=URL.replace('/I1/','/I6/'))
for team,yes,no in [('home',4,1.22),('away',2.25,1.57)]:
    for selection,odds in [('yes',yes),('no',no)]:add('Team Goals Range2–4','goal_range',selection,odds,team=team,min_goals=2,max_goals=4,captured_at='2026-10-30T16:45:09+00:00',source_url=URL.replace('/I1/','/I6/'))
for selection,odds in [('over',5),('under',1.16)]:add('First10minutes Goals0.5','totals',selection,odds,line=.5,period='first_10_minutes',captured_at='2026-10-30T16:45:09+00:00',source_url=URL.replace('/I1/','/I6/'))
# Full inclusive range tables, All view, captured13:47:28 Salta.
ranges=[(1,2),(1,3),(1,4),(1,5),(1,6),(2,3),(2,4),(2,5),(2,6),(3,4),(3,5),(3,6),(4,5),(4,6),(5,6)]
range_prices=[(None,[1.83,1.36,1.18,1.11,1.1,2,1.57,1.44,1.44,2.75,2.5,2.25,5,4.33,11],[1.83,3,4.5,6.5,7,1.72,2.25,2.62,2.62,1.4,1.5,1.57,1.16,1.2,1.05]),('home',[1.8,1.61,1.61,1.61,1.61,4.33,4,4,4,13,13,13,41,41,101],[1.9,2.2,2.2,2.2,2.2,1.2,1.22,1.22,1.22,1.04,1.04,1.04,1.004,1.004,1.001]),('away',[1.57,1.33,1.28,1.25,1.25,2.5,2.25,2.2,2.2,5.5,5.5,5,15,15,34],[2.25,3.25,3.5,3.75,3.75,1.5,1.57,1.61,1.61,1.14,1.14,1.16,1.03,1.03,1.005])]
for team,yes,no in range_prices:
    for (lo,hi),y,n in zip(ranges,yes,no):
        for selection,odds in [('yes',y),('no',n)]:add('Goal Range All','goal_range',selection,odds,team=team,min_goals=lo,max_goals=hi,captured_at='2026-10-30T16:47:28+00:00',source_url=URL.replace('/I1/','/I6/'))
# Half category direct DOM13:48:43 Salta; fixed-time score contracts.
for selection,odds in [('home',4.75),('draw',2.05),('away',2.62)]:add('Half Time Result','1x2',selection,odds,period='first_half',captured_at='2026-10-30T16:48:43+00:00')
for selection,odds in [('home_draw',1.44),('draw_away',1.16),('home_away',1.72)]:add('Half Time Double Chance','double_chance',selection,odds,period='first_half',captured_at='2026-10-30T16:48:43+00:00')
for selection,odds in [('home',1.44),('draw',3.25),('away',9)]:add('Half Time European Handicap','european_handicap',selection,odds,line=1,period='first_half',captured_at='2026-10-30T16:48:43+00:00')
for team,period,yes,no in [('home','first_half',2.75,1.4),('home','second_half',2.25,1.57),('away','first_half',2,1.72),('away','second_half',1.72,2)]:
    for selection,odds in [('yes',yes),('no',no)]:add('Team to Score in Half','team_to_score',selection,odds,team=team,period=period,captured_at='2026-10-30T16:48:43+00:00',source_url=URL.replace('/I1/','/I7/'))
# Half Time Correct Score All, reconfirmed13:49:47 Salta.
for home,away,odds in [(1,0,6),(2,0,23),(2,1,34),(3,0,81),(3,1,126),(3,2,301),(4,0,501),(1,1,8.5),(2,2,67),(0,1,3.75),(0,2,11),(1,2,23),(0,3,41),(1,3,67),(2,3,201),(0,4,126),(1,4,251)]:add('Half Time Correct Score All','correct_score','score',odds,score=[home,away],period='first_half',captured_at='2026-10-30T16:49:47+00:00')
# Asian main lines, captured13:50:08 Salta.
for selection,line,odds in [('home',.5,1.85),('away',-.5,1.95)]:add('Asian Handicap','asian_handicap',selection,odds,line=line,captured_at='2026-10-30T16:50:08+00:00',source_url=URL.replace('/I1/','/I3/'))
for selection,odds in [('over',2),('under',1.8)]:add('Asian Goals2.0,2.5','totals',selection,odds,line=2.25,captured_at='2026-10-30T16:50:08+00:00',source_url=URL.replace('/I1/','/I3/'),settlement_note='Half stake at2.0 and half at2.5; pushes and half losses retained')
# Corner category captured13:52:02 Salta. Full-time counts, not goals.
for selection,odds in [('over',1.72),('under',2)]:add('Corners2way9.5','totals',selection,odds,line=9.5,statistic='corners',captured_at='2026-10-30T16:52:02+00:00')
for lo,hi,odds in [(0,5,11),(6,8,3.25),(9,11,2.6),(12,14,4),(15,None,9)]:add('Corners Total Bands','goal_range','yes',odds,min_goals=lo,max_goals=hi,statistic='corners',captured_at='2026-10-30T16:52:02+00:00')
for team,line,over,under in [('home',4.5,2.2,1.61),('away',5.5,1.9,1.8)]:
    for selection,odds in [('over',over),('under',under)]:add('Team Corners','team_totals',selection,odds,team=team,line=line,statistic='corners',captured_at='2026-10-30T16:52:02+00:00')
# Cards category captured13:56:49 Salta; red-card weights must be verified.
for selection,odds in [('over',1.83),('under',1.83)]:add('Match Cards4.5','totals',selection,odds,line=4.5,statistic='cards',captured_at='2026-10-30T16:56:49+00:00',card_weighting_verified=False)
# Other specials captured13:58:21 Salta; comeback needs event trajectories.
for team,comeback,clean,either,both,scoreboth in [('home',19,6.5,2.5,17,6.5),('away',10,3,1.57,6.5,3.5)]:
    details={'captured_at':'2026-10-30T16:58:21+00:00','source_url':URL.replace('/I1/','/I19/')}
    add('Win From Behind','win_from_behind',team,comeback,**details)
    opponent='away' if team=='home' else 'home'
    add('Win To Nil','combo','and',clean,legs=[{'market':'1x2','selection':team},{'market':'team_totals','team':opponent,'selection':'under','line':.5}],mapping_status='binary_score_intersection',**details)
    add('Win Either Half','win_either_half',team,either,**details)
    add('Win Both Halves','combo','and',both,legs=[{'market':'1x2','selection':team,'period':'first_half'},{'market':'1x2','selection':team,'period':'second_half'}],mapping_status='binary_joint_period_intersection',**details)
    add('Score Both Halves','combo','and',scoreboth,legs=[{'market':'team_to_score','team':team,'selection':'yes','period':'first_half'},{'market':'team_to_score','team':team,'selection':'yes','period':'second_half'}],mapping_status='binary_joint_period_intersection',**details)
for selection,odds in [('home',11),('draw',1.12),('away',7.5)]:add('First10minutes Result','1x2',selection,odds,period='first_10_minutes',captured_at='2026-10-30T16:58:21+00:00')
for statistic,over,under in [('corners',1.57,2.25),('cards',6.5,1.11)]:
    for selection,odds in [('over',over),('under',under)]:add('First10minutes Counts','totals',selection,odds,line=.5,statistic=statistic,period='first_10_minutes',captured_at='2026-10-30T16:58:21+00:00')
# Quick Players complete64-row table,14:02:24 Salta. Each row has goal and goal/assist.
all_player_prices=[('Agustin Auzmendi',2.37,2.05),('Marcelo Torres',2.62,2.1),('Manuel Panaro',3.4,2.1),('Ibrahim Hesar',4,3.5),('Javier Ferreira',4,3.4),('Agustin Colazo',4.33,2.62),('Franco Torres',4.33,2.5),('Ignacio Fernandez',4.33,2.5),('Leandro Mamut',4.33,3.4),('Maximiliano Zalazar',4.33,3),('Nicolas Barros Schelotto',4.33,2.62),('Sergio Troncoso',4.33,2.5),('Yeison Moreno',4.33,3),('Jeremias Merlo',4.5,2.5),('Lucas Janson',4.5,3.25),('Mauro Valiente',4.5,3.6),('Joaquin Rivero',4.75,3.25),('Mauro Molina',4.75,3.25),('Agustin Martinez',5.5,3.75),('Augusto Max',5.5,3.75),('Francisco Galvan',5.5,4.5),('Gabriel Alanis',5.5,3.2),('Ignacio Miramon',5.5,4.33),('Juan Garro',5.5,3.1),('Juan Perez',5.5,3.75),('Lucas Gonzalez',5.5,4.33),('Martín Garnerone',5.5,3.4),('Mateo Bajamich',5.5,4.33),('Ramon Abila',5.5,3.6),('Alexis Steimbach',6.5,3.6),('Nicolas Talpone',6.5,5),('Santiago Villarreal',6.5,3.75),('Siro Rosane',6.5,4.5),('Benjamin Moyano',7.5,4),('Tomas Escobar Carranza',7.5,4),('Facundo Di Biasi',8,4.5),('Francesco Lo Celso',8,4),('Mariano Ojeda',8,3.75),('Mateo Seoane',8,3.25),('Matias Melluso',8,3.75),('Pedro Torrejon',8,3.75),('Tomas Gonzalez',8,5),('Valentin Fenoglio',8,6),('Juan Chala',9,4),('Alejandro Cabrera',10,6),('Francisco Romero',10,6.5),('Pablo Aguiar',10,4.5),('Agustin Quiroga',11,7.5),('Gonzalo Errecalde',11,6.5),('Lucas Lamella',11,6.5),('Enzo Martinez',12,9),('Fabricio Corbalan',12,6.5),('German Conti',12,9),('Juan Cortazzo',12,9),('Lucas Banos',12,8),('Renzo Giampaoli',12,7),('Bautista Barros Schelotto',15,6.5),('Gonzalo Gonzalez',15,6),('Raul Lozano',15,9),('Facundo Cobos',17,9),('Juan Antonini',17,12),('Matias Valenti',17,10),('Sergio Ojeda',17,12),('Matias Pagliaricci',21,11)]
assert len(all_player_prices)==64
for name,goal,either in all_player_prices:
    for market,odds in [('player_goal',goal),('player_goal_or_assist',either)]:add('Quick Players Complete','%s'%market,'yes',odds,participant=name,statistic='player_event',substitute_plus=True,captured_at='2026-10-30T17:02:24+00:00',source_url=URL.replace('/I1/','/I101/'))
# BetBuilder displayed assist singles,14:04:58 Salta. No constructed wager submitted.
for name,odds in [('Manuel Panaro',4.33),('Ibrahim Hesar',13),('Javier Ferreira',11),('Agustin Colazo',5.5)]:add('BetBuilder Assist','player_assist','yes',odds,participant=name,statistic='player_event',substitute_plus=True,captured_at='2026-10-30T17:04:58+00:00',source_url=URL.replace('/I1/','/I99/'))
# Expanded five-leg corner boost,14:07:45 Salta. No half-corner history available.
add('Each Team2+CornersEachHalf + BTTS','combo','and',9,legs=[{'market':'team_totals','team':team,'selection':'over','line':1.5,'statistic':'corners','period':period} for team in ['home','away'] for period in ['first_half','second_half']]+[{'market':'btts','selection':'yes'}],offered_boost=True,mapping_status='joint_half_corner_history_unavailable',captured_at='2026-10-30T17:07:45+00:00')
report={'meta':{'event_id':'202426204','event':'Estudiantes Río Cuarto — Gimnasia LP','kickoff':'2026-10-30T22:00:00+00:00','source_url':URL,'source':'Direct read-only browser DOM, user tab','manual_transcription':True,'capture_started_at':'2026-10-30T16:36:46+00:00','execution_enabled':False,'all_quotes_currently_executable':False,'capture_ended_at':'2026-10-30T17:08:24+00:00','inspected_categories':['Popular','Bet Builder','Quick Players','Scorers','Shots','Cards/Fouls','Result','Corners','Goals','Half','Other','Asian Lines'],'coverage_note':'Priced rows transcribed from12 inspected category views and expanded All ranges/scores. Repeated equivalent prices retained as observations. Some expanded sections displayed labels without prices; no price was invented. Custom builder combinations are not an exhaustive finite universe. No bet selected or sent.','candidate_corner_under5_5_reconfirmed_at':'2026-10-30T17:08:24+00:00'},'quotes':quotes}
report['meta']['observed_quote_rows']=len(quotes)
identity_fields=['market','selection','period','statistic','odds','line','team','score','min_goals','max_goals','participant','legs']
report['meta']['distinct_syntactic_selections']=len({json.dumps({k:q.get(k) for k in identity_fields},sort_keys=True,ensure_ascii=False) for q in quotes})
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print({'quotes':len(quotes),'output':str(OUT)})
