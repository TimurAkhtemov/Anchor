# Architecture

The full reference for how Anchor is put together: data sources, the dbt model map,
the serve layer, and orchestration. The README carries the pitch and the design
reasoning; this document carries the inventory.

```
FRED API + yfinance + holdings (SnapTrade / Fidelity CSV)
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
  serve   — LLM briefing · web bundle · Next.js static site (web/)
```

## Namespaces: dev / prod and demo / real

**dev / prod.** Models materialize into a named, layered **prod** namespace
(`anchor_staging` / `anchor_intermediate` / `anchor_marts` / `anchor_seeds`) via
`dbt build --target prod`; local dev runs collapse into a single personal sandbox schema.
The serve layer reads the stable `anchor_marts` contract, never a developer sandbox.
Routing lives in `transformation/macros/generate_schema_name.sql`.

**demo / real.** A second dimension, orthogonal to dev/prod: the `holdings_source` var
(`demo` default, `real` opt-in) picks which holdings world `stg_holdings__positions`
reads, and a `prod-private` target routes real-world builds into a fully separate
`anchor_*_private` dataset family (`make build-private`). A compile-time macro assertion
(`assert_portfolio_isolation`, an `on-run-start` hook) fails the build outright if
`holdings_source: real` is ever combined with a public target (`prod`/`ci`). The public
contract structurally cannot be built from real data, not even by mistake.

## Data sources

| Source | Dataset | Contents |
|---|---|---|
| **FRED** | `raw_fred` | 4 macro series: `DFF` (fed funds), `CPIAUCSL` (CPI), `UNRATE` (unemployment), `DGS10` (10-year) |
| **yfinance** | `raw_yfinance` | ~44-ticker **dynamic** universe (held tickers ∪ all 11 SPDR sector ETFs ∪ cap-style/market/bond-market/duration benchmark ETFs) + 5y daily prices. The universe is *derived* from holdings each run, not a hardcoded ticker list |
| **Holdings** | `raw_holdings` | `holdings_demo` (committed sample portfolio, appended with an `as_of` batch date) / `holdings_real` (private, gitignored: SnapTrade live pull or Fidelity CSV export) · `fund_classifications_real` (private fund → asset-class override mapping) |

The committed demo portfolio is deliberately built to exercise every routing branch:
individual stocks across cap tiers (both equity axes), an equity ETF, a bond ETF and bond
mutual fund (bond-market + duration axes), a held-SPY root position, and cash. The
two-axis *and* five-axis benchmarking design is demonstrable end to end without real
financial data.

Ingestion is `WRITE_TRUNCATE` full-refresh for FRED and yfinance; holdings is
`WRITE_APPEND`, banking history keyed by `as_of` by design.

## The dbt model layers

_Paths are relative to `transformation/`, the dbt project root._

**Staging** (`models/staging/`), silver. Rename / typecast only, no business logic.
- `stg_fred__series`, `stg_fred__observations`, `stg_yfinance__tickers`, `stg_yfinance__prices` (incremental in prod)
- `stg_holdings__positions`: demo/real positions, deduped to the latest `as_of` per (account, ticker); world selected by the `holdings_source` var
- `stg_holdings__fund_classifications`: unions the committed demo seed with the private real-fund CSV (staging is the only place the two worlds merge)

**Intermediate** (`models/intermediate/`), shared computation.
- `int_ticker_returns`: per-ticker returns (daily/1m/ytd/1y) to a common as-of date, anchored to the benchmark-ETF trading calendar so one holding's oddball bar can't move the as-of date for everyone else
- `int_macro_indicators`: FRED series normalized to one row per indicator (value, 3mo delta)
- `int_sector_rate_comovement`: each sector ETF's trailing correlation with the 10-year
- `int_holdings_classified`: one valued row per held ticker: `asset_class` (override mapping wins over quote_type-derived fallback), `cap_tier` (equities only), dual-source `valuation_source` (market vs. source-valued)
- `int_benchmark_routing`: resolves each holding to its N benchmarks per asset class, flags self-pairings (roots)

**Snapshot** (`snapshots/`): `snap_yfinance_tickers`, an SCD2 check snapshot of ticker
metadata (sector, market cap) so classification changes are history-preserved. Prod writes
to `anchor_snapshots`.

**Marts** (`models/marts/`), gold, the served tier.

| Tier | Model | What it produces |
|---|---|---|
| Macro | `macro_indicators` | per-indicator cards: value + delta + direction + source series (traceability) |
| Macro | `macro_trend` | sparkline series (trailing 12mo; inflation as YoY trajectory) |
| Macro | `macro_regime` | one-row regime statement (rates / inflation / labor) |
| Sector | `sector_performance` | all 11 SPDR sector ETFs' returns + realized rate co-movement + label |
| Holdings | `portfolio_composition` | one row per held ticker (incl. cash + roots): weight, market value, unrealized gain, valuation source. The sizing mart |
| Holdings | `holdings_benchmarks` | each holding paired with its asset-class-appropriate benchmark set, relative position + label per horizon |
| Shared | `ticker_trend` | sparkline series for every ticker (scoped to the active world's universe) |
| Shared | `as_of_calendar` | the single shared as-of date every return is measured to |

**Contracts and lineage.** `holdings_benchmarks` and `portfolio_composition` carry
enforced dbt contracts, so column or type drift fails the build before the app breaks.
`models/marts/_exposures.yml` declares the public web dashboard (via the web bundle
export) as the downstream consumer. Source freshness thresholds are set on the FRED and
yfinance sources.

**Tests.** 131 tests across the project: uniqueness and not-null on composite grains,
accepted values on every categorical, relationship tests between layers, and five singular
guardrail tests in `tests/`:

| Guardrail | Fails the build when |
|---|---|
| `assert_holdings_benchmarked_on_expected_axes` | any holding resolves to a different number of benchmark axes than its asset class prescribes (seed drift) |
| `assert_held_funds_classified` | a held ETF or mutual fund has no classification row |
| `assert_source_valuation_is_intentional` | a normally-priced instrument (equity, fixed income, commodity) is valued from the import instead of a live close |
| `assert_portfolio_weights_sum` | composition weights don't sum to 100% (within a rounding tolerance) |
| `assert_as_of_calendar_single_row` | the shared as-of calendar has more or fewer than one row |

## The serve layer

**One static site, two worlds (`web/`).** A Next.js static export in the "Morning paper"
design: the briefing headline and summary, then macro regime and indicator cards →
sector performance → holdings, each tier read under the one above it, with an optional
guided reading. It renders one JSON bundle and has no backend and no credentials.

- **Public demo:** `web/public/data/anchor.json` (committed, demo world only) built and
  deployed by Vercel at [anchor-pi-five.vercel.app](https://anchor-pi-five.vercel.app).
- **Real portfolio:** the same app built against a private bundle in `var/` and served by
  `scripts/private_static_server.py` on `127.0.0.1:8501` only. Nothing private is
  committed.
- `app/export_web.py` writes the bundle from the marts; `app/bundle_validation.py`
  refuses a public bundle with any ticker outside the demo universe, an empty section,
  or a settled date older than 4 days.
- **Composition-driven holdings tier.** The UI iterates `portfolio_composition` grouped
  by asset class and attaches each ticker's `holdings_benchmarks` rows: master-detail on
  one entity, not a relationship recomputed in the UI. Classes with no v1 benchmark axis
  render an explicit "not benchmarked" line.
- **Honest color semantics.** Macro deltas carry direction words, not green/red, because
  macro is context. Returns and ahead/behind *are* green/red (`#1f6f3f` / `#b3362b`,
  checked for colour-blind separation) with a sign and label, never colour alone.
- Playwright covers the figure-to-focus resolver with unit tests and the built page with
  browser tests at desktop and phone widths.

**v1: Streamlit.** The serve layer started as a Streamlit dashboard with a data seam
(`data.py`) that read live BigQuery locally and a committed parquet snapshot in the
public deploy. It is frozen on the `streamlit-v1` branch and still live at
[anchor-dashboard.streamlit.app](https://anchor-dashboard.streamlit.app) with its last
demo data. The move to Next.js came when the scroll-told briefing outgrew Streamlit's
rerun model and one static bundle could serve both worlds.

**LLM briefing (`copilot_briefing`).** `app/generate_briefing.py` feeds the gold marts,
the macro regime, and sourced headlines to a model and writes one row per run into the
active marts dataset: `briefing_json` (a hard-validated tour script with per-step targets
and figures), `briefing_md` (assembled narration), and `sources` (the headlines, kept as
the audit trail). A rejected script is regenerated up to 3 times with the validator's
errors fed back. Providers: Claude (`claude-sonnet-5-5`) for the public demo only, and a
local model (Qwen via llama-server) for the real portfolio; `build_provider` refuses a
cloud provider for real data before any network call. The table is outside dbt lineage,
and the site renders without it. Design: `llm_copilot_briefing_design.md`,
`immersive_briefing_design.md`, `briefing_daily_note_design.md`.

## Orchestration and CI

**Public refresh (`.github/workflows/public-refresh.yml`).** Tue-Sat 10:00 UTC, a thin
trigger over `make` targets: ingest → `dbt build --target prod` → briefing (only for a
new settled date) → export to a temp file → validate → web build + Playwright → one
commit touching only the bundle → Vercel deploys. It authenticates as
`anchor-public-refresh`, a service account with Data Editor on the public datasets and
read access to `raw_holdings.holdings_demo` only; `scripts/check_public_credential.py`
proves it is denied every private table. Runbook: `public_refresh_operations.md`.

**Private refresh (LaunchAgent).** Tue-Sat 06:00 ET on the owner's Mac:
`scripts/private_daily.py` runs SnapTrade → FRED/yfinance → `prod-private` → local
briefing → private bundle → private site, then swaps it in atomically. Runbook:
`private_daily_operations.md`.

**Why morning runs.** Yahoo can still serve blank closes at 21:30 ET (2026-11-10: 9
bars), which the valuation guardrails correctly refuse. Ingestion drops the current day
before the 21:30 ET cutoff, so a morning run settles the previous weekday.

**Dagster (`orchestration/`, retired).** The pipeline was first one software-defined
asset graph via `dagster-dbt`, with a Dagster+ Serverless deployment built. Once the
serve layer became one static bundle, the job was a straight line of `make` targets, and
a GitHub Actions trigger replaced it. The code stays as a record; nothing schedules it.

**CI (`.github/workflows/ci.yml`).** Every pull request runs pytest, then `dbt build`
(dbt-core 1.11) against an isolated `dbt_ci` dataset, then the web job (`npm run build`,
typecheck, lint, Playwright). The dbt docs site is generated locally as a static page
(`site/index.html`) and deployed to GitHub Pages by `docs.yml`.

**Leak checks.** `scripts/audit_public_tables.py` checks every public dataset (including
`dbt_ci`) for tickers outside the demo universe; `scripts/scan_for_private_tickers.py`
scans files or git history for real holdings. Both print counts only.

**dbt engines.** Local work uses dbt-fusion, run from inside `transformation/` because
fusion's `--project-dir` flag mishandles seed paths. CI uses dbt-core on its own runner.
The two can't share `transformation/dbt_packages/`, so keep one engine locally.
