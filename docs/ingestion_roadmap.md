# Data Ingestion Roadmap — Freshness & Source Strategy

_Status: exploratory / deferred. Nothing here is built yet. Captured 2026-06-10 while building the holdings gold tier. Read alongside `CLAUDE.md` and `handoff.md`._

## Why this exists

The current pipeline pulls daily prices from **yfinance** via a `WRITE_TRUNCATE`
full refresh. Two freshness problems surfaced:

1. **yfinance's trailing bar is unreliable.** The most-recent session can arrive
   with volume populated but **null OHLC** (its adjusted prices haven't finalized).
   We hit exactly this: the 2026-06-09 bar came back OHLC-null for all 14 tickers.
   Mitigated in-model by filtering `close_price is not null` in
   `int_ticker_returns` / `ticker_trend` (anchor to the latest *complete* close),
   but the root cause is the source.
2. **Being "a day behind" is not intrinsic to market data.** Settled EOD closes are
   final within minutes of the 4pm ET close. We lag because (a) yfinance scrapes
   Yahoo's unofficial endpoints with no SLA and flakes on the newest bar, and
   (b) the pull isn't scheduled around the close.

**Freshness target for Anchor:** EOD-fresh — today's close visible tonight. The
product is a macro→sector→holdings "zoom out, be at ease" dashboard, **not** a
day-trading screen. Realtime/intraday is an explicit anti-goal: it adds cost and a
jittery UX that fights the product's calm framing.

## Target architecture — dual-source split by role

backfill and freshness have opposite requirements, so split them:

```
yfinance   ──(one-time / periodic)──►  deep 5y+ history, bulk, free, flakiness OK
EOD API    ──(nightly, post-close)───►  just the last 1–2 sessions, reliable, small
                     │
                     ▼
          bronze price history  ──►  silver (staging) ──► gold
```

yfinance leaves the critical daily path (its trailing-bar flakiness stops
mattering); a reliable feed owns the one thing it's bad at — the freshest bar.

## yfinance's lifecycle (does it still run daily?)

**No — yfinance never runs daily in the target state.** Three coherent end-states:

- **A. yfinance one-time, EOD daily forever.** Simplest, but *rots*: corporate
  actions retroactively restate adjusted closes, so a frozen yfinance history
  drifts onto a different basis than the EOD tail → silent seam. Only acceptable if
  long-horizon return correctness doesn't matter.
- **B. yfinance periodic re-backfill (weekly/monthly or on corporate actions) +
  EOD daily.** yfinance runs occasionally, off the critical path, purely to keep
  deep history correctly re-adjusted. Pragmatic dual-source interim.
- **C. Single-source on the EOD API, yfinance retired.** If the provider ships deep
  adjusted history (many do, 15–30y), do one final migration pull and drop
  yfinance. One source = no seam, no dual-adjustment problem. Cleanest invariant.

**Lean: aim for C, treat B as the interim.** yfinance is the free convenience
backfill that gets us moving today; its role sunsets. Gated by the adjustment
policy + the provider's history depth (see forks #4 and provider notes).

## Structural decisions (the forks)

### 1. Bronze table shape
`raw_yfinance_prices` lies the moment a second source writes prices.
- **Option:** rename to source-neutral `raw_prices` + a `source` column
  (`'yfinance'` / `'tiingo'` / …), one unified history. **(lean)**
- **Alt:** per-source raw tables, union in staging.
Source-neutral + `source` column makes precedence explicit and is the honest shape.

### 2. Where incrementality lives
`WRITE_TRUNCATE` is fine for backfill, wasteful/fragile nightly.
- **Option:** dbt `incremental` model with `unique_key=(ticker, trading_date)`
  — more demonstrable AE skill, and the grain test we already added becomes its
  enforced contract. **(lean for portfolio value)**
- **Alt:** `MERGE` on `(ticker, trading_date)` in the Python load.

### 3. Source precedence / dedup
Once two sources can supply the same `(ticker, date)`, silver must pick one:
`row_number() over (partition by ticker, trading_date order by source_priority,
ingested_at)`. EOD-API wins where it covers; yfinance fills older history. The
uniqueness test enforces the resolution actually happened.

### 4. Adjustment continuity — THE GATING DECISION
yfinance returns **split/dividend-adjusted** closes by default. If the nightly API
returns **raw** closes, an adjusted history is stitched to a raw tail and every
return spanning the seam is silently wrong. Requirements:
- Provider must give **adjusted** closes (or both, pick consistently).
- New splits shift the *whole* history's adjustment factor → argues for periodic
  re-backfill (end-state B), or single-source (C), over append-forever (A).
- **Decide the adjustment policy BEFORE the provider** — it gates everything else.

## Orchestration
Today: manual `python ingest_*.py`. Target: scheduler that sequences
**ingest → dbt build**, fired post-close (~6pm ET).
- Lightweight / portfolio-friendly: GitHub Actions, or Cloud Scheduler → Cloud Run.
- "Real" orchestration showcase: Airflow / Dagster / Prefect.

## Freshness as a tested contract (the safety net)
Use dbt's native **source freshness** check: assert `raw_prices` max load is within
N hours of expected; fail loudly if a nightly pull stalls. Combined with the grain
test and the defensive last-complete-close fallback, this makes "are we a day
behind?" a *tested* property, not a hope.

## Provider selection criteria (defer actual pick)
Reputable EOD providers to evaluate (verify current free-tier limits — they change):
Tiingo, EOD Historical Data (EODHD), Alpha Vantage, Polygon, Twelve Data, Finnhub.
Evaluate on:
- **Adjusted-close support** (must-have; see fork #4).
- **History depth** (decides whether end-state C is viable → retire yfinance).
- ETF + equity coverage.
- Free-tier rate limits / ticker count.

## The thread
The freshness problem isn't really "which API." It's that **daily freshness should
be an enforced, tested contract** — source freshness + grain + last-complete-close
fallback. The API swap is just what makes that contract *achievable*.

## When we pick this up — first decisions to lock
1. Adjustment policy (fork #4) — gates the provider choice.
2. End-state target: B (dual interim) vs C (single-source) — depends on provider history depth.
3. Bronze shape: source-neutral `raw_prices` + `source` column (recommended).
