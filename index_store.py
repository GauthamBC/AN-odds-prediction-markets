"""Short-lived, local SQLite index of recent public quotes.

Provides a normalized quote table and incremental discovery between Streamlit
reruns. This is an *ephemeral* runtime index on Streamlit Cloud, not a permanent
hosted database or a background crawler. Only quotes fetched within TTL are
returned. Manually verified mappings are kept in GitHub CSV separately.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import time
from core import Quote

INDEX_PATH=Path(__file__).parent / '.an_live_index.sqlite3'


def _connect(path):
    conn=sqlite3.connect(str(path),timeout=5)
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('''CREATE TABLE IF NOT EXISTS latest_quotes (
        exchange TEXT NOT NULL, market_id TEXT NOT NULL,
        event_id TEXT NOT NULL, event_title TEXT NOT NULL, outcome TEXT NOT NULL,
        payload TEXT NOT NULL, seen_at REAL NOT NULL,
        PRIMARY KEY(exchange,market_id))''')
    conn.execute('CREATE INDEX IF NOT EXISTS quotes_seen_at ON latest_quotes(seen_at)')
    return conn


def add_quotes(quotes, path=INDEX_PATH, now=None):
    now=time.time() if now is None else now
    if not quotes:return 0
    with _connect(path) as conn:
        conn.executemany('''INSERT INTO latest_quotes
            (exchange,market_id,event_id,event_title,outcome,payload,seen_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(exchange,market_id) DO UPDATE SET
            event_id=excluded.event_id,event_title=excluded.event_title,
            outcome=excluded.outcome,payload=excluded.payload,seen_at=excluded.seen_at''',
            [(q.exchange,q.market_id,q.event_id,q.event_title,q.outcome,json.dumps(asdict(q)),now) for q in quotes])
        conn.execute('DELETE FROM latest_quotes WHERE seen_at < ?', (now-86400,))
    return len(quotes)


def recent_quotes(ttl_seconds=240, path=INDEX_PATH, now=None):
    now=time.time() if now is None else now
    if not Path(path).exists():return []
    with _connect(path) as conn:
        rows=conn.execute('SELECT payload FROM latest_quotes WHERE seen_at >= ?',
                          (now-ttl_seconds,)).fetchall()
    items=[]
    for (raw,) in rows:
        try:items.append(Quote(**json.loads(raw)))
        except (TypeError,ValueError):pass
    return items


def store_stats(path=INDEX_PATH):
    if not Path(path).exists():return {'quotes':0,'events':0}
    with _connect(path) as conn:
        rows=conn.execute('SELECT count(*),count(DISTINCT exchange || ":" || event_id) FROM latest_quotes').fetchone()
    return {'quotes':rows[0],'events':rows[1]}
