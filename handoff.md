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

## IMMEDIATE next step — the rest of the ops capstone

Remaining cheap/high-impact wins, in rough order:

- **dbt docs / lineage** — `dbt docs generate` → static site on GitHub Pages. Highest
  portfolio value, layered `anchor_*` schemas make the graph readable. Can be generated
  locally (creds present) and the static site committed/served — no secret needed for v1.
- **CI on PRs** — GitHub Actions: `dbt build` (needs the BQ SA key as a repo secret) +
  SQLFluff lint. **Prereq:** upload `~/.dbt/anchor-bigquery-key.json` as a GitHub Actions
  secret (sensitive/outward-facing — confirm before doing it).
- **Scheduling** — post-close cron (GitHub Actions): `ingest → dbt build --target prod
  → export_snapshot → push` (auto-redeploys the live app). Needs the same BQ secret +
  the FRED API key secret, and a push-back token.

The BQ-secret setup is the shared unlock for CI + scheduling; dbt docs can land first
without it.

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
