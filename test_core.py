from datetime import datetime, timezone
from core import Quote,american,midpoint,parse_array
from feeds import _kalshi_market,_poly_market
from matching import combine_quotes
from model import AccuracyModel, Observation, recency_weight


def q(exchange,outcome,p,*,event_id='123',title='Who will win the championship?'):
    return Quote(exchange,event_id+outcome,event_id,title,title,outcome,p,'Sports',100,10,'2026-12-01T00:00:00Z','https://example.com')

def test_american():
    assert american(.67)=='-203'
    assert american(.33)=='+203'
    assert american(.5)=='+100'
    assert american(None)=='—'

def test_midpoint():
    assert midpoint('0.30','0.50','0.44')==.4
    assert midpoint('0','0','0.37')==.37
    assert midpoint(None,None,None) is None

def test_kalshi_normalization():
    x=_kalshi_market({'ticker':'ABC-1','event_ticker':'ABC','status':'open','market_type':'binary',
                      'yes_bid_dollars':'0.44','yes_ask_dollars':'0.46','yes_sub_title':'Team A'},
                     {'title':'Who will win the NBA Finals?','category':'Sports'})
    assert x.exchange=='Kalshi' and abs(x.probability-.45)<1e-9 and x.outcome=='Team A'

def test_polymarket_binary():
    ev={'id':'e','title':'Will there be a hurricane?','slug':'hurricane','markets':[{}]}
    m={'id':'99','active':True,'closed':False,'outcomes':'["Yes","No"]',
       'outcomePrices':'["0.4","0.6"]'}
    out=_poly_market(m,ev)
    assert len(out)==1 and out[0].outcome=='Yes' and out[0].probability==.4

def test_conservative_matching():
    ka=q('Kalshi','Team A',.7,event_id='k')
    po=q('Polymarket','Team A',.6,event_id='p')
    cards=combine_quotes([ka],[po]); assert len(cards)==1 and cards[0].matched
    wrong=q('Polymarket','Team B',.6,event_id='p')
    cards=combine_quotes([ka],[wrong]); assert len(cards)==2 and not any(c.matched for c in cards)

def test_untrained_model_does_not_fake_single_source_prediction():
    m=AccuracyModel([])
    x=m.predict(q('Kalshi','Team A',.7),q('Polymarket','Team A',.6))
    assert abs(x['probability']-.65)<1e-9 and not x['calibrated']
    assert m.predict(q('Kalshi','Team A',.7),None)['probability'] is None

def test_recency_weight_decay():
    now=datetime(2026,10,30,tzinfo=timezone.utc)
    assert recency_weight(datetime(2026,10,30,tzinfo=timezone.utc),now)==1
    assert abs(recency_weight(datetime(2025,4,30,tzinfo=timezone.utc),now)-.5)<.03


def test_polymarket_fetch_reads_nested_event(monkeypatch):
    import feeds
    ev = {'id':'evt-1', 'slug':'championship-2026',
          'title':'Who will win the NBA Finals?', 'tags':[{'label':'Sports'}],
          'markets':[{'id':'m-1', 'active':True, 'closed':False,
                      'groupItemTitle':'Team A',
                      'outcomes':'["Yes", "No"]',
                      'outcomePrices':'["0.73", "0.27"]'}]}
    monkeypatch.setattr(feeds,'session',lambda:object())
    monkeypatch.setattr(feeds,'get_json',lambda session,url,params:[ev])
    quotes,meta=feeds.fetch_polymarket(3)
    assert len(quotes)==1
    assert quotes[0].exchange=='Polymarket'
    assert quotes[0].outcome=='Yes' # Single binary event, show YES
    assert quotes[0].probability==.73
    assert meta['endpoint']=='/events'
    assert meta['complete']


def test_polymarket_market_fallback(monkeypatch):
    import feeds
    m={'id':'44', 'active':True, 'closed':False,
       'question':'Will there be a major hurricane?',
       'slug':'major-hurricane',
       'outcomes':'["Yes","No"]',
       'outcomePrices':'["0.35","0.65"]'}
    calls=[]
    def fake_get_json(session,url,params):
        calls.append(url)
        if url.endswith('/events'):
            raise feeds.FeedError('simulated /events API problem')
        return [m]
    monkeypatch.setattr(feeds,'session',lambda:object())
    monkeypatch.setattr(feeds,'get_json',fake_get_json)
    quotes,meta=feeds.fetch_polymarket(2)
    assert any('/events' in url for url in calls)
    assert any('/markets' in url for url in calls)
    assert len(quotes)==1 and abs(quotes[0].probability-.35)<1e-9
    assert meta['endpoint']=='/markets (fallback)'


def test_unmatched_market_cards_show_both_exchanges_at_top():
    kalshi=[q('Kalshi','Team A',.7,event_id='k'+str(i),title='Kalshi event '+str(i)) for i in range(3)]
    polymarket=[q('Polymarket','Team B',.4,event_id='p'+str(i),title='Polymarket event '+str(i)) for i in range(3)]
    cards=combine_quotes(kalshi,polymarket)
    assert len(cards)==6
    assert [cards[i].rows[0].kalshi is not None for i in range(4)]==[True,False,True,False]
    assert [cards[i].rows[0].polymarket is not None for i in range(4)]==[False,True,False,True]


def test_presidential_market_titles_match_across_exchanges():
    from matching import canonical_event_key
    k=q('Kalshi','Gavin Newsom',.16,event_id='kal-2028',
        title='2028 U.S. Presidential Election winner?')
    p=q('Polymarket','Gavin Newsom',.17,event_id='poly-2028',
        title='Presidential Election Winner 2028')
    assert canonical_event_key(k.event_title,'Sports') is None
    k.category=p.category='Politics'
    cards=combine_quotes([k],[p])
    assert len(cards)==1 and cards[0].matched
    assert abs(cards[0].rows[0].polymarket.probability-.17)<1e-6


def test_nomination_not_presidential_general_election():
    k=q('Kalshi','Gavin Newsom',.16,event_id='kal',
        title='2028 Democratic presidential nominee')
    p=q('Polymarket','Gavin Newsom',.17,event_id='poly',
        title='Presidential Election Winner 2028')
    k.category=p.category='Politics'
    assert len(combine_quotes([k],[p]))==2


def test_political_year_not_matched_even_with_same_candidate():
    k=q('Kalshi','Gavin Newsom',.16,event_id='kal',title='2028 U.S. Presidential Election winner?')
    p=q('Polymarket','Gavin Newsom',.17,event_id='poly',title='Presidential Election Winner 2032')
    k.category=p.category='Politics'
    assert len(combine_quotes([k],[p]))==2


def test_us_feed_explicit_price_and_separate_venue(monkeypatch):
    import feeds
    monkeypatch.setattr(feeds,'session',lambda:object())
    sample={'markets':[{'id':'77','slug':'senate-texas-dem','eventId':'senate-tx-2026',
                        'eventTitle':'Texas Senate winner 2026',
                        'question':'Will Democrat win Texas Senate?',
                        'outcome':'Democrat', 'yesPrice':'0.65',
                        'active':True,'closed':False,'category':'Politics'}]}
    monkeypatch.setattr(feeds,'get_json',lambda *args:sample)
    quotes,meta=feeds.fetch_polymarket_us(3,bbo_limit=0)
    assert len(quotes)==1 and quotes[0].exchange=='Polymarket US'
    assert abs(quotes[0].probability-.65)<1e-9
    assert meta['complete'] and meta['events_scanned']==1


def test_us_unpriced_market_bbo_fallback(monkeypatch):
    import feeds
    monkeypatch.setattr(feeds,'session',lambda:object())
    markets={'markets':[{'id':'1','slug':'market-one','eventTitle':'Hurricane 2026',
                         'active':True,'closed':False,'category':'Weather'}]}
    def getter(session,url,params):
        if url.endswith('/bbo'):
            return {'marketData':{'bestBid':{'px':{'value':'0.43'}},
                                  'bestAsk':{'px':{'value':'0.47'}}}}
        return markets
    monkeypatch.setattr(feeds,'get_json',getter)
    quotes,meta=feeds.fetch_polymarket_us(1,bbo_limit=2)
    assert len(quotes)==1 and abs(quotes[0].probability-.45)<1e-9
    assert meta['bbo_lookups']==1


def test_us_resolved_market_not_shown(monkeypatch):
    import feeds
    monkeypatch.setattr(feeds,'session',lambda:object())
    monkeypatch.setattr(feeds,'get_json',lambda *args:{'markets':[{'slug':'ended','yesPrice':.8,
                                                                  'status':'settled','closed':True}]})
    quotes,_=feeds.fetch_polymarket_us(1,bbo_limit=0)
    assert not quotes


def test_matching_us_does_not_use_international_history():
    k=q('Kalshi','Team A',.7,event_id='k')
    p=q('Polymarket US','Team A',.6,event_id='p')
    m=AccuracyModel([])
    r=m.predict(k,p)
    assert abs(r['probability']-.65)<1e-10 and r['paired_samples']==0 and not r['calibrated']
