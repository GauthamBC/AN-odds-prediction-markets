"""Synthetic regression cases modeled on user-provided dashboard comparisons.

These tests do not assert real exchange price correctness or live API parity.
"""
from core import Quote
from matching import combine_quotes, pair_score
from feeds import _kalshi_market, _poly_market


def q(source, event, title, name, p, category='Politics', date='2028-11-07T00:00:00Z', recent=0):
    return Quote(source, f'{event}-{name}', event, title, title, name, p, category,
                 1000, 250, date, 'https://example.test',volume_24h=recent)


def test_nominations_reordered_in_both_directions():
    kalshi=[q('Kalshi','K','2028 Democratic presidential nominee',n,p) for n,p in [('Gavin Newsom',.17),('Jon Ossoff',.16)]]
    poly=[q('Polymarket US','P','Democratic Presidential Nominee 2028',n,p) for n,p in [('Gavin Newsom',.19),('Jon Ossoff',.17)]]
    cs=combine_quotes(kalshi,poly)
    assert len(cs)==1 and cs[0].matched
    assert all(r.kalshi and r.polymarket for r in cs[0].rows)
    assert not cs[0].rule_reviewed


def test_nominee_never_joined_to_general_election():
    kalshi=[q('Kalshi','K','2028 Democratic presidential nominee','Gavin Newsom',.18)]
    poly=[q('Polymarket US','P','2028 US presidential election winner','Gavin Newsom',.20)]
    assert not any(c.matched for c in combine_quotes(kalshi,poly))


def test_sports_reversed_competitors_match_at_same_time():
    kalshi=[q('Kalshi','K','New England vs Miami',n,p,'Sports','2026-11-01T20:00:00Z') for n,p in [('New England',.55),('Miami',.45)]]
    poly=[q('Polymarket','P','Miami versus New England',n,p,'Sports','2026-11-01T21:00:00Z') for n,p in [('New England',.54),('Miami',.46)]]
    cs=combine_quotes(kalshi,poly)
    assert len(cs)==1 and cs[0].matched


def test_sports_different_match_dates_never_join():
    kalshi=[q('Kalshi','K','New England vs Miami',n,p,'Sports','2026-11-01T20:00:00Z') for n,p in [('New England',.55),('Miami',.45)]]
    poly=[q('Polymarket','P','Miami versus New England',n,p,'Sports','2026-11-15T21:00:00Z') for n,p in [('New England',.54),('Miami',.46)]]
    assert not any(c.matched for c in combine_quotes(kalshi,poly))


def test_shared_names_insufficient_without_same_event():
    kalshi=[q('Kalshi','K','Who wins 2028 presidential election?', 'Gavin Newsom',.23)]
    poly=[q('Polymarket','P','2028 Democratic presidential nominee','Gavin Newsom',.25)]
    assert not any(c.matched for c in combine_quotes(kalshi,poly))


def test_recent_activity_changes_popularity_order():
    a=[q('Kalshi','A','A vs B','A',.75,'Sports','2026-11-01T20:00:00Z',recent=3),
       q('Kalshi','A','A vs B','B',.25,'Sports','2026-11-01T20:00:00Z',recent=4)]
    b=[q('Kalshi','B','C vs D','C',.55,'Sports','2026-11-01T20:00:00Z',recent=60),
       q('Kalshi','B','C vs D','D',.45,'Sports','2026-11-01T20:00:00Z',recent=40)]
    assert combine_quotes(a+b,[])[0].title=='C vs D'


def test_volume24_field_from_kalshi():
    market={'ticker':'T-1','status':'open','market_type':'binary','yes_bid_dollars':'0.4',
            'yes_ask_dollars':'0.5','volume_fp':'1000','volume_24h_fp':'99'}
    out=_kalshi_market(market,{'title':'Some event','category':'Sports'})
    assert out.volume==1000 and out.volume_24h==99


def test_volume24_field_from_poly():
    market={'id':'8','active':True,'closed':False,'outcomes':['Yes','No'],
            'outcomePrices':['0.7','0.3'],'volumeNum':1000,'volume24hr':42,'groupItemTitle':'Team One'}
    out=_poly_market(market,{'id':'7','title':'Team One wins championship','tags':[{'label':'Sports'}]})
    assert out[0].volume_24h==42
