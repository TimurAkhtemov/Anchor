# Anchor

**A macro-aware personal investment dashboard.** Anchor enforces a single reading
order — **macro environment → sector performance → individual holdings** — where
each tier is read in the context of the one above it. You don't look at a stock's
move in isolation; you read it under its sector, and its sector under the macro
regime.

This is a portfolio project targeting analytics-engineering roles. The deliverable
is the **build** — layered dbt modeling, deliberate design decisions, and honest
treatment of limitations — not just a working chart.

> **Status:** bronze → silver → gold → serve is built, tested, and green (92/92 dbt
> nodes), and **deployed live: [anchor-dashboard.streamlit.app](https://anchor-dashboard.streamlit.app)**.
> The dashboard reads the gold marts through a swappable data seam (live BigQuery
> locally, committed snapshot in the cloud). Orchestration/CI, dynamic portfolio
> ingestion, and multi-asset benchmarking are designed and documented (`docs/`) but
> not yet built.

---

## The core idea

The product's whole premise is that **relationships belong in the data layer, not
the UI**. The dashboard never joins two independent cuts and hopes they line up — a
holding's return is computed *together with* its benchmark's return as a single row;
a sector's rate co-movement is a column on the sector model; the macro regime is a
synthesized artifact. If the framing matters, it lives in gold.

```
FRED API + yfinance
        │  (Python ingestion)
        ▼
  bronze  — raw BigQuery tables (faithful source capture)
        │  dbt
        ▼
  silver  — staging: rename / typecast only
        │
        ▼
   gold   — relationship-framed marts the dashboard reads
        │
        ▼
   serve  — Streamlit, three-tier top-down layout (app/)
```

**dev / prod separation.** Models materialize into a named, layered **prod**
namespace (`anchor_staging` / `anchor_intermediate` / `anchor_marts` / `anchor_seeds`)
via `dbt build --target prod`; local dev runs collapse into a single personal sandbox
schema. The serve layer (and any future scheduled build) reads the stable
`anchor_marts` contract, never a developer sandbox. Routing lives in
`macros/generate_schema_name.sql` (the dbt-fundamentals custom-schema pattern).

---

## Data sources

| Source | Dataset | Contents |
|---|---|---|
| **FRED** | `raw_fred` | 4 macro series: `DFF` (fed funds), `CPIAUCSL` (CPI), `UNRATE` (unemployment), `DGS10` (10-year) |
| **yfinance** | `raw_yfinance` | 14 tickers: 5 sector ETFs (`XLK XLF XLE XLV XLI`) · 3 cap-style ETFs (`SPY MDY IWM`) · 6 holdings (`AAPL JPM HIMS TALO CVLG IMMR`) + 5y daily prices |

The 6 holdings are deliberately spread across cap tiers (large/mid/small) so both
benchmark axes are demonstrable — `AAPL` and `IMMR` are both Technology but opposite
cap tiers, which is the clearest one-glance proof the two-axis design does something.

---

## The dbt model layers

**Staging** (`models/staging/`) — silver. Rename / typecast only, no business logic.
- `stg_fred__series`, `stg_fred__observations`, `stg_yfinance__tickers`, `stg_yfinance__prices`

**Intermediate** (`models/intermediate/`) — shared computation.
- `int_ticker_returns` — per-ticker returns (daily/1m/ytd/1y) to a common as-of date
- `int_macro_indicators` — FRED series normalized to one row per indicator (value, 3mo delta)
- `int_sector_rate_comovement` — each sector ETF's trailing correlation with the 10-year

**Marts** (`models/marts/`) — gold, the served tier.

| Tier | Model | What it produces |
|---|---|---|
| Macro | `macro_indicators` | per-indicator cards: value + delta + direction + source series (traceability) |
| Macro | `macro_trend` | sparkline series (trailing 12mo; inflation as YoY trajectory) |
| Macro | `macro_regime` | one-row regime statement (rates / inflation / labor) |
| Sector | `sector_performance` | sector ETF returns + realized rate co-movement + label |
| Holdings | `holdings_benchmarks` | each holding paired with **both** benchmarks, relative position + label per horizon |
| Shared | `ticker_trend` | sparkline series for every ticker (sectors + holdings) |

---

## The serve layer (`app/`)

A single top-down Streamlit page enforcing the reading order: macro regime + indicator
cards → sector performance → holdings, each tier under the one above it. **Live:
[anchor-dashboard.streamlit.app](https://anchor-dashboard.streamlit.app).**

- **`app/data.py` — the data seam.** The UI calls `data.get_*()` functions and never
  knows the source. Today every read is a cached live query against `anchor_marts`; a
  single `SOURCE` switch + one `_read()` choke point lets the public deploy swap to a
  committed snapshot file with **zero UI edits**. This mirrors the gold contract:
  callers get relationship-framed DataFrames, never raw joins.
- **`app/ui.py` — the visual vocabulary.** Shared palette, chips, status pills, and
  Altair sparklines so the three tiers read as one product (theme in
  `.streamlit/config.toml`).
- **Honest color semantics.** Macro deltas are direction-colored (orange/blue/gray),
  never green/red — macro is context, not performance. Returns and ahead/behind labels
  *are* green/red, because there the judgment is the point.

```bash
streamlit run app/app.py     # reads anchor_marts via the data seam
```

---

## Key design decisions (the "why")

- **Two-axis benchmarking.** Each holding is benchmarked on its **sector** ETF *and*
  its **cap-style** ETF (Large→SPY, Mid→MDY, Small→IWM). A single (sector × cap) ETF
  doesn't exist as a liquid instrument — mid-cap sector ETFs barely trade. *When the
  joint cell doesn't exist, benchmark on the marginals.*
- **Generic benchmark model.** A holding has N benchmarks, each tagged with a
  `benchmark_type`; the comparison is always `holding% − benchmark%`. Adding an axis
  later is a seed row, not a rewrite. The mapping lives in the `benchmark_etfs` seed.
- **Live classification.** `sector` and `market_cap` come straight from yfinance — no
  override dimension to maintain. (Seed keys use Yahoo's taxonomy, not GICS — "Financial
  Services" not "Financials" — verified against live strings; wrong keys silently null-join.)
- **Common as-of date.** Every return is measured to one shared date (`max(trading_date)`)
  so a holding and its benchmark are always compared over the identical window.
- **Defensive against incomplete bars.** yfinance can return a trailing session with
  volume but null OHLC; models filter to the latest *complete* close rather than trust
  the newest bar.
- **Realized co-movement, not hardcoded narratives.** The sector tier shows each sector's
  *measured* recent correlation with rates — not a textbook "tech is rate-sensitive"
  assertion. This surfaced a real divergence (financials moving *against* rates in the
  current window, contra the "banks like higher rates" story), which a hardcoded seed
  would have gotten confidently wrong.
- **Grains and guardrails are tested.** Composite primary keys are asserted; a guardrail
  test fails the build if any holding doesn't resolve to *both* benchmark axes (catching
  seed drift before it silently drops a comparison).
- **Knobs are config, not magic numbers.** The in-line band, regime thresholds,
  co-movement window, and trend windows are all `dbt` vars.

---

## Limitations & honest caveats

Surfacing these is the point — analytical maturity is knowing what your numbers *don't*
say.

- **Single-asset-class today.** Only individual equities are modeled as holdings. Held
  **ETFs and bonds are not handled** — a real portfolio's bulk. Designed in
  `docs/multi_asset_benchmarking.md`; not built.
- **Cap-weighted benchmarks partly benchmark themselves.** Mega-caps are large chunks of
  their own sector ETF (AAPL ≈ 12% of XLK), so "AAPL vs XLK" has some circularity.
- **Cap axis = "vs the cap tier broadly."** "vs IWM" means vs small-caps across all
  sectors, not a size+sector peer set. Intentional (marginals), but not a like-for-like peer.
- **Sector tier shows only the 5 ingested sector ETFs**, not all 11 SPDR sectors —
  broadening is a ticker-config change, not a model change.
- **CPI lag.** Inflation is monthly and released with a lag, so the regime's inflation
  dimension is inherently ~2 months staler than the daily rate series.
- **Co-movement is descriptive and noisy.** It's a trailing correlation over one window,
  not a structural sensitivity or a forecast — and it's regime-dependent.
- **Data freshness rides yfinance.** Free, scraped, no SLA, flaky on the newest bar.
  Designed migration path in `docs/ingestion_roadmap.md`.
- **Ticker is namespace-scoped.** The `ticker` primary key is unique within yfinance's
  single-source US-listed namespace; a multi-exchange future needs `(symbol, MIC)` + a
  surrogate key.

---

## Roadmap

Captured design, deferred build:

- **`docs/ingestion_roadmap.md`** — freshness & source strategy: yfinance for deep
  backfill, a reliable EOD API for the nightly post-close increment; dbt source-freshness
  as a tested contract; incremental loading.
- **`docs/multi_asset_benchmarking.md`** — asset-class-aware benchmarking: held equity
  ETFs (market axis) and bonds (duration/credit axes) absorbed by the same generic
  `benchmark_type` design; the "sector" tier generalizing into an asset-class-specific
  context tier.
- **Dynamic holdings ingestion** (`docs/holdings_ingestion.md`) — a `holdings` bronze
  table from real brokerage data, replacing the static watchlist. Connection path:
  CSV-export first, then **SnapTrade** for a live Fidelity link (read-only; Fidelity GA;
  free personal tier). Deliberate **demo (sample portfolio) vs. real (private)** split so
  the public deploy never shows real financial data. Real holdings force the multi-asset
  work — they ship as one "make it real" milestone.
- **Ops** — **public deploy is live** (Streamlit Community Cloud reads the committed
  snapshot via the `data.py` `SOURCE` switch; `app/export_snapshot.py` regenerates it).
  Remaining: scheduled post-close `ingest → dbt build --target prod → export_snapshot
  → push`, CI (`dbt build` + SQLFluff on PRs), and dbt docs/lineage on GitHub Pages.

---

## Setup & run

**Prerequisites:** Google BigQuery project + service-account key, a `FRED_API_KEY`, the
`anchor` dbt profile, Python venv.

```bash
# 1. Python deps + ingestion (writes bronze tables to BigQuery)
pip install -r ingestion/requirements.txt
python ingestion/ingest_fred.py
python ingestion/ingest_yfinance.py

# 2. dbt packages + build + test
dbt deps
dbt build                  # dev: run + test all models into the personal sandbox
dbt build --target prod    # prod: materialize into the anchor_* datasets

# 3. serve layer (reads anchor_marts)
pip install -r app/requirements.txt
streamlit run app/app.py
```

Useful selectors: `dbt build --select staging`, `dbt build --select marts`,
`dbt show --inline "select * from {{ ref('holdings_benchmarks') }}" --limit 20`.

---

## Tech stack

- **Warehouse:** Google BigQuery (`anchor-495115`)
- **Transformation:** dbt (Fusion 2.0), with `dbt_utils` + `codegen`
- **Ingestion:** Python — FRED REST via `requests`, `yfinance`, `pandas` → BigQuery, python-dotenv
- **Serve:** Streamlit + Altair, reading the marts through a cached data seam

## Repo layout

```
ingestion/    Python bronze-ingestion scripts (FRED, yfinance)
models/
  staging/    silver — rename/typecast
  intermediate/  shared computation
  marts/      gold — the served, relationship-framed tier
macros/       ahead_behind, three_way_state, generate_schema_name (dev/prod routing)
seeds/        benchmark_etfs.csv (the benchmark axis mapping)
tests/        singular guardrail tests
app/          Streamlit serve layer — app.py (page), data.py (seam), ui.py (visuals)
.streamlit/   theme config
docs/         roadmap design docs (ingestion, multi-asset)
```
