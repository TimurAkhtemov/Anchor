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
  serve   — Streamlit dashboard (app/) · LLM briefing · Next.js tour (web/)
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
`models/marts/_exposures.yml` declares the Streamlit dashboard and the parquet snapshot
export as downstream consumers. Source freshness thresholds are set on the FRED and
yfinance sources.

**Tests.** 118 tests across the project: uniqueness and not-null on composite grains,
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

**Streamlit dashboard (`app/`).** A single top-down page enforcing the reading order:
macro regime and indicator cards → sector performance → holdings, each tier under the one
above it. Live at [anchor-dashboard.streamlit.app](https://anchor-dashboard.streamlit.app).

- `app/data.py` is the data seam. The UI calls `data.get_*()` functions and never knows
  the source. Every read goes through one cached `_read()` choke point with a `SOURCE`
  switch: live BigQuery locally, the committed parquet snapshot (`app/snapshot/`) in the
  public deploy. Swapping sources takes zero UI edits.
- `app/ui.py` is the visual vocabulary: shared palette, chips, status pills, and Altair
  sparklines so the three tiers read as one product.
- **Composition-driven holdings tier.** The UI iterates `portfolio_composition` grouped
  by asset class and attaches each ticker's `holdings_benchmarks` rows by join:
  master-detail on one entity, not a relationship recomputed in the UI. Asset classes
  with no v1 benchmark axis render an explicit "not benchmarked" line instead of an empty
  comparison.
- **Honest color semantics.** Macro deltas are direction-colored, never green/red, because
  macro is context, not performance. Returns and ahead/behind labels *are* green/red,
  because there the judgment is the point.

**LLM briefing (`copilot_briefing`).** `app/generate_briefing.py` feeds the gold marts,
the macro regime, and sourced headlines to a local Ollama model (default `gemma4:31b`) and
writes one row per run into the active marts dataset: `briefing_json` (a hard-validated
tour script with per-step targets and figures), `briefing_md` (assembled narration), and
`sources` (the headlines fed to the prompt, kept as the audit trail). The provider seam
structurally refuses to send the real portfolio to a cloud model. This table is outside
dbt lineage, and it is the only served table whose absence the app tolerates (the sidebar
falls back to deterministic lines). Design: `llm_copilot_briefing_design.md`,
`immersive_briefing_design.md`, `briefing_daily_note_design.md`.

**Web tour (`web/`).** A Next.js static export that renders the briefing as six scroll
scenes (macro → sectors → holdings) from a committed JSON bundle
(`web/public/data/anchor.json`, produced by `app/export_web.py`). No backend, no
credentials, demo portfolio only by construction. Playwright covers the figure-to-focus
resolver with unit tests and the built page with a browser smoke test.

## Orchestration and CI

**Dagster (`orchestration/`).** The whole pipeline as one software-defined asset graph via
`dagster-dbt`: holdings, FRED, and yfinance ingestion assets feed the dbt models, which
feed the parquet snapshot export. This is the artifact dbt docs can't produce on their
own, because dbt's lineage stops at its own sources. Runs locally with `make dagster`;
the unattended Dagster+ Serverless deploy is the next ops milestone.

**CI (`.github/workflows/ci.yml`).** Every pull request runs pytest over the ingestion
code, then `dbt build` (dbt-core 1.11) against an isolated `ci` target, then the web
job (`npm run build`, typecheck, lint, Playwright smoke). The dbt docs site is generated
locally as a static page (`site/index.html`) and deployed to GitHub Pages by `docs.yml`.

**dbt engines.** Local work uses dbt-fusion, run from inside `transformation/` because
fusion's `--project-dir` flag mishandles seed paths. CI uses dbt-core on its own runner.
The two can't share `transformation/dbt_packages/`, so keep one engine locally.
