# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Anchor is a macro-aware personal investment dashboard. The core product principle is a forced reading order: **macro environment → sector performance → individual holdings**. Each tier is read in the context of the one above it.

Architecture: `FRED API + yfinance → bronze (BigQuery raw tables) → silver (dbt staging) → gold (dbt relationship-framed models) → serve (Streamlit)`

This is a portfolio project targeting analytics engineering roles — demonstrating the full AE arc, not just pipeline plumbing.

## Working style (how to collaborate on this project)

The user is learning analytics engineering as we build, and wants to hold the wheel. Match this style:

- **Socratic, not autopilot.** On real decisions (modeling, benchmarks, materialization, what belongs in gold vs. the UI), surface the choice, explain the tradeoff in a sentence or two, and let the user decide. Build autonomously only on boilerplate (rename/typecast staging, YAML tests, mechanical edits).
- **Verify against real data before baking it in.** When a value will be hardcoded into a model, seed, or join key, check it against the actual source first (e.g. query BigQuery, probe yfinance) rather than asserting from memory. Several traps this session were caught this way (yfinance uses Yahoo's sector taxonomy, not GICS; mid-cap sector ETFs don't exist; example holdings were all large-cap).
- **Explain the "why," concisely.** One line on the reasoning behind a decision, not a lecture. Name the general principle when there is one ("when the joint cell doesn't exist, benchmark on the marginals").
- **Be honest about caveats and limitations** — flag them as analytical maturity, not hide them. Don't over-claim "done": if something was built but not yet run/verified, say so explicitly.
- **Move fast, keep momentum.** Don't pad. Pause at clean, committable chunks.

## Infrastructure

- **Data warehouse**: Google BigQuery (`anchor-495115`)
- **Credentials**: Service account key at `~/.dbt/anchor-bigquery-key.json`
- **dbt profile**: `anchor` (configured in `~/.dbt/profiles.yml`)
- **Environment variables**: `FRED_API_KEY` in `.env` (loaded via python-dotenv)

## Common commands

```bash
# Run ingestion (from repo root, with venv active)
python ingestion/ingest_fred.py
python ingestion/ingest_yfinance.py

# dbt — cd into transformation/ first (the dbt project dir). Local engine = dbt-fusion
# (~/.local/bin/dbt); CI uses dbt-core 1.11. Run from the project dir, NOT via
# --project-dir: fusion mishandles seed paths under --project-dir.
cd transformation
dbt run                          # build all models
dbt run --select staging         # staging models only
dbt run --select marts           # gold/mart models only
dbt test                         # run all tests
dbt build                        # run + test together (dev sandbox)
dbt build --target prod          # materialize the prod datasets (anchor_*)

# Serve layer (Streamlit dashboard, reads anchor_marts via the data seam)
streamlit run app/app.py
python app/export_snapshot.py    # refresh the committed snapshot the live demo reads

# Pipeline steps (tool-agnostic; the Makefile is what Dagster will wrap as assets)
make ingest | make build-prod | make snapshot | make refresh
```

Note: `make snapshot`/`make refresh` may need
`GOOGLE_APPLICATION_CREDENTIALS=~/.dbt/anchor-bigquery-key.json` for `app/export_snapshot.py`
unless Application Default Credentials are configured.

Live: dashboard → anchor-dashboard.streamlit.app · dbt docs → timurakhtemov.github.io/Anchor

## Data sources

**FRED** (`raw_fred` dataset in BigQuery):
- `raw_fred_series` — metadata for 4 series: `DFF`, `CPIAUCSL`, `UNRATE`, `DGS10`
- `raw_fred_observations` — long-format time series (series_id, date, value)

**yfinance** (`raw_yfinance` dataset in BigQuery):
- `raw_yfinance_tickers` — metadata for 14 tickers (includes `market_cap`, used to bucket holdings into cap tiers)
- `raw_yfinance_prices` — daily OHLCV bars (long format, one row per ticker/date)
- Tickers = sector ETFs `XLK, XLF, XLE, XLV, XLI` + cap-style ETFs `SPY, MDY, IWM` + holdings `AAPL, JPM, HIMS, TALO, CVLG, IMMR`

## dbt model layers

_The dbt project lives in `transformation/`; the paths below are relative to it._

**Staging** (`models/staging/`) — silver layer. Rename/typecast only. No business logic.
- `stg_fred__series`, `stg_fred__observations`
- `stg_yfinance__tickers`, `stg_yfinance__prices` (`prices` is incremental in prod)

**Snapshot** (`snapshots/`) — history-preserving metadata.
- `snap_yfinance_tickers` — SCD2/check snapshot for ticker metadata changes; prod writes to `anchor_snapshots`.

**Gold / marts** (`models/marts/`) — relationship-framed outputs the dashboard reads. **Built, tested, deployed.**
- `macro_indicators` (cards) + `macro_trend` (sparklines) + `macro_regime` (regime banner)
- `sector_performance` — sector ETF performance contextualized against the macro regime
- `holdings_benchmarks` — holding % paired with each benchmark % as one row (not two cuts the UI joins)
- `ticker_trend` — sparkline series for every ticker

**Lineage / contracts.**
- `models/marts/_exposures.yml` declares the Streamlit dashboard and parquet snapshot export as downstream consumers of the six served marts.
- `holdings_benchmarks` has an enforced dbt contract; if its output columns/types drift, dbt should fail before the app silently breaks.

## Benchmarking design (two-axis)

Each holding is benchmarked on **two independent axes**, each against a liquid ETF:
- **Sector axis** — holding vs its SPDR sector ETF (XLK, XLF, …)
- **Cap-style axis** — holding vs its market-cap tier: Large (>$10B)→SPY, Mid ($2–10B)→MDY, Small (<$2B)→IWM

Why two axes rather than one (sector × cap) ETF: that grid can't be filled with liquid instruments (mid-cap sector ETFs barely exist; small-cap sector ETFs trade ~1.5k shares/day). When the joint cell doesn't exist, benchmark on the marginals.

**Generic benchmark model:** a holding has N benchmarks, each an ETF tagged with `benchmark_type` (`sector`, `cap_style`). The comparison is always `holding% − benchmark%`, computed per benchmark. Adding an axis later is a seed row, not a rewrite. The mapping lives in the `benchmark_etfs` seed (`transformation/seeds/benchmark_etfs.csv`): `benchmark_type, lookup_key, etf_ticker, etf_name`.

**Classification is live from yfinance** — `sector` and `market_cap` come straight from the yfinance `info` fields; no override dimension.

⚠️ **yfinance uses Yahoo's sector taxonomy, not GICS names.** The seed's `lookup_key` must match the exact strings yfinance emits or the join silently returns null. Verified strings: `Technology, Financial Services, Healthcare, Energy, Industrials, Communication Services, Consumer Cyclical, Consumer Defensive, Utilities, Real Estate, Basic Materials`.

## Key modeling constraint

Holding % and benchmark % must be computed together in gold so each pairing is a single model output. The dashboard never joins two independent datasets — that framing belongs in gold. The `ahead/behind/in-line` label (sign of holding% − benchmark%, against a threshold band) is computed here too.

## Long-term direction

The static watchlist is a proof-of-concept. The intended future state is dynamic portfolio ingestion from Robinhood/Fidelity — feeding a `holdings` bronze table (ticker, quantity, cost basis, sector) that the gold layer joins against. The long-format bronze design and config-driven ticker list are intentionally built to make this a config swap, not a rewrite.
