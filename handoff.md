# Anchor — Session Handoff

_Last updated: 2026-06-11 (serve layer + prod datasets). The **`README.md` is the
canonical project doc** — architecture, model map, design decisions, limitations,
roadmap. Read it first. This file is just the lean "current state + what's next"
pointer. Also see `CLAUDE.md` (working style) and `docs/` (deferred roadmaps)._

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

## IMMEDIATE next step — scheduling (the last ops piece)

**Scheduled post-close pipeline** (GitHub Actions cron): `ingest → dbt build --target
prod → export_snapshot → git push` — refreshes prod marts then the live demo snapshot
(Streamlit auto-redeploys; docs can re-publish too). Needs: the `BQ_SA_KEY` secret
(already set), a **`FRED_API_KEY`** secret (for ingestion), and a push-back token/perms
so the Action can commit the regenerated `app/snapshot/*.parquet`. Optional polish:
SQLFluff lint (its dbt templater needs warehouse creds, so fold it into the CI job).

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
