"""Optional one-shot active-market scanner, separate from the Streamlit dashboard.

Usage: python index_markets.py --kalshi-pages 25 --poly-pages 25 --us-pages 10
This populates the local SQLite short-lived quote index only. It does NOT
backfill resolved markets or install a background job. On Streamlit Cloud the
local SQLite file is ephemeral and may be lost on redeploy or restart.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from feeds import fetch_kalshi, fetch_polymarket, fetch_polymarket_us
from index_store import add_quotes, store_stats


def main():
    parser=argparse.ArgumentParser(description='Collect current active prediction-market quotes')
    parser.add_argument('--kalshi-pages',type=int,default=12)
    parser.add_argument('--poly-pages',type=int,default=12)
    parser.add_argument('--us-pages',type=int,default=4)
    parser.add_argument('--no-us',action='store_true')
    args=parser.parse_args()
    feeds=[('Kalshi',fetch_kalshi,args.kalshi_pages),('Polymarket Intl',fetch_polymarket,args.poly_pages)]
    if not args.no_us:feeds.append(('Polymarket US',fetch_polymarket_us,args.us_pages))
    for name, fn, pages in feeds:
        try:
            rows,meta=fn(max_pages=max(1,pages))
            stored=add_quotes(rows)
            print(f'{name}: {len(rows)} usable quotes saved; {meta.get("events_scanned")} records scanned; '
                  f'{"complete" if meta.get("complete") else "partial"} pagination; {meta.get("endpoint")}')
        except Exception as ex:
            print(f'{name}: unavailable ({str(ex)[:220]})')
    stats=store_stats()
    print(f'Index has {stats["quotes"]} stored quote records across {stats["events"]} venue-specific events.')
    print('Only observations fresher than the dashboard TTL are displayed; older values are never advertised as live.')


if __name__=='__main__':
    main()
