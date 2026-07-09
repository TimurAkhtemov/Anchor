# Anchor — Session Handoff

_Last updated: 2026-07-09 ("make it real" capstone complete + pushed: dynamic holdings
ingestion (SnapTrade live + Fidelity CSV), asset-class-aware benchmarking (5 classes ×
5 axes), `portfolio_composition` sizing mart, structural demo/private isolation, a
composition-driven app, the `holdings_demo` Dagster asset, and refreshed docs/snapshot.
Next = **Dagster+ Serverless** for the unattended scheduled run — the last item on the
ops capstone). The **`README.md` is the canonical project doc** —
architecture, model map, design decisions, limitations, roadmap. Read it first. This
file is just the lean "current state + what's next" pointer. Also see `CLAUDE.md`
(working style) and `docs/` (deferred roadmaps)._

## State of the world

**Bronze → silver → gold → serve is complete, tested, and green — `dbt build` = 140/140**
(18 models, 118 tests, 1 snapshot, 2 seeds, 1 hook). The full `macro → sector → holdings`
spine is built, verified against real data (both demo and a real portfolio), and rendered
by a Streamlit dashboard whose holdings tier is now driven by actual position weights
across five asset classes, not a static watchlist.

**Repo layout (2026-06-16):** the dbt project lives in `transformation/` (moved out of the
repo root); `ingestion/`, `app/`, `orchestration/` are siblings. **dbt engine:** local work
+ Dagster + the dbt-MCP use **dbt-fusion** (run from *inside* transformation/ — the
Makefile/Dagster cd in; fusion's `--project-dir` mishandles seed paths); **CI uses dbt-core
1.11** on its own isolated runner. dbt-core and dbt-fusion can't share
`transformation/dbt_packages/`, so keep one engine locally (fusion).

Gold marts (all in `transformation/models/marts/`):
- **Macro:** `macro_indicators` (cards), `macro_trend` (sparklines), `macro_regime` (regime banner)
- **Sector:** `sector_performance` (+ `int_sector_rate_comovement`) — all 11 SPDR sectors
- **Holdings:** `portfolio_composition` (sizing: weight, value, gain, valuation source),
  `holdings_benchmarks` (asset-class-routed, up to 5 axes — the load-bearing one)
- **Shared:** `ticker_trend`, `int_ticker_returns`, `int_macro_indicators`,
  `int_holdings_classified`, `int_benchmark_routing`

Bronze→silver is live and freshly refreshed as of 2026-07-09 (FRED 4 series; yfinance's
~44-ticker *derived* universe — held tickers ∪ all benchmark ETFs — replaces the old
fixed 14; `raw_holdings` added for demo + real positions). `dbt source freshness --target
prod` passes after refresh.

**Dev / prod datasets.** Models route via
`transformation/macros/generate_schema_name.sql`: plain `dbt build` collapses into the personal
sandbox `dbt_timurakhtemov` (which still holds orphaned dbt-tutorial tables — harmless,
not the serve source); `dbt build --target prod` materializes the named contract
`anchor_staging` / `anchor_intermediate` / `anchor_marts` / `anchor_seeds`; the ticker
metadata dbt snapshot writes to `anchor_snapshots` in prod. **The dashboard reads
`anchor_marts`.** A `prod` target was added to `~/.dbt/profiles.yml`
(dataset `anchor`, same SA key).

**Serve layer — `app/`.** Single top-down page (macro → sectors →
holdings), live from `anchor_marts`. `app/data.py` is the data seam (cached `_read()`
choke point + a `SOURCE` switch for the future snapshot path — no UI knows the source);
`app/ui.py` is the shared visual vocabulary; `.streamlit/config.toml` is the teal theme.
Run with `streamlit run app/app.py` (needs `GOOGLE_APPLICATION_CREDENTIALS`). Gotcha:
restarting the streamlit server drops open browser tabs' connections — hard-refresh
(Cmd+Shift+R) after a restart or the page renders stale/half-scrolled.

## DONE — public deploy

**Live: https://anchor-dashboard.streamlit.app** (Streamlit Community Cloud, public
repo, deploys from `main`, entrypoint `app/app.py`). Serves the committed parquet
snapshot (`app/snapshot/*.parquet`) — no GCP creds. `app/data.py` auto-detects source
(bigquery local / snapshot cloud); `app/export_snapshot.py` regenerates the snapshot
(run it + push to refresh the live demo). See the `reference-live-deploy` memory.

## DONE — dbt docs / lineage

**Live: https://timurakhtemov.github.io/Anchor/** (GitHub Pages, published by
`.github/workflows/docs.yml`). v1 is secret-free: serves the committed self-contained
static site `site/index.html` (`dbt docs generate --static --project-dir transformation
--target prod`). Refresh = regenerate, copy `transformation/target/static_index.html` →
`site/index.html`, push. Pages source is
set to "GitHub Actions". (Action versions bumped to Node-24 runtimes 2026-06-16:
checkout@v6, setup-python@v6, configure-pages@v6, upload-pages-artifact@v5, deploy-pages@v5.)

## DONE — CI

**`.github/workflows/ci.yml`** builds + tests on every PR/push to main: `dbt build
--target ci` compiles all models, builds into the isolated `dbt_ci` dataset, runs all
data tests (118 as of 2026-07-09) plus model builds/seeds/snapshots. Auth via the
**`BQ_SA_KEY`** repo secret (the existing SA key — set this session). `ci/profiles.yml`
defines the `ci` target. A guard job skips the build (run stays green) if the secret is
ever absent. Locally verified green on 2026-07-01: `make refresh` got ingestion + dbt
build to 93/93 (then 140/140 after the make-it-real capstone — see below), then snapshot
export was rerun with `GOOGLE_APPLICATION_CREDENTIALS=~/.dbt/anchor-bigquery-key.json`
because `app/export_snapshot.py` expects ADC when invoked directly.
Keyless upgrade (Workload Identity Federation) is a ~5-line workflow swap, noted in the
workflow header.

## DONE — dbt-depth pass

Completed and pushed 2026-07-01 (`feat(dbt): add depth pass and refresh snapshots`).

- **Incremental price staging.** `stg_yfinance__prices` is now an incremental BigQuery
  merge table keyed on `(ticker, trading_date)`, partitioned by `trading_date`, clustered
  by `ticker`, and reloading the latest 7 days to absorb yfinance corrections/trailing-bar
  finalization.
- **SCD2 ticker metadata snapshot.** `snap_yfinance_tickers` tracks changes in company
  name, sector, industry, market cap, exchange, and currency. Prod relation:
  `anchor_snapshots.snap_yfinance_tickers`; dev/CI use the active target schema.
- **Freshness contract.** Raw yfinance tables warn/error at 36h/72h; raw FRED tables at
  7d/14d. `dbt source freshness --target prod` passes after the 2026-07-01 refresh.
- **Exposures.** dbt lineage includes the Streamlit dashboard and parquet snapshot export
  downstream of the served marts (`portfolio_composition` added with the make-it-real
  capstone — see below).
- **Model contract.** `holdings_benchmarks` has an enforced column/type contract while
  preserving its existing grain, relationship, accepted-value, and guardrail tests.

## DONE — Dagster orchestration (dagster-dbt)

**The whole pipeline is now one Dagster asset graph** (`orchestration/`, run locally with
`make dagster` → UI at localhost:3000). Built + verified end-to-end this session. See
`orchestration/README.md` for the design write-up.

- **Bronze ingestion as assets.** `ingest_fred` / `ingest_yfinance` are `@multi_asset`s,
  each yielding two nodes (the four `raw_*` tables). The ingestion scripts got a thin
  refactor — an importable `ingest_*(client)` that returns row counts and raises instead
  of `sys.exit`; the `main()` CLI is preserved so `make ingest` / CI are unchanged.
- **dbt models as assets, fused onto bronze.** `@dbt_assets` auto-loads every model +
  seed in the manifest; an `AnchorDbtTranslator` maps each dbt `source()` onto the bronze
  asset keys, so the graph is **continuous** bronze → silver (staging/intermediate) →
  gold (marts) — the cross-boundary lineage plain dbt docs can't show. Models grouped by
  layer; `dbt build` runs on `--target prod`; all tests surface as asset checks.
- **Snapshot as the terminal asset.** `snapshot_parquet`, downstream of the served marts,
  runs `export_snapshot` (same thin-refactor treatment) → `app/snapshot/*.parquet`.
- **`holdings_demo` (added with the make-it-real capstone).** A single `@asset` upstream
  of `ingest_yfinance` (the ticker universe is derived from held tickers, so holdings
  must land first) that loads the committed sample portfolio. Real/SnapTrade pulls are
  deliberately manual and local — the scheduled public graph never touches real data.
- **Fusion/dagster-dbt manifest gotcha (found + fixed this session).** dagster-dbt's
  asset-graph construction walks the manifest through dbt-core's `NodeSelector`, which
  unconditionally reads `node.config.enabled` — but dbt-fusion never populates `config`
  on `on-run-start`/`on-run-end` hook ("operation") nodes (the privacy-interlock hook
  added with `prod-private`), so loading `Definitions` crashed with an `AttributeError`.
  Hooks aren't `ref()`-able resources Dagster needs to model as assets, so
  `resources.py` now strips operation nodes from its copy of the parsed manifest right
  after `prepare_if_dev()` — a few lines, doesn't touch how dbt itself builds, and the
  manifest is a gitignored build artifact so nothing this touches is committed.
- **Schedule.** `daily_refresh` — weekday 18:30-ET post-close over the whole graph,
  **stopped by default** (toggle in the UI).
- **One auth seam.** A `BigQueryResource` injects the client into every Python asset
  (local ADC → keyfile; cloud → `gcp_credentials` secret), unifying the auth the
  ingestion + snapshot scripts each wired up separately.
- **Verified:** full graph materializes through Dagster in dependency order —
  ingest_fred + ingest_yfinance (parallel) → dbt build → snapshot, RUN_SUCCESS (~1m35s).
  Payoff lineage screenshot captured (`docs/images/dagster-lineage.png`, local — PNGs are gitignored).

**Why in-process assets (not subprocess):** future-proofs the roadmap — new sources
(SnapTrade holdings) reuse the resource; partitioned/incremental loads pass config into
the functions; data-quality checks emit from the returned counts; cloud deploy swaps
resource config, not code. Decision made Socratically this session.

**Env to run:** `make dagster` sets `GOOGLE_APPLICATION_CREDENTIALS`, `DBT_PROFILES_DIR`
(~/.dbt — where the `prod` target lives), `DAGSTER_HOME` (gitignored), and
`PYTHONPATH=orchestration`. `prepare_if_dev()` regenerates the dbt manifest under
`dagster dev` so the asset graph never drifts.

## DONE — make-it-real capstone (dynamic holdings + multi-asset benchmarking)

**The static 6-stock watchlist is retired.** Real portfolio holdings — ingested
dynamically, sized by actual position weights, benchmarked per asset class — now drive
the holdings tier. Locked design: `docs/make_it_real_design.md`. Built across 8 commit
groups (loader → yfinance universe → staging/classification → gold rework → privacy
plumbing → serve layer → SnapTrade → this ops pass); see `git log` for the full trail.

**What shipped:**
- **One holdings loader, two transports, one schema** (`ingestion/ingest_holdings.py`):
  `--from-csv` parses a Fidelity positions export (the committed `data/sample_portfolio.csv`
  is in the same format); `--from-snaptrade` pulls live positions via the SnapTrade SDK
  (read-only, Fidelity GA, free personal tier). Both funnel into the same
  `raw_holdings.holdings_<demo|real>` schema, `WRITE_APPEND` with an `as_of` batch date
  (banks position history from day one for a future portfolio-over-time UI).
- **Asset-class-aware benchmark routing (5 classes × 5 axes).** `int_holdings_classified`
  + `int_benchmark_routing` route equities to sector + cap-style, equity funds to market,
  fixed income to bond-market + duration, and leave commodity/alt with zero axes
  (display-only, guardrail-tested) — one generic `benchmark_type` model, no per-class
  special-casing in the mart itself.
- **Dual-source valuation.** `valuation_source` (`market` vs `source`) is explicit:
  `quantity × latest_close` when a public price exists, the import's own value when it
  doesn't (cash NAV, plan-internal instruments like an employer-plan target-date fund).
  A guardrail test (`assert_source_valuation_is_intentional`) fails the build if any
  *normal* instrument (not cash/alt) is ever source-valued — a transiently unpriced
  holding must fail loudly, not silently go stale.
- **`portfolio_composition`** — the sizing mart: one row per held ticker including cash
  and roots (weight, market value, cost basis, unrealized gain, `is_root`).
- **Structural demo/private isolation.** A `prod-private` dbt target (`anchor_*_private`
  datasets) + a `holdings_source` var (`demo` default) + a compile-time `on-run-start`
  hook (`assert_portfolio_isolation`) that fails the build if `holdings_source: real` is
  ever combined with a public target. The public deploy cannot see real data even by
  mistake — verified by building `prod-private --vars '{holdings_source: real}'` locally
  green, and `prod`/`ci` refusing the same vars.
- **Composition-driven app.** The holdings tier iterates `portfolio_composition` grouped
  by asset class, attaches `holdings_benchmarks` rows by ticker, and shows an allocation
  bar. Roots get a "market root" badge; holdings with zero benchmark axes (commodity,
  alt) render an explicit "not benchmarked" line instead of blank space.

**How to run it:**
```bash
make ingest-holdings-demo && python ingestion/ingest_yfinance.py && cd transformation && dbt build
# real (local only, never in a public target):
make ingest-holdings-real && make build-private
# or connect live once, then re-pull anytime:
python ingestion/snaptrade_connect.py
python ingestion/ingest_holdings.py --from-snaptrade --portfolio real
```
Private inputs (never committed): `data/private/fidelity_positions.csv` +
`data/private/fund_classifications_real.csv`, both gitignored; SnapTrade secrets live in
`.env` (also gitignored).

**Honest deviations from the locked design** (the point of surfacing them — see
`docs/make_it_real_design.md` for the original spec):
- **SnapTrade became the primary real-data transport.** The CSV path was sequenced first
  to prove the models, per the design's own risk-control call — but SnapTrade shipped and
  became primary use before a real Fidelity export was ever run through the CSV parser.
  It's validated only against the committed sample file's format; treat the CSV real-path
  as unverified against actual export drift.
- **Commodity + alt asset classes were added mid-build**, beyond the locked design's four
  (stocks, equity funds, bond funds, cash) — the real portfolio contained both. They
  required the explicit `valuation_source` split (source-valued = cash NAV + plan-internal
  instruments) and are intentionally unbenchmarked in v1 (display-only).
- **The common as-of calendar is anchored to the benchmark ETF set**, not the full priced
  universe — a holding's oddball bar (e.g. a fund NAV stamped ahead of the market's last
  complete close) must not move the as-of date for everyone else.
- **Classification is an override table, not a pure derivation** — human classification
  (the fund seed / private CSV) wins over `quote_type`-derived fallback whenever both
  exist, since no metadata source can classify what a fund holds inside.

**Verified:** `dbt build` green in both worlds (140/140 demo; real-world spot-check green
too); app checked in both demo and real mode; snapshot re-exported and inspected —
demo-tickers-only, confirmed by a dedicated singular assertion against the exported
parquet files; CI green on push.

## Recommended next session (decided 2026-06-16) — a dbt-depth pass

_Historical — this pass shipped 2026-07-01 (see "DONE — dbt-depth pass" above); kept
below for the record._

Goal: make the project more impressive *on the dbt side*. Highest-ROI, and most needs no
new data — these are senior-dbt patterns currently missing:
- **Incremental model** — prices grow daily; textbook `is_incremental()` + `unique_key`.
- **Snapshot (SCD2)** — `transformation/snapshots/` is empty (just `.gitkeep`); snapshot
  ticker `sector` / `market_cap` over time.
- **Exposures** — declare the Streamlit dashboard + the snapshot as consumers so lineage
  shows model → dashboard.
- **Source freshness** — `loaded_at` thresholds on the FRED/yfinance sources (designed in
  `docs/ingestion_roadmap.md`).
- **Model contract** — enforce column types/constraints on `holdings_benchmarks` (the
  load-bearing mart).

Why this first: Serverless (below) is ops/hosting — zero dbt. Multi-asset is the deeper
modeling lift but coupled to holdings ingestion (plumbing). The dbt-depth pass is fast,
high-signal, and independent. **Sequence: dbt-depth → multi-asset (make-it-real) →
Serverless (deploy last, so the live schedule showcases the fuller graph).**

## Later — Dagster+ Serverless (unattended schedule)

Local `dagster dev` gives the asset-graph artifact but doesn't run unattended (laptop).
**Dagster+ Serverless** (free tier, same code) is the live scheduled story. Needs: a
build-time manifest (`dagster-dbt project prepare-and-package`, since `prepare_if_dev`
only fires locally) and the `gcp_credentials` secret wired to the `BigQueryResource`. The
`git push` that refreshes the live Streamlit demo from the new snapshot stays a separate
step (Dagster materializes the parquet, not the commit). Secrets `BQ_SA_KEY` +
`FRED_API_KEY` remain set.

**Fusion gotchas (local engine = dbt-fusion 2.0 preview at `~/.local/bin/dbt`):**
(1) Run it from *inside* `transformation/` — its `--project-dir` flag mishandles seed file
paths, so the `benchmark_etfs` seed fails from the repo root (the Makefile `cd`s in; Dagster
runs dbt from the project dir; the dbt-MCP sets `DBT_PROJECT_DIR`). (2) dbt-core and
dbt-fusion **cannot share `transformation/dbt_packages/`** — each re-creates `pkg 2`/`pkg 3`
dirs and breaks the other, so everything LOCAL is fusion and CI is core on its own runner.
(3) harmless deferral-manifest 404 warning. `make build-prod` (fusion) = 140/140 green.
(4) dagster-dbt's manifest reader crashes on dbt-fusion's null `config` for hook
("operation") nodes — worked around in `orchestration/anchor_orchestration/resources.py`
by stripping those nodes from Dagster's parsed copy of the manifest (see the "make-it-real
capstone" section above); a build-time manifest for Serverless will need the same
treatment if `dagster-dbt project prepare-and-package` hits the same node type.
Optional later polish: SQLFluff lint folded into CI.

## Strategic direction (agreed) — two capstones make it "a living data product"

The dbt+dashboard is functionally complete but reads as *modeling-only*; the value is
turning it into a running product. After Streamlit:

1. **Ops capstone:** ✅ live deploy (Streamlit Cloud) · ✅ dbt docs/lineage (Pages) ·
   ✅ CI on PRs (`dbt build`, GHA) · ✅ **orchestration = Dagster asset graph** (local
   `dagster dev`, now including the `holdings_demo` bronze asset) · next: Dagster+
   Serverless (unattended run) · later: data-quality (Elementary), SQLFluff lint.
2. **"Make it real" capstone:** ✅ **shipped 2026-07-09.** Dynamic holdings (SnapTrade
   live + Fidelity CSV) → asset-class-aware multi-asset benchmarking (5 classes × 5
   axes) → `portfolio_composition` sizing → structural demo/private isolation →
   composition-driven app. See "DONE — make-it-real capstone" above.

**Both capstones are now shipped.** The only remaining ops item is Dagster+ Serverless
(unattended schedule, same code) — everything else on both lists is built, tested, and
live.

## Roadmap docs

- `docs/make_it_real_design.md` — **built** (2026-07-09), see "DONE — make-it-real
  capstone" above. The locked build spec; kept as the design record + honest-deviation
  reference.
- `docs/holdings_ingestion.md`, `docs/multi_asset_benchmarking.md` — **superseded** by
  `make_it_real_design.md` (their open decisions are resolved there); kept as design
  history only.
- `docs/ingestion_roadmap.md` — **still deferred.** Price-data freshness/source strategy:
  EOD API for the nightly post-close increment, incremental loading beyond prices.
  (Source-freshness tests already shipped in the dbt-depth pass.)

## Open items / things to watch

- **Caveats are catalogued in the README "Limitations" section** — don't re-derive them.
  Key live ones: quantities are as-of the last import (prices are daily, so value mixes
  fresh + stale between pulls), the CSV real-import path is unvalidated against an actual
  Fidelity export, alt instruments are display-only (no v1 benchmark axis), duration
  buckets are hand-assigned, CPI lag in the regime, co-movement is descriptive/noisy,
  yfinance freshness, namespace-scoped ticker key.
- **yfinance trailing-bar gotcha is handled** (models filter null-OHLC bars), but it
  recurs each pull — the durable fix lives in `docs/ingestion_roadmap.md`.
- Ingestion is `WRITE_TRUNCATE` full-refresh for FRED/yfinance; holdings is `WRITE_APPEND`
  (banks history by design). Incremental yfinance loading beyond prices is future work.
- `dbt-fusion 2.0 preview` emits harmless warnings (deferral manifest 404, package
  project-file warnings); not errors. It also never populates `config` on hook nodes —
  harmless for `dbt build` itself, but see the Dagster manifest workaround above if you
  touch `orchestration/anchor_orchestration/resources.py`.

## How to work on this project

See `CLAUDE.md` "Working style": Socratic (surface decisions, user decides), verify
against real data before baking values in, explain the "why" concisely, honest about
caveats, move fast on boilerplate. The user is learning AE as we build and holds the
wheel on design calls.
