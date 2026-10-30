"""Read-only public API clients, no API keys or account permissions required.

Prices are indicative exchange-implied probabilities, NOT executable betting odds.
"""
from __future__ import annotations
import logging
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from core import Quote, category, midpoint, number, parse_array, probability

KALSHI = "https://external-api.kalshi.com/trade-api/v2"
POLY = "https://gamma-api.polymarket.com"

class FeedError(RuntimeError):
    pass


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": "ActionNetworkOddsStudioPrototype/0.1 (research dashboard)", "Accept": "application/json"})
    retry = Retry(total=3, connect=3, read=2, backoff_factor=0.8,
                  status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10))
    return s


def get_json(s, url, params):
    try:
        response = s.get(url, params=params, timeout=(7, 24))
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise FeedError(f"{url.split('/')[2]}: {str(exc)[:180]}") from exc


def _kalshi_market(m, event):
    if (m.get("status") or "open") not in ("open", "active"):
        return None
    # Explicit binary YES contract only. Numeric/scalar markets without YES/NO semantics omitted.
    if m.get("market_type", "binary") not in ("binary", ""):
        return None
    p = midpoint(m.get("yes_bid_dollars"), m.get("yes_ask_dollars"), m.get("last_price_dollars"))
    if p is None:
        # Older fallback: cent-based fields. Never reinterpret new *_dollars as cents.
        p = midpoint(
            number(m.get("yes_bid"), 0) / 100 if m.get("yes_bid") is not None else None,
            number(m.get("yes_ask"), 0) / 100 if m.get("yes_ask") is not None else None,
            number(m.get("last_price"), 0) / 100 if m.get("last_price") is not None else None)
    if p is None:
        return None
    event_title = event.get("title") or m.get("title") or "Untitled market"
    outcome = m.get("yes_sub_title") or m.get("subtitle") or "Yes"
    market_id = str(m.get("ticker") or "")
    event_id = str(m.get("event_ticker") or event.get("event_ticker") or market_id)
    return Quote("Kalshi", market_id, event_id, event_title, m.get("title") or event_title,
                 str(outcome), p, category(event_title, event.get("category", "")),
                 number(m.get("volume_fp", m.get("volume"))),
                 number(m.get("liquidity_dollars"), number(m.get("open_interest_fp"))),
                 m.get("expected_expiration_time") or m.get("close_time"),
                 "https://kalshi.com/markets",
                 (m.get("rules_primary") or "")[:500])


def fetch_kalshi(max_pages=4):
    """Fetch open events, 200/page; provide cursor exhaust signal. Large fetches can take time."""
    s = session()
    quotes = []
    cursor = None
    exhausted = False
    fetched = 0
    seen_cursors = set()
    for _ in range(max_pages):
        params = {"limit": 200, "status": "open", "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        payload = get_json(s, f"{KALSHI}/events", params)
        events = payload.get("events", [])
        fetched += len(events)
        for e in events:
            for m in e.get("markets", []):
                q = _kalshi_market(m, e)
                if q: quotes.append(q)
        next_cursor = payload.get("cursor")
        if not next_cursor or next_cursor in seen_cursors or not events:
            exhausted = True
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return quotes, {"events_scanned":fetched, "complete":exhausted}


def _poly_market(m, event):
    if m.get("closed") or m.get("active") is False:
        return []
    outs = parse_array(m.get("outcomes"))
    prices = parse_array(m.get("outcomePrices"))
    if not outs or len(outs) != len(prices):
        return []
    name = event.get("title") or m.get("question") or "Untitled market"
    tags = event.get("tags") or []
    tag_names = " ".join(t.get("label", "") if isinstance(t, dict) else str(t) for t in tags)
    kind = category(name, tag_names)
    ident = str(m.get("id") or m.get("conditionId") or m.get("slug") or "")
    eid = str(event.get("id") or m.get("id") or "")
    url_slug = event.get("slug") or m.get("slug") or ""
    link = f"https://polymarket.com/event/{url_slug}"
    quote_list = []
    group_label = m.get("groupItemTitle") or ""
    # In a market with YES/NO, the YES token is the contract. In a multi-outcome market,
    # each named outcome is a separate contract.
    is_binary = len(outs) == 2 and [str(o).strip().lower() for o in outs] == ["yes", "no"]
    for i, (out, p_raw) in enumerate(zip(outs, prices)):
        if is_binary and i == 1:
            continue
        p = probability(p_raw)
        if p is None or not 0 < p < 1:
            continue
        label = (group_label or m.get("question") or "Yes") if is_binary else str(out)
        # for a single binary event, a YES token represents 'Yes'.
        if is_binary and len(event.get("markets") or []) == 1:
            label = "Yes"
        quote_list.append(Quote("Polymarket", f"{ident}:{i}", eid, name, m.get("question") or name,
                                label, p, kind, number(m.get("volumeNum", m.get("volume"))),
                                number(m.get("liquidityNum", m.get("liquidity"))),
                                m.get("endDate") or event.get("endDate"), link,
                                (m.get("description") or "")[:500]))
    return quote_list


def _poly_from_market_listing(m):
    """Normalize a standalone Gamma /markets item if /events has no nested quotes."""
    events = m.get("events") or []
    event = events[0] if events and isinstance(events[0], dict) else {}
    event = {"id":str(event.get("id") or m.get("eventId") or m.get("id")),
             "title":event.get("title") or m.get("question") or "Untitled market",
             "slug":event.get("slug") or m.get("slug"),
             "tags":event.get("tags") or m.get("tags") or [],
             "endDate":event.get("endDate") or m.get("endDate"),
             "markets":[m]}
    return _poly_market(m, event)


def _poly_events(s, max_pages, order=None):
    quotes, scanned, skipped, exhausted = [], 0, 0, False
    for page in range(max_pages):
        params = {"active":"true", "closed":"false", "limit":100, "offset":page*100}
        if order:
            params.update({"order":order,"ascending":"false"})
        events = get_json(s, f"{POLY}/events", params)
        if not isinstance(events, list):
            raise FeedError("Polymarket /events returned unexpected JSON (expected list)")
        scanned += len(events)
        for event in events:
            if not isinstance(event,dict):
                skipped += 1
                continue
            nested = event.get("markets") or []
            if not isinstance(nested,list):
                skipped += 1
                continue
            for m in nested:
                if isinstance(m,dict):
                    parsed = _poly_market(m,event)
                    quotes.extend(parsed)
                    if not parsed: skipped += 1
        if len(events) < 100:
            exhausted=True
            break
    return quotes, {"events_scanned":scanned, "contracts_skipped":skipped,
                    "complete":exhausted, "endpoint":"/events"}


def _poly_markets_fallback(s,max_pages):
    """Official alternate Gamma endpoint when events endpoint supplies no usable prices."""
    quotes, scanned, skipped, exhausted = [], 0, 0, False
    for page in range(max_pages):
        params = {"active":"true", "closed":"false", "limit":100,
                  "offset":page*100, "order":"volumeNum", "ascending":"false"}
        markets = get_json(s, f"{POLY}/markets", params)
        if not isinstance(markets,list):
            raise FeedError("Polymarket /markets returned unexpected JSON (expected list)")
        scanned += len(markets)
        for market in markets:
            if isinstance(market,dict):
                parsed=_poly_from_market_listing(market)
                quotes.extend(parsed)
                if not parsed: skipped += 1
        if len(markets)<100:
            exhausted=True
            break
    return quotes,{"events_scanned":scanned, "contracts_skipped":skipped,
                   "complete":exhausted, "endpoint":"/markets (fallback)"}


def fetch_polymarket(max_pages=4):
    """Public Gamma discovery: ranked events -> unsorted events -> independent markets fallback.

    Record which endpoint succeeded and never manufacture prices if all requests fail.
    """
    s=session()
    errors=[]
    # Different API versions have accepted different order field spellings.
    for ordering in ("volume24hr", "volume_24hr", None):
        try:
            quotes, meta=_poly_events(s,max_pages,ordering)
            if quotes:
                meta["sort"]=ordering or "default"
                return quotes, meta
            errors.append(f"/events sort={ordering}: no usable quotes")
        except FeedError as exc:
            errors.append(str(exc))
    try:
        quotes, meta=_poly_markets_fallback(s,max_pages)
        if quotes:
            return quotes,meta
        errors.append("/markets fallback: no usable quotes")
    except FeedError as exc:
        errors.append(str(exc))
    # Make the failure visible instead of implying unmatched odds are zero.
    raise FeedError("Polymarket did not return usable quotes. " + " | ".join(errors[-3:]))
