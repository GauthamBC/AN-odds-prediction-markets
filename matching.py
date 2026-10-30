"""Conservative event/outcome matching. Never assume similarly named markets share rules."""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from rapidfuzz import fuzz, process
from core import Quote, clean_text, date_from_string

@dataclass
class Row:
    label: str
    kalshi: Quote | None = None
    polymarket: Quote | None = None

@dataclass
class MarketCard:
    title: str
    category: str
    rows: list[Row]
    volume: float
    matched: bool
    match_score: float = 0.0


def outcome_compatible(k: Quote, p: Quote, single_k: bool, single_p: bool):
    a, b = clean_text(k.outcome), clean_text(p.outcome)
    if a and b and a == b:
        return True
    if a and b and fuzz.ratio(a, b) >= 90:
        return True
    # Both YES contracts with nearly identical questions in one-contract events.
    if single_k and single_p and a in ("", "yes") and b in ("", "yes") and fuzz.ratio(clean_text(k.question), clean_text(p.question)) >= 94:
        return True
    return False


def close_compatible(k: Quote, p: Quote):
    a, b = date_from_string(k.close_at), date_from_string(p.close_at)
    if a is None or b is None:
        return True
    # Different market closes can legitimately differ. Reject distant expirations;
    # never equate e.g. next month's outcome with next year's.
    return abs((a-b).days) <= (4 if k.category == "Sports" else 35)


def event_match_score(a: str, b: str):
    na, nb = clean_text(a), clean_text(b)
    if not na or not nb:
        return 0
    return max(fuzz.ratio(na, nb), fuzz.token_sort_ratio(na, nb),
               fuzz.ratio(na.replace(' ', ''), nb.replace(' ', '')))


def combine_quotes(kalshi: list[Quote], polymarket: list[Quote], aliases: dict | None = None):
    aliases = aliases or {}
    grouped = defaultdict(list)
    for q in kalshi + polymarket:
        grouped[(q.exchange, q.event_id)].append(q)
    k_events = {key: val for key, val in grouped.items() if key[0] == "Kalshi"}
    p_events = {key: val for key, val in grouped.items() if key[0] == "Polymarket"}
    p_by_category = defaultdict(list)
    for key, vals in p_events.items():
        p_by_category[vals[0].category].append(key)
    used_p = set()
    cards = []
    for k_key, ks in k_events.items():
        candidate = None
        best_score = 0
        title = ks[0].event_title
        for pk in p_by_category[ks[0].category]:
            if pk in used_p:
                continue
            ps = p_events[pk]
            explicit = aliases.get(ks[0].event_id) == ps[0].event_id
            score = 100.0 if explicit else event_match_score(title, ps[0].event_title)
            if score < 91:
                continue
            compatible = any(outcome_compatible(k, p, len(ks)==1, len(ps)==1)
                             and close_compatible(k, p) for k in ks for p in ps)
            if compatible and score > best_score:
                best_score, candidate = score, pk
        paired = p_events.get(candidate, []) if candidate else []
        if candidate:
            used_p.add(candidate)
        rows = []
        used_outcomes = set()
        for k in ks:
            p_match = None
            for p in paired:
                if p.market_id not in used_outcomes and outcome_compatible(k, p, len(ks)==1, len(paired)==1) and close_compatible(k,p):
                    p_match = p
                    used_outcomes.add(p.market_id)
                    break
            rows.append(Row(k.outcome if clean_text(k.outcome) != "yes" else "Yes", k, p_match))
        for p in paired:
            if p.market_id not in used_outcomes:
                rows.append(Row(p.outcome, None, p))
        cards.append(MarketCard(title, ks[0].category, rows,
                                sum(q.volume for q in ks + paired), candidate is not None,
                                best_score))
    for pk, ps in p_events.items():
        if pk in used_p:
            continue
        cards.append(MarketCard(ps[0].event_title, ps[0].category,
                                [Row(p.outcome, None, p) for p in ps],
                                sum(q.volume for q in ps), False))
    # Show each exchange in the first screen even when they have no cross-exchange match.
    # Sorting by pooled volume incorrectly mixes Kalshi contract counts with Polymarket USD.
    matched_cards=[c for c in cards if c.matched]
    only_k=[c for c in cards if not c.matched and any(r.kalshi for r in c.rows)]
    only_p=[c for c in cards if not c.matched and any(r.polymarket for r in c.rows)]
    matched_cards.sort(key=lambda c:-c.volume)  # approximate within matched events only
    only_k.sort(key=lambda c:-c.volume)          # within-exchange ordering
    only_p.sort(key=lambda c:-c.volume)
    # Alternation prevents one exchange from taking every initial dashboard card.
    mixed=[]
    for i in range(max(len(only_k),len(only_p))):
        if i<len(only_k): mixed.append(only_k[i])
        if i<len(only_p): mixed.append(only_p[i])
    return matched_cards+mixed
