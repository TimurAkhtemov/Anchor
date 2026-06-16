# Anchor — Session Handoff

_Last updated: 2026-06-16 (Dagster orchestration built; repo restructured — dbt now lives
in `transformation/`; CI + Pages bumped to Node-24 actions, all green on remote. Next =
Dagster+ Serverless for the unattended scheduled run). The **`README.md` is the
canonical project doc** —
architecture, model map, design decisions, limitations, roadmap. Read it first. This
file is just the lean "current state + what's next" pointer. Also see `CLAUDE.md`
(working style) and `docs/` (deferred roadmaps)._

## State of the world

**Bronze → silver → gold → serve is complete, tested, and green — `dbt build` = 92/92.**
The full `macro → sector → holdings` spine is built, verified against real data, and
now rendered by a Streamlit dashboard.

**Repo layout (2026-06-16):** the dbt project lives in `transformation/` (moved out of the
repo root); `ingestion/`, `app/`, `orchestration/` are siblings. **dbt engine:** local work
+ Dagster + the dbt-MCP use **dbt-fusion** (run from *inside* transformation/ — the
Makefile/Dagster cd in; fusion's `--project-dir` mishandles seed paths); **CI uses dbt-core
1.11** on its own isolated runner. dbt-core and dbt-fusion can't share
`transformation/dbt_packages/`, so keep one engine locally (fusion).

Gold marts (all in `transformation/models/marts/`):
- **Macro:** `macro_indicators` (cards), `macro_trend` (sparklines), `macro_regime` (regime banner)
- **Sector:** `sector_performance` (+ `int_sector_rate_comovement`)
- **Holdings:** `holdings_benchmarks` (two-axis, the load-bearing one)
- **Shared:** `ticker_trend`, `int_ticker_returns`, `int_macro_indicators`

Bronze→silver was already live (FRED 4 series / 44,979 obs; yfinance 14 tickers /
17,570 bars) and remains green.

**Dev / prod datasets.** Models route via
`transformation/macros/generate_schema_name.sql`: plain `dbt build` collapses into the personal
sandbox `dbt_timurakhtemov` (which still holds orphaned dbt-tutorial tables — harmless,
not the serve source); `dbt build --target prod` materializes the named contract
`anchor_staging` / `anchor_intermediate` / `anchor_marts` / `anchor_seeds`. **The
dashboard reads `anchor_marts`.** A `prod` target was added to `~/.dbt/profiles.yml`
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
92 tests. Auth via the **`BQ_SA_KEY`** repo secret (the existing SA key — set this
session). `ci/profiles.yml` defines the `ci` target. A guard job skips the build (run
stays green) if the secret is ever absent. Verified green (build ran 92/92, ~1m29s).
Keyless upgrade (Workload Identity Federation) is a ~5-line workflow swap, noted in the
workflow header.

## DONE — Dagster orchestration (dagster-dbt)

**The whole pipeline is now one Dagster asset graph** (`orchestration/`, run locally with
`make dagster` → UI at localhost:3000). Built + verified end-to-end this session. See
`orchestration/README.md` for the design write-up.

- **Bronze ingestion as assets.** `ingest_fred` / `ingest_yfinance` are `@multi_asset`s,
  each yielding two nodes (the four `raw_*` tables). The ingestion scripts got a thin
  refactor — an importable `ingest_*(client)` that returns row counts and raises instead
  of `sys.exit`; the `main()` CLI is preserved so `make ingest` / CI are unchanged.
- **dbt models as assets, fused onto bronze.** `@dbt_assets` auto-loads all 13 models +
  the seed; an `AnchorDbtTranslator` maps each dbt `source()` onto the bronze asset keys,
  so the graph is **continuous** bronze → silver (staging/intermediate) → gold (marts) —
  the cross-boundary lineage plain dbt docs can't show. Models grouped by layer; `dbt
  build` runs on `--target prod`; the 78 tests surface as asset checks.
- **Snapshot as the terminal asset.** `snapshot_parquet`, downstream of the six marts,
  runs `export_snapshot` (same thin-refactor treatment) → `app/snapshot/*.parquet`.
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

## IMMEDIATE next step — Dagster+ Serverless (unattended schedule)

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
(3) harmless deferral-manifest 404 warning. `make build-prod` (fusion) = 92/92 green.
Optional later polish: SQLFluff lint folded into CI.

## Strategic direction (agreed) — two capstones make it "a living data product"

The dbt+dashboard is functionally complete but reads as *modeling-only*; the value is
turning it into a running product. After Streamlit:

1. **Ops capstone:** ✅ live deploy (Streamlit Cloud) · ✅ dbt docs/lineage (Pages) ·
   ✅ CI on PRs (`dbt build`, GHA) · ✅ **orchestration = Dagster asset graph** (local
   `dagster dev`) · next: Dagster+ Serverless (unattended run) · later: data-quality
   (dbt source-freshness; maybe Elementary), SQLFluff lint.
2. **"Make it real" capstone:** dynamic holdings (real portfolio) → multi-asset. These
   are **coupled** — real holdings contain ETFs/bonds/cash, which force the multi-asset
   work and the `cap_tier` null→'Small' fix.

The ops capstone is essentially shipped (Dagster local is built; only the unattended
Dagster+ run remains); the "make it real" capstone (dynamic holdings → multi-asset) is
now the big value-add.

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
