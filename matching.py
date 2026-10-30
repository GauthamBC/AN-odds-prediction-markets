"""Event- and outcome-aware cross-exchange matching.

Only scores candidate matches: a match must still pass the event date and
outcome checks. Different resolution rules can remain even after these checks;
for public use, review the actual contracts.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime,timezone
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
    rule_reviewed:bool=False
    activity_24h:float=0.0

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
    aliases={'democrat':'democratic party','democrats':'democratic party',
             'republican':'republican party','republicans':'republican party',
             'gop':'republican party','democratic nominee':'democratic party',
             'republican nominee':'republican party'}
    if a and b and aliases.get(a,a)==aliases.get(b,b):return True
    if a and b and min(len(a),len(b))>=8 and fuzz.ratio(a,b)>=92:return True
    if single_k and single_p and a in ('','yes') and b in ('','yes'):
        return fuzz.ratio(clean_text(k.question),clean_text(p.question))>=96
    return False


def _rows_matchable(ks,ps,verified_outcomes=None):
    verified_outcomes=verified_outcomes or set()
    return any((outcome_compatible(k,p,len(ks)==1,len(ps)==1) or
                (k.market_id,p.exchange,p.market_id) in verified_outcomes)
               and close_compatible(k,p) for k in ks for p in ps)


def _meaningful_name(q):
    name=clean_text(q.outcome).strip()
    return name if name not in ('', 'yes', 'no', 'other', 'none', 'draw', 'tie') else ''


def _names(qs):
    return {name for q in qs if (name:=_meaningful_name(q))}


def _title_tokens(title):
    t=str(title or '').lower()
    t=re.sub(r'\b(?:u\.?s\.?a?|united states|american)\b','us',t)
    t=re.sub(r'\b(?:2028|2027|2026|2025)\b',lambda m:' '+m.group(0)+' ',t)
    t=re.sub(r'\b(?:versus|v\.?|against|face|faces)\b','vs',t)
    t=re.sub(r'\b(?:presidential|president)\b','president',t)
    t=re.sub(r'\b(?:nomination|nominee|candidate)\b','nominee',t)
    t=re.sub(r'\b(?:gubernatorial|governor)\b','governor',t)
    t=re.sub(r'\b(?:win|winning|wins|winner|wins?)\b','winner',t)
    stop={'who','will','which','the','a','an','be','is','as','by','for','of','in','on','to',
          'what','does','do','would','this','next','election','elections','market'}
    return {w for w in re.findall(r'[a-z0-9]+',t) if w not in stop}


def _identity_incompatible(a,b,category):
    # Guard strongly against matching different propositions with common people.
    aa,bb=str(a).lower(),str(b).lower()
    years_a=set(re.findall(r'(?<!\d)20\d{2}(?!\d)',aa))
    years_b=set(re.findall(r'(?<!\d)20\d{2}(?!\d)',bb))
    if years_a and years_b and years_a.isdisjoint(years_b):return True
    if category=='Politics':
        def election_type(s):
            if re.search(r'\b(nominee|nomination|primary|primaries)\b',s):return 'nominee'
            if re.search(r'\b(election|president|presidential|senate|governor|gubernatorial)\b',s):return 'general'
            return None
        x,y=election_type(aa),election_type(bb)
        if x and y and x!=y:return True
        if ('republican' in aa or 'gop' in aa) != ('republican' in bb or 'gop' in bb):
            if 'nominee' in (x,y):return True
        if ('democrat' in aa) != ('democrat' in bb):
            if 'nominee' in (x,y):return True
    return False


def _date_match(k,p):
    a,b=date_from_string(k.close_at),date_from_string(p.close_at)
    if not a or not b:return None
    return abs((a-b).total_seconds())/86400


def pair_score(ks,ps,verified_outcomes=None,verified=False):
    """Return candidate confidence for a shared event, NOT rule verification.

    Strong candidate agreement takes priority over string similarity.  Never
    conflate short and long political propositions or different election years.
    """
    if not ks or not ps:return 0
    k,p=ks[0],ps[0]
    if k.category!=p.category or _identity_incompatible(k.event_title,p.event_title,k.category):return 0
    if not _rows_matchable(ks,ps,verified_outcomes):return 0
    ck=canonical_event_key(k.event_title,k.category)
    cp=canonical_event_key(p.event_title,p.category)
    if ck and cp and ck!=cp:return 0
    if ck and cp and ck==cp:
        if k.category=='Sports':
            days=_date_match(k,p)
            if days is None or days>3:return 0
        return 100 if verified else 98
    kt,pt=_title_tokens(k.event_title),_title_tokens(p.event_title)
    j=len(kt&pt)/len(kt|pt) if kt|pt else 0
    title_ratio=max(fuzz.token_sort_ratio(' '.join(sorted(kt)),' '.join(sorted(pt))),
                    fuzz.ratio(' '.join(sorted(kt)),' '.join(sorted(pt))))
    kn,pn=_names(ks),_names(ps)
    overlap=len(kn&pn)
    # Candidate name overlap helps discover equivalent market phrasing.
    precision=overlap/min(len(kn),len(pn)) if kn and pn else 0
    name_score=min(100,100*precision)
    if k.category=='Sports':
        # Do not join a spread/total/handicap with a match-winner contract.
        def contract_type(q):
            t=(str(q.event_title)+' '+str(q.question)).lower()
            if re.search(r'\b(spread|handicap|winning margin)\b',t):return 'spread'
            if re.search(r'\b(over.?under|total points|total goals|total runs)\b',t):return 'total'
            return 'winner'
        if contract_type(k)!=contract_type(p):return 0
        days=_date_match(k,p)
        if days is None or days>2.5:return 0
        # Same athletes/teams plus comparable event title, within two days.
        if overlap>=2 and title_ratio>=52:return 88+min(8,j*12)
        if title_ratio>=96 and overlap>=1:return 95
        return 0
    if overlap>=2 and title_ratio>=57 and j>=.20:
        return min(97,80+12*precision+5*j)
    if overlap>=1 and title_ratio>=90:
        return min(97,85+10*precision)
    if title_ratio>=97 and overlap>=1:return 96
    # Binary YES/NO propositions may have no candidate label. Require
    # nearly identical text; "Yes" alone cannot validate the event.
    if all(clean_text(x.outcome) in ('yes','no') for x in ks+ps) and title_ratio>=98:
        return 93
    return 0


def event_volumes(rows):
    """Keep separate exchange volume measures; deduplicate poly markets."""
    k={r.kalshi.market_id:r.kalshi.volume for r in rows if r.kalshi}
    poly={}
    for r in rows:
        if r.polymarket:
            q=r.polymarket
            base_id=q.market_id.rsplit(':',1)[0] if ':' in q.market_id else q.market_id
            poly[(q.exchange,base_id)]=q.volume
    return sum(k.values()),sum(poly.values())


def _card_title(title,category,rows,matched=False,score=0.0,reviewed=False):
    venue=next((r.polymarket.exchange for r in rows if r.polymarket),'')
    k_total,p_total=event_volumes(rows)
    # Volume in each venue has different units; never add unlike values.
    # Use the displayed venue's 24h activity to rank within its own group.
    k_24={r.kalshi.market_id:r.kalshi.volume_24h for r in rows if r.kalshi}
    p_24={}
    for r in rows:
        if r.polymarket:
            q=r.polymarket
            base=q.market_id.rsplit(':',1)[0] if ':' in q.market_id else q.market_id
            p_24[(q.exchange,base)]=q.volume_24h
    activity=sum(k_24.values()) if k_24 else sum(p_24.values())
    return MarketCard(title,category,rows,k_total if k_total else p_total,matched,score,venue,reviewed,activity)


def combine_quotes(kalshi:list[Quote],polymarket:list[Quote],aliases:dict|None=None,outcome_aliases:set|None=None):
    aliases=aliases or {};outcome_aliases=outcome_aliases or set()
    groups=defaultdict(list)
    for q in kalshi+polymarket:
        groups[(q.exchange,q.event_id)].append(q)
    k_events={k:v for k,v in groups.items() if k[0]=='Kalshi'}
    p_events={k:v for k,v in groups.items() if k[0] in POLY_SOURCES}
    by_can=defaultdict(set);by_name=defaultdict(set);by_token=defaultdict(set)
    for key,qs in p_events.items():
        cat=qs[0].category
        for token in _title_tokens(qs[0].event_title):
            by_token[(cat,token)].add(key)
        ck=canonical_event_key(qs[0].event_title,cat)
        if ck:by_can[ck].add(key)
        for name in _names(qs):by_name[(cat,name)].add(key)
    used=set();cards=[]
    for kk,ks in k_events.items():
        cat=ks[0].category
        ck=canonical_event_key(ks[0].event_title,cat)
        candidates=set(by_can.get(ck,set())) if ck else set()
        for name in _names(ks):candidates.update(by_name.get((cat,name),set()))
        # Indexed token retrieval avoids O(Kalshi-events * Polymarket-events)
        # fuzzy scanning. Particularly important for larger Streamlit scans.
        if len(candidates)<5:
            token_hits=defaultdict(int)
            tokens=_title_tokens(ks[0].event_title)
            for token in tokens:
                for pk in by_token.get((cat,token),()):
                    token_hits[pk]+=1
            ordered=sorted(token_hits,key=lambda pk:token_hits[pk],reverse=True)
            for pk in ordered[:100]:
                if token_hits[pk]>=max(2,min(3,len(tokens))):
                    if event_match_score(ks[0].event_title,p_events[pk][0].event_title,cat)>=70:
                        candidates.add(pk)
        options=[]
        for pk in candidates:
            if pk in used:continue
            ps=p_events[pk]
            reviewed=pk in aliases.get(ks[0].event_id,[])
            score=pair_score(ks,ps,outcome_aliases,reviewed)
            if score>=88:
                # Slight preference for US comparison where both venues offer
                # equivalent events; still a separate source in the quote.
                venue_bonus=0.01 if pk[0]=='Polymarket US' else 0
                options.append((score+venue_bonus,pk,reviewed))
        options.sort(key=lambda x:x[0],reverse=True)
        selected=options[0] if options else None
        if selected:
            _,pk,verified=selected;used.add(pk)
            ps=p_events[pk]
        else:
            pk=None;ps=[];verified=False
        rows=[];used_outcomes=set()
        for k in ks:
            best=None
            for p in ps:
                if p.market_id in used_outcomes:continue
                if (outcome_compatible(k,p,len(ks)==1,len(ps)==1) or
                    (k.market_id,p.exchange,p.market_id) in outcome_aliases) and close_compatible(k,p):
                    best=p;used_outcomes.add(p.market_id);break
            rows.append(Row(k.outcome,k,best))
        for p in ps:
            if p.market_id not in used_outcomes:rows.append(Row(p.outcome,None,p))
        cards.append(_card_title(ks[0].event_title,cat,rows,bool(ps),float(selected[0]) if selected else 0,verified))
    for pk,ps in p_events.items():
        if pk not in used:cards.append(_card_title(ps[0].event_title,ps[0].category,[Row(p.outcome,None,p) for p in ps]))
    matched=[c for c in cards if c.matched]
    only_k=[c for c in cards if not c.matched and any(r.kalshi for r in c.rows)]
    only_p=[c for c in cards if not c.matched and any(r.polymarket for r in c.rows)]
    def popularity(card):
        # Prefer markets that have actually traded recently; fall back to
        # all-time volume only when the exchange supplies no 24-hour number.
        return (card.activity_24h>0,card.activity_24h,card.volume)
    matched.sort(key=popularity,reverse=True)
    only_k.sort(key=popularity,reverse=True)
    only_p.sort(key=popularity,reverse=True)
    mixed=[]
    for i in range(max(len(only_k),len(only_p))):
        if i<len(only_k):mixed.append(only_k[i])
        if i<len(only_p):mixed.append(only_p[i])
    return matched+mixed
