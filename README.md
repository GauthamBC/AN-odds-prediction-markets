# AN Odds Studio v2.0 — manual-refresh Digital PR market intelligence

A GitHub-root / Streamlit Cloud prototype. **All files are flat**; no subdirectories are required. Built on The Prediction Markets API (TPM) **public v1** rather than bespoke Kalshi–Polymarket fuzzy matching.

## Deploy (GitHub + Streamlit Cloud)

1. Upload all project files into the root of your existing GitHub repository. **Do not overwrite your populated `history.csv` with the empty template** if you've already collected historical observations.
2. In Streamlit Community Cloud, choose that repository and set the app's entry point to **`streamlit_app.py`**.
3. Open your app's **Settings → Secrets**. Paste this TOML, replacing placeholders with your own values:

```toml
TPM_API_KEY = "paste-your-thepredictionmarkets-api-key-here"
ADMIN_REFRESH_PASSWORD = "choose-a-private-admin-password"
```

**Never put real secrets in a GitHub file, send them in chat, or commit `.streamlit/secrets.toml`.** The app transmits `TPM_API_KEY` only in the server-side `X-API-Key` header when you explicitly refresh, request outcomes, or check quota.

4. Save the secrets and restart/reboot the app if needed.
5. Open the Streamlit left sidebar, enter the admin password, and press **Refresh all active markets** once. The app retrieves the complete catalogue using cursor pagination and enriches up to **150** high-interest event details for side-by-side display. With only the key configured and no admin password, refreshing remains available to everyone and the app warns you.
6. Use **USA / Canada / Global**, category filters and search to browse cached markets at **zero additional API requests**. Click **Explore** or **View all outcomes** to retrieve a particular event's full outcome set once and cache it until the next manual refresh.

## What you'll see

- **Top 5 trending markets** per selected region/category, ranked by TPM-reported *24-hour USD trading volume* (not number of transactions).
- **Biggest probability movers**, from provider-supplied `leading_outcome.change_24h`, when present.
- **Biggest Kalshi–Polymarket disagreements**, derived from API match-group IDs and prefetched details. These are comparisons, not guaranteed identical contracts or arbitrage opportunities.
- **All active markets**, search/pagination, compact cards, provider price columns where details have been retrieved, on-demand full outcomes and illustrative American moneylines.
- **AN Model**: historical data/recency calibration framework is preserved in `model.py` and `history.csv`, but until sufficient validated observations have been collected it shows a **clearly labeled indicative 50/50 blend**. Missing or stale quotes are **never** replaced with fake values. Rules not verified are labeled.
- **Usage checker**, manually invoked under admin settings. `/rate-limit` reports monthly quota.

## API behavior and costs

- On a catalogue refresh: `GET /events?status=trading&limit=200` with cursor until *all pages* are fetched; then `GET /events/{slug}?max_outcomes=12` for a selected diversified set of up to 150 popular events. No arbitrary 500/1,000-market truncation. Any interrupted catalogue scan keeps the previous saved snapshot.
- When a person chooses to expand a particular event: `GET /events/{slug}` for complete outcomes; the result is stored. Reopening the same event uses the stored result.
- Opening, searching, switching region/category, pagination, charting, recalculating AN values and changing view settings **do not trigger external API requests**.
- Refresh uses the user's real key's quota, so the request cost is **number of API pages + prefetched details + any retries**. You can inspect count in the sidebar. No unattended background polling.
- The catalogue summary provides **only a featured outcome and a single displayed probability**. Separate Kalshi and Polymarket prices require event-detail data. The dashboard does not invent two source quotes from one summary value.
- Official API docs: https://thepredictionmarkets.com/api/docs/reference and https://thepredictionmarkets.com/api/docs/reference/event-detail

## Geography and limitations

- USA / Canada / Global filters represent **the event's subject matter**, based on a transparent keyword classifier in `region_rules.py`. They are *not* a count of traders in those countries. Some topics can be relevant to multiple regions. Tune with verified team/city lists over time.
- TPM's published API documents two venues, **Kalshi and Polymarket International**. **Polymarket US is not guaranteed** by this provider; don't assume identical PredictionPro coverage.
- A quote may be `stale` or `unknown`: those quotes are withheld from AN blends. `comparison: comparable` and `contract_compatibility: unverified` aren't audited settlement-rule equivalence. Interpret indicative blends accordingly.
- **Local SQLite is ephemeral on Streamlit Cloud.** It survives reruns while the container exists, but can disappear on app restart/redeploy. If you need historical snapshots preserved and shared continuously, migrate `snapshot_store.py` to a hosted database such as Supabase/Postgres; do not rely on Streamlit cache as durable cloud storage.
- Validate commercial re-display/attribution terms with the provider before an official public AN launch.
- **No live exchange-integration test** was possible in the build environment; Python unit tests verify data parsing, cursor pagination, grouping, freshness restrictions and snapshot preservation with representative API fixtures.

## Run locally

```bash
pip install -r requirements.txt
# Create a LOCAL .streamlit/secrets.toml with TPM_API_KEY (never commit it)
streamlit run streamlit_app.py
```

## Tests

```bash
python -m unittest -v test_tpm.py
```

## How the historical model could be trained

The previous `model.py` remains available, with an 18-month exponential half-life and history starting 2025-03-01. Populate `history.csv` **only with audited, timestamped, settled events and comparable contract outcomes**. Evaluate with time-split out-of-sample Brier scores before describing AN odds as historically superior. `history.csv` must not be populated using the current API's latest prices and future outcomes (that would leak information).
