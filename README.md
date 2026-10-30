# AN Odds Studio — Streamlit prototype v1.3

An **internal research prototype** for Action Network, showing active prediction-market quotes from **Kalshi**, **Polymarket International** and optionally **Polymarket US**. It attempts conservative cross-venue matching, shows probabilities and their **fair American-moneyline equivalents**, and offers an experimental AN model column.

> **Important:** The AN model is **NOT independently validated**. With an empty historical CSV it produces a *provisional 50/50 benchmark only* for matched contracts. The numbers are indicative probabilities, **not tradable sportsbook odds**. Do not present the dashboard as Action Network's validated proprietary pricing engine.

## How to deploy to GitHub + Streamlit

**All files go in the repository root. No nested directories required.**

1. Create a GitHub repository, e.g. `an-odds-studio`.
2. Upload all 12 files from the ZIP directly to the repository root.
3. At [share.streamlit.io](https://share.streamlit.io), select the repository and `streamlit_app.py`.
4. Deploy and inspect **Data diagnostics and research methodology** at the bottom.
5. The optional **Polymarket US** source can be disabled in the sidebar if it is blocked or its quote fields change. US and International are distinct platforms and are never silently conflated.
6. Adjust API page limits in the sidebar. Higher values take longer and may hit rate limits.

### Files

- `streamlit_app.py` — dark responsive interface, cards, search, category/source filters, optional US feed, export.
- `feeds.py` — read-only Kalshi event cursor pagination; Polymarket International Gamma event pages and market fallback; optional Polymarket US gateway listing with bounded BBO lookups.
- `matching.py` — normalized event and outcome matching; 2028 US presidential general versus nomination distinction; year, close-time and outcome guardrails.
- `core.py` — quote structures, categories, probability formatting, fair moneyline conversion.
- `model.py` — recency-decayed calibration and paired-outcome Brier weighting **only if** compatible historical observations are supplied.
- `backfill_history.py` — **experimental partial** historical price+resolution sampler, requires running in a local environment with internet access.
- `history.csv` — intentionally empty historical observations template.
- `market_aliases.csv` — optional manually approved exchange event IDs (requires careful settlement-rule review).
- `requirements.txt`, `test_core.py`, `.gitignore`, `README.md`.

### What's new in v1.3

- **More live-market coverage:** independent pagination caps for Kalshi and Polymarket International. Counts reflect what was scanned, **not exchange-wide totals**.
- **Optional Polymarket US:** separate public read-only market feed via `gateway.polymarket.us/v1/markets`, with a small number of optional read-only BBO quote lookups. The gateway may return metadata without quote prices; these records are **not** invented or displayed as 0%.
- **Better matching:** recognizes canonical elections even with reordered titles, e.g. “2028 U.S. Presidential Election winner?” vs “Presidential Election Winner 2028,” while preventing 2028 nominations and general election outcomes from being merged.
- **Source clarity:** US quotes are marked `US`; Polymarket International and US have independent identifiers and separate historical calibration.
- **Live-only dashboard:** no settled historical contracts appear in the card feed.
- **Diagnostics:** counts, endpoints, scan-completeness, failures and optional US BBO lookup stats.
- **Original compact three-column market cards:** Kalshi / Polymarket / AN Model, with current probability above fair American odds, expanded outcomes, table view and CSV export.

## Historical accuracy model (separate from live listings)

Historical period begins **March 1, 2025**. Default half-life is **18 months**, giving older observations gradually lower training weight.

To run a **limited, experimental** historical sample locally:

```bash
pip install -r requirements.txt
python backfill_history.py --source kalshi --max-markets 250
python backfill_history.py --source polymarket --max-markets 250
pytest -q
streamlit run streamlit_app.py
```

**This is not a turnkey archive or validated model.** The sampler covers limited resolved binary contracts and the available history endpoints; it can return zero rows if historical snapshots are unavailable. For a production model, build a comprehensive historical ETL with normalized event/outcome IDs, settled outcomes, aligned 7-day/1-day forecasting horizons, liquidity filters, contract-rule checks and time-ordered out-of-sample backtesting. Use matched-event Brier scores and calibrators evaluated on unseen outcomes. In particular, **do not count a model's guessed probability as a historical observation**.

For platform-specific calibration, `history.csv` takes `platform` values `Kalshi`, `Polymarket` and, *if separately backfilled and verified*, `Polymarket US`. **The included sampler does not currently backfill Polymarket US**. Accuracy trained on International data must not be reused as US accuracy.

## Live API references

- [Kalshi Get Events](https://docs.kalshi.com/api-reference/events/get-events)
- [Polymarket International market discovery](https://docs.polymarket.com/market-data/discover-markets)
- [Polymarket US read-only data guide](https://docs.polymarket.us/data-guide/overview)

## Limits and safeguards

- **Live API calls were not verifiable in the artifact-generation environment**. The API parsers are covered by mocked unit tests; inspect live integration on Streamlit.
- An automated event match does **not** prove identical exchange settlement criteria. In production, compare the legal rules for each paired contract and review matches manually/through a certified rules engine.
- A Kalshi trading-volume count is not equivalent to a Polymarket USD traded-volume measure; they aren't combined.
- Polymarket International and US are separate trading venues; US public API fields may differ. Some US listings require BBO requests and unpriced contracts are omitted. The dashboard will show failures in diagnostics rather than silently fabricating a quote.
- The source HTML provided for comparison was used to understand event representation and match-testing requirements, **not as a data source or a dependency**; this application reads the exchanges directly.
- The interface is an independently written research prototype; no competing site's assets, artwork or proprietary source-code bundles are included.
- Before public launch, verify data licensing, market-data redistribution, gambling/financial promotions compliance, model validation and disclosure language with Action Network's appropriate reviewers.
