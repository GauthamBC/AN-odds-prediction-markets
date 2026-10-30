"""EXPERIMENTAL public-data historical sampler for fixed 7-day-ahead forecasts.

This is NOT a complete historical archive builder and does NOT provide automatically
validated accuracy. Use audited event matching and held-out testing before publication.

Usage (from project root):
  python backfill_history.py --source kalshi --max-markets 250
  python backfill_history.py --source polymarket --max-markets 250

Each source requires external network access; the script adds only verified
binary-settled markets with a historic observed price close to 7 days before
an event's close timestamp. Results are appended incrementally to history.csv.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import time
from feeds import session, get_json, KALSHI, POLY, FeedError
from core import category, date_from_string, parse_array, number, clean_text
from matching import canonical_event_key

START = datetime(2025, 3, 1,tzinfo=timezone.utc)
DATA = Path(__file__).resolve().parent/'history.csv'
FIELDS = ('platform','category','event_key','observed_at','probability','outcome','horizon')


def get_price_kalshi(s, market, target):
    ticker=market.get('ticker')
    if not ticker:return None
    t=int(target.timestamp())
    params={'start_ts':t-86400,'end_ts':t+86400,'period_interval':60}
    candidates=[]
    for endpoint in [f'{KALSHI}/series/{ticker.split("-")[0]}/markets/{ticker}/candlesticks',
                     f'{KALSHI}/historical/markets/{ticker}/candlesticks']:
        try:
            data=get_json(s,endpoint,params)
            for x in data.get('candlesticks',[]):
                observed=x.get('end_period_ts')
                if not observed or abs(int(observed)-t)>86400:continue
                bid=number((x.get('yes_bid') or {}).get('close'),-1)
                ask=number((x.get('yes_ask') or {}).get('close'),-1)
                last=number((x.get('price') or {}).get('close'),-1)
                # Older API OHLC series may be quoted in cents; convert only
                # when the numeric magnitude clearly indicates cent pricing.
                if 1 < bid <= 100 and 1 < ask <= 100:
                    bid,ask=bid/100,ask/100
                if 1 < last <= 100:last=last/100
                p=(bid+ask)/2 if 0<bid<=ask<1 else last
                if 0<p<1:candidates.append((abs(int(observed)-t),observed,p))
            if candidates:break
        except FeedError:
            continue
    if not candidates:return None
    _,when,p=min(candidates)
    return datetime.fromtimestamp(int(when),timezone.utc),p


def get_price_poly(s, market, target):
    tokens=parse_array(market.get('clobTokenIds'))
    if not tokens:return None
    t=int(target.timestamp())
    try:
        data=get_json(s,'https://clob.polymarket.com/prices-history',
                      {'market':str(tokens[0]),'startTs':t-86400,'endTs':t+86400,'fidelity':60})
    except FeedError:
        return None
    xs=[]
    for x in data.get('history',[]):
        p=number(x.get('p'),-1)
        when=x.get('t')
        if when and 0<p<1 and abs(int(when)-t)<=86400:
            xs.append((abs(int(when)-t),int(when),p))
    if not xs:return None
    _,when,p=min(xs)
    return datetime.fromtimestamp(when,timezone.utc),p


def iter_kalshi(s,max_pages):
    # Current historical cutoff splits archived and newer settled markets.
    for endpoint in (f'{KALSHI}/markets',f'{KALSHI}/historical/markets'):
        cursor=None
        for _ in range(max_pages):
            params={'limit':500,'mve_filter':'exclude'}
            if endpoint.endswith('/markets') and '/historical/' not in endpoint:
                params['status']='settled'
                params['min_settled_ts']=int(START.timestamp())
            if cursor:params['cursor']=cursor
            try:
                data=get_json(s,endpoint,params)
            except FeedError as exc:
                print(f'Warning: {exc}',file=sys.stderr)
                break
            for x in data.get('markets',[]):yield x
            new=data.get('cursor')
            if not new or new==cursor:break
            cursor=new


def iter_poly(s,max_pages):
    for page in range(max_pages):
        params={'closed':'true','limit':300,'offset':page*300,'order':'closed_time','ascending':'false'}
        try:
            rows=get_json(s,f'{POLY}/markets',params)
        except FeedError as exc:
            print(f'Warning: {exc}',file=sys.stderr)
            break
        if not isinstance(rows,list):break
        yield from rows
        if len(rows)<300:break


def historical_event_key(title, outcome, cat):
    """Standardize recognizable events; never assume similarly named contracts match rules."""
    identifier=canonical_event_key(title,cat)
    parent=':'.join(identifier) if identifier else clean_text(title)
    outcome_key=clean_text(str(outcome).replace('.', ''))
    return parent+'|'+outcome_key


def build_row_kalshi(s,m):
    if m.get('result') not in ('yes','no'):return None
    closed=date_from_string(m.get('close_time'))
    if not closed or not START<=closed<datetime.now(timezone.utc):return None
    target=closed-timedelta(days=7)
    if target<START:return None
    quote=get_price_kalshi(s,m,target)
    if not quote:return None
    when,p=quote
    title=m.get('title') or ''
    outcome=m.get('yes_sub_title') or 'Yes'
    cat=category(title)
    key=historical_event_key(title,outcome,cat)
    return {'platform':'Kalshi','category':cat,'event_key':key,
            'observed_at':when.isoformat(),'probability':p,
            'outcome':1 if m['result']=='yes' else 0,'horizon':'2-7d'}


def build_row_poly(s,m):
    if m.get('closed') is not True:return None
    outs=parse_array(m.get('outcomes'))
    prices=parse_array(m.get('outcomePrices'))
    tokens=parse_array(m.get('clobTokenIds'))
    if len(outs)!=2 or len(prices)!=2 or len(tokens)<2:return None
    # Strictly resolved YES/NO binary markets only. Canceled/ambiguous excluded.
    if [str(x).lower() for x in outs]!=['yes','no']:return None
    a,b=number(prices[0],-.1),number(prices[1],-.1)
    if not ((a>=.999 and b<=.001) or (a<=.001 and b>=.999)):return None
    closed=date_from_string(m.get('closedTime') or m.get('endDate'))
    if not closed or not START<=closed<datetime.now(timezone.utc):return None
    target=closed-timedelta(days=7)
    if target<START:return None
    quote=get_price_poly(s,m,target)
    if not quote:return None
    when,p=quote
    title=m.get('question') or ''
    event_list=m.get('events') or []
    title_event=event_list[0].get('title',title) if event_list and isinstance(event_list[0],dict) else title
    cat=category(title_event)
    key=historical_event_key(title_event,m.get('groupItemTitle') or 'Yes',cat)
    return {'platform':'Polymarket','category':cat,'event_key':key,
            'observed_at':when.isoformat(),'probability':p,'outcome':1 if a>=.999 else 0,
            'horizon':'2-7d'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',choices=['kalshi','polymarket'],required=True)
    parser.add_argument('--max-markets',type=int,default=300,help='Max settled markets sampled per run')
    parser.add_argument('--max-pages',type=int,default=8,help='Stop paginated discovery after this many pages')
    args=parser.parse_args()
    DATA.parent.mkdir(parents=True,exist_ok=True)
    seen=set()
    if DATA.exists():
        with DATA.open(encoding='utf-8',newline='') as f:
            seen={(r.get('platform'),r.get('event_key'),r.get('observed_at')) for r in csv.DictReader(f)}
    s=session()
    scan=iter_kalshi(s,args.max_pages) if args.source=='kalshi' else iter_poly(s,args.max_pages)
    builder=build_row_kalshi if args.source=='kalshi' else build_row_poly
    scanned=added=0
    with DATA.open('a',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if f.tell()==0:w.writeheader()
        for market in scan:
            if scanned>=args.max_markets:break
            scanned+=1
            try:
                row=builder(s,market)
            except (ValueError,TypeError,KeyError,FeedError) as exc:
                print(f'Skipping {market.get("id",market.get("ticker"))}: {exc}',file=sys.stderr)
                continue
            if not row:continue
            key=(row['platform'],row['event_key'],row['observed_at'])
            if key in seen:continue
            w.writerow(row);f.flush();seen.add(key);added+=1
            if added%25==0:print('Saved',added,'records...')
            time.sleep(.08)
    print(f'Scanned {scanned}, appended {added} authentic eligible 7-day snapshots. Historical coverage is partial.')

if __name__=='__main__':main()
