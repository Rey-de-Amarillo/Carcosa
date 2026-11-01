import unittest
from scripts.build_football_audit import normalize_quote

class FootballAuditAdapterTests(unittest.TestCase):
    def row(self, **changes):
        row={'sport':'football','event_id':'a','region':'eu','home_team':'A (FC)','away_team':'B. United','selection':'A (FC)','market_key':'h2h','odds':2.2,'line':None,'bookmaker':'book','last_update':'2026-10-30T10:00:00Z'}
        return {**row,**changes}
    def test_exact_participants_and_literal_score_syntax(self):
        q,err=normalize_quote(self.row(market_key='correct_score',selection='A (FC):2|B. United:1'),9)
        self.assertIsNone(err);self.assertEqual(q['score'],[2,1]);self.assertFalse(q['verified_rules'])
        self.assertEqual(normalize_quote(self.row(selection='A'),1)[1],'unknown_selection')
    def test_other_statistics_and_periods_do_not_enter_goals_matrix(self):
        for key in ('alternate_totals_corners','alternate_totals_cards','player_goals_alternate','btts_h1','h2h_3_way_h2'):
            q,err=normalize_quote(self.row(market_key=key),1)
            self.assertIsNone(q);self.assertIsNotNone(err)
    def test_opposing_handicaps_keep_the_selected_team_line(self):
        q,_=normalize_quote(self.row(market_key='spreads',selection='B. United',line=.25),1)
        self.assertEqual((q['selection'],q['line']),('away',.25))
    def test_team_total_requires_known_description(self):
        row=self.row(market_key='team_totals',selection='Over',line=1.5)
        self.assertEqual(normalize_quote(row,1)[1],'unknown_team_participant')
        q,err=normalize_quote({**row,'description':'B. United'},1)
        self.assertIsNone(err);self.assertEqual(q['team'],'away')
    def test_double_chance_is_not_an_exclusive_result(self):
        q,err=normalize_quote(self.row(market_key='double_chance',selection='B. United or Draw'),1)
        self.assertIsNone(err);self.assertEqual((q['market'],q['selection']),('double_chance','draw_away'))
    def test_exchange_and_unbounded_lines_are_excluded(self):
        self.assertEqual(normalize_quote(self.row(exchange=True),1)[1],'exchange_or_dfs_costs_unverified')
        self.assertEqual(normalize_quote(self.row(market_key='totals',line=9.5,selection='Over'),1)[1],'goal_line_search_bound')

if __name__=='__main__': unittest.main()
