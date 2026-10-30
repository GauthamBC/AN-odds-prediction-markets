"""Persistent *within Streamlit app runtime* SQLite snapshots; no automatic API polling.

Streamlit Community Cloud may erase local files on restart. Supabase/hosted DB needed
for durable cross-restart persistence. Don't silently claim cloud persistence.
"""
from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB = os.getenv('AN_SNAPSHOT_DB', 'an_snapshot.sqlite3')

def connect(path=DEFAULT_DB):
    con = sqlite3.connect(path, timeout=20, check_same_thread=False)
    con.execute('PRAGMA busy_timeout=20000')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE IF NOT EXISTS events (slug TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS details (slug TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL, full INTEGER NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    con.commit()
    return con

def meta(con):
    return dict(con.execute('SELECT key,value FROM metadata'))

def snapshot(con):
    return [json.loads(x[0]) for x in con.execute('SELECT payload FROM events')]

def detail(con, slug, *, full=False):
    row = con.execute('SELECT payload,full FROM details WHERE slug=?', (slug,)).fetchone()
    if not row or (full and not row[1]):
        return None
    return json.loads(row[0])

def save_detail(con, obj, *, full):
    slug = obj.get('slug')
    if not slug:
        return
    prior = con.execute('SELECT full FROM details WHERE slug=?', (slug,)).fetchone()
    if prior and prior[0] and not full:
        return
    with con:
        con.execute('INSERT OR REPLACE INTO details VALUES (?,?,?,?)',
            (slug,json.dumps(obj,allow_nan=False),datetime.now(timezone.utc).isoformat(),int(full)))

def publish(con, rows, *, pages, request_count, detail_rows=None, detail_errors=0):
    """Only called for complete successful catalogue; all-or-nothing replacement."""
    if not rows:
        raise ValueError('Empty catalogue; preserving previous saved snapshot.')
    stamp = datetime.now(timezone.utc).isoformat()
    details = detail_rows or []
    with con:
        con.execute('DELETE FROM events')
        con.executemany('INSERT INTO events VALUES (?,?)',
                        ((r['slug'],json.dumps(r,allow_nan=False)) for r in rows))
        # Every refresh invalidates old detail prices.
        con.execute('DELETE FROM details')
        for r in details:
            if not r.get('slug'):
                continue
            con.execute('INSERT OR REPLACE INTO details VALUES (?,?,?,?)',
                        (r['slug'],json.dumps(r,allow_nan=False),stamp,0))
        for k,v in {'updated_at':stamp,'pages':str(pages),'last_requests':str(request_count),
                    'event_count':str(len(rows)), 'details_prefetched':str(len(details)),
                    'detail_errors':str(detail_errors)}.items():
            con.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(k,v))
