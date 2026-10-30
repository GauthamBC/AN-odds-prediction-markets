"""AN Odds Studio | Read-only live dashboard & experimental historical calibration.

Run: streamlit run streamlit_app.py
Live exchange data is separate from the resolved-market historical training CSV.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import csv
import io
import math

import pandas as pd
import streamlit as st

from core import CATEGORY_NAMES, american, date_from_string
from feeds import (FeedError, fetch_kalshi, fetch_polymarket, fetch_polymarket_us,
                   fetch_polymarket_search, fetch_polymarket_slug, merge_quotes, KNOWN_GAMMA_SLUGS)
from matching import combine_quotes, canonical_event_key, event_volumes
from model import AccuracyModel, read_history

st.set_page_config(
    page_title="Markets Dashboard | AN Odds Studio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
:root { color-scheme:dark; }
html,body,[class*="css"],.stApp,div[data-testid="stAppViewContainer"] {font-family:'Inter',system-ui,sans-serif;}
.stApp {background:#0b0d16;color:#f9faff;}
header[data-testid="stHeader"] {background:#0b0d16;}
#MainMenu,footer {visibility:hidden;}
.block-container {max-width:1510px;padding:1.0rem 2.05rem 2.8rem;}
[data-testid="stVerticalBlock"] {gap:.47rem;}
[data-testid="stElementContainer"]:has(.an-card) {height:100%;}
[data-testid="stHorizontalBlock"] {gap:1rem;}
.an-nav {display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #242637;padding:8px 0 16px;margin-bottom:22px;gap:16px;}
.an-nav-left {display:flex;align-items:center;gap:32px;}
.an-logo {font-size:18px;letter-spacing:-.75px;font-weight:900;white-space:nowrap;color:#fff;}
.an-logo-mark {display:inline-flex;width:24px;height:24px;border-radius:7px;background:#25d38c;color:#081b13;align-items:center;justify-content:center;margin-right:7px;transform:skew(-8deg);}
.an-nav-item {font-size:13px;color:#a5b0c8;font-weight:500;padding:14px 4px;}
.an-nav-item.active{color:#54e1ad;border-bottom:2px solid #54e1ad;}
.an-nav-tag {color:#9fb0c8;border:1px solid #32364d;font-size:11px;font-weight:700;border-radius:100px;padding:7px 11px;white-space:nowrap;}
.an-head {margin:4px 0 13px;}
.an-title {font-size:clamp(32px,3.55vw,43px);font-weight:850;letter-spacing:-1.7px;line-height:1.15;color:#f7f9ff;}
.an-subtitle {color:#97a4bf;font-size:14px;margin-top:9px;line-height:1.55;}
.an-sources {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:13px 0 14px;}
.an-source {background:#11131e;border:1px solid #34364d;border-radius:13px;min-height:102px;padding:16px 18px 15px;display:flex;flex-direction:column;justify-content:space-between;}
.an-source-row {display:flex;align-items:center;justify-content:space-between;gap:8px;}
.an-source-name{font-weight:850;font-size:21px;letter-spacing:-.6px;}
.an-kname{color:#37d493;}.an-pname{color:#2690ff;}
.an-source-count{font-size:13px;color:#e3eaf7;font-weight:700;font-variant-numeric:tabular-nums;}
.an-source-caption{font-size:12px;color:#99a9c6;margin-top:14px;line-height:1.3;}
.an-rule{height:1px;background:#24283b;margin:5px 0 16px;}
.an-results {font-size:12px;color:#8191b2;font-variant-numeric:tabular-nums;}
.an-results b{color:#b6c8e7;}
.an-mini-info{font-size:11px;color:#8090ad;margin:0 0 9px;}
/* Form controls: compact horizontal style instead of Streamlit's stacked filters. */
div[data-testid="stTextInput"] input {height:43px;border-radius:8px;background:#161924;color:#f5f7fb;border:1px solid #34394e;font-size:13px;padding-left:14px;}
div[data-testid="stTextInput"] input:focus {border-color:#39d8a2;box-shadow:0 0 0 1px #39d8a233;}
div[data-testid="stTextInput"] label {display:none;}
div[data-testid="stPills"] button,div[data-testid="stSegmentedControl"] button {border:1px solid #30344a!important;background:#10131f!important;color:#a6b4d2!important;font-size:12px!important;border-radius:20px!important;min-height:32px!important;padding:5px 11px!important;}
div[data-testid="stSegmentedControl"] button{border-radius:7px!important;}
div[data-testid="stPills"] button[aria-pressed="true"],div[data-testid="stSegmentedControl"] button[aria-pressed="true"] {background:#24293d!important;color:#fff!important;border-color:#495372!important;font-weight:800;}
/* Streamlit may use aria-checked in some versions */
div[data-testid="stPills"] button[aria-checked="true"],div[data-testid="stSegmentedControl"] button[aria-checked="true"] {background:#24293d!important;color:#fff!important;border-color:#495372!important;}
[data-testid="stPills"] {margin-top:2px;}
div[data-testid="stButton"] button,div[data-testid="stDownloadButton"] button {background:#161b2a;border:1px solid #353d56;color:#e2ebfc;border-radius:8px;font-size:12px;font-weight:700;min-height:37px;}
div[data-testid="stButton"] button:hover,div[data-testid="stDownloadButton"] button:hover {border-color:#3cdaaa;color:#44dcaa;}
/* Comparable to screenshot #1 cards: compact, aligned and easy to scan. */
.an-card {background:#11131e;border:1px solid #32364b;border-radius:13px;margin:4px 0 13px;padding:17px 17px 14px;min-height:238px;display:flex;flex-direction:column;}
.an-card-head {display:flex;gap:12px;align-items:flex-start;min-height:58px;}
.an-icon {width:46px;height:46px;flex:0 0 46px;display:flex;align-items:center;justify-content:center;border-radius:9px;background:linear-gradient(135deg,#493775,#292147);font-size:23px;}
.an-heading{flex:1;min-width:0;}
.an-card-title{font-size:14px;font-weight:800;color:#f6f8fe;letter-spacing:-.15px;line-height:1.35;overflow-wrap:anywhere;}
.an-meta{font-size:11px;color:#93a7cc;margin-top:5px;line-height:1.3;}
.an-match-chip{font-size:9px;color:#80dfbb;border:1px solid #235c47;background:#103128;border-radius:5px;padding:3px 5px;white-space:nowrap;}
.an-table{width:100%;border-collapse:collapse;table-layout:fixed;margin-top:11px;}
.an-table th{font-size:10px;letter-spacing:.55px;font-weight:700;color:#8497c1;padding:10px 3px 11px;text-align:center;border-top:1px solid #252c3f;}
.an-table th:first-child{text-align:left;width:47%;}
.an-table td{padding:7px 3px;color:#ecf3ff;font-size:12px;vertical-align:middle;text-align:center;}
.an-table td:first-child{text-align:left;font-weight:500;overflow-wrap:anywhere;padding-right:7px;}
.an-table th.an-kalshi-col{color:#43dba1;}.an-table th.an-poly-col{color:#55a0ff;}.an-table th.an-an-col{color:#f8cc70;}
.an-val{border:1px solid #373c55;display:inline-flex;flex-direction:column;gap:3px;align-items:center;justify-content:center;padding:5px 3px;border-radius:7px;min-width:49px;background:#101520;color:#f5f7ff;font-weight:800;font-size:12px;font-variant-numeric:tabular-nums;}
.an-val.k{border-color:#1d6c52;background:#0d3b2c;color:#41e3a3;}
.an-val.p{border-color:#295780;background:#102f4e;color:#66acff;}
.an-val.a{border-color:#7e6333;background:#3b3019;color:#ffe09c;}
.an-ml{font-size:9px;font-weight:650;opacity:.78;white-space:nowrap;}
.an-empty-val{color:#53627e;font-size:12px;}
.an-card-bottom{margin-top:auto;padding-top:10px;display:flex;align-items:center;justify-content:space-between;gap:9px;border-top:1px solid #24283b;color:#8fa1c2;font-size:10px;}
.an-card-bottom a{color:#9fbaff;text-decoration:none;white-space:nowrap;}.an-card-bottom a:hover{text-decoration:underline;}
.an-source-tag{font-weight:600;color:#8ea3c8;}
.an-expand{margin:5px 0 11px;font-size:11px;color:#becbec;}
.an-expand summary{cursor:pointer;list-style:none;text-align:center;color:#abcaff;padding:7px 2px;}
.an-expand summary:hover{color:#f4f8ff;}
.an-expand summary::-webkit-details-marker{display:none;}
.an-expand[open] summary{border-bottom:1px solid #273046;margin-bottom:7px;}
.an-expand .an-table{margin-top:0;}
.an-expand .an-table td{border-bottom:1px solid #202737;}
.an-footnote {font-size:11px;color:#8495b4;line-height:1.65;margin:13px 0;}
.an-blank {color:#9bb0cd;text-align:center;border:1px dashed #363c53;padding:24px;border-radius:12px;}
.an-status-line{font-size:11px;color:#9eb0d0;}
.an-poly-us{display:inline-block;background:#26447c;border:1px solid #4073bc;border-radius:4px;font-size:9px;color:#b9d8ff;padding:1px 4px;margin-left:5px;}
.an-baseline{color:#f4c56b;font-size:10px;font-weight:600;padding:6px 0 2px;}
@media(max-width:1150px){.an-card{padding:13px 11px 10px;}.an-val{min-width:43px;font-size:11px}.an-table th:first-child{width:43%;}.an-icon{width:38px;height:38px;flex-basis:38px;font-size:20px}.an-card-title{font-size:12px}}
@media(max-width:790px){.block-container{padding:1rem .8rem 2rem;}.an-nav-left{gap:12px}.an-nav-item{display:none}.an-card{padding:14px}.an-card-title{font-size:14px}.an-sources{grid-template-columns:1fr;gap:9px}.an-source{min-height:85px;padding:13px}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

BASE = Path(__file__).parent
HISTORY = BASE / "history.csv"
ALIASES = BASE / "market_aliases.csv"

with st.sidebar:
    st.subheader("Market coverage")
    kalshi_pages = st.select_slider("Kalshi pages", options=[1, 2, 4, 8, 12, 20, 35, 60], value=8,
                                     help="Up to 200 events per page. More pages increase load times.")
    poly_pages = st.select_slider("Polymarket International pages", options=[1, 2, 4, 8, 12, 20, 35, 60], value=12,
                                   help="Up to 100 events per page. Uses public Gamma API.")
    include_us = st.checkbox("Include Polymarket US", value=True,
                             help="Optional separate US feed. Its market coverage, identifiers and price availability differ from international Polymarket.")
    us_pages = st.select_slider("Polymarket US pages", options=[1, 2, 4, 8, 12, 20], value=4,
                                disabled=not include_us)
    us_bbo = st.select_slider("US price lookups for unpriced listings", options=[0, 10, 24, 50], value=24, disabled=not include_us,
                              help="US listings can omit prices. Optional read-only BBO lookups make separate requests and may take longer.")
    st.caption("These controls set *scan limits*, not guaranteed totals. Feeds refresh from public endpoints every two minutes.")
    auto_search = st.checkbox("Find counterparts beyond scanned pages", value=True,
                              help="Fetch matching markets directly from official Polymarket search/slug endpoints. Uses a small number of extra API calls.")
    st.divider()
    st.markdown("**Experimental AN model**")
    st.caption("Historical start: March 1, 2025 · 18-month half-life. With no validated history, the AN column is an unvalidated 50/50 benchmark.")
    st.caption("Resolved markets are kept out of the live dashboard; their pre-resolution prices and outcomes belong in history.csv.")
    st.divider()
    st.link_button("Kalshi API docs", "https://docs.kalshi.com/api-reference/events/get-events")
    st.link_button("Polymarket Intl API", "https://docs.polymarket.com/market-data/discover-markets")
    st.link_button("Polymarket US docs", "https://docs.polymarket.us/data-guide/overview")

@st.cache_data(ttl=120, show_spinner=False)
def load_live(k_pages: int, p_pages: int, us_on: bool, u_pages: int, bbo_limit: int):
    """Fetch open markets only; settle/historical markets are not requested."""
    quotes = {"Kalshi": [], "Polymarket": [], "Polymarket US": []}
    diagnostics = {}
    errors = {}
    feeds = [("Kalshi", fetch_kalshi, k_pages), ("Polymarket", fetch_polymarket, p_pages)]
    if us_on:
        feeds.append(("Polymarket US", fetch_polymarket_us, u_pages))
    for platform, fn, n_pages in feeds:
        try:
            quotes[platform], diagnostics[platform] = fn(n_pages, bbo_limit=bbo_limit) if platform=="Polymarket US" else fn(n_pages)
        except Exception as ex:
            errors[platform] = str(ex)[:270]
            diagnostics[platform] = {"events_scanned": 0, "complete": False, "endpoint": "Unavailable"}
    return quotes, diagnostics, errors, datetime.now(timezone.utc).isoformat()

@st.cache_data(ttl=300, show_spinner=False)
def targeted_discovery(kalshi_quotes, query, enabled=True):
    """Discover a few event counterparts missed by top-24h-volume pagination.

    Only official Gamma prices are used. Search is bounded to limit API calls.
    Failures do not block the dashboard; they are reported in diagnostics.
    """
    if not enabled:
        return [], [], []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    tasks = []
    # A meaningful direct search must work even for an event absent from Kalshi's scan.
    if len(query.strip()) >= 5:
        tasks.append(('search', query.strip()[:130]))
    # Find frequently searched, long-duration political counterparts by stable slug.
    groups = {}
    for item in kalshi_quotes:
        key = canonical_event_key(item.event_title, item.category)
        if key in KNOWN_GAMMA_SLUGS:
            groups[key] = max(groups.get(key, 0), item.volume)
    for key in sorted(groups, key=lambda k: -groups[k])[:4]:
        tasks.append(('slug', KNOWN_GAMMA_SLUGS[key]))
    # Search the most active Kalshi events by event TOTAL, not just by individual
    # child contract; a top-volume market can be absent from the Polymarket 24h scan.
    # Discovery never means automatic matching: the matching engine checks both sides.
    totals = {}
    for q in kalshi_quotes:
        if q.category != 'Other':
            totals[q.event_title] = totals.get(q.event_title, 0) + q.volume
    primary = sorted(totals, key=lambda t: -totals[t])[:6]
    if len(query.strip()) >= 5:
        token = query.strip().lower()
        # Give the user's active search priority over general top-volume coverage.
        primary = [t for t in totals if token in t.lower()][:3] + primary
    for title in primary:
        tasks.append(('search', title[:130]))
    tasks = list(dict.fromkeys(tasks))[:11]
    rows, info, errors = [], [], []
    def execute(task):
        mode, argument = task
        if mode == 'slug':
            return fetch_polymarket_slug(argument), mode + ':' + argument
        result, _ = fetch_polymarket_search(argument)
        return result, mode + ':' + argument
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(execute, t): t for t in tasks}
        for future in as_completed(futures):
            try:
                result, label = future.result()
                rows.extend(result)
                info.append(f'{label} → {len(result)} quotes')
            except Exception as exc:
                mode, argument = futures[future]
                errors.append(f'{mode}:{argument} → {str(exc)[:130]}')
    return merge_quotes(rows), sorted(info), sorted(errors)

st.markdown('''<div class="an-nav"><div class="an-nav-left"><div class="an-logo"><span class="an-logo-mark">A</span> ACTION NETWORK <span style="color:#8d9fbe;font-size:12px;font-weight:600">/ ODDS STUDIO</span></div><span class="an-nav-item active">Markets</span><span class="an-nav-item">Live intelligence</span></div><span class="an-nav-tag">INTERNAL PROTOTYPE</span></div>''', unsafe_allow_html=True)
st.markdown('''<div class="an-head"><div class="an-title">Markets Dashboard</div><div class="an-subtitle">Browse active Kalshi and Polymarket markets side by side, with Action Network fair-odds estimates where outcomes can be matched.</div></div>''', unsafe_allow_html=True)

with st.spinner("Retrieving active exchange markets…"):
    live, diagnostics, errors, refreshed = load_live(kalshi_pages, poly_pages, include_us, us_pages, us_bbo)

source_cards = []
scan = diagnostics.get("Kalshi", {})
source_cards.append(
    f'<div class="an-source"><div class="an-source-row"><span class="an-source-name an-kname">Kalshi</span>'
    f'<span class="an-source-count">{len(live["Kalshi"]):,} quotes</span></div>'
    f'<div class="an-source-caption">Active markets · {scan.get("events_scanned",0):,} events scanned · '
    f'{"Complete" if scan.get("complete") else "Partial scan"}</div></div>'
)
p_int = len(live["Polymarket"]); p_us = len(live["Polymarket US"])
source_cards.append(
    f'<div class="an-source"><div class="an-source-row"><span class="an-source-name an-pname">Polymarket</span>'
    f'<span class="an-source-count">{p_int+p_us:,} quotes</span></div>'
    f'<div class="an-source-caption">International: {p_int:,} quotes · US: {p_us:,} quotes (separate venues)</div></div>'
)
st.markdown('<div class="an-sources">' + ''.join(source_cards) + '</div>', unsafe_allow_html=True)
st.markdown('<div class="an-rule"></div>', unsafe_allow_html=True)

aliases = {}
if ALIASES.exists():
    with ALIASES.open(newline="", encoding="utf-8") as f:
        for record in csv.DictReader(f):
            k = record.get("kalshi_event_id", "").strip()
            p = record.get("polymarket_event_id", "").strip()
            if k and p:
                aliases[k] = p


if errors:
    for name, error in errors.items():
        st.error(f"{name} live feed problem: {error}")
if not any(live.values()):
    st.warning("No active quotes could be loaded. Check the API connections and diagnostics below.")

# All primary controls are on one neat toolbar, as in the reference dashboard.
t_search, t_source, t_layout, t_refresh = st.columns([4.6, 2.8, 1.5, .65], vertical_alignment="center", gap="small")
with t_search:
    search = st.text_input("Search markets", placeholder="⌕  Search markets or outcomes", key="market_search", label_visibility="collapsed")
with t_source:
    source_view = st.segmented_control("Source", ["All", "Kalshi", "Polymarket", "Poly US", "Matched"], default="All", key="source_view", label_visibility="collapsed")
with t_layout:
    layout = st.segmented_control("Layout", ["Grid", "Table"], default="Grid", key="market_layout", label_visibility="collapsed")
with t_refresh:
    if st.button("↻", help="Refresh the live feeds (2-minute cache)", use_container_width=True):
        load_live.clear()
        st.rerun()

# Search beyond the limited high-volume scan; preserve unique exchange venue IDs.
extra_poly, discovery_info, discovery_errors = targeted_discovery(
    live["Kalshi"], search or "", auto_search
)
poly_all = merge_quotes(live["Polymarket"], live["Polymarket US"], extra_poly)
cards = combine_quotes(live["Kalshi"], poly_all, aliases)
model = AccuracyModel(read_history(HISTORY))
matched_total = sum(1 for c in cards if c.matched)

cat_col, count_col = st.columns([5.8, 1], vertical_alignment="center", gap="small")
with cat_col:
    chosen = st.pills(
        "Category", ["All markets", "Sports", "Entertainment", "Politics", "Crypto", "Economics", "Science & Tech", "Weather", "Other"],
        default="All markets", key="category_choice", label_visibility="collapsed",
    )
with count_col:
    st.markdown(f'<div class="an-results" style="text-align:right">{len(cards):,} indexed events</div>', unsafe_allow_html=True)

search_normalized = (search or "").strip().lower()
filtered = []
for card in cards:
    if chosen and chosen != "All markets" and card.category != chosen:
        continue
    if search_normalized and search_normalized not in (card.title + " " + " ".join(r.label for r in card.rows)).lower():
        continue
    has_k = any(r.kalshi is not None for r in card.rows)
    has_p = any(r.polymarket is not None for r in card.rows)
    if source_view == "Kalshi" and not has_k:
        continue
    if source_view == "Polymarket" and not has_p:
        continue
    if source_view == "Poly US" and not any(r.polymarket and r.polymarket.exchange == "Polymarket US" for r in card.rows):
        continue
    if source_view == "Matched" and not card.matched:
        continue
    filtered.append(card)

scan_complete = bool(diagnostics) and all(d.get("complete") for d in diagnostics.values())
coverage_label = "full pagination" if scan_complete else "partial API coverage"
st.markdown(
    f'<div class="an-mini-info">Showing <b>{len(filtered):,}</b> active events from this snapshot · '
    f'<b>{matched_total:,}</b> potentially matched event pairs · {coverage_label} · '
    f'Updated {datetime.fromisoformat(refreshed):%H:%M UTC}</div>',
    unsafe_allow_html=True,
)

CATEGORY_ICONS = {
    "Sports": "🏅", "Politics": "🏛️", "Entertainment": "🎬", "Crypto": "₿",
    "Economics": "📈", "Science & Tech": "🔬", "Weather": "⛅", "Other": "✦",
}


def display_probability(prob: float) -> str:
    """Readable at both large and tiny probabilities."""
    percent = prob * 100
    if percent > 99.9:
        return ">99.9%"
    if 0 < percent < .1:
        return "<0.1%"
    if percent < 1:
        return f"{percent:.1f}%"
    return f"{percent:.0f}%" if percent >= 10 else f"{percent:.1f}%"


def quote_cell(quote, marker: str):
    if quote is None:
        return '<span class="an-empty-val">—</span>'
    p = quote.probability
    venue = " · US" if quote.exchange == "Polymarket US" else ""
    return f'<span class="an-val {marker}" title="{escape(quote.exchange,quote=True)}">{escape(display_probability(p))}<span class="an-ml">{escape(american(p))}{venue}</span></span>'


def model_cell(kalshi, polymarket):
    prediction = model.predict(kalshi, polymarket)
    if prediction["probability"] is None:
        return '<span class="an-empty-val">—</span>'
    p = prediction["probability"]
    return f'<span class="an-val a" title="{escape(prediction["status"], quote=True)}">{escape(display_probability(p))}<span class="an-ml">{escape(american(p))}</span></span>'


def compact_volume(value: float) -> str:
    if value >= 1e9:
        return f"{value / 1e9:.1f}B"
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    if value >= 1e3:
        return f"{value / 1e3:.1f}K"
    return f"{value:,.0f}"


def rows_markup(rows):
    return "".join(
        '<tr>'
        + f'<td>{escape(r.label)}</td>'
        + f'<td>{quote_cell(r.kalshi, "k")}</td>'
        + f'<td>{quote_cell(r.polymarket, "p")}</td>'
        + f'<td>{model_cell(r.kalshi, r.polymarket)}</td>'
        + '</tr>' for r in rows
    )


def card_markup(card):
    sorted_rows = sorted(card.rows, key=lambda r: max(
        r.kalshi.probability if r.kalshi else 0,
        r.polymarket.probability if r.polymarket else 0,
    ), reverse=True)
    top = sorted_rows[:2]
    rest = sorted_rows[2:]
    icon = CATEGORY_ICONS.get(card.category, "✦")
    dates = [date_from_string(q.close_at) for r in card.rows for q in (r.kalshi, r.polymarket) if q and q.close_at]
    dates = [d for d in dates if d]
    close_label = min(dates).strftime("%b %-d, %Y") if dates else "Date unlisted"
    status = '<span class="an-match-chip" title="Automated candidate match; contract rules require manual verification">MATCHED*</span>' if card.matched else ""
    heading = f'''<div class="an-card-head"><span class="an-icon">{icon}</span><div class="an-heading"><div class="an-card-title">{escape(card.title)}</div><div class="an-meta">{escape(close_label)} · {escape(card.category)} {status}</div></div></div>'''
    tablehead = '<thead><tr><th>OUTCOME</th><th class="an-kalshi-col">KALSHI</th><th class="an-poly-col">POLY</th><th class="an-an-col">AN MODEL</th></tr></thead>'
    main_table = f'<table class="an-table">{tablehead}<tbody>{rows_markup(top)}</tbody></table>'
    expanded = (
        f'<details class="an-expand"><summary>Show all {len(sorted_rows)} outcomes ▾</summary>'
        f'<table class="an-table"><tbody>{rows_markup(rest)}</tbody></table></details>'
        if rest else '<div style="height:9px"></div>'
    )
    kalshi = {q.market_id: q for r in card.rows for q in (r.kalshi,) if q}
    poly = {q.market_id: q for r in card.rows for q in (r.polymarket,) if q}
    k_total, p_total = event_volumes(card.rows)
    source_info = []
    if kalshi:
        source_info.append("Kalshi: " + compact_volume(k_total) + " contracts traded")
    if poly:
        venue = next(iter(poly.values())).exchange
        source_info.append(("Polymarket US: " if venue == "Polymarket US" else "Polymarket Intl: ") + compact_volume(p_total) + " reported vol")
    source_links = []
    for source, group in (("Kalshi", kalshi), ("Polymarket", poly)):
        if group:
            first = next(iter(group.values()))
            source_links.append(f'<a href="{escape(first.url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(first.exchange)} ↗</a>')
    foot = '<div class="an-card-bottom"><span class="an-source-tag">' + escape(" · ".join(source_info)) + '</span><span>' + " · ".join(source_links) + '</span></div>'
    return f'<div class="an-card">{heading}{main_table}{expanded}{foot}</div>'


# Pagination follows the cards, not above them.
PAGE_SIZE = 18
filter_key = (search_normalized, chosen, source_view, layout, kalshi_pages, poly_pages, include_us, us_pages, us_bbo, auto_search)
if st.session_state.get("last_filter") != filter_key:
    st.session_state["last_filter"] = filter_key
    st.session_state["page"] = 1
max_page = max(1, math.ceil(len(filtered) / PAGE_SIZE))
st.session_state["page"] = min(st.session_state.get("page", 1), max_page)
current_page = st.session_state["page"]
visible = filtered[(current_page - 1) * PAGE_SIZE : current_page * PAGE_SIZE]

if not visible:
    st.markdown('<div class="an-blank">No active markets match the selected filters. Try a different category or source.</div>', unsafe_allow_html=True)
elif layout == "Grid":
    for i in range(0, len(visible), 3):
        cols = st.columns(3, gap="medium")
        for col, card in zip(cols, visible[i:i + 3]):
            with col:
                st.markdown(card_markup(card), unsafe_allow_html=True)
else:
    table_rows = []
    for card in visible:
        for r in card.rows:
            prediction = model.predict(r.kalshi, r.polymarket)
            table_rows.append({
                "Market": card.title,
                "Category": card.category,
                "Outcome": r.label,
                "Kalshi %": round(100 * r.kalshi.probability, 2) if r.kalshi else None,
                "Polymarket %": round(100 * r.polymarket.probability, 2) if r.polymarket else None,
                "AN model %": round(100 * prediction["probability"], 2) if prediction["probability"] is not None else None,
                "AN fair moneyline": american(prediction["probability"]),
                "Model status": prediction["status"],
            })
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True, height=650)

prev_col, pager_col, next_col = st.columns([1, 5, 1], vertical_alignment="center")
with prev_col:
    if st.button("← Previous", disabled=current_page <= 1, use_container_width=True):
        st.session_state["page"] -= 1
        st.rerun()
with pager_col:
    st.markdown(f'<div class="an-results" style="text-align:center">Page {current_page:,} of {max_page:,} · {len(filtered):,} filtered events</div>', unsafe_allow_html=True)
with next_col:
    if st.button("Next →", disabled=current_page >= max_page, use_container_width=True):
        st.session_state["page"] += 1
        st.rerun()

# Full export of the indexed and filtered ACTIVE markets, not just the current page.
export_rows = []
for card in filtered:
    for r in card.rows:
        pred = model.predict(r.kalshi, r.polymarket)
        export_rows.append({
            "market": card.title, "category": card.category, "outcome": r.label,
            "kalshi_probability": r.kalshi.probability if r.kalshi else "",
            "polymarket_probability": r.polymarket.probability if r.polymarket else "",
            "an_probability": pred["probability"] if pred["probability"] is not None else "",
            "an_moneyline": american(pred["probability"]),
            "an_status": pred["status"],
            "matched": card.matched,
            "kalshi_url": r.kalshi.url if r.kalshi else "",
            "polymarket_url": r.polymarket.url if r.polymarket else "",
        })
buf = io.StringIO()
writer = csv.DictWriter(buf, fieldnames=list(export_rows[0]) if export_rows else ["market"])
writer.writeheader()
writer.writerows(export_rows)

st.markdown('<div class="an-rule"></div>', unsafe_allow_html=True)
download_col, note_col = st.columns([1.5, 4.5], vertical_alignment="center")
with download_col:
    st.download_button(
        "↓ Export filtered active markets",
        data=buf.getvalue(), file_name="AN_Odds_Studio_Active_Markets.csv",
        mime="text/csv", disabled=not export_rows,
        use_container_width=True,
    )
with note_col:
    status_msg = (
        f"Experimental historical data loaded ({len(model.rows):,} observations), but requires independent backtesting."
        if model.rows else "AN Model currently uses an **unvalidated 50/50 baseline** on matched events. Historical training has not been completed."
    )
    st.caption(status_msg)

with st.expander("Data diagnostics and research methodology"):
    st.markdown("**Live data coverage**")
    for source in diagnostics:
        d = diagnostics[source]
        st.write(
            f"- **{source}:** {len(live[source]):,} usable quotes from {d.get('events_scanned', 0):,} "
            f"events; {'complete' if d.get('complete') else 'partial'} scan. "
            f"Endpoint {d.get('endpoint', '/events')}."
        )
    st.write(f"Potentially matched event pairs: **{matched_total:,}**. These are candidate matches; settlement criteria still need verification.")
    st.markdown("**Targeted Polymarket discovery (beyond paginated scans)**")
    if discovery_info:
        for item in discovery_info:
            st.caption(item)
    else:
        st.caption("No additional search results requested.")
    if discovery_errors:
        for item in discovery_errors:
            st.caption("Discovery issue: " + item)
    st.caption("Polymarket US and International are separate exchanges with different market lists and histories. Our calibration does not transfer accuracy estimates between the two.")
    st.markdown("**Live vs. historical markets**")
    st.markdown(
        "- **Main dashboard:** only open/active market API listings, refreshed on a 120-second cache. "
        "No intentionally closed or settled markets are fetched.\n"
        "- **Historical calibration:** the separate `history.csv` is populated by a dedicated backfill script or a verified dataset. "
        "It contains resolved outcomes and pre-resolution snapshots dated March 2025 onward. "
        "Those historical rows are never mixed into the public-facing market cards.\n"
        "- **AN probability:** an experimental 50/50 benchmark until sufficient verified matched histories exist. "
        "Moneylines are fair-odds conversions, not tradable sportsbook prices."
    )
    st.markdown(
        "**Important:** market counts reflect API page caps, not all listings on the exchanges. "
        "A missing opposite-exchange quote means there is no sufficiently reliable match in the scanned data. "
        "Kalshi volume is the reported number of $1-face-value contracts traded, not the cash paid to trade them. "
        "Polymarket reported volume may use a different accounting convention. Do not compare these figures as equivalent cash amounts. "
        "Check actual market rules, fees and settlement criteria before publication."
    )

st.markdown('<div class="an-footnote">Research prototype for internal evaluation. Data attribution: Kalshi and Polymarket. Market probabilities may be delayed or non-executable. No trading takes place through this dashboard.</div>', unsafe_allow_html=True)
