"""Event- and outcome-aware cross-exchange matching.

Only scores candidate matches: a match must still pass the event date and
outcome checks. Different resolution rules can remain even after these checks;
for public use, review the actual contracts.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
import re
from rapidfuzz import fuzz
from core import Quote, clean_text, date_from_string

POLY_SOURCES=('Polymarket US','Polymarket')

@dataclass
class Row:
    label:str
    kalshi:Quote|None=None
    polymarket:Quote|None=None

@dataclass
class MarketCard:
    title:str
    category:str
    rows:list[Row]
    volume:float
    matched:bool
    match_score:float=0.0
    poly_venue:str=''

STATES={
 'alabama':'AL','alaska':'AK','arizona':'AZ','arkansas':'AR','california':'CA','colorado':'CO',
 'connecticut':'CT','delaware':'DE','florida':'FL','georgia':'GA','hawaii':'HI','idaho':'ID',
 'illinois':'IL','indiana':'IN','iowa':'IA','kansas':'KS','kentucky':'KY','louisiana':'LA',
 'maine':'ME','maryland':'MD','massachusetts':'MA','michigan':'MI','minnesota':'MN',
 'mississippi':'MS','missouri':'MO','montana':'MT','nebraska':'NE','nevada':'NV',
 'new hampshire':'NH','new jersey':'NJ','new mexico':'NM','new york':'NY',
 'north carolina':'NC','north dakota':'ND','ohio':'OH','oklahoma':'OK','oregon':'OR',
 'pennsylvania':'PA','rhode island':'RI','south carolina':'SC','south dakota':'SD',
 'tennessee':'TN','texas':'TX','utah':'UT','vermont':'VT','virginia':'VA',
 'washington':'WA','west virginia':'WV','wisconsin':'WI','wyoming':'WY',
 'district of columbia':'DC'}

# Convert highly standardized political markets into canonical event identities.
def canonical_event_key(title:str, cat:str):
    text=clean_text(title)
    years=re.findall(r'\b20\d{2}\b',str(title))
    year=years[0] if len(set(years))==1 else None
    if cat=='Politics' and year:
        original=str(title).lower()
        is_nominee=any(term in original for term in ('nominee','nomination','primary winner','primaries'))
        is_presidential=any(term in original for term in ('president','presidential','white house'))
        if is_presidential:
            if is_nominee:
                party='dem' if any(x in original for x in ('democratic','democrat')) else (
                      'rep' if any(x in original for x in ('republican','gop')) else 'unknown')
                if party!='unknown':return ('politics',f'us-president-nominee-{party}-{year}')
                return None
            if 'election' in original or 'winner' in original:
                return ('politics',f'us-president-general-{year}')
        office='senate' if 'senate' in text else ('governor' if any(x in text for x in ('governor','gubernatorial')) else None)
        if office:
            state=next((abbr for state,abbr in STATES.items() if re.search(r'\b'+re.escape(state)+r'\b',original)),None)
            if state:return ('politics',f'us-{state.lower()}-{office}-{year}')
    if cat=='Entertainment' and year:
        if any(x in text for x in ('oscar','academy awards')):
            if 'best picture' in text:return ('entertainment',f'oscars-best-picture-{year}')
    return None


def important_numbers(s):
    return set(re.findall(r'(?<!\w)\d+(?:\.\d+)?%?(?!\w)',str(s or '').lower()))


def event_match_score(a:str,b:str,cat:str='Other'):
    ka,kb=canonical_event_key(a,cat),canonical_event_key(b,cat)
    if ka and kb:return 100.0 if ka==kb else 0.0
    if ka or kb:
        # A standard political event must not accidentally match a vague one.
        return 0.0
    if important_numbers(a)!=important_numbers(b):
        return 0.0
    na,nb=clean_text(a),clean_text(b)
    if not na or not nb:return 0.0
    return max(fuzz.ratio(na,nb),fuzz.token_sort_ratio(na,nb),fuzz.ratio(na.replace(' ',''),nb.replace(' ','')))


def close_compatible(k:Quote,p:Quote):
    a,b=date_from_string(k.close_at),date_from_string(p.close_at)
    if a is None or b is None:return True
    max_days=120 if k.category=='Politics' else (4 if k.category=='Sports' else 45)
    return abs((a-b).total_seconds())<=max_days*86400


def outcome_compatible(k:Quote,p:Quote,single_k=False,single_p=False):
    a,b=clean_text(str(k.outcome).replace(".","")),clean_text(str(p.outcome).replace(".",""))
    if a and b and a==b:return True
    if a and b and min(len(a),len(b))>=8 and fuzz.ratio(a,b)>=92:return True
    if single_k and single_p and a in ('','yes') and b in ('','yes'):
        return fuzz.ratio(clean_text(k.question),clean_text(p.question))>=96
    return False


def _rows_matchable(ks,ps):
    return any(outcome_compatible(k,p,len(ks)==1,len(ps)==1) and close_compatible(k,p) for k in ks for p in ps)


def _card_title(title,category,rows,matched=False,score=0.0):
    venue=next((r.polymarket.exchange for r in rows if r.polymarket),'')
    # Kalshi volume is contracts, Polymarket volume is dollars. DO NOT ADD them.
    # Sorting by their combined numeric values creates a misleading comparison.
    k_total=sum(q.volume for q in {r.kalshi.market_id:r.kalshi for r in rows if r.kalshi}.values())
    p_total=sum(q.volume for q in {r.polymarket.market_id:r.polymarket for r in rows if r.polymarket}.values())
    return MarketCard(title,category,rows,max(k_total,p_total),matched,score,venue)


def combine_quotes(kalshi:list[Quote],polymarket:list[Quote],aliases:dict|None=None):
    aliases=aliases or {}
    groups=defaultdict(list)
    for q in kalshi+polymarket:
        groups[(q.exchange,q.event_id)].append(q)
    k_events={k:v for k,v in groups.items() if k[0]=='Kalshi'}
    p_events={k:v for k,v in groups.items() if k[0] in POLY_SOURCES}
    p_by_canonical=defaultdict(list)
    p_by_category=defaultdict(list)
    for pk,ps in p_events.items():
        cat=ps[0].category
        key=canonical_event_key(ps[0].event_title,cat)
        if key:p_by_canonical[key].append(pk)
        else:p_by_category[cat].append(pk)
    used_p=set(); cards=[]
    for kk,ks in k_events.items():
        cat=ks[0].category
        key=canonical_event_key(ks[0].event_title,cat)
        candidates=list(p_by_canonical.get(key,[])) if key else p_by_category[cat]
        best_pk=None;best_score=0
        for pk in candidates:
            if pk in used_p:continue
            ps=p_events[pk]
            explicit=aliases.get(ks[0].event_id)==ps[0].event_id
            score=100.0 if explicit else event_match_score(ks[0].event_title,ps[0].event_title,cat)
            if score < (97 if cat=='Sports' else 92):continue
            if not _rows_matchable(ks,ps):continue
            # When both international and US are present, prefer US for comparable
            # US-only political events, but never fuse them into one column.
            if score > best_score or (score==best_score and pk[0]=='Polymarket US'):
                best_score=score;best_pk=pk
        paired=p_events[best_pk] if best_pk else []
        if best_pk:used_p.add(best_pk)
        rows=[];used_rows=set()
        for k in ks:
            found=None
            for p in paired:
                if p.market_id in used_rows:continue
                if outcome_compatible(k,p,len(ks)==1,len(paired)==1) and close_compatible(k,p):
                    found=p;used_rows.add(p.market_id);break
            rows.append(Row(k.outcome if clean_text(k.outcome)!='yes' else 'Yes',k,found))
        for p in paired:
            if p.market_id not in used_rows:
                rows.append(Row(p.outcome,None,p))
        cards.append(_card_title(ks[0].event_title,cat,rows,bool(best_pk),best_score))
    for pk,ps in p_events.items():
        if pk in used_p:continue
        cards.append(_card_title(ps[0].event_title,ps[0].category,[Row(p.outcome,None,p) for p in ps]))
    matched=[c for c in cards if c.matched]
    only_k=[c for c in cards if not c.matched and any(r.kalshi for r in c.rows)]
    only_p=[c for c in cards if not c.matched and any(r.polymarket for r in c.rows)]
    matched.sort(key=lambda c:-c.volume)
    only_k.sort(key=lambda c:-c.volume)
    only_p.sort(key=lambda c:-c.volume)
    mixed=[]
    for i in range(max(len(only_k),len(only_p))):
        if i<len(only_k):mixed.append(only_k[i])
        if i<len(only_p):mixed.append(only_p[i])
    return matched+mixed
