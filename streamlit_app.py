"""Action Network Odds Studio — internal research prototype.

Run: streamlit run streamlit_app.py
Uses public read-only exchange APIs. Not a sportsbook or trading service.
"""
from __future__ import annotations
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import csv
import io
import os
import pandas as pd
import streamlit as st
from core import CATEGORY_NAMES, american
from feeds import FeedError, fetch_kalshi, fetch_polymarket
from matching import combine_quotes
from model import AccuracyModel, read_history

st.set_page_config(page_title="AN Odds Studio • Market Intelligence",page_icon="📈",layout="wide",initial_sidebar_state="collapsed")

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"],div[data-testid="stAppViewContainer"] {font-family:'DM Sans',system-ui,sans-serif;}
.stApp {background:linear-gradient(160deg,#09111C 0%,#090D18 42%,#0D1422 100%);color:#F0F5FE;}
.block-container {padding-top:1.9rem;max-width:1470px;padding-left:2rem;padding-right:2rem;}
header[data-testid="stHeader"] {background:transparent;}
#MainMenu, footer {visibility:hidden;}
h1,h2,h3 {letter-spacing:-.045em;}
.stTextInput input {background:#141B2B!important;color:#eff6ff!important;border:1px solid #2D3951!important;}
div[data-testid="stMetric"]{background:#141B2B;border:1px solid #28354A;border-radius:14px;padding:13px 18px;}
div[data-testid="stMetricLabel"]{color:#A3B1CA;}
div[data-testid="stMetricValue"]{font-size:1.35rem;}
.stButton>button,.stDownloadButton>button {border-radius:9px!important;border:1px solid #34445C;background:#19263A;color:#F1F7FE;}
.stButton>button:hover {border-color:#42D89B;color:#42D89B;}
.stSelectbox div[data-baseweb="select"],.stMultiSelect div[data-baseweb="select"] {background:#151e2d;}
[data-testid="stRadio"] label {font-size:.92rem;}
.an-topline {color:#52DDA5;font-size:12px;letter-spacing:2px;font-weight:800;margin-bottom:12px;}
.an-title {font-size:clamp(35px,4vw,57px);font-weight:800;letter-spacing:-2.1px;line-height:1.05;margin:0 0 10px 0;}
.an-subtitle {color:#A3B2CB;font-size:16px;line-height:1.6;margin-bottom:24px;}
.an-brand {display:flex;align-items:center;justify-content:space-between;padding-bottom:17px;margin-bottom:27px;border-bottom:1px solid #263147;}
.an-logo {font-size:20px;font-weight:800;letter-spacing:-.6px;color:#F8FAFC;}
.an-logo span {color:#42D89B;}
.an-pilot {font-size:12px;color:#AFC0D8;border:1px solid #30445D;padding:6px 10px;border-radius:99px;}
.an-feed {padding:19px;border:1px solid #2D3B53;border-radius:14px;background:linear-gradient(115deg,#141E2E,#111827);margin-bottom:20px;min-height:114px;}
.an-feed-name{font-size:23px;font-weight:800;letter-spacing:-.5px;}
.an-feed-sub{font-size:13px;color:#A8B8D2;margin-top:11px;}
.an-divider{height:1px;background:#27354b;margin:15px 0 20px;}
.an-card {background:#131B2A;border:1px solid #2C3951;border-radius:16px;padding:19px 18px 14px;min-height:260px;margin:0 0 20px;box-shadow:0 6px 18px rgba(0,0,0,.07);}
.an-card-head {display:flex;justify-content:space-between;gap:15px;min-height:62px;}
.an-card-title{font-size:17px;line-height:1.34;font-weight:800;letter-spacing:-.3px;color:#F4F7FF;}
.an-cat{font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:700;color:#A7B7D0;margin-top:7px;}
.an-match {font-size:10px;font-weight:800;white-space:nowrap;color:#46DCA1;border:1px solid #245A53;background:#12382E;padding:5px 7px;border-radius:6px;height:fit-content;}
.an-onesource {font-size:10px;font-weight:800;white-space:nowrap;color:#F2C179;border:1px solid #5C4B2A;background:#322B1A;padding:5px 7px;border-radius:6px;height:fit-content;}
.an-matrix {width:100%;border-collapse:collapse;margin-top:11px;table-layout:fixed;}
.an-matrix thead th{font-size:11px;letter-spacing:.2px;text-align:right;padding:7px 3px 11px;color:#8EA0BD;font-weight:700;border-bottom:1px solid #273449;}
.an-matrix thead th:first-child{text-align:left;width:40%;}
.an-matrix tbody td{border-bottom:1px solid #202D43;font-size:13px;padding:11px 4px;text-align:right;vertical-align:middle;}
.an-matrix tbody tr:last-child td{border-bottom:0;}
.an-matrix tbody td:first-child{text-align:left;color:#EDF3FD;font-weight:600;word-break:break-word;}
.an-cell{display:inline-block;border:1px solid #36445F;border-radius:7px;padding:6px 5px;min-width:52px;text-align:center;background:#0D1422;font-weight:800;font-variant-numeric:tabular-nums;}
.an-kalshi{color:#45DD9C;background:#0D352C;border-color:#17674C;}
.an-poly{color:#7CB4FF;background:#122C4E;border-color:#235581;}
.an-model{color:#F8F0C4;background:#42391D;border-color:#72622A;}
.an-odd{font-size:10px;font-weight:600;opacity:.8;display:block;margin-top:3px;}
.an-card-foot{font-size:11px;color:#899BB6;border-top:1px solid #273449;padding-top:11px;margin-top:10px;display:flex;justify-content:space-between;gap:5px;}
.an-card-foot a {color:#A8D4FF;text-decoration:none;}
.an-card-foot a:hover{text-decoration:underline;}
.an-note {color:#97A8C5;font-size:12px;line-height:1.55;margin:10px 0 14px;}
.an-empty{border:1px dashed #40516C;border-radius:14px;padding:32px;text-align:center;color:#B4C2D9;}
@media(max-width:800px){.block-container{padding-left:.8rem;padding-right:.8rem;}.an-card{padding:12px;}.an-matrix thead th{font-size:9px;}.an-matrix thead th:first-child{width:36%;}.an-matrix tbody td{font-size:11px;}.an-cell{min-width:43px;padding:5px 3px;}}
</style>
"""
st.markdown(STYLE,unsafe_allow_html=True)
st.markdown('<div class="an-brand"><div class="an-logo"><span>▰</span> ACTION NETWORK <span style="font-size:11px;color:#98ABC5;font-weight:500">/ ODDS STUDIO</span></div><div class="an-pilot">INTERNAL RESEARCH PROTOTYPE</div></div>',unsafe_allow_html=True)
st.markdown('<div class="an-topline">PREDICTION-MARKET INTELLIGENCE</div><div class="an-title">Markets Dashboard</div><div class="an-subtitle">Live probabilities from Kalshi and Polymarket, compared with Action Network’s provisional fair-odds model.</div>',unsafe_allow_html=True)

with st.sidebar:
    st.markdown('### Data and model settings')
    pages = st.select_slider('API pages per platform',options=[1,2,3,5,10,20,40,80,160],value=5,
             help='More pages increase market coverage but slow loading and can hit API limits. Each platform paginates independently.')
    st.caption('Kalshi fetches up to 200 events/page; Polymarket up to 100 events/page.')
    st.markdown('**Model**')
    history_file = Path(__file__).parent/'history.csv'
    st.caption('Training start: March 1, 2025. Recency half-life: 18 months. Historical estimates activate only when verified settled-event records are present.')
    st.markdown('**Development status**')
    st.caption('Indicative exchange probabilities, not executable prices. Automated matching is conservative; confirm settlement criteria before publishing.')
    with st.expander('Source API links'):
        st.link_button('Kalshi public API', 'https://docs.kalshi.com/api-reference/events/get-events')
        st.link_button('Polymarket Gamma API', 'https://docs.polymarket.com/')

@st.cache_data(ttl=120,show_spinner=False)
def load_live(page_cap):
    # Isolate failures: a single unavailable exchange does not hide the other.
    quotes = {"Kalshi":[],"Polymarket":[]}
    meta = {}
    errors = {}
    for source, fn in (("Kalshi",fetch_kalshi),("Polymarket",fetch_polymarket)):
        try:
            quotes[source],meta[source] = fn(page_cap)
        except FeedError as e:
            errors[source]=str(e)
            meta[source]={"events_scanned":0,"complete":False}
    return quotes, meta, errors, datetime.now(timezone.utc).isoformat()

left_feed,right_feed = st.columns(2)
with left_feed:
    st.markdown('<div class="an-feed"><div class="an-feed-name" style="color:#45DD9C">● Kalshi</div><div class="an-feed-sub">Open event contracts · Read-only probability feed</div></div>',unsafe_allow_html=True)
with right_feed:
    st.markdown('<div class="an-feed"><div class="an-feed-name" style="color:#479CFF">◈ Polymarket</div><div class="an-feed-sub">Active prediction markets · Read-only probability feed</div></div>',unsafe_allow_html=True)

refresh_col,stamp_col = st.columns([1,5],vertical_alignment='center')
with refresh_col:
    if st.button('↻ Refresh live data',use_container_width=True):
        load_live.clear()
        st.rerun()
with stamp_col:
    st.caption('Live API snapshot · 2-minute cache · Manual refresh available')

with st.spinner('Loading markets from public APIs…'):
    live,meta,errors,fetched_at = load_live(pages)
st.caption(f'Last successful fetch attempt: {datetime.fromisoformat(fetched_at):%d %b %Y, %H:%M:%S} UTC')
for key,error in errors.items():
    st.warning(f'{key} feed unavailable: {error}. Other feed may still be accessible.')
if not live['Kalshi'] and not live['Polymarket']:
    st.error('No live data could be retrieved. This app requires a deployed server with outbound access to the official exchange APIs. No example predictions have been substituted.')
    st.stop()

aliases = {}
alias_file=Path(__file__).parent/'market_aliases.csv'
if alias_file.exists():
    with alias_file.open(encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            if r.get('kalshi_event_id') and r.get('polymarket_event_id'):
                aliases[r['kalshi_event_id']]=r['polymarket_event_id']

cards = combine_quotes(live['Kalshi'],live['Polymarket'],aliases)
model = AccuracyModel(read_history(history_file))
matched = sum(1 for c in cards if c.matched)

mc = st.columns(4)
for col,title,value in zip(mc,['Events displayed','Cross-platform matched','Kalshi contract quotes','Polymarket contract quotes'],
                           [f'{len(cards):,}',f'{matched:,}',f"{len(live['Kalshi']):,}",f"{len(live['Polymarket']):,}"]):
    with col: st.metric(title,value)

notes = []
for exchange in ('Kalshi','Polymarket'):
    if not meta[exchange]['complete']:
        notes.append(f"{exchange} scan limited to {meta[exchange]['events_scanned']:,} events")
if notes:
    st.info('Partial coverage: '+' · '.join(notes)+'. Increase API pages in the sidebar to scan more. Market counts are NOT total exchange listings.')
if not model.rows:
    st.warning('**AN model: provisional 50/50 baseline.** No real historical results are loaded yet. We do not claim this estimate is independently validated. See README for the historical backfill workflow.')
else:
    st.info(f'Historical calibration engine: {len(model.rows):,} imported settled observations. Individual categories activate only after minimum sample thresholds. Out-of-sample validation is still required before external publication.')

st.markdown('<div class="an-divider"></div>',unsafe_allow_html=True)
filter_col, category_col, source_col, format_col = st.columns([3.1,2.1,1.4,1.15],vertical_alignment='bottom')
with filter_col: search = st.text_input('Search markets',placeholder='Search events, outcomes, teams...',label_visibility='visible')
with category_col: chosen = st.selectbox('Category',['All categories',*CATEGORY_NAMES])
with source_col: source_view = st.selectbox('Coverage',['All markets','Both exchanges','Kalshi only','Polymarket only'])
with format_col: layout = st.radio('Layout',['Grid','Table'],horizontal=True)

filtered=[]
for c in cards:
    if chosen != 'All categories' and c.category != chosen: continue
    if search and search.lower() not in (c.title+' '+' '.join(r.label for r in c.rows)).lower(): continue
    k_count=sum(x.kalshi is not None for x in c.rows)
    p_count=sum(x.polymarket is not None for x in c.rows)
    if source_view == 'Both exchanges' and not c.matched: continue
    if source_view == 'Kalshi only' and (not k_count or p_count): continue
    if source_view == 'Polymarket only' and (not p_count or k_count): continue
    filtered.append(c)

st.caption(f'{len(filtered):,} events match filters · {sum(c.matched for c in filtered):,} matched events · Unmatched events remain visible with blanks for unavailable values')

if 'last_filter' not in st.session_state:st.session_state.last_filter=None
filter_token=(search,chosen,source_view,layout,pages)
if st.session_state.last_filter!=filter_token:
    st.session_state.last_filter=filter_token
    st.session_state.page_num=1

per_page=st.selectbox('Events per page',[12,24,48,96],index=1)
page_count=max(1,(len(filtered)+per_page-1)//per_page)
if st.session_state.get('page_num',1)>page_count:st.session_state.page_num=1
page_num=st.number_input('Page',min_value=1,max_value=page_count,step=1,key='page_num')
visible=filtered[(page_num-1)*per_page:page_num*per_page]


def format_volume(v):
    if v>=1e9:return f'{v/1e9:.1f}B'
    if v>=1e6:return f'{v/1e6:.1f}M'
    if v>=1e3:return f'{v/1e3:.1f}K'
    return f'{v:,.0f}'


def quote_html(q, cls):
    if not q:return '<span style="color:#7889A4">—</span>'
    return f'<span class="an-cell {cls}">{q.probability*100:.1f}%<span class="an-odd">{escape(american(q.probability))}</span></span>'


def model_html(k,p):
    res=model.predict(k,p)
    if res['probability'] is None:return '<span style="color:#7889A4">—</span>',res
    pr=res['probability']
    return f'<span class="an-cell an-model">{pr*100:.1f}%<span class="an-odd">{escape(american(pr))}</span></span>',res


def render_card(c):
    rows_html=[]
    statuses=set()
    for r in c.rows[:6]:
        an,res=model_html(r.kalshi,r.polymarket)
        statuses.add(res['status'])
        label=escape(r.label[:90])
        rows_html.append(f'<tr><td title="{label}">{label}</td><td>{quote_html(r.kalshi,"an-kalshi")}</td><td>{quote_html(r.polymarket,"an-poly")}</td><td>{an}</td></tr>')
    more=f'<div class="an-note">+{len(c.rows)-6} more outcomes — switch to Table view for the full list</div>' if len(c.rows)>6 else ''
    status='Matched · review contract rules' if c.matched else 'One source only'
    tag='an-match' if c.matched else 'an-onesource'
    urls={}
    for r in c.rows:
        for q in (r.kalshi,r.polymarket):
            if q:urls[q.exchange]=q.url
    linkstr=' · '.join(f'<a href="{escape(u,quote=True)}" target="_blank" rel="noopener noreferrer">{escape(name)} ↗</a>' for name,u in urls.items())
    source_vol = {}
    for name in ('Kalshi','Polymarket'):
        unique_q = {q.market_id:q for r in c.rows for q in (r.kalshi,r.polymarket) if q and q.exchange == name}
        if unique_q:
            suffix = ' contracts' if name == 'Kalshi' else ' USD vol.'
            amount = format_volume(sum(q.volume for q in unique_q.values()))
            source_vol[name] = name + ': ' + ('$' if name == 'Polymarket' else '') + amount + suffix
    volumes = escape(' · '.join(source_vol.values()))
    return f'''<div class="an-card"><div class="an-card-head"><div><div class="an-card-title">{escape(c.title)}</div><div class="an-cat">{escape(c.category)}</div></div><div class="{tag}">{status}</div></div>
    <table class="an-matrix"><thead><tr><th>OUTCOME</th><th style="color:#45DD9C">KALSHI</th><th style="color:#76ACFF">POLY</th><th style="color:#F5D688">AN MODEL</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table>{more}
    <div class="an-card-foot"><span>{volumes}</span><span>{linkstr}</span></div></div>'''

if not visible:
    st.markdown('<div class="an-empty">No markets found for the selected filters.</div>',unsafe_allow_html=True)
elif layout=='Grid':
    for i in range(0,len(visible),3):
        cols=st.columns(3,gap='medium')
        for col,c in zip(cols,visible[i:i+3]):
            with col:st.markdown(render_card(c),unsafe_allow_html=True)
else:
    table=[]
    for c in visible:
        for r in c.rows:
            forecast=model.predict(r.kalshi,r.polymarket)
            table.append({'Market':c.title,'Category':c.category,'Outcome':r.label,
                          'Kalshi %':round(100*r.kalshi.probability,2) if r.kalshi else None,
                          'Polymarket %':round(100*r.polymarket.probability,2) if r.polymarket else None,
                          'AN model %':round(100*forecast['probability'],2) if forecast['probability'] is not None else None,
                          'AN fair moneyline':american(forecast['probability']),
                          'AN model status':forecast['status']})
    st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True,height=min(850,90+34*len(table)))

# Export full filtered results, not just the currently visible page.
export_rows=[]
for c in filtered:
    for r in c.rows:
        pred=model.predict(r.kalshi,r.polymarket)
        export_rows.append({'event':c.title,'category':c.category,'outcome':r.label,
           'kalshi_probability':r.kalshi.probability if r.kalshi else '',
           'polymarket_probability':r.polymarket.probability if r.polymarket else '',
           'an_probability':pred['probability'] if pred['probability'] is not None else '',
           'an_fair_american_moneyline':american(pred['probability']),
           'an_model_status':pred['status'], 'matched':c.matched,
           'kalshi_url':r.kalshi.url if r.kalshi else '',
           'polymarket_url':r.polymarket.url if r.polymarket else ''})
buf=io.StringIO()
if export_rows:
    w=csv.DictWriter(buf,fieldnames=list(export_rows[0]))
    w.writeheader();w.writerows(export_rows)
st.download_button('↓ Export filtered markets (CSV)',data=buf.getvalue(),file_name='AN_Odds_Studio_Live_Markets.csv',mime='text/csv',disabled=not export_rows)

with st.expander('Methodology, model training and critical limitations'):
    st.markdown('''
**Source columns:** exchange-implied YES or named-outcome prices (Kalshi bid/ask midpoint when available; Polymarket latest Gamma outcome prices). These are indicative and may differ from executable bid/ask prices.

**AN column:** displayed **only when an outcome is confidently matched across BOTH platforms**. With no verified historical dataset, the provisional estimate is a transparent 50/50 mean; when sufficient imported historical observations exist, an 18-month half-life discounts older records, locally calibrates each platform and adjusts blending weights **only from matched, resolved historical events**. Minimum sample safeguards prevent unreliable category claims.

**History:** observations must be dated from **March 1, 2025** and include an actual 0/1 settlement result and an actual pre-settlement probability. No historical performance is fabricated. A five-year/24-month decision can be tested later via time-ordered backtesting.

**Matching:** cross-platform contracts may differ in timing, outcome definition, fees, void rules and settlement policies. Matching uses conservative titles, outcome labels and dates; it **cannot guarantee** identical rules. Always verify source contracts.

**Coverage:** API pagination determines what has been scanned. A partial scan must never be described as all active exchange markets. Some newly listed or thin markets do not have usable price fields.

**Volume:** Kalshi volume counts contracts, while Polymarket volume is often USD-denominated. For that reason this interface's combined volume is **only a rough ranking heuristic**, not a meaningful pooled dollar volume. Do not cite combined totals externally.

**Internal research prototype only.** AN fair American moneyline is a mathematical probability conversion without bookmaker margin, not an executable quote, investment advice or a validated forecast. The app does not place trades or access private accounts.
''')
st.markdown('<div class="an-note">*Source volumes use different units (Kalshi contracts vs. Polymarket USD). Cross-market sorting is approximate; volumes must not be added together. Data source attribution: Kalshi and Polymarket. Prototype is not affiliated with either exchange.</div>',unsafe_allow_html=True)
