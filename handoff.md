# Anchor — Session Handoff

_Last updated: 2026-06-11 (serve layer + deploy + dbt docs + CI all live; next =
Dagster orchestration). The **`README.md` is the canonical project doc** —
architecture, model map, design decisions, limitations, roadmap. Read it first. This
file is just the lean "current state + what's next" pointer. Also see `CLAUDE.md`
(working style) and `docs/` (deferred roadmaps)._

## State of the world

**Bronze → silver → gold → serve is complete, tested, and green — `dbt build` = 92/92.**
The full `macro → sector → holdings` spine is built, verified against real data, and
now rendered by a Streamlit dashboard.

Gold marts (all in `models/marts/`):
- **Macro:** `macro_indicators` (cards), `macro_trend` (sparklines), `macro_regime` (regime banner)
- **Sector:** `sector_performance` (+ `int_sector_rate_comovement`)
- **Holdings:** `holdings_benchmarks` (two-axis, the load-bearing one)
- **Shared:** `ticker_trend`, `int_ticker_returns`, `int_macro_indicators`

Bronze→silver was already live (FRED 4 series / 44,979 obs; yfinance 14 tickers /
17,570 bars) and remains green.

**Dev / prod datasets (new this session).** Models now route via
`macros/generate_schema_name.sql`: plain `dbt build` collapses into the personal
sandbox `dbt_timurakhtemov` (which still holds orphaned dbt-tutorial tables — harmless,
not the serve source); `dbt build --target prod` materializes the named contract
`anchor_staging` / `anchor_intermediate` / `anchor_marts` / `anchor_seeds`. **The
dashboard reads `anchor_marts`.** A `prod` target was added to `~/.dbt/profiles.yml`
(dataset `anchor`, same SA key).

**Serve layer (new this session) — `app/`.** Single top-down page (macro → sectors →
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
static site `site/index.html` (`dbt docs generate --static --target prod`). Refresh =
regenerate, copy `target/static_index.html` → `site/index.html`, push. Pages source is
set to "GitHub Actions". (Node 20 action-deprecation warning is non-blocking; bump
action versions when convenient.)

## DONE — CI

**`.github/workflows/ci.yml`** builds + tests on every PR/push to main: `dbt build
--target ci` compiles all models, builds into the isolated `dbt_ci` dataset, runs all
92 tests. Auth via the **`BQ_SA_KEY`** repo secret (the existing SA key — set this
session). `ci/profiles.yml` defines the `ci` target. A guard job skips the build (run
stays green) if the secret is ever absent. Verified green (build ran 92/92, ~1m29s).
Keyless upgrade (Workload Identity Federation) is a ~5-line workflow swap, noted in the
workflow header.

## IMMEDIATE next step — Dagster orchestration (dagster-dbt)

**Decision (this session): orchestrate with Dagster, not a GitHub Actions cron.** Why:
targeting AE *startup* roles — Dagster is the mainstream, asset-native orchestrator and
a stronger signal than cron; Airflow was rejected as too heavy (needs hosting, overkill
for one daily linear job). The GHA cron (`refresh.yml`) was **built then dropped** this
session in favor of this. **CI stays on GitHub Actions** (CI ≠ orchestration). The
`Makefile` (`ingest`/`build-prod`/`snapshot`/`refresh`) was kept — its targets are the
tool-agnostic steps Dagster wraps as assets (the whole point of that decoupling).

**The build (run local `dagster dev` first):**
- `pip install dagster dagster-dbt dagster-webserver` (add to a new `orchestration/` or
  `dagster/` project + its own requirements).
- **dbt as assets:** `dagster-dbt` `@dbt_assets` loads every model from the dbt manifest
  as a Dagster asset (lineage auto-derived). Point it at this project + the prod target.
- **Ingestion as upstream assets:** `@asset` wrappers for `ingest_fred` / `ingest_yfinance`
  (the bronze sources the dbt staging models read) — call the functions in
  `ingestion/*.py` (or shell to `make ingest`).
- **Snapshot as downstream asset:** `@asset` (downstream of the marts) that runs
  `app/export_snapshot.py` → `app/snapshot/*.parquet`.
- **Schedule:** a daily (post-close) schedule materializing the full graph.
- **The payoff artifact:** one unified asset/lineage graph FRED/yfinance → bronze →
  staging → marts → snapshot — which plain dbt docs can't show (it stops at the dbt
  boundary). Screenshot it; that's the portfolio win.

**Hosting reality (Dagster is NOT serverless like cron — it needs a host):**
- v1 = local `dagster dev` (free, immediate, gives the asset-graph artifact; doesn't run
  unattended).
- Live scheduled story = **Dagster+ Serverless** (free tier; reuses the same code) — do
  as a follow-up after the local graph works.
- Hybrid (GHA cron runs `dagster job execute`) is possible but defeats the "real
  orchestrator" point.

**Gotcha:** the ingestion scripts hardcode a local keyfile path but fall back to ADC
(`GOOGLE_APPLICATION_CREDENTIALS`) when it's absent — fine for assets. Secrets
`BQ_SA_KEY` + `FRED_API_KEY` remain set (FRED now unused until Dagster-in-cloud).
Optional later polish: SQLFluff lint folded into CI.

## Strategic direction (agreed) — two capstones make it "a living data product"

The dbt+dashboard is functionally complete but reads as *modeling-only*; the value is
turning it into a running product. After Streamlit:

1. **Ops capstone:** ✅ live deploy (Streamlit Cloud) · ✅ dbt docs/lineage (Pages) ·
   ✅ CI on PRs (`dbt build`, GHA) · ⏳ **orchestration = Dagster** (next) · later:
   data-quality (dbt source-freshness; maybe Elementary), SQLFluff lint.
2. **"Make it real" capstone:** dynamic holdings (real portfolio) → multi-asset. These
   are **coupled** — real holdings contain ETFs/bonds/cash, which force the multi-asset
   work and the `cap_tier` null→'Small' fix.

Most of the ops capstone is shipped; Dagster orchestration is the remaining piece, then
the "make it real" capstone is the big value-add.

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
