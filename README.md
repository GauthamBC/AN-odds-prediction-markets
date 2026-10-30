# AN Odds Studio — v1.2 (compact Markets Dashboard)

An internal, **read-only Streamlit dashboard** for open Kalshi and active Polymarket prediction markets, plus an **experimental** Action Network blended probability where compatible contracts are automatically matched.

## What changed in v1.2

- Replaced the tall Streamlit metrics-and-filter layout with a compact, three-column market grid inspired by the supplied reference screenshot. The visual is inspired by the layout, not a copy of any third-party branding.
- Search bar, exchange selection (All, Kalshi, Polymarket, Matched), grid/table switch and **category pills** sit directly above the cards.
- Each card has a category icon, event name, close date when available, two leading outcomes, **Kalshi / Polymarket / AN MODEL** columns, and an expandable list of remaining outcomes.
- Percentage **and fair American moneyline** appear inside each populated column. This moneyline is merely a mathematical conversion, not an available sportsbook price.
- Displays simple Kalshi and Polymarket data-source panels rather than promotional offers or codes.
- Moved source diagnostics, methodology, export and model caveats below the results. Pagination appears **below** the cards.
- Still shows only current active markets on the dashboard, **not historical settled markets**.

## Upload to GitHub / Streamlit

All files are flat in the repository root. Upload the 12 files as-is:

`streamlit_app.py`, `requirements.txt`, `core.py`, `feeds.py`, `matching.py`, `model.py`, `backfill_history.py`, `history.csv`, `market_aliases.csv`, `test_core.py`, `README.md`, `.gitignore`

Deploy from [Streamlit Community Cloud](https://share.streamlit.io/) with main file `streamlit_app.py`.

Or run locally:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Public Streamlit URLs may be accessible to anyone. Use an authenticated deployment or restrict access for confidential internal evaluations.

## Are these current or historical markets?

**The main dashboard uses only live/open listings**:

- Kalshi `GET /events?status=open&with_nested_markets=true`.
- Polymarket Gamma `GET /events?active=true&closed=false` (falling back to `/markets` when necessary).

The feeds are **snapshots refreshed every 120 seconds** (or when manually refreshed), not a tick-by-tick WebSocket stream. The interface is **page-capped**; its market count means "active events scanned," not a complete count of everything available on either exchange. Unquoted contracts may be excluded. Increase `API pages per platform` in the left sidebar to expand coverage, subject to rate limits and speed.

**Historical resolved markets are separate:** `history.csv` intentionally has no invented observations. The file would store historical pre-resolution quotes with real outcomes, starting March 1, 2025, for model calibration. `backfill_history.py` is a basic **manual sampling script**, not an automatic, verified ingestion pipeline. Running this Streamlit app does **not** automatically collect all historical markets or train the model.

Historical records must be verified, deduplicated, aligned at comparable forecast horizons, and paired by equivalent outcomes and settlement rules. The main dashboard should remain active-market-only even after training data is supplied.

## How does AN Model work today?

It shows **a provisional, unvalidated 50/50 blend** when the same event/outcome is plausibly matched across Kalshi and Polymarket. It does not display a synthetic AN price for unmatched single-source markets. The reason many cells can still be blank is not necessarily a feed failure: only a small percentage of independently listed contracts can be matched with sufficient certainty from titles/outcome labels/dates.

Historical model code in `model.py` supports March 2025 onward with an 18-month decay half-life and experimental category-specific calibration using real resolved outcomes once imported. **Do not claim AN is more accurate** until time-ordered held-out backtests demonstrate improvements over Kalshi, Polymarket, and a simple average. Automated text matching is not a contract-rule audit.

## Data and trading caveats

- Kalshi bid/ask midpoints (or last-trade fallback) and Polymarket's Gamma outcome prices are indicative. They can differ from executable quotes.
- Contract settlement rules, void policies and cutoff times may differ even when titles match.
- Source volume metrics have **different units:** Kalshi volume is typically contracts, and Polymarket volume is typically USD. We do not sum those together as a combined dollar figure.
- A 0.2% probability can mathematically imply a very large positive American moneyline; this is **not** a sportsbook offer.
- Check applicable exchange API terms, licensing and data-display permissions before publishing the dashboard commercially.

## Tests

```bash
pytest -q
```

API references: [Kalshi Events](https://docs.kalshi.com/api-reference/events/get-events) · [Polymarket Gamma](https://docs.polymarket.com/)
