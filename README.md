# Action Network Odds Studio — v1.5 (internal Streamlit research prototype)

**Status: experimental and read-only.** The dashboard compares **active** markets
from Kalshi, Polymarket International and Polymarket US (separate venues), then
shows a provisional AN probability and fair American moneyline **only when a
candidate event and outcome can be matched**. The baseline is **50/50**, not a
historically validated forecast. Do not present it as independent fair value.

The appearance is inspired by a compact three-column market dashboard. This
code does not use PredictionPro's private backend, CSS or proprietary matching
data. All live market inputs come from public exchange data services.

## Deploy to GitHub + Streamlit Community Cloud

All **17 project files live directly in the repository root**. No subfolders
are required. Use **`streamlit_app.py`** as the Streamlit entrypoint.

1. Upload all the files into one GitHub repository, including `requirements.txt`.
2. Open https://share.streamlit.io and deploy `streamlit_app.py`.
3. In the sidebar, choose the maximum API scan pages you want (more pages take longer).
4. Search e.g. `2028 Democratic presidential nominee` and inspect the results.
5. In **Data diagnostics**, check the Polymarket US /events feed, discovery
   results, number of candidate pairs and whether any source is unavailable.

No API keys are required for the documented public, read-only endpoints, but
rates/availability may vary. Streamlit Cloud's filesystem is **ephemeral**;
local database contents disappear after restarts or redeploys.

## What changed in v1.5

- **`feeds.py`:** event-first **Polymarket US** integration at
  `https://gateway.polymarket.us/v1/events`, using nested `markets` and
  `marketSides`. Only the **long (YES)** side is treated as the positive
  outcome. A generic NO side is never mislabeled as a candidate.
- **`feeds.py`:** price parsing from `marketSides.price`, nested `quote`, or
  documented BBO/price fields. If a price cannot be interpreted in a known
  0–1 probability representation, no quote is fabricated.
- **`feeds.py`:** optional Polymarket US `/v1/search` counterpart discovery,
  alongside International Gamma discovery. If no US event prices are available,
  the US `/v1/markets` list is used as a fallback.
- **`matching.py`:** normalized events and outcomes, with conservative checks
  for mismatched titles, years, participant names, forecast dates and category.
  Candidate matches are displayed with **POSSIBLE MATCH*** until reviewed.
- **`mappings.py` + `market_aliases.csv` + `outcome_aliases.csv`:** reviewed event and individual contract mappings are stored
  in a version-controlled CSV; **only** records with `verified_rules=true`
  and a named venue are considered reviewed. The app exports new *unverified*
  pairs as a CSV that the team can examine before committing them to GitHub.
- **`index_store.py`:** small SQLite table keyed by `(venue, market_id)` for
  recent normalized quote snapshots. In the dashboard, entries older than
  **300 seconds** are excluded to avoid treating old observations as live.
- **`index_markets.py`:** optional, manual/externally scheduled, one-shot
  indexer. For example `python index_markets.py --kalshi-pages 25 --poly-pages 25 --us-pages 10`.
- **`test_v15.py`:** regression tests for event grouping, marketSides,
  search, verified mappings and the short-lived index.

## Crucial caveat: more matching is not automatically better matching

An apparent match must have identical **resolution rules**, entity or candidate,
contract date and (for sports) market type. 2028 nomination != 2028 general
presidential winner. Generic fuzzy matches alone are **never** marked verified.
Even reviewed event pairs should have **outcome-level identity** checked.
Sports market comparisons remain particularly conservative to avoid conflating
moneyline, spread, totals or repeated matchups.

Manual verification workflow:

1. Download **Export pairs for rule review** from the dashboard.
2. Download **Export outcome pairs for review** as well, if you need
   stable identity mappings for renamed candidate/contract titles.
3. Open both exchange links and compare the actual contract settlement rules.
4. Set `verified_rules=true` only on explicitly checked event or outcome lines.
5. Copy them into the repository-root `market_aliases.csv` and
   `outcome_aliases.csv` respectively. Keep both CSV column headers unchanged.
6. Redeploy. Unreviewed proposals must not be automatically promoted.

### Volume metrics

Kalshi's `volume_fp` is a count of **contracts traded**; Polymarket volumes may
be reported on a different basis. Do not add them, compare them as equivalent
cash trading volume, or equate them to PredictionPro's separate volume label.
Polymarket multi-outcome contracts use one volume per underlying market, not
one volume multiplied by the number of outcome quotes.

### Live coverage vs. resolved history

- **Active markets**: sourced from live exchange APIs. Scan page caps mean
  the total active inventory is **not guaranteed** to be complete. The search
  tool expands discovery beyond the initial ranking, but may still miss markets.
- **Indexing**: the local SQLite cache lasts only within one writable runtime.
  The 300-second display TTL guards against obvious stale quotes; it does not
  prove a contract is still open at display time. A true 24/7 market index
  requires an external durable database and a scheduled ingestion worker.
- **Historical settled markets**: **not displayed** in the live dashboard.
  `history.csv` is a template for pre-resolution probability snapshots and
  actual resolved outcomes starting **2025-03-01**.
- **AN probability**: a provisional 50/50 blend until sufficient independently
  verified historical observations are loaded and out-of-sample calibration
  tests have passed. A prediction shown for an automated candidate pair
  requires independent rule verification before public use.
- **American moneyline**: mathematical fair-odds conversion, not an executable
  sportsbook price, a wager recommendation or trading offer.

## Source documentation

- Kalshi: https://docs.kalshi.com/api-reference/events/get-events
- Polymarket Intl Gamma: https://docs.polymarket.com/developers/gamma-markets-api/overview
- Polymarket US events: https://docs.polymarket.us/api-reference/events/get-events
- Polymarket US markets: https://docs.polymarket.us/api-reference/markets/get-markets
- Polymarket US market BBO: https://docs.polymarket.us/api-reference/markets/get-market-bbo
- Polymarket US search: https://docs.polymarket.us/api-reference/search/search

## Testing

Run: `python -m pytest -q`. Latest run: **31 tests passed** using fixture data;
no live exchange API calls or Streamlit browser session were tested here.

**Do not commit populated historical/private datasets or runtime SQLite files
without checking usage permissions and data sensitivity.** The `.gitignore`
excludes temporary runtime files. Historic data collection, perpetual indexing,
and a statistically validated AN model are separate future workstreams.
