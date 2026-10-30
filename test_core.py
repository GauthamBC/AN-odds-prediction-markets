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
