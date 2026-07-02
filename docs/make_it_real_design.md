# "Make It Real" — Dynamic Holdings + Multi-Asset Benchmarking (v1 Design)

_Status: **locked design, approved 2026-07-01** — supersedes the exploratory
`docs/holdings_ingestion.md` and `docs/multi_asset_benchmarking.md` (kept as design
history; their open decisions are resolved here). This is the build spec for the
"make it real" capstone._

## Goal

Replace the static 6-stock watchlist with **real portfolio holdings** (Fidelity),
benchmarked **per asset class**, sized by **actual position weights**, with a strict
**demo/private split**: the public deploy only ever sees a committed sample
portfolio; real holdings build into private datasets viewed locally.

In one sentence: holdings stop being config and become data; everything downstream
(ticker universe, classification, benchmark routing, sizing) derives from them.

## Decisions locked (with why)

| # | Decision | Why |
|---|---|---|
| 1 | **Full multi-asset v1**: stocks, equity funds, bond funds, cash | The real portfolio contains all four — scope driven by real data, not hypotheticals |
| 2 | **Sizing modeled in gold** (weights, allocation, unrealized gain) | Sizing is the point of "real"; holding-vs-whole-portfolio is a relationship, and relationships live in gold |
| 3 | **Demo/real = separate datasets** (`anchor_*` vs `anchor_*_private`) | The leak-prevention guarantee is structural (exporter physically can't see private data), not a WHERE clause |
| 4 | **Bond duration axis in v1** (alongside `bond_market`) | Tightest macro→holdings causal link in the product (DGS10 already on the dashboard); cost is a few seed rows |
| 5 | **SnapTrade in v1, sequenced last** | The live-connection flex; lands after CSV proves the models, so external-API friction can only delay itself |
| 6 | **Classification in dbt** from yfinance `quote_type` + a fund seed; never in the loader | Business logic belongs where it's versioned and testable; bronze stays faithful capture |
| 7 | **Fund classification is a maintained mapping, not derived** | Verified live 2026-07-01: yfinance `category` is **None for Fidelity mutual funds** — FXAIX (equity) and FXNAX (bond) are indistinguishable from metadata. Alternative sources ruled out (see appendix). A guardrail test fails the build on any unclassified held fund |
| 8 | **Real-fund classifications stay out of the repo** | Committed seed covers demo funds only; real funds live in a gitignored CSV landed as a private bronze table (staging unions the two). "Nothing about the real portfolio in the repo" stays absolute — not even tickers |
| 9 | **Holdings load appends with `as_of`**; staging reads latest | Banks position history from day one for the future portfolio-over-time milestone; costs nothing now |
| 10 | **Market value recomputed** as `quantity × latest_close` in gold (CSV's own value kept in bronze for audit) | Weights stay fresh between imports. Exception: cash-like rows use the source value (fixed $1 NAV / no price series) |
| 11 | **Root rule**: a holding whose routed benchmark is itself (held SPY → market axis SPY) suppresses the self-pairing; flagged `is_root` in composition | Holding-vs-itself is 0 by construction. VOO-vs-SPY *stays* — tracking difference is a real comparison |
| 12 | **Cap tier computed only for equities** | Fixes the catalogued `else 'Small'` bug that would mislabel every fund (null `market_cap`) as Small-cap |
| 13 | **Sector ETF ingestion broadens 5 → all 11 SPDRs** | Real holdings will hit sectors beyond the current 5; the seed already lists all 11; sector tier fills out — intentional demo improvement |
| 14 | **Multi-user is a documented seam, not built** | Single-user product; demo/private is dataset-level tenancy at N=2. Evolution path documented below |

## Architecture

```
 Fidelity CSV export ──┐
 SnapTrade pull ───────┼──► raw_holdings.holdings_real   (private)
 sample portfolio CSV ─┴──► raw_holdings.holdings_demo   (committed sample)
                                    │
        yfinance metadata + prices  │   universe = held tickers ∪ benchmark ETFs
                                    ▼
              staging: positions (latest as_of) · tickers (+ quote_type) · prices
                                    │
                                    ▼
              intermediate: classify (asset_class, sub_style, cap tier for
              equities only) · route to benchmarks per asset class
                                    │
                                    ▼
              gold: holdings_benchmarks (holding × benchmark pairings)
                    portfolio_composition (sizing: weights, value, gain, cash)
                                    │
                          demo world ─► anchor_marts ─► snapshot ─► public app
                          real world ─► anchor_marts_private ─► local app only
```

## Bronze

**One loader, `ingestion/ingest_holdings.py`**, normalizes to a common schema and
writes `raw_holdings.holdings_demo` or `holdings_real`:

- `--from-csv <file> --portfolio demo|real` — parses a **Fidelity positions
  export**. The committed `data/sample_portfolio.csv` is in Fidelity's format, so
  the demo path exercises the real parser. Quirks handled here and only here:
  `**` ticker suffixes stripped; no-symbol rows ("Pending Activity") kept with null
  ticker; numeric cleanup (`$`, `,`, `--`). Parser is validated against a real
  export before the format is baked in (project rule).
- `--from-snaptrade --portfolio real` — phase 2; same schema, `source='snaptrade'`.

**Schema** (faithful capture, no business logic):
`account_number, account_name, ticker, description, quantity, price, market_value,
cost_basis_total, as_of (DATE), source ('sample'|'csv'|'snaptrade'), ingested_at`.
**WRITE_APPEND**; staging dedupes to the latest `as_of` (then latest `ingested_at`)
per (account, ticker).

**yfinance ingestion changes** (`ingest_yfinance.py`):
- Metadata pull adds `quoteType` → `quote_type` column on `raw_yfinance_tickers`.
- **Ticker universe becomes derived**: distinct held tickers (demo ∪ real, read from
  the holdings bronze tables) ∪ all `benchmark_etfs` seed ETFs. Fallback to the seed
  ETFs alone if holdings tables don't exist yet. Prices are public market data — one
  shared price table serves both worlds; privacy scoping happens in the marts.
- Benchmark ETF set grows: all 11 SPDR sector ETFs + SPY/MDY/IWM + AGG/SHY/IEF/TLT.

## Silver / intermediate

- `stg_holdings__positions` — typecast, latest-`as_of` dedupe, null ticker →
  `'CASH'` pseudo-ticker (accepted collision risk: no liquid US ticker "CASH").
- `stg_yfinance__tickers` gains `quote_type`. The SCD2 snapshot
  (`snap_yfinance_tickers`) adds `quote_type` to its `check_cols` (additive).
- `int_holdings_classified` — one row per held position with:
  - `asset_class`: `EQUITY` → `equity` · `MONEYMARKET` or `'CASH'` → `cash` ·
    `ETF`/`MUTUALFUND` → from the **fund classification mapping** (committed seed
    `fund_classifications.csv`: `ticker, asset_class, sub_style` for demo funds;
    private table `raw_holdings.fund_classifications_real` for real funds; staging
    unions them). `sub_style` = duration bucket for bonds (`short`/`intermediate`/
    `long`); **null sub_style = skip the duration axis** (e.g. held AGG is the root,
    not "vs IEF").
  - `cap_tier`: computed **only when** `asset_class = 'equity'` and `quote_type =
    'EQUITY'`; null otherwise.
- `int_benchmark_routing` — resolves each holding to its N benchmarks via
  `benchmark_etfs`, per the routing table below. Self-pairings dropped (root rule).

## Gold

**Benchmark routing** (lookup_key = the holding attribute each axis routes on):

| Asset class | Axes | lookup_key → benchmark |
|---|---|---|
| Equity (stock) | `sector` + `cap_style` | sector name → SPDR ETF · cap tier → SPY/MDY/IWM |
| Equity fund | `market` | `'equity'` → SPY |
| Fixed income | `bond_market` + `duration` | `'fixed_income'` → AGG · sub_style → SHY/IEF/TLT |
| Cash | — | never benchmarked; composition only |

New `benchmark_etfs` seed rows (ETF names verified against yfinance at seed time):

```
market,equity,SPY,...
bond_market,fixed_income,AGG,...
duration,short,SHY,...
duration,intermediate,IEF,...
duration,long,TLT,...
```

**Two marts, two grains:**

- `holdings_benchmarks` — same name, same grain (holding_ticker × benchmark_type),
  now driven by positions and routed per asset class. Gains `asset_class`,
  `quote_type`, `weight_pct`; `sector`/`market_cap`/`cap_tier` become nullable
  (funds). Cash and roots never appear here. Contract updated accordingly.
- `portfolio_composition` (new) — one row per held ticker **including cash and
  roots**, aggregated across accounts: `ticker, description, asset_class,
  quote_type, sub_style, quantity, latest_close, market_value, weight_pct,
  cost_basis, unrealized_gain_pct, is_root, as_of_date`. Cash rows: value from
  source, null gain. Weights = share of total portfolio market value.

`ticker_trend` scopes to the world's universe (held ∪ benchmark ETFs) so demo marts
— and therefore the public snapshot — never mention a real ticker. `sector_performance`
/ macro marts are world-independent (identical in both builds).

The UI reads composition as the driving list and attaches benchmark rows by ticker —
master-detail on one entity, not a recomputed relationship (those stay in gold).

**Honest caveat carried to README:** quantities are as-of the last import; prices
are daily. Market value mixes the two until the next import (mitigated by SnapTrade
auto-sync; solved by scheduled pulls later).

## Privacy plumbing

- New dbt target **`prod-private`** (same SA key, default dataset `anchor_private`);
  `generate_schema_name` routes it to `<custom_schema>_private`
  (`anchor_marts_private`, etc.) — full layer isolation, same pattern as prod.
- Var **`holdings_source: demo|real`** (default `demo`) picks the bronze table
  `stg_holdings__positions` reads.
- **Compile-time interlock**: building `--target prod` (or `ci`) with
  `holdings_source: real` raises a compile error via a macro assertion. The public
  contract cannot be built from real data, even by mistake.
- Real inputs live in gitignored **`data/private/`** (Fidelity CSV export +
  `fund_classifications_real.csv`). `.env` gains SnapTrade secrets (already
  gitignored — verify).
- `make build-private` wraps `dbt build --target prod-private --vars
  '{holdings_source: real}'`. CI and the Dagster daily graph stay demo by default.
- Snapshot exporter (`app/export_snapshot.py`) is untouched: it reads
  `anchor_marts` only. No filter to forget.

## Serve layer

- `app/data.py`: `ANCHOR_PORTFOLIO=real` env switch points `_read()` at
  `anchor_marts_private` (bigquery source only; snapshot source is demo by
  construction). New `portfolio_composition()` reader.
- `app/app.py` holdings tier becomes **composition-driven**: iterate
  `portfolio_composition` grouped by asset class (equities → fixed income → cash),
  each card showing weight, market value, unrealized gain, with benchmark rows
  attached by ticker. Cap-tier chip only for equities; cash renders as a balance
  row; roots get a "market root" badge. A small **allocation bar** (weight by asset
  class) heads the tier. Ahead/behind rollup counts per axis within asset class.
- Sector tier: no code change; fills to 11 sectors from data.
- Optional follow-up (not v1): "hide amounts" toggle for screen-sharing real mode.

## SnapTrade (phase 2 of the milestone)

- One-time `ingestion/snaptrade_connect.py`: register SnapTrade user → print hosted
  portal URL → user completes Fidelity login in browser (credentials never touch our
  code) → `SNAPTRADE_USER_SECRET` stored in `.env`.
- Recurring `ingest_holdings.py --from-snaptrade`: SDK positions pull → normalize →
  append to `holdings_real`, `source='snaptrade'`.
- Secrets: `SNAPTRADE_CLIENT_ID`, `SNAPTRADE_CONSUMER_KEY`, `SNAPTRADE_USER_ID`,
  `SNAPTRADE_USER_SECRET` — `.env` only, never committed.
- Free tier: 1 user / 5 connections — fits. Read-only scope. Revocable at broker or
  aggregator.
- Sequencing is the risk control: CSV path proves the models end to end first.

## Demo sample portfolio (fixture + showroom)

Designed to exercise **every routing branch**: the existing 6 stocks (AAPL, JPM,
HIMS, TALO, CVLG, IMMR — continuity, both equity axes) + VOO (equity ETF → market,
honest near-zero tracking diff) + SPY (root) + BND (bond ETF → bond_market +
duration) + FXAIX (equity mutual fund — the seed-required path) + FXNAX (bond
mutual fund → both bond axes) + SPAXX (cash) + a pending-activity row (parser
edge case). Plausible fake quantities/costs.

## Tests & validation

- **pytest** on the CSV parser (ticker normalization, pending-activity, numerics).
- dbt: contracts on both marts; grain uniqueness; `accepted_values` on
  `asset_class`; **per-asset-class axis-count guardrail** (equity → both axes,
  fixed income → bond_market + duration-when-sub_style, equity fund → market);
  **fund-coverage guardrail** (held ETF/MUTUALFUND without a classification row
  fails the build); weights sum to 100 ± ε.
- End-to-end: `dbt build` (demo) green; `dbt build --target prod-private` with real
  data green locally; app verified in both modes; snapshot re-export inspected
  (demo tickers only); CI green.
- Verify-before-baking checkpoints during implementation: real Fidelity CSV column
  format; ETF seed names; SPAXX/FXAIX price-history behavior in yfinance.

## Ops

- Dagster: new `ingest_holdings_demo` asset upstream of `ingest_yfinance` (universe
  dependency) and mapped to the `raw_holdings` dbt source. Real/SnapTrade pulls stay
  manual for now (not in the public daily graph).
- Exposures: dashboard exposure gains `portfolio_composition`.
- Docs: dbt docs regenerate; README (architecture, limitations, roadmap), handoff,
  CLAUDE.md refreshed at the end.

## Commit sequence (each buildable, reviewable)

1. Holdings loader (CSV mode) + sample portfolio + bronze source defs + parser tests
2. yfinance `quote_type` + derived universe + 11 sectors + bond benchmark ETFs
3. Staging/intermediate + classification seeds + guardrail tests
4. Gold rework (`holdings_benchmarks`, `portfolio_composition`) + contracts
5. Privacy plumbing (target, schema routing, interlock, Makefile, gitignore)
6. Serve layer (data seam + composition-driven holdings tier)
7. SnapTrade (connect + pull)
8. Ops (Dagster asset, exposures, docs, README/handoff)

## Out of scope for v1

Portfolio-over-time UI (data banks now via `as_of` appends) · credit axis for bonds
(seed rows later) · generalized bond context tier · private *deploy* (real = local
only) · multi-user (below) · EOD API migration (`docs/ingestion_roadmap.md`) ·
brokers beyond Fidelity.

## Multi-user evolution (documented seam, deliberately unbuilt)

Where holdings *rest* is already right (warehouse, IAM) — the CSV is transport, not
storage. A platform version changes: (1) every bronze row gains a `user_id`;
(2) isolation slides from dataset-level (demo/private, N=2) to row-level policies
at N=many; (3) ingestion doors become app upload (TLS → landing table, file
discarded) or the OAuth aggregator flow — which SnapTrade phase 2 already builds at
N=1; (4) per-user secrets move from `.env` to a secrets manager. The dbt models are
largely unchanged — the payoff of keying bronze correctly.

## Appendix — live-verified classification behavior (2026-07-01)

| Ticker | quoteType | category | sector | marketCap |
|---|---|---|---|---|
| AAPL | EQUITY | None | Technology | 4.32T |
| SPY | ETF | 'Large Blend' | None | None |
| FXAIX | MUTUALFUND | **None** | None | None |
| FXNAX | MUTUALFUND | **None** | None | None |
| SPAXX | MONEYMARKET | None | None | None |
| AGG | ETF | 'Intermediate Core Bond' | None | None |
| TLT | ETF | 'Long Government' | None | None |

Implications baked into this design: `quote_type` is the reliable spine
(MONEYMARKET even self-identifies); `category` cannot classify mutual funds (the
fund seed is *required*, not a preference); `marketCap` is null for all funds (cap
tier must be equity-only). ETF `category` strings exist and can serve as a future
cross-check test against the seed — never as the routing source.

### Alternatives to the maintained fund seed — checked and ruled out (2026-07-01)

Pressure-tested (by Timur) before locking decision 7, since "hand-maintain a
mapping" deserved a challenge:

- **SnapTrade positions API** — `security_type` for a mutual fund is just `oef`
  (Open Ended Fund); no asset_class/category/sector anywhere in the symbol schema.
  Same ceiling as yfinance `quote_type`. Key insight: the live broker connection
  removes *transport* friction (CSV export/upload), not *classification* friction —
  two separate frictions, easy to conflate.
- **OpenFIGI** — `marketSector`/`securityType2` classify the security *wrapper*
  ("Equity" for any fund share), not what the fund holds inside.
- **SEC EDGAR (Form N-PORT)** — the only free source with ground truth (funds file
  actual portfolio holdings quarterly), but no ticker→asset_class endpoint: it
  means ticker→series/class-ID mapping plus quarterly XML parsing. Real engineering
  for a problem that costs ~2 minutes per newly-added fund.
- **Financial Modeling Prep** — a fund sector-weighting endpoint *might* reveal
  asset class indirectly; unconfirmed (needs a live key + test call, not
  docs-reading). Not load-bearing for v1 either way.

Net: nothing removes the manual seed without paying for Morningstar-grade data or
building a filings parser that costs more than what it replaces. The seed +
fail-loud coverage guardrail stands.
