"""Pure data transformation for TPM summaries, matched outcomes, featured quotes and trends."""
from __future__ import annotations
from collections import defaultdict
from core import Quote, american
from model import AccuracyModel
from region_rules import regions

CATEGORIES = ['All','Sports','Politics','Entertainment','Economics','Crypto','Science & Tech','Other']
REGIONS = ['USA','Canada','Global']

def safe_num(value, default=0.0):
    try:
        n=float(value)
        return n if n == n and abs(n)<float('inf') else default
    except (TypeError,ValueError,OverflowError):
        return default

def volume24(r):
    return max(0.0,safe_num(r.get('volume_24h')))

def movement24(r):
    val = (r.get('leading_outcome') or {}).get('change_24h')
    if val is None:
        return None
    return safe_num(val, None)

def prefetch_candidates(rows, cap=90):
    """Top by 24h volume across each region and category, not just national lifetime futures."""
    ordered = sorted(rows,key=volume24,reverse=True)
    picked=[];seen=set()
    def pick(seq, n):
        count=0
        for r in seq:
            if count>=n:break
            slug=r['slug']
            if slug not in seen:
                seen.add(slug);picked.append(slug)
            count+=1
    pick(ordered,12)
    for region in REGIONS:
        reg=[r for r in ordered if region in regions(r)]
        pick(reg,5)
        for cat in CATEGORIES[1:]:
            matched=[r for r in reg if str(r.get('category') or 'other').lower()==cat.lower()]
            pick(matched,5)
    movers=[r for r in rows if movement24(r) is not None]
    pick(sorted(movers,key=lambda r:abs(movement24(r)),reverse=True),12)
    # Already selected ordered by popularity, if cap exceeded, select globally highest-volume
    return picked[:cap]

def outcomes_by_group(d):
    """Map API-provided match.group_id only: never infer same contract from name alone."""
    groups={}
    unmatched=[]
    for market in d.get('markets') or []:
        venue=market.get('venue')
        if venue not in ('kalshi','polymarket'):
            continue
        for outcome in market.get('outcomes') or []:
            q=outcome.get('quote') or {}
            p=q.get('probability')
            if p is None:
                continue
            p=safe_num(p, None)
            if p is None or p<0 or p>1:
                continue
            match=outcome.get('match') or {}
            group_id=match.get('group_id')
            item={'name':outcome.get('title') or '?','p':p,'venue':venue,
                  'f':str(q.get('freshness') or 'unknown'),
                  'compatibility':str(match.get('contract_compatibility') or 'unverified'),
                  'market_id':market.get('market_id') or '',
                  'url':market.get('url') or '',
                  'volume':market.get('volume') or 0,
                  'key':match.get('key') or ''}
            if not group_id:
                unmatched.append(item)
                continue
            group=groups.setdefault(str(group_id),{'name':item['name'],'prices':{},'id':str(group_id),'outcome_key':item['key']})
            # Avoid accidental overwrites from duplicate contracts from same venue.
            previous=group['prices'].get(venue)
            if previous is None or safe_num(item['volume'])>safe_num(previous.get('volume')):
                group['prices'][venue]=item
                group['name']=item['name']
    result=list(groups.values())
    for item in unmatched:
        result.append({'name':item['name'],'prices':{item['venue']:item},'id':None,'outcome_key':None})
    result.sort(key=lambda g:max((v['p'] for v in g['prices'].values()),default=0),reverse=True)
    return result

def is_price_fresh(item):
    return item is not None and item['f'].lower() in ('live','fresh')

def forecast(detail, group, model=None):
    """Experimental only. A matched candidate is NOT automatically verified equivalent."""
    prices=group.get('prices') or {}
    k=prices.get('kalshi');p=prices.get('polymarket')
    if not k or not p:
        return {'prob':None,'moneyline':'—','status':'Only one source'}
    if not (is_price_fresh(k) and is_price_fresh(p)):
        return {'prob':None,'moneyline':'—','status':'Source quote stale/unknown'}
    checked = (str(detail.get('comparison') or '').lower()=='verified' and
              k['compatibility'].lower()=='verified' and p['compatibility'].lower()=='verified')
    if not checked:
        # Show an indicative number for internal exploration, but do NOT call it a validated AN forecast.
        prob=(k['p']+p['p'])/2
        return {'prob':prob,'moneyline':american(prob),
                'status':'Indicative 50/50 — rules NOT verified','validated':False}
    if model is None:
        prob=(k['p']+p['p'])/2
        return {'prob':prob,'moneyline':american(prob),'status':'Verified pair · provisional 50/50','validated':False}
    cat=str(detail.get('category') or 'other').lower()
    cat = {'sports':'Sports','politics':'Politics','entertainment':'Entertainment',
           'economics':'Economics','crypto':'Crypto','science-and-tech':'Science & Tech',
           'weather':'Weather'}.get(cat,'Other')
    kw = {'exchange':'Kalshi','market_id':str(k.get('market_id')),
          'event_id':str(detail.get('slug')),'event_title':str(detail.get('title')),
          'question':str(detail.get('question')),'outcome':str(group.get('name')),
          'probability':k['p'],'category':cat,'volume':0.0,'liquidity':0.0,
          'close_at':detail.get('end_date'),'url':str(k.get('url'))}
    pw = dict(kw,exchange='Polymarket',market_id=str(p.get('market_id')),
              probability=p['p'],url=str(p.get('url')))
    res=model.predict(Quote(**kw), Quote(**pw))
    prob=res.get('probability')
    return {'prob':prob,'moneyline':american(prob),'status':res.get('status','Experimental'),
            'validated':res.get('calibrated',False),'weights':(res.get('k_weight'),res.get('p_weight'))}

def matched_disagreements(detail, model=None):
    rows=[]
    for g in outcomes_by_group(detail):
        k=g['prices'].get('kalshi');p=g['prices'].get('polymarket')
        if not (k and p and is_price_fresh(k) and is_price_fresh(p)):
            continue
        diff=abs(k['p']-p['p'])
        rows.append({'group':g,'diff':diff,'kalshi':k['p'],'polymarket':p['p'],
                     'forecast':forecast(detail,g,model)})
    return sorted(rows,key=lambda x:x['diff'],reverse=True)
