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
    s.headers.update({'User-Agent':'AN-Odds-Studio-Internal-Research/1.5', 'Accept':'application/json'})
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
    # Preserve the named selection even if API returns only one binary child.
    if is_binary and not m.get('groupItemTitle'):
        # Some grouped events omit groupItemTitle but put the candidate in the
        # contract question. Only infer a label for a very specific nomination
        # question; otherwise preserve the question / generic Yes accurately.
        if any(term in str(title).lower() for term in ('nominee', 'nomination')):
            import re
            match=re.match(r"^(?:will|does|can)\s+([a-z][a-z .'-]{2,65}?)\s+(?:be|win|become|get)\b",str(m.get('question') or ''),re.I)
            if match:
                label=match.group(1).strip()
        if len(event.get('markets') or [])==1 and label==str(m.get('question') or 'Yes'):
            label='Yes'
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
    """Read US quote objects; never reinterpret 65 as 65% without unit metadata."""
    if isinstance(value, dict):
        for key in ('value', 'price', 'px', 'amount'):
            if key in value:
                return _us_scalar(value[key])
        return None
    return probability(value)


def _us_market_sides(m):
    """Translate the documented Polymarket US marketSides into outcome quotes.

    Each side carries its own long/short direction and a display label may be
    supplied by subject/team/description. Generic NO sides are not separately
    listed as candidates. Restricting to long=True prevents mapping NO to YES.
    """
    sides = m.get('marketSides') or []
    if not isinstance(sides, list):
        return []
    result = []
    for index, side in enumerate(sides):
        if not isinstance(side, dict) or side.get('long') is not True:
            continue
        p = _us_scalar(side.get('price'))
        if p is None:
            p = _us_scalar(side.get('quote'))
        if p is None:
            continue
        subject = m.get('subject') or {}
        team = side.get('team') or {}
        if not isinstance(subject, dict): subject = {}
        if not isinstance(team, dict): team = {}
        label = (m.get('groupItemTitle') or m.get('outcomeName') or m.get('outcome')
                 or subject.get('displayName') or subject.get('name')
                 or m.get('titleShort') or m.get('subtitle')
                 or team.get('name') or side.get('description'))
        # 'Yes' is correct for a one-off binary proposition, but not for a
        # candidate contract whose question can name the person.
        if not label or str(label).strip().lower() in ('yes','no','long','buy yes','buy no'):
            label = _candidate_from_question(m.get('question') or '') or 'Yes'
        result.append((str(label).strip(), p, str(side.get('id') or index)))
    return result


def _candidate_from_question(q):
    import re
    match = re.match(r'^(?:will|does|can)\s+([a-z][a-z .\'-]{2,65}?)\s+(?:be|win|become|get|receive)\b',str(q).strip(), re.I)
    return match.group(1).strip() if match else None


def _us_bbo_price(s,slug):
    from urllib.parse import quote
    md=get_json(s,f'{POLY_US}/v1/markets/{quote(slug,safe="")}/bbo',{})
    md=md.get('marketData',md) if isinstance(md,dict) else {}
    if not isinstance(md,dict):return None
    bid=_us_scalar(md.get('bestBid'))
    ask=_us_scalar(md.get('bestAsk'))
    return midpoint(bid,ask,_us_scalar(md.get('currentPx')) or _us_scalar(md.get('lastTradePx')))


def _us_probability(m):
    outs=parse_array(m.get('outcomes'))
    prices=parse_array(m.get('outcomePrices'))
    if prices and (not outs or len(outs)==len(prices)):
        p=probability(prices[0])
        if p is not None: return p
    for k in ('yesPrice','yes_price','lastPrice','last_price','lastTradePrice','price'):
        p=_us_scalar(m.get(k))
        if p is not None:return p
    return midpoint(_us_scalar(m.get('bestBidQuote') or m.get('bestBid')),
                    _us_scalar(m.get('bestAskQuote') or m.get('bestAsk')))


def _us_rows(m,event=None):
    if not isinstance(m,dict) or m.get('closed') is True or m.get('active') is False or m.get('archived') is True:
        return []
    if str(m.get('status','')).lower() in ('closed','settled','resolved'):
        return []
    event=event or (m.get('event') if isinstance(m.get('event'),dict) else {}) or {}
    if event.get('active') is False or event.get('closed') is True or event.get('archived') is True:
        return []
    slug=str(m.get('slug') or m.get('marketSlug') or '')
    title=str(event.get('title') or m.get('eventTitle') or m.get('title') or m.get('question') or '')
    question=str(m.get('question') or title)
    eid=str(event.get('id') or event.get('slug') or m.get('eventId') or m.get('eventSlug') or slug or m.get('id'))
    mid=str(m.get('id') or slug or eid)
    subject=m.get('subject') if isinstance(m.get('subject'),dict) else {}
    label=(m.get('groupItemTitle') or m.get('outcomeName') or m.get('outcome')
           or m.get('label') or subject.get('displayName') or subject.get('name'))
    # Prefer native long-side quote and its associated subject/team metadata.
    raw_rows=_us_market_sides(m)
    if not raw_rows:
        p=_us_probability(m)
        if p is None:return []
        if not label or str(label).lower() in ('yes','no'):
            label=_candidate_from_question(question) or 'Yes'
        raw_rows=[(str(label),p,'0')]
    kind=category(title,(event.get('category') or m.get('category') or '')+' '+str(event.get('subcategory') or ''))
    return [Quote('Polymarket US',f'{mid}:{side_id}',eid,title,question,str(outcome),p,kind,
                  number(m.get('volume',m.get('volumeNum',0))),
                  number(m.get('liquidity',m.get('openInterest',0))),
                  m.get('endDate') or event.get('endDate') or m.get('gameStartTime'),
                  f'https://polymarket.us/event/{event.get("slug")}' if event.get('slug') else (f'https://polymarket.us/market/{slug}' if slug else 'https://polymarket.us'),
                  str(m.get('rulesDisclaimer') or m.get('description') or event.get('description') or '')[:800])
            for outcome,p,side_id in raw_rows if p is not None and 0 < p < 1]


def _us_market(m):
    """Backwards-compatible single-quote adapter; use _us_rows for real feeds."""
    rows=_us_rows(m)
    return rows[0] if rows else None


def _us_list(payload,plural):
    if isinstance(payload,list):return payload
    if not isinstance(payload,dict):return []
    data=payload.get(plural) or payload.get('data') or payload.get('results') or []
    if isinstance(data,dict):data=data.get(plural) or data.get('items') or []
    return data if isinstance(data,list) else []


def _us_event_quotes(ev):
    if not isinstance(ev,dict) or ev.get('active') is False or ev.get('closed') is True or ev.get('archived') is True:
        return []
    return [q for m in ev.get('markets') or [] if isinstance(m,dict) for q in _us_rows(m,ev)]


def fetch_polymarket_us(max_pages=3,bbo_limit=24):
    """Read parent events + nested marketSides first; fallback to market listings.

    Uses documented GET /v1/events (limit/offset/active/closed), then /v1/markets.
    Limited optional BBO requests for records with no usable displayed price.
    """
    s=session(); rows=[];seen=set();scanned=0;skipped=0;bbo_used=0;bbo_errors=0
    max_pages=max(1,int(max_pages));limit=100;exhausted=False;route='/v1/events';error=None
    try:
        for page in range(max_pages):
            events=_us_list(get_json(s,f'{POLY_US}/v1/events',{'limit':limit,'offset':page*limit,'active':'true','closed':'false'}),'events')
            scanned+=len(events)
            for ev in events:
                event_rows=_us_event_quotes(ev)
                for q in event_rows:
                    if (q.exchange,q.market_id) not in seen:rows.append(q);seen.add((q.exchange,q.market_id))
                if not event_rows:skipped+=1
            if len(events)<limit:exhausted=True;break
    except FeedError as exc:
        error=str(exc)
    if not rows:
        # Some exchange versions omit nested event prices, so market listings
        # can still provide standalone quotes. This is not an event join.
        route='/v1/markets (fallback)';scanned=0;exhausted=False
        for page in range(max_pages):
            markets=_us_list(get_json(s,f'{POLY_US}/v1/markets',{'limit':limit,'offset':page*limit,'active':'true','closed':'false'}),'markets')
            scanned+=len(markets)
            for m in markets:
                quote_rows=_us_rows(m)
                if not quote_rows and m.get('slug') and bbo_used<bbo_limit and m.get('active') is not False and m.get('closed') is not True:
                    bbo_used+=1
                    try:
                        price=_us_bbo_price(s,str(m['slug']))
                        if price is not None:
                            enriched=dict(m);enriched['yesPrice']=price
                            quote_rows=_us_rows(enriched)
                    except FeedError:bbo_errors+=1
                if not quote_rows:skipped+=1
                for q in quote_rows:
                    if (q.exchange,q.market_id) not in seen:rows.append(q);seen.add((q.exchange,q.market_id))
            if len(markets)<limit:exhausted=True;break
    return rows,{'events_scanned':scanned,'complete':exhausted,'endpoint':route,'pages':page+1,
                 'quotes':len(rows),'unpriced':skipped,'bbo_lookups':bbo_used,
                 'bbo_errors':bbo_errors,'event_feed_error':error}


def fetch_polymarket_us_search(query, limit=25):
    """Search on the US venue, which is distinct from Gamma International."""
    query=str(query).strip()
    if len(query)<4:return [],{'events_scanned':0,'quotes':0,'endpoint':'US /v1/search'}
    payload=get_json(session(),f'{POLY_US}/v1/search',{'query':query[:140],'limit':min(int(limit),50)})
    events=_us_list(payload,'events')
    markets=_us_list(payload,'markets')
    rows=[q for ev in events for q in _us_event_quotes(ev)]
    rows.extend(q for m in markets for q in _us_rows(m))
    return merge_quotes(rows),{'events_scanned':len(events),'quotes':len(rows),'endpoint':'US /v1/search'}

# Named, recognizable events are fetched from the exchange itself by slug. No
# odds or outcomes are hard-coded. These are discovery hints, not quote sources.
KNOWN_GAMMA_SLUGS = {
    ('politics', 'us-president-nominee-dem-2028'): 'democratic-presidential-nominee-2028',
    ('politics', 'us-president-nominee-rep-2028'): 'republican-presidential-nominee-2028',
}


def _gamma_event_rows(payload):
    """Normalize nested events from Gamma /events or /public-search."""
    if isinstance(payload, dict):
        events = payload.get('events') or []
    elif isinstance(payload, list):
        events = payload
    else:
        events = []
    result = []
    for ev in events:
        if not isinstance(ev, dict) or ev.get('closed') is True or ev.get('active') is False:
            continue
        for market in ev.get('markets') or []:
            if isinstance(market, dict):
                result.extend(_poly_market(market, ev))
    return result


def fetch_polymarket_search(query: str, limit: int = 30):
    """Use documented Gamma public search to find markets outside the top-volume scan.

    Returns quotes with the exact same identifiers as the ordinary Gamma feed.
    Searches only active events; verification of event rules is still required.
    """
    query = str(query).strip()
    if len(query) < 4 or len(query) > 150:
        return [], {'events_scanned': 0, 'quotes': 0, 'endpoint': '/public-search'}
    s = session()
    payload = get_json(s, f'{POLY}/public-search', {
        'q': query, 'limit_per_type': max(5, min(50, int(limit))),
        'events_status': 'active', 'keep_closed_markets': 0,
    })
    if not isinstance(payload, dict):
        raise FeedError('Gamma public search returned unexpected data')
    events = payload.get('events') or []
    rows = _gamma_event_rows(payload)
    return rows, {'events_scanned': len(events), 'quotes': len(rows),
                  'endpoint': '/public-search', 'query': query}


def fetch_polymarket_slug(slug: str):
    """Retrieve one known event by exact slug from the official Gamma event API."""
    slug = str(slug).strip()
    if not slug or '/' in slug or len(slug) > 150:
        return []
    response = get_json(session(), f'{POLY}/events', {'slug': slug})
    return _gamma_event_rows(response)


def merge_quotes(*lists):
    """Remove duplicate contract outcomes when discovery and paginated scans overlap."""
    unique = {}
    for batch in lists:
        for q in batch:
            unique[(q.exchange, q.market_id)] = q
    return list(unique.values())
