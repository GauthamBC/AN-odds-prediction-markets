"""AN Odds Studio — manual-only TPM-backed prediction markets research dashboard.

Usage: pip install -r requirements.txt && streamlit run streamlit_app.py
Add TPM_API_KEY to Streamlit Cloud -> App settings -> Secrets.
"""
from __future__ import annotations
from datetime import datetime, timezone
import html
import os
import threading
import time

import pandas as pd
import streamlit as st

from tpm_client import TPMClient, TPMError
from snapshot_store import connect, snapshot, detail as saved_detail, save_detail, publish, meta
from region_rules import match_filters, regions
from dashboard_logic import (
    CATEGORIES, REGIONS, volume24, movement24, safe_num,
    prefetch_candidates, outcomes_by_group, matched_disagreements, forecast,
)
from model import read_history, AccuracyModel
from core import american

st.set_page_config(page_title='AN Odds Studio | Digital PR Intelligence', page_icon='📈',
                   layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
:root {color-scheme:dark;}
.stApp {background:#0a1014;color:#eff5f1;}
.block-container {padding-top:1.5rem;padding-bottom:4rem;max-width:1480px;}
[data-testid="stHeader"] {background:#0a1014;}
h1,h2,h3 {font-weight:750!important;letter-spacing:-.025em;}
small,.stCaption {color:#96aaad!important;}
div[data-testid="stMetric"] {background:#121d22;border:1px solid #21343a;border-radius:13px;padding:.85rem 1rem;}
div[data-testid="stVerticalBlockBorderWrapper"] > div {border-color:#26383c!important;background:#0e181d!important;border-radius:14px!important;}
div.stButton > button {border-radius:10px!important;font-weight:650;background:#17272c;border:1px solid #2b4144;color:#e6f6ef;}
div.stButton > button:hover {background:#1c3733;border-color:#40977a;color:#fff;}
.stTextInput input {background:#122127;border:1px solid #2d454a;color:#fff;}
section[data-testid="stSidebar"] {background:#101b20;}
[data-testid="stAlert"] {border-radius:10px;}
.an-eyebrow{font-size:12px;color:#7eb89e;font-weight:800;letter-spacing:.15em;text-transform:uppercase}
.an-desc{color:#a1b3b7;font-size:14px;margin-top:-4px}
.an-mini{display:inline-block;color:#a2b4b9;font-size:11px;font-weight:650;padding:2px 7px;border:1px solid #263b40;border-radius:7px;margin-right:5px}
.an-price{font-size:24px;font-weight:770;color:#f2f8f6;line-height:1.05;letter-spacing:-.03em}
.an-label{font-size:11px;font-weight:720;color:#8b9fa2;text-transform:uppercase;letter-spacing:.08em}
.an-outcome{font-size:14px;font-weight:700;color:#f3f8f6;margin-bottom:2px}
.an-small{font-size:12px;color:#a2b3b4}
.an-strip{background:#0f1c20;border:1px solid #22353a;padding:11px 14px;border-radius:11px;margin-bottom:8px}
.an-green{color:#4bdd9c}
.an-gold{color:#ffcc75}
.an-blue{color:#77aefc}
.an-red{color:#fe9e96}
.an-title{font-size:17px;font-weight:760;line-height:1.27;color:#eff6f1;min-height:44px}
.an-badge{background:#163228;color:#70d9a3;border-radius:7px;padding:3px 8px;font-size:11px;font-weight:700}
.an-muted{color:#819599;font-size:12px}
hr{border-color:#24383c!important;}
</style>''',unsafe_allow_html=True)

@st.cache_resource
def refresh_mutex():
    return threading.Lock()

@st.cache_resource
def accuracy_model():
    return AccuracyModel(read_history('history.csv'))

def secret(name, default=''):
    try:
        return str(st.secrets.get(name, default) or '').strip()
    except (FileNotFoundError, KeyError):
        return default

def fmt_usd(v):
    n=safe_num(v)
    if n>=1e9:return f'${n/1e9:,.2f}B'
    if n>=1e6:return f'${n/1e6:,.2f}M'
    if n>=1e3:return f'${n/1e3:,.1f}K'
    return f'${n:,.0f}'

def pct(v):
    return '—' if v is None else f'{100*v:.1f}%'

def clean(s):
    return html.escape(str(s or ''),quote=True)

def find_featured(d):
    groups=outcomes_by_group(d)
    both=[g for g in groups if len(g['prices'])==2]
    return (both or groups or [None])[0]

def show_market_preview(row, cached_d=None, show_action=True, unique=''):
    title=clean(row.get('title') or 'Untitled market')
    cat=clean(str(row.get('category') or 'other').replace('-',' ').title())
    venues=', '.join('Kalshi' if x=='kalshi' else 'Polymarket' for x in row.get('venues') or [])
    outcome=row.get('leading_outcome') or {}
    d=cached_d
    featured=find_featured(d) if d else None
    with st.container(border=True):
        st.markdown(f'<div class="an-title">{title}</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="an-mini">{cat}</div><div class="an-mini">{clean(venues) or "Unknown venue"}</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="an-small" style="padding-top:8px">24h activity: <b>{fmt_usd(row.get("volume_24h"))}</b> · Lifetime: {fmt_usd(row.get("volume"))}</div>',unsafe_allow_html=True)
        st.write('')
        if featured:
            st.markdown(f'<div class="an-outcome">{clean(featured["name"])}</div>',unsafe_allow_html=True)
            col1,col2,col3=st.columns(3, gap='small')
            k=featured['prices'].get('kalshi')
            p=featured['prices'].get('polymarket')
            guess=forecast(d, featured, accuracy_model())
            with col1:
                st.markdown(f'<div class="an-label">Kalshi</div><div class="an-price an-green">{pct(k["p"] if k else None)}</div>',unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="an-label">Polymarket</div><div class="an-price an-blue">{pct(p["p"] if p else None)}</div>',unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="an-label">AN indicative</div><div class="an-price an-gold">{pct(guess["prob"])}</div>',unsafe_allow_html=True)
            st.caption(guess['status'])
        else:
            st.markdown(f'<div class="an-outcome">{clean(outcome.get("title") or "Featured outcome")}</div>',unsafe_allow_html=True)
            st.markdown(f'<div class="an-label">Provider featured price</div><div class="an-price">{pct(safe_num(outcome.get("probability"),None))}</div>',unsafe_allow_html=True)
            st.caption('Open event for separate Kalshi and Polymarket quotes. A catalogue summary does not include both.')
        if show_action and st.button('View all outcomes',key=f'expand_{unique}_{row.get("slug")}',use_container_width=True):
            st.session_state['expanded_slug']=row['slug']
            st.rerun()

def details_panel(con, slug, api_key, *, allowed=True):
    if not slug or not allowed:
        return
    st.divider()
    bar,btn=st.columns([7,1])
    bar.subheader('Event outcomes · Kalshi / Polymarket / AN')
    if btn.button('Close',key='close_detail'):
        st.session_state['expanded_slug']=None
        st.rerun()
    d=saved_detail(con,slug,full=True)
    if d is None:
        if not api_key:
            st.error('Configure TPM_API_KEY to retrieve this event.')
            return
        with st.spinner('Fetching complete event outcomes (one on-demand API request)…'):
            try:
                d=TPMClient(api_key).detail(slug)
                save_detail(con,d,full=True)
            except TPMError as exc:
                st.error(str(exc));return
    st.markdown(f'### {clean(d.get("title"))}')
    compare=d.get('comparison') or 'one exchange / unverified'
    st.caption(f'Exchange comparison: {compare} · Source: TPM event detail · Event closing: {d.get("end_date") or "unknown"}')
    if compare!='verified':
        st.info('Market titles or outcome names may match while settlement rules differ. AN numbers below are indicative blends, not validated fair odds.')
    rows=[]
    for g in outcomes_by_group(d):
        k=g['prices'].get('kalshi');p=g['prices'].get('polymarket')
        f=forecast(d,g,accuracy_model())
        rows.append({'Outcome':g['name'], 'Kalshi %':round(100*k['p'],2) if k else None,
                     'Polymarket %':round(100*p['p'],2) if p else None,
                     'AN indicative %':round(100*f['prob'],2) if f['prob'] is not None else None,
                     'AN fair odds (illustrative)':f['moneyline'],'Method / caveat':f['status'],
                     'Contract verification':'Verified' if f.get('validated') else 'Not established'})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True,height=min(560,80+len(rows)*36))
    st.caption('AN odds are illustrative, not tradable prices. Historical model from March 2025 only activates where sufficient audited observations exist.')
    if d.get('resolution') and (d['resolution'] or {}).get('summary'):
        st.info('Settlement summary: '+str(d['resolution']['summary']))
    links=[m for m in d.get('markets') or [] if m.get('url','').startswith('https://')]
    if links:
        st.markdown(' · '.join(f'[{clean(m.get("venue"))} market]({m["url"]})' for m in links))

def run_refresh(con,key):
    lock=refresh_mutex()
    if not lock.acquire(blocking=False):
        st.warning('A refresh is already in progress.')
        return
    try:
        client=TPMClient(key)
        prog=st.progress(0,text='Retrieving active-event catalogue…')
        def progress(page,count):
            prog.progress(min(.48, .03+page*.008),text=f'Catalogue: {page} pages · {count:,} active events collected')
        start=time.monotonic()
        data=client.catalogue(on_page=progress)
        candidates=prefetch_candidates(data.events,cap=150)
        details=[];errors=[]
        for i,slug in enumerate(candidates):
            try:
                details.append(client.detail(slug,max_outcomes=12))
            except TPMError as exc:
                errors.append(f'{slug}: {exc}')
            prog.progress(.48 + .50*(i+1)/max(1,len(candidates)),text=f'Featured outcomes: {i+1}/{len(candidates)} · {client.calls} API requests')
            if i<len(candidates)-1:
                time.sleep(.12)
        publish(con,data.events,pages=data.pages,request_count=client.calls,
                detail_rows=details,detail_errors=len(errors))
        prog.progress(1.0,text='Snapshot saved')
        st.success(f'Saved {len(data.events):,} active event summaries and {len(details)} featured event details. '
                   f'Used {client.calls} API requests in {time.monotonic()-start:.0f}s.')
        if errors:
            with st.expander(f'{len(errors)} featured detail fetches failed (catalogue still complete)'):
                st.code('\n'.join(errors[:35]))
        st.session_state['expanded_slug']=None
    except (TPMError, ValueError) as exc:
        st.error(f'Refresh failed: {exc}. The previous successful snapshot is unchanged.')
    finally:
        lock.release()

con=connect()
api_key=secret('TPM_API_KEY')
admin_password=secret('ADMIN_REFRESH_PASSWORD')
rows=snapshot(con)
info=meta(con)

st.markdown('<div class="an-eyebrow">ACTION NETWORK · DIGITAL PR RESEARCH</div>',unsafe_allow_html=True)
top_title, top_time=st.columns([3,1],vertical_alignment='center')
with top_title:
    st.title('AN Odds Studio')
    st.markdown('<div class="an-desc">Trending prediction markets, cross-exchange comparisons and experimental AN fair odds.</div>',unsafe_allow_html=True)
with top_time:
    st.markdown('<div class="an-label">LAST MANUAL REFRESH</div>',unsafe_allow_html=True)
    st.markdown(f'<b>{clean(info.get("updated_at","Not synced yet")[:19].replace("T"," "))}</b> <small>UTC</small>',unsafe_allow_html=True)

with st.sidebar:
    st.header('Data & administration')
    st.caption('Manual-only sync. Opening the dashboard, searching and changing categories do not call the market API.')
    if api_key:
        st.success('TPM API key configured')
    else:
        st.error('Missing TPM_API_KEY in Streamlit Secrets')
        st.code('TPM_API_KEY = "your-api-key"')
    unlocked=True
    if admin_password:
        password=st.text_input('Admin password to enable refresh',type='password',key='admin_unlock')
        unlocked=password==admin_password
    else:
        st.warning('Set ADMIN_REFRESH_PASSWORD in Secrets before sharing the dashboard, or any visitor can refresh and consume your quota.')
    if st.button('↻ Refresh all active markets',type='primary',disabled=not (api_key and unlocked),use_container_width=True):
        run_refresh(con,api_key)
        rows=snapshot(con);info=meta(con)
    if st.button('Check API quota',disabled=not(api_key and unlocked),use_container_width=True):
        try:
            quota=TPMClient(api_key).quota()
            month=quota.get('monthly') or {}
            st.info(f'Monthly usage: {month.get("used","?"):,} / {month.get("limit","?"):,} requests' if isinstance(month.get('used'),int) and isinstance(month.get('limit'),int) else str(quota))
        except TPMError as exc:
            st.error(str(exc))
    st.divider()
    st.caption(f'Cached: {info.get("event_count",0)} events · {info.get("details_prefetched",0)} featured details · {info.get("pages",0)} catalogue pages')
    st.caption('Provider: TPM v1, Kalshi + Polymarket International. Polymarket US is NOT independently covered by this feed.')
    st.caption('Local SQLite cache survives reruns but may be erased when Streamlit Cloud restarts. For durable snapshots, add a hosted database later.')


if not rows:
    st.subheader("First-time market sync")

    if not api_key:
        st.error("TPM_API_KEY is missing from Streamlit Secrets.")
    else:
        st.success("API key detected.")

        password_input = st.text_input(
            "Admin password",
            type="password",
            key="first_sync_password"
        )

        unlocked = (
            not admin_password
            or password_input == admin_password
        )

        if st.button(
            "Test API connection",
            disabled=not unlocked
        ):
            try:
                client = TPMClient(api_key)
                result = client.get(
                    "/events",
                    {"status": "trading", "limit": 1}
                )
                st.success("API responded successfully.")
            except TPMError as exc:
                st.error(f"API error: {exc}")

        if st.button(
            "Refresh all active markets",
            type="primary",
            disabled=not unlocked
        ):
            run_refresh(con, api_key)
            if snapshot(con):
                st.rerun()

    st.stop()

st.divider()
reg_col,cat_col,search_col=st.columns([1.3,2.2,2.2],gap='medium')
with reg_col:
    region=st.radio('Region',REGIONS,index=0,horizontal=True)
with cat_col:
    category=st.selectbox('Category',CATEGORIES,index=0)
with search_col:
    query=st.text_input('Search saved markets',placeholder='e.g. Lakers, Oscars, presidential election')

visible=match_filters(rows,region,category,query)
visible.sort(key=volume24,reverse=True)
with st.container():
    m1,m2,m3,m4=st.columns(4)
    m1.metric('Markets in selection',f'{len(visible):,}')
    m2.metric('Matched venues',f'{sum(len(r.get("venues") or [])>1 for r in visible):,}')
    m3.metric('24h traded value',fmt_usd(sum(volume24(r) for r in visible)))
    m4.metric('Outcomes prefetched',info.get('details_prefetched','0'))
    st.caption('Popularity is ranked by reported 24-hour USD trading volume, not transaction count. Region is topic relevance, not the location of traders.')

st.subheader('🔥 Top 5 Trending Markets')
st.caption('Highest 24-hour trading volume in the selected region and category.')
top=visible[:5]
if not top:
    st.info('No markets in this selection. Try another category or region.')
else:
    for rank,r in enumerate(top,1):
        detail_obj=saved_detail(con,r['slug'])
        title=clean(r.get('title'))
        col_a,col_b,col_c=st.columns([.55,6.1,1.2],vertical_alignment='center')
        with col_a:st.markdown(f'### {rank}')
        with col_b:
            leading=(r.get('leading_outcome') or {})
            label=clean(leading.get('title') or 'Featured outcome')
            st.markdown(f'<div class="an-outcome">{title}</div><div class="an-small">{clean(r.get("category") or "Other")} · {fmt_usd(volume24(r))} traded in 24h · {label}: {pct(safe_num(leading.get("probability"),None))}</div>',unsafe_allow_html=True)
            if detail_obj:
                fg=find_featured(detail_obj)
                if fg:
                    k=fg['prices'].get('kalshi');p=fg['prices'].get('polymarket');f=forecast(detail_obj,fg,accuracy_model())
                    st.caption(f'Kalshi {pct(k["p"] if k else None)} · Polymarket {pct(p["p"] if p else None)} · AN indicative {pct(f["prob"])}')
        with col_c:
            if st.button('Explore',key=f'top_{r["slug"]}',use_container_width=True):
                st.session_state['expanded_slug']=r['slug']
                st.rerun()
        st.divider()

op_a,op_b=st.columns(2,gap='large')
with op_a:
    st.subheader('📈 Biggest Probability Movers')
    movers=[r for r in visible if movement24(r) is not None]
    movers=sorted(movers,key=lambda r:abs(movement24(r)),reverse=True)[:5]
    if not movers:
        st.caption('No 24-hour probability changes supplied for this selection.')
    for r in movers:
        delta=movement24(r)
        st.markdown(f'<div class="an-strip"><b>{clean(r.get("title"))}</b><div class="an-small">{clean((r.get("leading_outcome") or {}).get("title"))} · {delta*100:+.1f} percentage points · {fmt_usd(volume24(r))} 24h volume</div></div>',unsafe_allow_html=True)
with op_b:
    st.subheader('⚖️ Kalshi vs Polymarket Disagreements')
    disagreements=[]
    for r in visible:
        d=saved_detail(con,r['slug'])
        if d:
            for x in matched_disagreements(d):
                disagreements.append((x['diff'],r,d,x))
    disagreements.sort(key=lambda x:x[0],reverse=True)
    if not disagreements:
        st.caption('No comparable paired outcomes in the prefetched snapshot. Expand an event to request full details.')
    for _,r,d,x in disagreements[:5]:
        g=x['group']
        checked=d.get('comparison')=='verified'
        st.markdown(f'<div class="an-strip"><b>{clean(r.get("title"))}</b><div class="an-small">{clean(g.get("name"))} · Kalshi {pct(x["kalshi"])} · Polymarket {pct(x["polymarket"])} · gap {100*x["diff"]:.1f} pp · {"Verified event" if checked else "Unverified rules"}</div></div>',unsafe_allow_html=True)
st.caption('Disagreements represent different quoted probabilities, not risk-free arbitrage. Event and outcome settlement rules may differ.')

st.divider()
st.subheader('All Active Markets')
order=st.selectbox('Sort markets by',['24h trading volume','Lifetime trading volume','Largest 24h probability movement'],index=0)
if order=='Lifetime trading volume':
    visible.sort(key=lambda r:safe_num(r.get('volume')),reverse=True)
elif order=='Largest 24h probability movement':
    visible.sort(key=lambda r:abs(movement24(r) or 0),reverse=True)
else:
    visible.sort(key=volume24,reverse=True)
PAGE_SIZE=12
max_page=max(1,(len(visible)+PAGE_SIZE-1)//PAGE_SIZE)
page=st.number_input('Page',min_value=1,max_value=max_page,value=1,step=1)
start=(page-1)*PAGE_SIZE
cards=visible[start:start+PAGE_SIZE]
for i in range(0,len(cards),3):
    columns=st.columns(3,gap='medium')
    for col,r in zip(columns,cards[i:i+3]):
        with col:
            show_market_preview(r,saved_detail(con,r['slug']),unique='catalogue')
st.caption(f'Showing {start+1 if cards else 0}–{min(start+PAGE_SIZE,len(visible))} of {len(visible):,} active markets. Others are in the saved catalogue and can be browsed without extra API calls.')

slug=st.session_state.get('expanded_slug')
if slug:
    details_panel(con,slug,api_key)

st.divider()
with st.expander('Methodology, source coverage and limitations'):
    st.markdown('''
- **Data provider:** The Prediction Markets API (TPM) v1; unified event IDs from its backend, not guessed title-based merges.
- **Venues:** Kalshi and Polymarket International, as provided by TPM. Polymarket US is not guaranteed by this API.
- **Refresh:** Manual only. Full active catalogue via `/events?status=trading` and cursor pagination. The selected popular events are enriched using `/events/{slug}` on refresh.
- **Other event details:** Fetched only when you choose **Explore** or **View all outcomes**. Full details are cached until the next manual refresh.
- **AN model:** Uses the existing experimental historical model if sufficient valid observations exist in `history.csv`, beginning March 1, 2025; otherwise it is an explicitly labeled 50/50 *indicative* blend. It must not be called validated accuracy or official sportsbook odds.
- **Compatibility:** TPM can group equivalent-looking outcomes even when rules are unverified. The dashboard labels those cases. Quotes labelled stale or unknown are excluded from the AN blend.
- **Region:** Heuristic classification based on what an event concerns. It does NOT measure where trading is happening. Some sports leagues and events qualify for more than one region.
- **Storage:** Local SQLite files in a running Streamlit instance are **not durable** across redeploys/restarts on Community Cloud.
- **Volume:** The TPM API describes `volume_24h` as dollar volume across venues. It is not an individual trade count and may not match PredictionPro's displayed volumes.
- **Publisher permissions:** Confirm third-party API commercial redistribution rights before publishing outside the internal prototype.
''')
