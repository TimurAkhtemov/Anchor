# Anchor — Session Handoff

_Last updated: 2026-06-11. The **`README.md` is now the canonical project doc** —
architecture, model map, design decisions, limitations, roadmap. Read it first.
This file is just the lean "current state + what's next" pointer. Also see
`CLAUDE.md` (working style) and `docs/` (deferred roadmaps)._

## State of the world

**Bronze → silver → gold is complete, tested, and green — `dbt build` = 92/92.**
The full `macro → sector → holdings` spine is built and verified against real data.

Gold marts (all in `models/marts/`):
- **Macro:** `macro_indicators` (cards), `macro_trend` (sparklines), `macro_regime` (regime banner)
- **Sector:** `sector_performance` (+ `int_sector_rate_comovement`)
- **Holdings:** `holdings_benchmarks` (two-axis, the load-bearing one)
- **Shared:** `ticker_trend`, `int_ticker_returns`, `int_macro_indicators`

Bronze→silver was already live (FRED 4 series / 44,979 obs; yfinance 14 tickers /
17,570 bars) and remains green. Models build into dev schema `dbt_timurakhtemov`.

## IMMEDIATE next step — Streamlit serve layer (v1)

The dbt layer is done for v1; this is where to pick up. **The approach is already
agreed — don't re-litigate, just scaffold:**

- **Layout:** single top-down page enforcing the reading order — macro cards + regime
  banner on top, sectors (with co-movement) in the middle, holdings (two-axis,
  ahead/behind) at the bottom. Build **all three tiers**, skeleton → fill. Sparklines
  from `macro_trend` / `ticker_trend`.
- **Data access:** local dev = query the BigQuery marts directly
  (`google-cloud-bigquery` + the SA key), cached with `@st.cache_data`. For the eventual
  **public deploy**, snapshot the marts to a small committed file (parquet/DuckDB) so the
  demo needs no live BQ creds and stays free. Defer the snapshot until the deploy step.
- **Charting:** Altair (control over sparklines + ahead/behind color encoding).
- **Demo data:** the current 6-stock watchlist *is* the demo portfolio for now.
- **Setup:** add `streamlit` (+ `altair`) to deps; cached BQ connection; stub the
  three-tier page; then fill each tier.

## Strategic direction (agreed) — two capstones make it "a living data product"

The dbt+dashboard is functionally complete but reads as *modeling-only*; the value is
turning it into a running product. After Streamlit:

1. **Ops capstone:** deploy live (Streamlit Community Cloud) → orchestrate/schedule
   (GitHub Actions or Dagster/Prefect: ingest → dbt build, post-close) → CI on PRs
   (`dbt build` + SQLFluff) → data-quality (dbt source-freshness; maybe Elementary)
   → dbt docs/lineage on GitHub Pages.
2. **"Make it real" capstone:** dynamic holdings (real portfolio) → multi-asset. These
   are **coupled** — real holdings contain ETFs/bonds/cash, which force the multi-asset
   work and the `cap_tier` null→'Small' fix.

Cheap, high-impact wins first: **live deploy, dbt docs, CI**.

## Roadmap docs (designed, not built)

- `docs/holdings_ingestion.md` — **Fidelity connection: SnapTrade is the viable path**
  (GA, read-only, free personal tier); CSV-export as v1; demo-vs-real split; `holdings`
  bronze schema reserving `asset_class`/`quote_type`.
- `docs/multi_asset_benchmarking.md` — held ETFs + bonds (asset-class-aware axes); same
  generic `benchmark_type` design absorbs them.
- `docs/ingestion_roadmap.md` — price-data freshness/source strategy (EOD API,
  post-close schedule, incremental, source-freshness tests).

## Open items / things to watch

- **Caveats are catalogued in the README "Limitations" section** — don't re-derive them.
  Key live ones: single-asset-class (no held ETFs/bonds yet), CPI lag in the regime,
  sector tier = only the 5 ingested ETFs, co-movement is descriptive/noisy, yfinance
  freshness, namespace-scoped ticker key.
- **yfinance trailing-bar gotcha is handled** (models filter null-OHLC bars), but it
  recurs each pull — the durable fix lives in `docs/ingestion_roadmap.md`.
- Ingestion is `WRITE_TRUNCATE` full-refresh; incremental is future work.
- `dbt-fusion 2.0 preview` emits harmless warnings (deferral manifest 404, package
  project-file warnings); not errors.

## How to work on this project

See `CLAUDE.md` "Working style": Socratic (surface decisions, user decides), verify
against real data before baking values in, explain the "why" concisely, honest about
caveats, move fast on boilerplate. The user is learning AE as we build and holds the
wheel on design calls.
