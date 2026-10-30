"""Regression tests for US parent-event parsing, durable mappings and indexing."""
from datetime import datetime, timezone
from pathlib import Path
import csv
from feeds import _us_rows, _us_event_quotes, fetch_polymarket_us, fetch_polymarket_us_search
from core import Quote
from index_store import add_quotes, recent_quotes
from mappings import read_mappings, proposed_mapping_rows
from matching import combine_quotes


def make_quote(exchange, label, p, event, title, close='2028-11-07T00:00:00Z'):
    return Quote(exchange,event + ':' + label,event,title,title,label,p,'Politics',80,10,close,'https://example.com')


def us_event():
    return {'id':'E2028','slug':'2028-dem-nominee','title':'Democratic Presidential Nominee 2028',
            'category':'Politics','active':True,'closed':False,'markets':[
                {'id':'M1','slug':'nominee-newsom','question':'Will Gavin Newsom win the nomination?',
                 'active':True,'closed':False,'subject':{'displayName':'Gavin Newsom'},
                 'marketSides':[{'id':'yes','long':True,'price':'0.19','description':'Yes'},
                                {'id':'no','long':False,'price':'0.81','description':'No'}]},
                {'id':'M2','slug':'nominee-ossoff','question':'Will Jon Ossoff win the nomination?',
                 'active':True,'closed':False,'titleShort':'Jon Ossoff',
                 'marketSides':[{'id':'yes','long':True,'price':'0.17'},
                                {'id':'no','long':False,'price':'0.83'}]}
            ]}


def test_us_parent_event_reconstructs_candidate_contracts():
    parsed=_us_event_quotes(us_event())
    assert len(parsed)==2
    assert {q.outcome:q.probability for q in parsed}=={'Gavin Newsom':.19,'Jon Ossoff':.17}
    assert {q.event_id for q in parsed}=={'E2028'}
    assert all(q.exchange=='Polymarket US' for q in parsed)
    assert all(':no' not in q.market_id for q in parsed)


def test_us_events_feed_preferred_over_flat_market_listing(monkeypatch):
    import feeds
    called=[]
    def fake_request(sess,url,params):
        called.append(url)
        return {'events':[us_event()]}
    monkeypatch.setattr(feeds,'session',lambda:object())
    monkeypatch.setattr(feeds,'get_json',fake_request)
    qs,meta=fetch_polymarket_us(max_pages=2,bbo_limit=0)
    assert len(qs)==2 and meta['endpoint']=='/v1/events'
    assert len(called)==1 and called[0].endswith('/v1/events')


def test_us_closed_parent_excluded():
    event=us_event();event['closed']=True
    assert _us_event_quotes(event)==[]


def test_us_market_side_only_no_long_side_not_inferred():
    m={'id':'M3','active':True,'closed':False,'marketSides':[{'id':'short','long':False,'price':'.9'}]}
    assert _us_rows(m)==[]


def test_us_search_uses_query_and_preserves_event(monkeypatch):
    import feeds
    captured=[]
    def getter(sess,url,params):
        captured.append((url,params))
        return {'events':[us_event()]}
    monkeypatch.setattr(feeds,'session',lambda:object())
    monkeypatch.setattr(feeds,'get_json',getter)
    qs,meta=fetch_polymarket_us_search('2028 Democratic nominee')
    assert len(qs)==2
    assert captured[0][0].endswith('/v1/search')
    assert captured[0][1]['query']=='2028 Democratic nominee'


def test_market_event_matched_correctly():
    k1=make_quote('Kalshi','Gavin Newsom',.16,'K2028','2028 Democratic presidential nominee')
    k2=make_quote('Kalshi','Jon Ossoff',.15,'K2028','2028 Democratic presidential nominee')
    cards=combine_quotes([k1,k2],_us_event_quotes(us_event()))
    assert len(cards)==1 and cards[0].matched
    assert {r.label for r in cards[0].rows}=={'Gavin Newsom','Jon Ossoff'}
    assert not cards[0].rule_reviewed


def test_verified_mappings_csv_wont_auto_trust_unreviewed(tmp_path):
    path=tmp_path/'market_aliases.csv'
    path.write_text('kalshi_event_id,polymarket_exchange,polymarket_event_id,verified_rules,notes\n'
                    'K2028,Polymarket US,E2028,false,not yet checked\n'
                    'K2028,Polymarket US,E2028,true,checked\n')
    mappings=read_mappings(path)
    assert mappings=={'K2028':[('Polymarket US','E2028')]}
    k=make_quote('Kalshi','Gavin Newsom',.16,'K2028','2028 Democratic presidential nominee')
    cards=combine_quotes([k],_us_event_quotes(us_event()),mappings)
    assert cards[0].rule_reviewed


def test_unverified_mapping_export_stays_unverified():
    k=make_quote('Kalshi','Gavin Newsom',.16,'K2028','2028 Democratic presidential nominee')
    cards=combine_quotes([k],_us_event_quotes(us_event()))
    rows=proposed_mapping_rows(cards)
    assert rows and rows[0]['verified_rules']=='false'
    assert rows[0]['polymarket_exchange']=='Polymarket US'


def test_index_store_is_ttl_bounded(tmp_path):
    db=tmp_path/'index.sqlite3'
    q=make_quote('Kalshi','Gavin Newsom',.16,'K2028','2028 Democratic presidential nominee')
    assert add_quotes([q],db,now=1000)==1
    assert len(recent_quotes(300,db,now=1200))==1
    assert recent_quotes(300,db,now=1400)==[]
    q.probability=.17
    add_quotes([q],db,now=1450)
    assert recent_quotes(300,db,now=1500)[0].probability==.17


def test_verified_outcome_alias_can_identify_renamed_candidate(tmp_path):
    from mappings import read_outcome_mappings,proposed_outcome_rows
    k=make_quote('Kalshi','Gavin Newsom',.16,'K2028','2028 Democratic presidential nominee')
    p=make_quote('Polymarket US','G. Newsom',.18,'E2028','Democratic Presidential Nominee 2028')
    assert len(combine_quotes([k],[p]))==2
    file=tmp_path/'outcome_aliases.csv'
    file.write_text('kalshi_market_id,polymarket_exchange,polymarket_market_id,verified_rules,notes\n'
                    f'{k.market_id},Polymarket US,{p.market_id},true,checked\n')
    codes=read_outcome_mappings(file)
    cards=combine_quotes([k],[p],outcome_aliases=codes)
    assert len(cards)==1 and cards[0].matched
    assert proposed_outcome_rows(cards)[0]['verified_rules']=='false'
