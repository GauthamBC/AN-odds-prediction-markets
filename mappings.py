"""Durable, repo-backed verified event-pair mappings (no automatic promotion).

Entries are trusted only when verified_rules is explicitly true. Never treat
simple title similarity as evidence that settlement rules match. No writes are
performed by the public Streamlit UI; download candidates and review before
committing them into the CSV in GitHub.
"""
from __future__ import annotations
import csv
from pathlib import Path

TRUTHY={'1','true','yes','verified','y'}
HEADERS=['kalshi_event_id','polymarket_exchange','polymarket_event_id','verified_rules','notes']


def read_mappings(path):
    result={}
    path=Path(path)
    if not path.is_file():return result
    with path.open(newline='',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            k=str(row.get('kalshi_event_id') or '').strip()
            p=str(row.get('polymarket_event_id') or '').strip()
            venue=str(row.get('polymarket_exchange') or '').strip()
            verified=str(row.get('verified_rules') or '').strip().lower() in TRUTHY
            # Legacy two-column CSV entries are never treated as verified.
            if not (k and p and venue in ('Polymarket','Polymarket US') and verified):continue
            result.setdefault(k,[]).append((venue,p))
    return result


def proposed_mapping_rows(cards):
    result=[]
    for card in cards:
        if not card.matched:continue
        k=next((r.kalshi for r in card.rows if r.kalshi),None)
        p=next((r.polymarket for r in card.rows if r.polymarket),None)
        if not k or not p:continue
        result.append({'kalshi_event_id':k.event_id,'polymarket_exchange':p.exchange,
                       'polymarket_event_id':p.event_id,'verified_rules':'false',
                       'notes':f'Candidate: {card.title}; matching confidence {card.match_score:.0f}. Check settlement criteria.'})
    return result

OUTCOME_HEADERS=['kalshi_market_id','polymarket_exchange','polymarket_market_id','verified_rules','notes']


def read_outcome_mappings(path):
    """Read only pairs whose individual contracts were manually rule-checked."""
    path=Path(path)
    if not path.is_file():return set()
    result=set()
    with path.open(newline='',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            k=str(row.get('kalshi_market_id') or '').strip()
            p=str(row.get('polymarket_market_id') or '').strip()
            venue=str(row.get('polymarket_exchange') or '').strip()
            checked=str(row.get('verified_rules') or '').strip().lower() in TRUTHY
            if k and p and venue in ('Polymarket','Polymarket US') and checked:
                result.add((k,venue,p))
    return result


def proposed_outcome_rows(cards):
    rows=[]
    for card in cards:
        for row in card.rows:
            if not (row.kalshi and row.polymarket):continue
            rows.append({'kalshi_market_id':row.kalshi.market_id,
                         'polymarket_exchange':row.polymarket.exchange,
                         'polymarket_market_id':row.polymarket.market_id,
                         'verified_rules':'false',
                         'notes':f'{card.title}: {row.label}; check identical YES/NO settlement terms'})
    return rows
