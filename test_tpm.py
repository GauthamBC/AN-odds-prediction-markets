import os
import tempfile
import unittest
from unittest.mock import Mock
from datetime import datetime,timezone

from tpm_client import TPMClient, TPMError
from snapshot_store import connect, publish, snapshot, detail, save_detail
from dashboard_logic import (outcomes_by_group, forecast, prefetch_candidates, matched_disagreements)
from region_rules import regions, match_filters

class FakeResponse:
    def __init__(self, data, status=200):
        self._data=data;self.status_code=status;self.ok=status<400;self.headers={};self.text='error'
    def json(self):return self._data

class TestClient(unittest.TestCase):
    def test_cursor_and_complete_scan(self):
        ses=Mock()
        ses.get.side_effect=[FakeResponse({'data':[{'slug':'a','status':'active'}],
                         'pagination':{'has_more':True,'next_cursor':'abc'}}),
                         FakeResponse({'data':[{'slug':'a','status':'active'}, {'slug':'b','status':'active'}],
                         'pagination':{'has_more':False}})]
        c=TPMClient('xx',session=ses,pause_seconds=0)
        res=c.catalogue()
        self.assertEqual([x['slug'] for x in res.events],['a','b'])
        self.assertEqual(res.api_calls,2)
        self.assertEqual(ses.get.call_args_list[0].kwargs['params']['status'],'trading')
        self.assertEqual(ses.get.call_args_list[1].kwargs['params']['cursor'],'abc')

    def test_partial_catalogue_detected(self):
        ses=Mock();ses.get.return_value=FakeResponse({'data':[], 'pagination':{'has_more':True}})
        with self.assertRaises(TPMError):TPMClient('x',session=ses,pause_seconds=0).catalogue()

    def test_details_no_heuristic_matching(self):
        event={'comparison':'comparable', 'category':'politics', 'slug':'elect', 'title':'Election',
              'markets':[{'venue':'kalshi','market_id':'abc', 'url':'https://kalshi.com','outcomes':[
                  {'title':'Alpha','volume':100,'quote':{'probability':.6,'freshness':'fresh'},
                   'match':{'group_id':'g1','key':'candidate:alpha','contract_compatibility':'unverified'}},
                  {'title':'Beta','quote':{'probability':.3,'freshness':'fresh'},'match':None}]},
              {'venue':'polymarket','market_id':'qwe', 'outcomes':[
                  {'title':'Alpha Candidate','volume':100,'quote':{'probability':.5,'freshness':'live'},
                   'match':{'group_id':'g1','key':'candidate:alpha','contract_compatibility':'unverified'}}]}]}
        groups=outcomes_by_group(event)
        matched=[g for g in groups if len(g['prices'])==2]
        self.assertEqual(len(matched),1)
        self.assertAlmostEqual(forecast(event,matched[0])['prob'],.55)
        self.assertIn('NOT verified',forecast(event,matched[0])['status'])
        self.assertEqual(len(matched_disagreements(event)),1)

    def test_does_not_blend_stale_quotes(self):
        e={'comparison':'verified','markets':[{'venue':'kalshi','outcomes':[{'title':'Y','quote':{'probability':.7,'freshness':'stale'},'match':{'group_id':'g','contract_compatibility':'verified'}}]},
                                             {'venue':'polymarket','outcomes':[{'title':'Y','quote':{'probability':.8,'freshness':'live'},'match':{'group_id':'g','contract_compatibility':'verified'}}]}]}
        self.assertIsNone(forecast(e,outcomes_by_group(e)[0])['prob'])

    def test_country_classification(self):
        self.assertIn('USA',regions({'title':'New York Knicks NBA champion'}))
        self.assertIn('Canada',regions({'title':'Toronto Maple Leafs win NHL'}))
        self.assertIn('Global',regions({'title':'Who wins the FIFA World Cup?'}))
        self.assertEqual(len(match_filters([{'title':'Canada election','slug':'can','category':'politics'}], 'Canada','Politics')),1)

    def test_prefetch_respects_regional_variety(self):
        xs=[{'slug':str(i),'title':f'{i}','category':'sports','volume_24h':1000-i} for i in range(25)]
        self.assertTrue(prefetch_candidates(xs,cap=20))
        self.assertLessEqual(len(prefetch_candidates(xs,cap=20)),20)

class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.con=connect(os.path.join(self.temp.name,'test.sqlite3'))
    def tearDown(self):
        self.con.close();self.temp.cleanup()
    def test_atomic_snapshot_preserves_old_on_invalid(self):
        a=[{'slug':'abc','title':'title'}]
        publish(self.con,a,pages=1,request_count=2)
        with self.assertRaises(ValueError):publish(self.con,[],pages=0,request_count=0)
        self.assertEqual(snapshot(self.con)[0]['slug'],'abc')
    def test_detail_refresh_invalidates_old(self):
        publish(self.con,[{'slug':'a'}],pages=1,request_count=1)
        save_detail(self.con,{'slug':'a','markets':[1]},full=True)
        self.assertIsNotNone(detail(self.con,'a',full=True))
        publish(self.con,[{'slug':'a'}],pages=1,request_count=1)
        self.assertIsNone(detail(self.con,'a',full=True))
    def test_fetched_full_detail_precedence(self):
        save_detail(self.con,{'slug':'a','markets':[1]},full=True)
        save_detail(self.con,{'slug':'a','markets':[2]},full=False)
        self.assertEqual(detail(self.con,'a')['markets'],[1])

if __name__=='__main__':unittest.main()
