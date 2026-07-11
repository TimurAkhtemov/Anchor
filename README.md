# Anchor

**A macro-aware personal investment dashboard.** Anchor enforces a single reading
order — **macro environment → sector performance → individual holdings** — where
each tier is read in the context of the one above it. You don't look at a stock's
move in isolation; you read it under its sector, and its sector under the macro
regime.

This is a portfolio project targeting analytics-engineering roles. The deliverable
is the **build** — layered dbt modeling, deliberate design decisions, and honest
treatment of limitations — not just a working chart.

> **Status:** bronze → silver → gold → serve is built, tested, and green (140/140 dbt
> nodes), and **deployed live: [anchor-dashboard.streamlit.app](https://anchor-dashboard.streamlit.app)**.
> Holdings are now **dynamic** — a real portfolio (SnapTrade live pull or Fidelity CSV
> export) replaces the static 6-stock watchlist, sized by actual position weights and
> benchmarked **per asset class** across five axes. A strict demo/private split (separate
> BigQuery datasets, compile-time enforced) means the public deploy only ever sees a
> committed sample portfolio. The dashboard reads the gold marts through a swappable data
> seam (live BigQuery locally, committed snapshot in the cloud). **CI** (dbt build + tests
> on every PR), **dbt docs/lineage**, and **orchestration** (a Dagster `dagster-dbt` asset
> graph, `orchestration/`) are built. Full design + honest caveats:
> `docs/make_it_real_design.md`.

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
`transformation/macros/generate_schema_name.sql` (the dbt-fundamentals custom-schema pattern).

**demo / real separation.** A second dimension, orthogonal to dev/prod: the `holdings_source`
var (`demo` default, `real` opt-in) picks which holdings world `stg_holdings__positions`
reads, and a `prod-private` target routes real-world builds into a fully separate
`anchor_*_private` dataset family (`make build-private`). A compile-time macro assertion
(`assert_portfolio_isolation`, an `on-run-start` hook) fails the build outright if
`holdings_source: real` is ever combined with a public target (`prod`/`ci`) — the public
contract structurally cannot be built from real data, not even by mistake.

---

## Data sources

| Source | Dataset | Contents |
|---|---|---|
| **FRED** | `raw_fred` | 4 macro series: `DFF` (fed funds), `CPIAUCSL` (CPI), `UNRATE` (unemployment), `DGS10` (10-year) |
| **yfinance** | `raw_yfinance` | ~44-ticker **dynamic** universe (held tickers ∪ all 11 SPDR sector ETFs ∪ cap-style/market/bond-market/duration benchmark ETFs) + 5y daily prices. The universe is *derived* from holdings each run, not a hardcoded ticker list |
| **Holdings** | `raw_holdings` | `holdings_demo` (committed sample portfolio, appended with an `as_of` batch date) / `holdings_real` (private, gitignored — SnapTrade live pull or Fidelity CSV export) · `fund_classifications_real` (private fund → asset-class override mapping) |

The committed demo portfolio is deliberately built to exercise every routing branch —
individual stocks across cap tiers (both equity axes), an equity ETF, a bond ETF and bond
mutual fund (bond-market + duration axes), a held-SPY root position, and cash — so the
two-axis *and* five-axis benchmarking design is demonstrable end to end without real
financial data.

---

## The dbt model layers

_Paths below are relative to `transformation/`, the dbt project root._

**Staging** (`models/staging/`) — silver. Rename / typecast only, no business logic.
- `stg_fred__series`, `stg_fred__observations`, `stg_yfinance__tickers`, `stg_yfinance__prices`
- `stg_holdings__positions` — demo/real positions, deduped to the latest `as_of` per (account, ticker); world selected by the `holdings_source` var
- `stg_holdings__fund_classifications` — unions the committed demo seed with the private real-fund CSV (staging is the only place the two worlds merge)

**Intermediate** (`models/intermediate/`) — shared computation.
- `int_ticker_returns` — per-ticker returns (daily/1m/ytd/1y) to a common as-of date, anchored to the benchmark-ETF trading calendar
- `int_macro_indicators` — FRED series normalized to one row per indicator (value, 3mo delta)
- `int_sector_rate_comovement` — each sector ETF's trailing correlation with the 10-year
- `int_holdings_classified` — one valued row per held ticker: `asset_class` (override mapping wins over quote_type-derived fallback), `cap_tier` (equities only), dual-source `valuation_source` (market vs. source-valued)
- `int_benchmark_routing` — resolves each holding to its N benchmarks per asset class, flags self-pairings (roots)

**Marts** (`models/marts/`) — gold, the served tier.

| Tier | Model | What it produces |
|---|---|---|
| Macro | `macro_indicators` | per-indicator cards: value + delta + direction + source series (traceability) |
| Macro | `macro_trend` | sparkline series (trailing 12mo; inflation as YoY trajectory) |
| Macro | `macro_regime` | one-row regime statement (rates / inflation / labor) |
| Sector | `sector_performance` | all 11 SPDR sector ETFs' returns + realized rate co-movement + label |
| Holdings | `portfolio_composition` | one row per held ticker (incl. cash + roots): weight, market value, unrealized gain, valuation source — the sizing mart |
| Holdings | `holdings_benchmarks` | each holding paired with its asset-class-appropriate benchmark set, relative position + label per horizon |
| Shared | `ticker_trend` | sparkline series for every ticker (scoped to the active world's universe) |

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
- **Composition-driven holdings tier.** The UI iterates `portfolio_composition`
  (grouped by asset class: equities → fixed income → commodity/alt → cash) and
  attaches each ticker's `holdings_benchmarks` rows by join — master-detail on one
  entity, not a relationship recomputed in the UI. An allocation bar heads the tier;
  roots get a "market root" badge; asset classes with no v1 benchmark axis (commodity,
  alt) render with an explicit "not benchmarked" line instead of an empty comparison.
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
- **Asset-class-aware routing (5 classes × 5 axes).** Real holdings are equities,
  equity/bond funds, cash, commodities, and alts — one generic benchmark model absorbs
  all of them by routing on `asset_class` instead of hardcoding "stock" logic.
  Commodity and alt holdings intentionally route to zero axes in v1 (display-only,
  guardrail-tested) rather than a forced, meaningless comparison. Full design:
  `docs/make_it_real_design.md`.
- **Root rule.** A holding whose only routed benchmark is itself (held SPY on the
  market axis) suppresses that self-pairing — holding-vs-itself is 0 by construction,
  so it displays as the reference point instead of a trivial row. VOO-vs-SPY *isn't*
  suppressed (different tickers) — tracking difference is a real comparison.
- **Structural privacy, not a WHERE clause.** Demo and real portfolios build into
  physically separate BigQuery dataset families (`anchor_*` vs `anchor_*_private`); a
  compile-time hook refuses to build a public target from real data. The public deploy
  cannot leak real holdings even by mistake — the guarantee is architectural.
- **Live classification for stocks, maintained override for funds.** `sector` and
  `market_cap` come straight from yfinance for individual equities — no override needed.
  (Seed keys use Yahoo's taxonomy, not GICS — "Financial Services" not "Financials" —
  verified against live strings; wrong keys silently null-join.) Funds are different:
  yfinance's `category` field is `None` for Fidelity mutual funds, so an equity fund and
  a bond fund are metadata-indistinguishable — `asset_class`/`sub_style` for funds come
  from a maintained mapping (a true *override*, checked before quote_type-derived
  fallback), with a guardrail test failing the build on any unclassified held fund.
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
  test fails the build if any holding doesn't resolve to the number of benchmark axes its
  asset class prescribes (catching seed drift before it silently drops a comparison), and
  a second guardrail fails the build if any non-cash/alt holding is valued from the import
  instead of live prices (catching a transiently unpriced instrument before it goes stale).
- **Knobs are config, not magic numbers.** The in-line band, regime thresholds,
  co-movement window, and trend windows are all `dbt` vars.

---

## Product principles

Anchor is a **portfolio-understanding** product, not a market-monitoring or
trade-execution product. Its job is to help people understand what they own, how the
pieces fit together, and whether the portfolio still reflects their intent. The product
should be fresh enough to trust, but slow enough to think.

- **Settled context over live stimulation.** Daily completed closes are the operating
  cadence. Intraday prices, flashing tickers, market movers, and 1D/1W performance views
  are deliberately out of scope; 1M is the shortest primary return horizon.
- **Zoom out before zooming in.** The reading order remains macro → sectors → holdings.
  Allocation and appropriate benchmark context are more important than an isolated gain.
- **Explain, do not provoke.** News and AI may clarify what happened, uncertainty, and
  relevant context; they must not predict prices or issue buy/sell recommendations.
- **Reflection over reaction.** Alerts belong to stale data, material portfolio drift, or
  a scheduled review—not ordinary price movement. Future interaction should support
  theses, target allocations, review dates, and explicit invalidation criteria.
- **Calm, honest presentation.** Every number carries an as-of date, missing data remains
  visibly missing, and restrained color avoids turning gains and losses into the page's
  emotional center.

Feature test: **does this help someone understand their portfolio, or help them react
faster to market movement?** If the principal benefit is faster reaction, it does not
belong in Anchor.

---

## Limitations & honest caveats

Surfacing these is the point — analytical maturity is knowing what your numbers *don't*
say.

- **Quantities are as-of the last import; prices are daily.** Market value recomputes
  daily (`quantity × latest_close`) but the quantity itself only refreshes on the next
  holdings pull — between imports, value mixes a fresh price with a stale share count.
  Mitigated by SnapTrade re-pulls (a manual `ingest-holdings-real` run away, not yet
  scheduled); not solved until pulls are automated.
- **CSV real-import path is unvalidated.** SnapTrade became the primary real-data
  transport; the CSV loader's Fidelity-export parser is proven only against the
  committed sample file's format (same shape by construction, not a real export). If
  Fidelity's actual export columns drift from the sample, the CSV path hasn't been
  checked against that drift.
- **Commodity and alt holdings are display-only in v1.** Neither asset class has a
  routed benchmark axis yet (no natural single-ETF comparison for commodities; plan-internal
  alts like an employer-plan target-date fund have no public price series at all) — both
  show in `portfolio_composition` (weight, value) with an explicit "not benchmarked" line,
  never silently.
- **Cost basis aggregates across accounts by summing, which treats nulls as zero.**
  A ticker held in two accounts where one has a tracked cost basis and the other
  doesn't (e.g. a retirement account that doesn't report it) sums to just the
  tracked figure — understating true cost basis and therefore overstating
  `unrealized_gain_pct` for that holding.
- **Duration buckets are hand-assigned per fund.** `sub_style` (short/intermediate/long)
  for bond funds comes from the same maintained classification mapping as `asset_class`
  — no metadata source derives a duration bucket automatically.
- **Cap-weighted benchmarks partly benchmark themselves.** Mega-caps are large chunks of
  their own sector ETF (AAPL ≈ 12% of XLK), so "AAPL vs XLK" has some circularity.
- **Cap axis = "vs the cap tier broadly."** "vs IWM" means vs small-caps across all
  sectors, not a size+sector peer set. Intentional (marginals), but not a like-for-like peer.
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

**Shipped, not deferred — the "make it real" capstone.** Dynamic holdings (SnapTrade
live pull / Fidelity CSV export), asset-class-aware benchmarking (5 classes × 5 axes),
portfolio sizing (`portfolio_composition`), and a structural demo/private split replaced
the static 6-stock watchlist this milestone. Full design + honest build deviations:
`docs/make_it_real_design.md` (locked spec) and `handoff.md` (what actually shipped).
`docs/holdings_ingestion.md` / `docs/multi_asset_benchmarking.md` are kept as design
history — superseded by `make_it_real_design.md`.

The next milestones deliberately deepen trust and reflection instead of increasing the
speed or intensity of market feedback:

1. **Unattended post-close operation.** Deploy the existing Dagster asset graph to
   Dagster+ Serverless, package the dbt manifest at build time, wire secrets, enable the
   weekday post-close schedule, and automate publication of the refreshed public
   snapshot. The scheduled graph remains demo-only; real/SnapTrade pulls stay private.
2. **Reliable settled EOD data.** Follow `docs/ingestion_roadmap.md`: move the newest
   completed session off yfinance's critical path, preserve adjusted-price continuity,
   and enforce freshness as a data contract. This improves trust without introducing
   intraday monitoring.
3. **Grounded portfolio history.** Holdings already bank `as_of`-keyed history. Build
   marts and UI for allocation drift, concentration, asset-class contribution, and
   changes in portfolio structure—not an animated brokerage-style P&L curve.
4. **Contextual portfolio briefing.** Evolve the deterministic sidebar into a cached
   post-close or weekly explanation grounded in gold marts, macro context, and carefully
   sourced events. It explains; it does not predict or recommend trades. See
   `docs/roadmap_ai_portfolio_analyst.md`.
5. **Intent and reflection.** Add position theses, target allocations, review dates, and
   prompts such as “what would invalidate this holding?” so the dashboard connects what
   the user owns to why they own it.

Later platform expansion remains intentionally separate: other brokers through
SnapTrade's OAuth flow, a credit axis for bonds, a generalized bond context tier,
multi-user identity plus row-level isolation, and optional data-quality/lint tooling
(Elementary and SQLFluff).

Already live: the public Streamlit snapshot, dbt docs/lineage on GitHub Pages, CI on
every PR/push, and the complete local Dagster bronze → silver → gold → serve asset graph.
Run the graph locally with `make dagster`.

---

## Setup & run

**Prerequisites:** Google BigQuery project + service-account key, a `FRED_API_KEY`, the
`anchor` dbt profile, Python venv.

```bash
# 1. Python deps + ingestion (writes bronze tables to BigQuery)
pip install -r ingestion/requirements.txt
python ingestion/ingest_fred.py
make ingest-holdings-demo  # committed sample portfolio -> raw_holdings.holdings_demo
python ingestion/ingest_yfinance.py   # ticker universe derives from held tickers + benchmark ETFs

# 2. dbt packages + build + test (run from the dbt project in transformation/)
cd transformation
dbt deps
dbt build                  # dev: into the personal sandbox (demo holdings by default)
dbt build --target prod    # prod: into the anchor_* datasets
cd ..

# 3. serve layer (reads anchor_marts)
pip install -r app/requirements.txt
streamlit run app/app.py

# 4. orchestration (optional) — the whole pipeline as a Dagster asset graph
pip install -r orchestration/requirements.txt
make dagster               # UI at localhost:3000; materialize holdings/ingest -> dbt -> snapshot
```

**Real portfolio (local only, never in the public deploy):** drop a Fidelity positions
export at `data/private/fidelity_positions.csv` (gitignored) plus a
`fund_classifications_real.csv`, then `make ingest-holdings-real && make build-private`
— builds into `anchor_*_private`, isolated from every public target by the compile-time
interlock above. Or connect live: `python ingestion/snaptrade_connect.py` once, then
`python ingestion/ingest_holdings.py --from-snaptrade --portfolio real`.

Run dbt from inside `transformation/` (local dbt is dbt-fusion, whose `--project-dir` flag
mishandles seeds — so `cd` in first). Useful selectors: `dbt build --select staging`,
`dbt build --select marts`, `dbt show --inline "select * from {{ ref('holdings_benchmarks') }}" --limit 20`.

---

## Tech stack

- **Warehouse:** Google BigQuery (`anchor-495115`)
- **Transformation:** dbt (Fusion 2.0), with `dbt_utils` + `codegen`
- **Ingestion:** Python — FRED REST via `requests`, `yfinance`, `pandas` → BigQuery,
  SnapTrade SDK (live brokerage positions), python-dotenv
- **Serve:** Streamlit + Altair, reading the marts through a cached data seam
- **Orchestration:** Dagster (`dagster-dbt`) — holdings/ingestion + dbt + snapshot as one asset graph

## Repo layout

```
ingestion/      Python bronze-ingestion scripts (FRED, yfinance, holdings loader + SnapTrade)
data/           sample_portfolio.csv (committed demo fixture); private/ (real inputs, gitignored)
transformation/ the dbt project:
  models/       staging (silver) / intermediate / marts (gold)
  macros/       ahead_behind, three_way_state, generate_schema_name (dev/prod + demo/private
                routing), assert_portfolio_isolation (privacy interlock)
  seeds/        benchmark_etfs.csv (benchmark axis mapping), fund_classifications.csv (demo
                fund → asset-class mapping)
  tests/        singular guardrail tests
orchestration/  Dagster code location — holdings/FRED/yfinance ingestion + dbt + snapshot as
                one asset graph
app/            Streamlit serve layer — app.py (page), data.py (seam), ui.py (visuals)
ci/             dbt CI profile (used by .github/workflows/ci.yml)
.streamlit/     theme config
docs/           design docs — make_it_real_design.md (locked spec), the Dagster study review
```
