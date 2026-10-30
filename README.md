# Update — v1.1: Polymarket visibility and API fallback

The original first screen could look Kalshi-only because unmatched events were sorted together by **non-comparable volume units**, and cross-exchange name matching was strict. This version:

- Alternates Kalshi-only and Polymarket-only cards in the default grid; matched cards come first.
- Adds **Polymarket markets**, **Kalshi markets** and **Matched pairs** coverage filters.
- Shows source-level quote counts, endpoint used, skipped data, and connection/parsing errors.
- Tries Polymarket Gamma `/events` with alternate sorting and a Gamma `/markets` fallback.
- Leaves the AN column blank unless there is a plausible cross-exchange outcome match. Historical calibration remains unvalidated until legitimate historical outcomes are collected.

**Important:** An empty Polymarket column on a *particular Kalshi event* can be correct: that event may have no matching Polymarket contract, or its rules might differ. A zero Polymarket *quote count*, however, indicates an API or parsing problem. Use the new **Live source diagnostics** expander to distinguish them. If Streamlit Cloud is blocked by Polymarket's edge network, code changes cannot guarantee bypassing that restriction; check the reported HTTP error and network access legitimately.

# AN Odds Studio — internal Streamlit prototype

A dark-mode prediction-markets dashboard with **Kalshi | Polymarket | AN Model** columns, plus fair American moneyline prices, categories, search, grid/table views, CSV export and live refresh.

**Status: working code, not yet live-endpoint tested in this build environment.** The build environment had no outbound DNS access to the exchanges, so public API integrations have been coded from their official documentation and verified with mocked unit tests, not against production responses. It is for internal research, not public betting or investment decisions.

## GitHub root files — no folders

`streamlit_app.py`, `requirements.txt`, `core.py`, `feeds.py`, `matching.py`, `model.py`, `backfill_history.py`, `history.csv`, `market_aliases.csv`, `test_core.py`, `README.md`, `.gitignore`.

**Required to run dashboard:** `streamlit_app.py`, `requirements.txt`, `core.py`, `feeds.py`, `matching.py`, `model.py`. Include both CSV files for model/backfill support. The CLI, test, README, and gitignore files are optional but recommended.

## Start locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open the localhost URL Streamlit prints. An internet-enabled machine is required to see live prices. There is no need for API credentials for these public read-only feeds.

## Deploy to Streamlit Community Cloud (you handle GitHub)

1. Upload **all files directly to the repository root**, without adding folders. The dashboard uses CSS for the dark theme so no `.streamlit/` configuration directory is required.
2. Sign in to [share.streamlit.io](https://share.streamlit.io/), select **Create app**, then select your repository, branch, and `streamlit_app.py` as the entrypoint.
3. Deploy and open the app. In the sidebar choose the maximum number of API pages to scan. Start with 3–5 pages and gradually increase. Check the dashboard's **Partial coverage** indicator.
4. Public Streamlit URLs are accessible to others unless restricted. Keep this app private for internal testing; don't confuse a private GitHub repo with authenticated access to the web app.

You can edit and redeploy after testing. No GitHub integration or credentials are built into the app.

## What is truly live?

- **Kalshi:** public read-only `/events` with `with_nested_markets=true`, paginated by cursor; YES bid/ask midpoint where both exist, with last trade fallback.
- **Polymarket:** public read-only Gamma `/events` with nested market outcome prices; paginated by offset.
- **API refresh:** Streamlit cache TTL 120 seconds and manual refresh button. **Not** a continuous real-time WebSocket stream.
- **Coverage:** page-capped, **not** necessarily the entire universe of open markets. Unavailable quotes are omitted. Large all-market crawls should eventually be done in a scheduled backend indexer with proper caching and a database.
- **Market matching:** intentionally conservative. Only market/event titles, outcome definitions and close dates that appear compatible are paired. Since settlement rules can differ, all matched pairs require human review before editorial use. Optional exact event ID overrides can be added to `market_aliases.csv`; this does not replace contract-rule verification.
- **AN column:** only appears for confidently paired outcomes. Unmatched contracts show dashes, not invented synthetic comparisons.

## When does the AN model become historically weighted?

**The shipped `history.csv` intentionally contains ONLY the schema, and NO invented historical observations.** Until authentic settled records are imported, the dashboard computes a **provisional, unvalidated 50/50 blend** of the two prices for matched outcomes. This is NOT a demonstrated accuracy improvement.

An experimental historical backfill CLI is included:

```bash
python backfill_history.py --source kalshi --max-markets 300 --max-pages 8
python backfill_history.py --source polymarket --max-markets 300 --max-pages 8
```

This sampler attempts to retrieve fixed 7-day pre-event historical prices and actual 0/1 resolution outcomes starting in March 2025, through the exchanges' public historical APIs. **It is a sampler, not a full automated historical archive or a validated match audit.** For a serious calibration model, collect substantial coverage, review settlement labels, align equivalent markets and inspect forecasts for look-ahead leakage.

Historical observations are stored in `history.csv` as:

| Field | Meaning |
| --- | --- |
| platform | `Kalshi` or `Polymarket` |
| category | `Sports`, `Politics`, `Entertainment`, etc. |
| event_key | **Identical across platforms only after human-verified same-event matching** |
| observed_at | ISO-8601 time of the past price observation |
| probability | Pre-outcome probability in `(0,1)` |
| outcome | Actual final 0/1 resolution for the *same* outcome |
| horizon | `0-1d`, `2-7d`, `8-30d` or `31d+` |

For automatic matched historical comparison, event keys **must be aligned and resolution rules audited**. Inaccurate event keys will distort the relative reliability weights. In initial collection, different platform naming conventions will often produce unmatched keys, leaving blending at 50/50, which is safer than fabricating comparisons. The historical row count by itself is not evidence of valid cross-platform matches.

The implemented **experimental accuracy engine** uses:

- Historical start: **March 1, 2025**.
- Exponential time-decay weights: **18-month half-life**.
- Source-specific **local calibration corrections** activated only after at least 50 eligible rows and 18 effective weighted observations.
- **Platform reliability weights only when >=50 matched, identically resolved event/outcome historical pairs** are available, and at least 25 recency-weighted observations remain.
- Strong regularization and a maximum 10 percentage-point calibration adjustment.
- Computed fair American moneyline, without sportsbook margin.

### Production readiness before wider AN discussion

1. Perform a complete category audit from March 2025 onward, checking **same market types** and comparable quote horizons.
2. Establish rigorous contract resolution mapping (titles alone are insufficient), complete historical snapshots, liquidity requirements, and outlier exclusions.
3. Run **time-ordered out-of-sample backtests** comparing AN vs. Kalshi, Polymarket and 50/50 mean using Brier and calibration diagnostics.
4. Review Kalshi / Polymarket licensing, attribution, API rate-limit policy and rights to redistribute data publicly.
5. Add a scheduled data indexer and persistent DB for comprehensive market coverage (Streamlit Cloud's local filesystem should not be treated as persistent).
6. Have AN editorial, legal/compliance and engineering approve any public presentation. Avoid claiming model accuracy that hasn't been demonstrated.

## Tests

```bash
pytest -q
```

## API documentation

- [Kalshi Events](https://docs.kalshi.com/api-reference/events/get-events)
- [Kalshi Markets](https://docs.kalshi.com/api-reference/market/get-markets)
- [Kalshi Historical Candlesticks](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks)
- [Polymarket Market Data](https://docs.polymarket.com/)

## Important technical caveats

- Exchange prices are not guaranteed to be executable trades; feed data may lag or be thinly traded.
- Source volume fields have **different units**: Kalshi uses contract counts, Polymarket frequently USD. The app's *combined reported volume* is only a rough sorting heuristic and **must not be interpreted as dollars or cited**. Consider replacing with comparable normalized liquidity in production.
- Kalshi and Polymarket contract titles and settlements may diverge. Conservative matching favors avoiding errors rather than maximizing pair count.
- Binary probabilities for separate, mutually exclusive outcomes may not sum to exactly 100% due to bid/ask, spreads and missing outcomes. Do **not** automatically normalize or present those as a coherent outright market until contract grouping is verified.
- Event/market API field names can change. If a platform changes a schema, update `feeds.py` accordingly.
