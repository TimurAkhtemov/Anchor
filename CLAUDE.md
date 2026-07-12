# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Anchor is a macro-aware personal investment dashboard. The core product principle is a forced reading order: **macro environment → sector performance → individual holdings**. Each tier is read in the context of the one above it.

Architecture: `FRED API + yfinance → bronze (BigQuery raw tables) → silver (dbt staging) → gold (dbt relationship-framed models) → serve (Streamlit)`

This is a portfolio project targeting analytics engineering roles — demonstrating the full AE arc, not just pipeline plumbing.

## Working style (how to collaborate on this project)

The user is learning analytics engineering as we build, and wants to hold the wheel. Match this style:

- **Socratic, not autopilot.** On real decisions (modeling, benchmarks, materialization, what belongs in gold vs. the UI), surface the choice, explain the tradeoff in a sentence or two, and let the user decide. Build autonomously only on boilerplate (rename/typecast staging, YAML tests, mechanical edits).
- **Verify against real data before baking it in.** When a value will be hardcoded into a model, seed, or join key, check it against the actual source first (e.g. query BigQuery, probe yfinance) rather than asserting from memory. Several traps this session were caught this way (yfinance uses Yahoo's sector taxonomy, not GICS; mid-cap sector ETFs don't exist; example holdings were all large-cap).
- **Explain the "why," concisely.** One line on the reasoning behind a decision, not a lecture. Name the general principle when there is one ("when the joint cell doesn't exist, benchmark on the marginals").
- **Be honest about caveats and limitations** — flag them as analytical maturity, not hide them. Don't over-claim "done": if something was built but not yet run/verified, say so explicitly.
- **Move fast, keep momentum.** Don't pad. Pause at clean, committable chunks.

## Infrastructure

- **Data warehouse**: Google BigQuery (`anchor-495115`)
- **Credentials**: Service account key at `~/.dbt/anchor-bigquery-key.json`
- **dbt profile**: `anchor` (configured in `~/.dbt/profiles.yml`)
- **Environment variables**: `FRED_API_KEY` in `.env` (loaded via python-dotenv)

## Common commands

```bash
# Run ingestion (from repo root, with venv active)
python ingestion/ingest_fred.py
python ingestion/ingest_yfinance.py              # ticker universe derives from held tickers + benchmark ETFs
python ingestion/ingest_holdings.py --from-csv data/sample_portfolio.csv --portfolio demo
python ingestion/ingest_holdings.py --from-snaptrade --portfolio real   # requires .env secrets

# dbt — cd into transformation/ first (the dbt project dir). Local engine = dbt-fusion
# (~/.local/bin/dbt); CI uses dbt-core 1.11. Run from the project dir, NOT via
# --project-dir: fusion mishandles seed paths under --project-dir.
cd transformation
dbt run                          # build all models
dbt run --select staging         # staging models only
dbt run --select marts           # gold/mart models only
dbt test                         # run all tests
dbt build                        # run + test together (dev sandbox; demo holdings by default)
dbt build --target prod          # materialize the prod datasets (anchor_*)
dbt build --target prod-private --vars '{holdings_source: real}'   # real portfolio, isolated datasets

# Serve layer (Streamlit dashboard, reads anchor_marts via the data seam)
streamlit run app/app.py
python app/export_snapshot.py    # refresh the committed snapshot the live demo reads
python app/generate_briefing.py --portfolio demo   # LLM briefing -> copilot_briefing (needs Ollama running)

# Web tour surface (web/ — Next.js static export; heed web/AGENTS.md before writing code there)
python app/export_web.py                      # refresh committed web/public/data/anchor.json (or: make export-web)
cd web && npm run dev                         # local dev
cd web && npm run build                       # static export -> web/out/ (what CI and Vercel run)
cd web && npm run build && npm run test:e2e   # Playwright: resolver units + browser smoke (serves out/)

# Pipeline steps (tool-agnostic; the Makefile is what Dagster wraps as assets)
make ingest | make ingest-holdings-demo | make ingest-holdings-real | make build-prod | make build-private | make briefing | make briefing-real | make snapshot | make refresh
```

Note: `make snapshot`/`make refresh` may need
`GOOGLE_APPLICATION_CREDENTIALS=~/.dbt/anchor-bigquery-key.json` for `app/export_snapshot.py`
unless Application Default Credentials are configured. `make refresh` only touches the
demo world (ingest → build-prod → briefing → snapshot; the briefing step needs local
Ollama, and its failure halts the chain before the snapshot exports — strict by design).
Real-portfolio builds are always a manual `make build-private` (+ `make briefing-real`),
never part of the scheduled/public pipeline. Optional `.env` config for the briefing:
`ANCHOR_BRIEFING_PROVIDER` (`ollama` default; `anthropic` = cloud model, DEMO world only —
a structural guard in `build_provider` hard-fails cloud + real before any network call;
**scope: the cloud path is deferred until public deployment — everything stays local/Ollama
for the MVP**, no API key in `.env` by design),
`ANCHOR_BRIEFING_MODEL` (default `gemma4:31b` — won the post-ship A/B on verdict/attribution
discipline; ~4 min/generation is fine at pipeline time), `OLLAMA_HOST`,
`ANCHOR_BRIEFING_CLOUD_MODEL` (default `claude-opus-4-8`), `ANTHROPIC_API_KEY`.

Live: dashboard → anchor-dashboard.streamlit.app · dbt docs → timurakhtemov.github.io/Anchor

## Data sources

**FRED** (`raw_fred` dataset in BigQuery):
- `raw_fred_series` — metadata for 4 series: `DFF`, `CPIAUCSL`, `UNRATE`, `DGS10`
- `raw_fred_observations` — long-format time series (series_id, date, value)

**yfinance** (`raw_yfinance` dataset in BigQuery):
- `raw_yfinance_tickers` — metadata for a **~44-ticker dynamic universe**, `quote_type` included (`EQUITY`/`ETF`/`MUTUALFUND`/`MONEYMARKET` — the classification spine)
- `raw_yfinance_prices` — daily OHLCV bars (long format, one row per ticker/date)
- The universe is *derived* each ingestion run, not hardcoded: held tickers (demo ∪ real) ∪ every `benchmark_etfs` seed ETF — all 11 SPDR sector ETFs + cap-style (`SPY, MDY, IWM`) + market/bond-market/duration ETFs (`AGG, SHY, IEF, TLT`)

**Holdings** (`raw_holdings` dataset in BigQuery):
- `holdings_demo` — committed sample portfolio (`data/sample_portfolio.csv`), `WRITE_APPEND` with an `as_of` batch date
- `holdings_real` — private, gitignored; loaded from a Fidelity CSV export or a live SnapTrade pull, never committed
- `fund_classifications_real` — private fund → asset-class override mapping (real funds only; the demo equivalent is the committed `fund_classifications` seed)

## dbt model layers

_The dbt project lives in `transformation/`; the paths below are relative to it._

**Staging** (`models/staging/`) — silver layer. Rename/typecast only. No business logic.
- `stg_fred__series`, `stg_fred__observations`
- `stg_yfinance__tickers`, `stg_yfinance__prices` (`prices` is incremental in prod)
- `stg_holdings__positions` — demo/real positions (world picked by the `holdings_source` var), deduped to the latest `as_of` per (account, ticker)
- `stg_holdings__fund_classifications` — unions the committed demo seed with the private real-fund CSV; the only place the two worlds merge

**Intermediate** (`models/intermediate/`) — shared computation, silver layer.
- `int_ticker_returns` — per-ticker returns to a common as-of date, anchored to the benchmark-ETF trading calendar (a holding's oddball bar can't move the as-of date for everyone else)
- `int_macro_indicators`, `int_sector_rate_comovement`
- `int_holdings_classified` — one valued row per held ticker: `asset_class` (override mapping wins over `quote_type`-derived fallback), `cap_tier` (equities only, never inherited by funds), dual-source `valuation_source` (`market` = `quantity × latest_close`, `source` = the import's own value — cash NAV / plan-internal instruments)
- `int_benchmark_routing` — resolves each holding to its benchmark set per asset class; flags self-pairings (`is_self`, the root rule)

**Snapshot** (`snapshots/`) — history-preserving metadata.
- `snap_yfinance_tickers` — SCD2/check snapshot for ticker metadata changes; prod writes to `anchor_snapshots`.

**Gold / marts** (`models/marts/`) — relationship-framed outputs the dashboard reads. **Built, tested, deployed.**
- `macro_indicators` (cards) + `macro_trend` (sparklines) + `macro_regime` (regime banner)
- `sector_performance` — all 11 SPDR sector ETFs, contextualized against the macro regime
- `portfolio_composition` — the sizing mart: one row per held ticker (incl. cash + roots) with weight, market value, cost basis, unrealized gain, `valuation_source`, `is_root`
- `holdings_benchmarks` — holding % paired with each asset-class-routed benchmark % as one row (not two cuts the UI joins); up to 5 axes per holding
- `ticker_trend` — sparkline series for every ticker, scoped to the active world's universe

**Serve-layer table (not dbt):** `copilot_briefing` — the LLM daily briefing artifact,
written into the active marts dataset by `app/generate_briefing.py` (local Ollama; real
portfolio structurally requires a local provider). One row, grain `horizon='all'`;
`sources` JSON persists the headlines fed to the prompt as the audit trail;
`briefing_json` carries the structured tour script (per-step targets/figures,
hard-validated — see `docs/immersive_briefing_design.md`) and `briefing_md` is
assembled from its narrations. The briefing's next evolution is designed and locked:
`docs/briefing_daily_note_design.md` (v3 "Daily Note" — active arc on
`feat/briefing-daily-note`; read it before briefing/web work). Not in dbt
lineage (documented limitation); the only served table whose absence the app tolerates
(sidebar falls back to the deterministic v0 lines). Design:
`docs/llm_copilot_briefing_design.md`.

**Lineage / contracts.**
- `models/marts/_exposures.yml` declares the Streamlit dashboard and parquet snapshot export as downstream consumers of all served marts, including `portfolio_composition`.
- `holdings_benchmarks` and `portfolio_composition` both have enforced dbt contracts; if their output columns/types drift, dbt should fail before the app silently breaks.
- **Privacy isolation.** A `prod-private` target (`anchor_*_private` datasets) + `holdings_source` var (`demo` default) + a compile-time `on-run-start` hook (`assert_portfolio_isolation`) that fails the build if `holdings_source: real` is ever combined with a public target (`prod`/`ci`). The public contract structurally cannot be built from real data.

## Benchmarking design (asset-class-aware, up to 5 axes)

Routing is per `asset_class` (`equity`, `fixed_income`, `commodity`, `cash`, `alt`), all through one generic benchmark model — no per-class special-casing in the mart:

- **Equity stocks** — 2 axes: **sector** (vs its SPDR sector ETF, e.g. XLK) + **cap-style** (vs its market-cap tier: Large (>$10B)→SPY, Mid ($2–10B)→MDY, Small (<$2B)→IWM). Why two axes rather than one (sector × cap) ETF: that grid can't be filled with liquid instruments (mid-cap sector ETFs barely exist; small-cap sector ETFs trade ~1.5k shares/day). When the joint cell doesn't exist, benchmark on the marginals.
- **Equity funds** (held ETFs/mutual funds classified `equity`) — 1 axis: **market** (vs SPY — "did it beat the index?").
- **Fixed income** — up to 2 axes: **bond_market** (vs AGG, always) + **duration** (vs SHY/IEF/TLT, only when the fund-classification mapping assigns a `sub_style` bucket — null `sub_style` = skip the axis, not a bug).
- **Cash, commodity, alt** — **0 axes in v1.** No natural single-ETF comparison exists yet for commodities; cash and alts (plan-internal instruments) aren't benchmarkable at all. These still appear in `portfolio_composition` (weight, value) — display-only, never silently dropped (a guardrail test asserts the 0-axis count is intentional, not a routing gap).

**Generic benchmark model:** a holding has N benchmarks, each an ETF tagged with `benchmark_type` (`sector`, `cap_style`, `market`, `bond_market`, `duration`). The comparison is always `holding% − benchmark%`, computed per benchmark. The mapping lives in the `benchmark_etfs` seed (`transformation/seeds/benchmark_etfs.csv`): `benchmark_type, lookup_key, etf_ticker, etf_name`. Nuance on the "just a seed row" claim: a **new axis for an existing asset class** (e.g. a credit axis for bonds) really is a seed row — the routing model already loops over whatever axes the seed defines for that class. A **new asset class** is more than that: a seed row *plus* one routing branch in `int_benchmark_routing`, a new guardrail case (the axis-count test needs to know what "correct" looks like for the class), and an `accepted_values` addition on the `holdings_benchmarks` contract.

**Classification: live from yfinance for stocks, a maintained override table for funds.** `sector` and `market_cap` come straight from the yfinance `info` fields for individual equities — no override needed. Funds are different: yfinance's `category` is `None` for Fidelity mutual funds (an equity fund and a bond fund are metadata-indistinguishable), so `asset_class`/`sub_style` for funds come from a maintained mapping — a true **override** (checked before the `quote_type`-derived fallback, not a fallback itself) — committed seed (`fund_classifications.csv`) for demo funds, a private gitignored CSV for real funds. A guardrail test fails the build on any held ETF/mutual fund with no classification row.

**Valuation is dual-source (`valuation_source`).** Market-valued rows (`market`) recompute `quantity × latest_close` so weights stay fresh between imports; source-valued rows (`source`) keep the import's own value — used for cash (fixed $1 NAV, no price series) and any instrument with no public close (plan-internal alts). A guardrail test (`assert_source_valuation_is_intentional`) fails the build if any *other* asset class (equity, fixed_income, commodity) is ever source-valued — that would mean a normally-priced instrument transiently has no yfinance close, which must fail loudly rather than silently go stale.

⚠️ **yfinance uses Yahoo's sector taxonomy, not GICS names.** The seed's `lookup_key` must match the exact strings yfinance emits or the join silently returns null. Verified strings: `Technology, Financial Services, Healthcare, Energy, Industrials, Communication Services, Consumer Cyclical, Consumer Defensive, Utilities, Real Estate, Basic Materials`.

## Key modeling constraint

Holding % and benchmark % must be computed together in gold so each pairing is a single model output. The dashboard never joins two independent datasets — that framing belongs in gold. The `ahead/behind/in-line` label (sign of holding% − benchmark%, against a threshold band) is computed here too.

## Long-term direction

**Dynamic portfolio ingestion is built** — the static watchlist is retired. A `raw_holdings` bronze dataset (`holdings_demo`/`holdings_real`, `ticker, quantity, cost_basis_total, as_of, source, …`) feeds the gold layer via SnapTrade (live Fidelity link) or a Fidelity CSV export; see `docs/make_it_real_design.md` for the locked design and `handoff.md` for what shipped and the honest deviations from it.

Next follows the grounding-first sequence in the README: Dagster+ Serverless for the
unattended post-close run, reliable settled EOD ingestion, portfolio history centered on
allocation drift and contribution, a non-advisory contextual briefing, then intent and
reflection tools. Brokers beyond Fidelity and multi-user (`user_id` + row-level
isolation) are later platform expansion, not the next product milestone.
