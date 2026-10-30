"""Public, read-only prediction-market feeds. No trading credentials required.

All API coverage numbers are partial until pagination has truly exhausted.
Polymarket International and Polymarket US are separate exchanges: never silently
combine their quotes into one source or pretend one is the other.
"""
from __future__ import annotations
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from core import Quote, category, midpoint, number, parse_array, probability

KALSHI = 'https://external-api.kalshi.com/trade-api/v2'
POLY = 'https://gamma-api.polymarket.com'
POLY_US = 'https://gateway.polymarket.us'

class FeedError(RuntimeError):
    pass

def session():
    s=requests.Session()
    s.headers.update({'User-Agent':'AN-Odds-Studio-Internal-Research/1.3', 'Accept':'application/json'})
    retries=Retry(total=2, connect=2, read=1, backoff_factor=.5,
                  status_forcelist=[429,500,502,503,504], allowed_methods=['GET'])
    s.mount('https://',HTTPAdapter(max_retries=retries,pool_connections=12,pool_maxsize=12))
    return s

def get_json(s,url,params):
    try:
        response=s.get(url,params=params,timeout=(5,16))
        response.raise_for_status()
        return response.json()
    except (requests.RequestException,ValueError) as exc:
        raise FeedError(f'{url.split("/")[2]}: {str(exc)[:160]}') from exc


def _kalshi_market(m,event):
    if m.get('status','open') not in ('open','active') or m.get('market_type','binary') not in ('binary',''):
        return None
    p=midpoint(m.get('yes_bid_dollars'),m.get('yes_ask_dollars'),m.get('last_price_dollars'))
    if p is None:
        p=midpoint(number(m.get('yes_bid'))/100 if m.get('yes_bid') is not None else None,
                   number(m.get('yes_ask'))/100 if m.get('yes_ask') is not None else None,
                   number(m.get('last_price'))/100 if m.get('last_price') is not None else None)
    if p is None:return None
    title=event.get('title') or m.get('title') or 'Untitled market'
    outcome=m.get('yes_sub_title') or m.get('subtitle') or 'Yes'
    mid=str(m.get('ticker') or '')
    eid=str(m.get('event_ticker') or event.get('event_ticker') or mid)
    return Quote('Kalshi',mid,eid,title,m.get('title') or title,str(outcome),p,
                 category(title,event.get('category') or event.get('series_ticker') or ''),
                 number(m.get('volume_fp',m.get('volume'))),
                 number(m.get('liquidity_dollars'),number(m.get('open_interest_fp'))),
                 m.get('expected_expiration_time') or m.get('close_time'),
                 f'https://kalshi.com/markets/{eid.lower()}',
                 (m.get('rules_primary') or '')[:800])


def fetch_kalshi(max_pages=8):
    s=session(); quotes=[]; cursor=None; seen_cursors=set(); seen_events=set(); scanned=0; exhausted=False
    for page in range(max_pages):
        params={'limit':200,'status':'open','with_nested_markets':'true'}
        if cursor:params['cursor']=cursor
        try:payload=get_json(s,f'{KALSHI}/events',params)
        except FeedError:
            if page: break
            raise
        events=payload.get('events') or []
        scanned+=len(events)
        for ev in events:
            if not isinstance(ev,dict):continue
            eid=str(ev.get('event_ticker'))
            if eid in seen_events:continue
            seen_events.add(eid)
            quotes.extend(q for m in ev.get('markets',[]) if isinstance(m,dict) if (q:=_kalshi_market(m,ev)))
        nxt=payload.get('cursor')
        if not nxt or nxt==cursor or nxt in seen_cursors or not events:
            exhausted=True;break
        seen_cursors.add(nxt);cursor=nxt
    return quotes,{'events_scanned':scanned,'complete':exhausted,'endpoint':'/events',
                   'pages':page+1,'quotes':len(quotes)}


def _poly_market(m,event):
    if m.get('closed') is True or m.get('active') is False:return []
    outs=parse_array(m.get('outcomes'));prices=parse_array(m.get('outcomePrices'))
    if not outs or len(outs)!=len(prices):return []
    title=event.get('title') or m.get('question') or 'Untitled market'
    tags=event.get('tags') or []
    raw=' '.join(t.get('label','') if isinstance(t,dict) else str(t) for t in tags)
    kind=category(title,raw)
    mid=str(m.get('id') or m.get('conditionId') or m.get('slug') or '')
    eid=str(event.get('id') or m.get('eventId') or mid)
    slug=event.get('slug') or m.get('slug') or ''
    link=f'https://polymarket.com/event/{slug}'
    is_binary=len(outs)==2 and [str(o).strip().lower() for o in outs]==['yes','no']
    label=m.get('groupItemTitle') or m.get('question') or 'Yes'
    if is_binary and len(event.get('markets') or [])==1:label='Yes'
    out=[]
    for i,(name,value) in enumerate(zip(outs,prices)):
        if is_binary and i==1:continue
        p=probability(value)
        if p is None or not 0<p<1:continue
        outcome=label if is_binary else str(name)
        out.append(Quote('Polymarket',f'{mid}:{i}',eid,title,m.get('question') or title,
                         str(outcome),p,kind,number(m.get('volumeNum',m.get('volume'))),
                         number(m.get('liquidityNum',m.get('liquidity'))),
                         m.get('endDate') or event.get('endDate'),link,(m.get('description') or '')[:800]))
    return out


def _poly_from_market_listing(m):
    events=m.get('events') or []
    e=events[0] if events and isinstance(events[0],dict) else {}
    event={'id':str(e.get('id') or m.get('eventId') or m.get('id')),
           'title':e.get('title') or m.get('question') or 'Untitled market',
           'slug':e.get('slug') or m.get('slug'),'tags':e.get('tags') or m.get('tags') or [],
           'endDate':e.get('endDate') or m.get('endDate'),'markets':[m]}
    return _poly_market(m,event)


def _poly_events(s,max_pages,order='volume_24hr'):
    quotes=[]; scanned=0; seen=set();exhausted=False;skipped=0
    for page in range(max_pages):
        params={'active':'true','closed':'false','limit':100,'offset':page*100,
                'order':order,'ascending':'false'}
        events=get_json(s,f'{POLY}/events',params)
        if not isinstance(events,list):raise FeedError('Gamma /events returned non-list JSON')
        scanned+=len(events)
        for ev in events:
            if not isinstance(ev,dict):continue
            eid=str(ev.get('id') or ev.get('slug'))
            if eid in seen:continue
            seen.add(eid)
            for m in ev.get('markets') or []:
                if isinstance(m,dict):
                    rows=_poly_market(m,ev);quotes.extend(rows)
                    if not rows:skipped+=1
        if len(events)<100:exhausted=True;break
    return quotes,{'events_scanned':scanned,'complete':exhausted,'endpoint':'/events',
                   'pages':page+1,'quotes':len(quotes),'skipped':skipped}


def _poly_markets_fallback(s,max_pages):
    quotes=[];scanned=0;seen=set();exhausted=False
    for page in range(max_pages):
        params={'active':'true','closed':'false','limit':100,'offset':page*100,
                'order':'volumeNum','ascending':'false'}
        markets=get_json(s,f'{POLY}/markets',params)
        if not isinstance(markets,list):raise FeedError('Gamma /markets returned non-list JSON')
        scanned+=len(markets)
        for m in markets:
            if not isinstance(m,dict):continue
            key=str(m.get('id') or m.get('slug'))
            if key in seen:continue
            seen.add(key);quotes.extend(_poly_from_market_listing(m))
        if len(markets)<100:exhausted=True;break
    return quotes,{'events_scanned':scanned,'complete':exhausted,
                   'endpoint':'/markets (fallback)','pages':page+1,'quotes':len(quotes)}


def fetch_polymarket(max_pages=8):
    s=session();errors=[]
    for order in ('volume_24hr',None):
        try:
            q,meta=_poly_events(s,max_pages,order) if order else _poly_events(s,max_pages,'id')
            if q:return q,meta
            errors.append(f'{order}: no parseable prices')
        except FeedError as exc:errors.append(str(exc))
    try:
        q,meta=_poly_markets_fallback(s,max_pages)
        if q:return q,meta
    except FeedError as exc:errors.append(str(exc))
    raise FeedError('Gamma feed unavailable: '+' | '.join(errors[-3:]))


def _us_scalar(value):
    """Extract a YES-side price from price-node objects used in the US book."""
    if isinstance(value,dict):
        for k in ('px','price','value','amount'):
            if k in value:return _us_scalar(value[k])
        return None
    return probability(value)


def _us_bbo_price(s,slug):
    from urllib.parse import quote
    data=get_json(s,f'{POLY_US}/v1/markets/{quote(slug,safe="")}/bbo',{})
    md=data.get('marketData',data) if isinstance(data,dict) else {}
    if not isinstance(md,dict):return None
    bid=_us_scalar(md.get('bestBid') or md.get('bid'))
    ask=_us_scalar(md.get('bestAsk') or md.get('ask'))
    return midpoint(bid,ask)


def _us_probability(m):
    """Only use documented price-like fields; do not interpret missing price as zero.

    Market listings can be metadata-only. If so we omit the quote rather than
    manufacture a probability; optional BBO fetching may supply one later.
    """
    outs=parse_array(m.get('outcomes'))
    prices=parse_array(m.get('outcomePrices'))
    if len(prices)>=1 and (not outs or len(outs)==len(prices)):
        p=probability(prices[0])
        if p is not None and 0<p<1:return p
    for key in ('yesPrice','yes_price','lastPrice','last_price','lastTradePrice','price'):
        p=probability(m.get(key))
        if p is not None and 0<p<1:return p
    return midpoint(_us_scalar(m.get('bestBid')),_us_scalar(m.get('bestAsk')))


def _us_market(m):
    if not isinstance(m,dict):return None
    if m.get('closed') is True or m.get('active') is False or str(m.get('status','')).lower() in ('closed','settled','resolved'):
        return None
    # Polymarket US often has a binary YES contract per event outcome.
    p=_us_probability(m)
    if p is None:return None
    ev=m.get('event') if isinstance(m.get('event'),dict) else {}
    slug=str(m.get('slug') or m.get('marketSlug') or '')
    title=ev.get('title') or m.get('eventTitle') or m.get('title') or m.get('question') or ''
    question=m.get('question') or title
    label=m.get('groupItemTitle') or m.get('outcome') or m.get('outcomeName') or m.get('label') or 'Yes'
    # For independent binary questions, Yes is the only defensible label.
    outs=parse_array(m.get('outcomes'))
    if label=='Yes' and len(outs)>0 and str(outs[0]).strip().lower() not in ('yes','no'):
        label=outs[0]
    mid=str(m.get('id') or slug)
    eid=str(ev.get('id') or m.get('eventId') or m.get('eventSlug') or slug)
    return Quote('Polymarket US',mid,eid,str(title),str(question),str(label),p,
                 category(title,ev.get('category') or m.get('category') or ''),
                 number(m.get('volume') or m.get('volumeNum') or m.get('volume24hr')),
                 number(m.get('liquidity') or m.get('openInterest')),
                 m.get('endDate') or m.get('closeTime') or ev.get('endDate'),
                 f'https://polymarket.us/market/{slug}' if slug else 'https://polymarket.us',
                 str(m.get('rules') or m.get('description') or '')[:800])


def fetch_polymarket_us(max_pages=3,bbo_limit=24):
    """Optional US public gateway; endpoint not identical to Gamma.

    Some listings have metadata but no price. Report that fact explicitly.
    Do not make extra per-contract BBO requests on a dashboard-wide scan.
    """
    s=session();quotes=[];scanned=0;seen=set();exhausted=False;unpriced=0;bbo_used=0;bbo_errors=0
    limit=100
    for page in range(max_pages):
        params={'limit':limit,'offset':page*limit,'active':'true','closed':'false'}
        try:data=get_json(s,f'{POLY_US}/v1/markets',params)
        except FeedError:
            if page:break
            raise
        if isinstance(data,dict):
            markets=data.get('markets') or data.get('data') or data.get('results') or []
            if isinstance(markets,dict):markets=markets.get('markets') or markets.get('items') or []
        elif isinstance(data,list):markets=data
        else:markets=[]
        if not isinstance(markets,list):raise FeedError('US /v1/markets unexpected response structure')
        scanned+=len(markets)
        for m in markets:
            if not isinstance(m,dict):continue
            key=str(m.get('id') or m.get('slug'))
            if key in seen:continue
            seen.add(key)
            q=_us_market(m)
            if q is None and m.get('slug') and bbo_used<bbo_limit and m.get('active') is not False and not m.get('closed'):
                bbo_used+=1
                try:
                    bookprice=_us_bbo_price(s,str(m['slug']))
                    if bookprice is not None:
                        enriched=dict(m);enriched['yesPrice']=bookprice
                        q=_us_market(enriched)
                except FeedError:
                    bbo_errors+=1
            if q:quotes.append(q)
            else:unpriced+=1
        if len(markets)<limit:exhausted=True;break
    return quotes,{'events_scanned':scanned,'complete':exhausted,'endpoint':'US /v1/markets',
                   'pages':page+1,'quotes':len(quotes),'unpriced':unpriced,
                   'bbo_lookups':bbo_used,'bbo_errors':bbo_errors}
