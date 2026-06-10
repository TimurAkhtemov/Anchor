# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Anchor is a macro-aware personal investment dashboard. The core product principle is a forced reading order: **macro environment → sector performance → individual holdings**. Each tier is read in the context of the one above it.

Architecture: `FRED API + yfinance → bronze (BigQuery raw tables) → silver (dbt staging) → gold (dbt relationship-framed models) → serve (Streamlit)`

This is a portfolio project targeting analytics engineering roles — demonstrating the full AE arc, not just pipeline plumbing.

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

# dbt
dbt run                          # build all models
dbt run --select staging         # staging models only
dbt run --select marts           # gold/mart models only
dbt test                         # run all tests
dbt test --select stg_fred__observations  # single model tests
dbt build                        # run + test together
```

## Data sources

**FRED** (`raw_fred` dataset in BigQuery):
- `raw_fred_series` — metadata for 4 series: `DFF`, `CPIAUCSL`, `UNRATE`, `DGS10`
- `raw_fred_observations` — long-format time series (series_id, date, value)

**yfinance** (`raw_yfinance` dataset in BigQuery):
- `raw_yfinance_tickers` — metadata for 13 tickers (includes `market_cap`, used to bucket holdings into cap tiers)
- `raw_yfinance_prices` — daily OHLCV bars (long format, one row per ticker/date)
- Tickers = sector ETFs `XLK, XLF, XLE, XLV, XLI` + cap-style ETFs `SPY, MDY, IWM` + holdings `AAPL, JPM, XOM, UNH, BA`

## dbt model layers

**Staging** (`models/staging/`) — silver layer. Rename/typecast only. No business logic.
- `stg_fred__series`, `stg_fred__observations`
- `stg_yfinance__tickers`, `stg_yfinance__prices`

**Gold / marts** (`models/marts/`) — relationship-framed outputs the dashboard reads. *Not yet built.*
- Must produce: macro indicators with current value + delta + sparkline series
- Must produce: sector ETF performance contextualized against macro regime
- Must produce: holding % change paired with its sector's % change as a single output (not two independent cuts the UI joins)

## Benchmarking design (two-axis)

Each holding is benchmarked on **two independent axes**, each against a liquid ETF:
- **Sector axis** — holding vs its SPDR sector ETF (XLK, XLF, …)
- **Cap-style axis** — holding vs its market-cap tier: Large (>$10B)→SPY, Mid ($2–10B)→MDY, Small (<$2B)→IWM

Why two axes rather than one (sector × cap) ETF: that grid can't be filled with liquid instruments (mid-cap sector ETFs barely exist; small-cap sector ETFs trade ~1.5k shares/day). When the joint cell doesn't exist, benchmark on the marginals.

**Generic benchmark model:** a holding has N benchmarks, each an ETF tagged with `benchmark_type` (`sector`, `cap_style`). The comparison is always `holding% − benchmark%`, computed per benchmark. Adding an axis later is a seed row, not a rewrite. The mapping lives in the `benchmark_etfs` seed (`seeds/benchmark_etfs.csv`): `benchmark_type, lookup_key, etf_ticker, etf_name`.

**Classification is live from yfinance** — `sector` and `market_cap` come straight from the yfinance `info` fields; no override dimension.

⚠️ **yfinance uses Yahoo's sector taxonomy, not GICS names.** The seed's `lookup_key` must match the exact strings yfinance emits or the join silently returns null. Verified strings: `Technology, Financial Services, Healthcare, Energy, Industrials, Communication Services, Consumer Cyclical, Consumer Defensive, Utilities, Real Estate, Basic Materials`.

## Key modeling constraint

Holding % and benchmark % must be computed together in gold so each pairing is a single model output. The dashboard never joins two independent datasets — that framing belongs in gold. The `ahead/behind/in-line` label (sign of holding% − benchmark%, against a threshold band) is computed here too.

## Long-term direction

The static watchlist is a proof-of-concept. The intended future state is dynamic portfolio ingestion from Robinhood/Fidelity — feeding a `holdings` bronze table (ticker, quantity, cost basis, sector) that the gold layer joins against. The long-format bronze design and config-driven ticker list are intentionally built to make this a config swap, not a rewrite.
