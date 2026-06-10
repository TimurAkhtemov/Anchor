# Anchor — Session Handoff

_Last updated: 2026-06-10. Read alongside `CLAUDE.md` (architecture + working style) and the Google Drive `Anchor Project` folder (`anchor_product_onepager.md`, `anchor_data_flow.md`)._

## Goal

Anchor is a macro-aware personal investment dashboard. Core principle: a forced reading order **macro → sector → holdings**, where each tier is read in the context of the one above. It's a portfolio piece targeting analytics-engineering roles, so the build itself (layered dbt modeling, deliberate design decisions) is the deliverable — not just a working dashboard.

Architecture: `FRED + yfinance → bronze (BigQuery raw) → silver (dbt staging) → gold (dbt marts) → serve (Streamlit)`.

## State of the world (verified this session)

Bronze → silver is **live and green** in BigQuery (`anchor-495115`). Everything below was actually run and verified, not just written:

- **FRED ingestion** → `raw_fred` : 4 series (DFF, CPIAUCSL, UNRATE, DGS10), 44,979 observations.
- **yfinance ingestion** → `raw_yfinance` : 14 tickers, 17,570 price bars (5y daily). Now also captures `market_cap`.
- **Seed** `benchmark_etfs` loaded (14 rows: 11 sector + 3 cap_style).
- **`dbt build`**: PASS=23, 0 errors (4 staging views + 18 tests + 1 seed).
- **End-to-end join verified**: all 6 holdings resolve to both a sector ETF and a cap ETF with zero nulls (see table below). This is effectively a working prototype of the gold-layer join.

| Holding | Sector → ETF | Cap (B) → ETF |
|---|---|---|
| AAPL | Technology → XLK | 4267 Large → SPY |
| JPM | Financial Services → XLF | 838 Large → SPY |
| HIMS | Healthcare → XLV | 6.7 Mid → MDY |
| TALO | Energy → XLE | 2.5 Mid → MDY |
| CVLG | Industrials → XLI | 1.1 Small → IWM |
| IMMR | Technology → XLK | 0.2 Small → IWM |

(AAPL + IMMR are both Technology but different cap tiers — the clearest one-glance proof the two-axis design does something.)

## Key design decisions made (the "why" — don't re-litigate)

1. **Two-axis benchmarking.** Each holding is benchmarked on (a) its **sector** ETF and (b) its **cap-style** ETF (Large>$10B→SPY, Mid $2–10B→MDY, Small<$2B→IWM). Rationale: a single (sector × cap) ETF doesn't exist as liquid instruments — see failed attempts. When the joint cell doesn't exist, benchmark on the marginals.
2. **Generic benchmark model.** A holding has N benchmarks, each an ETF tagged with `benchmark_type` (`sector`, `cap_style`). Comparison is always `holding% − benchmark%`. Adding an axis later = a seed row, not a rewrite. Mapping lives in `seeds/benchmark_etfs.csv`.
3. **Classification is live from yfinance** (`sector`, `market_cap` from `info`). No override dimension — less to maintain, stays honest to current market reality.
4. **Seed keys use yfinance's Yahoo taxonomy, not GICS** (verified exact strings). "Financial Services" not "Financials", "Healthcare" not "Health Care", "Consumer Cyclical" not "Consumer Discretionary", etc. Wrong keys = silent null joins.
5. **Holdings deliberately spread across cap tiers** so both axes are demonstrable (the previous all-large-cap set made the cap axis degenerate).

## Failed attempts / dead-ends (don't retry these)

- **Mapping a holding to "the ETF that contains it"** — fails two ways: yfinance only exposes top-10 holdings (a small-cap holding won't appear), and mega-caps are huge chunks of their own benchmark (AAPL ≈ 12% of XLK, JPM ≈ 11% of XLF) → circularity.
- **(sector × cap) ETF grid** — not buildable. Mid-cap sector ETFs essentially don't exist; small-cap sector ETFs (Invesco PSC\*) are too illiquid to be benchmarks (PSCF: $20M AUM, ~1,566 shares/day). Verified via yfinance AUM/volume.
- **Clustering stocks to derive sectors** — rejected: GICS/Yahoo already gives a clean auditable label, and ML-derived sectors break the product's traceability principle.
- **Authoring seed keys from textbook GICS names** — would have silently null-joined; caught by verifying live yfinance strings first.

## Next steps (in order)

1. **Build the gold layer** — this is the main event and the best learning. Suggested models:
   - Macro tier: per-indicator current value + delta vs prior period + short trend series + source series_id (for traceability footer). Consider a rule-based regime statement.
   - Sector tier: per sector ETF — current price, 1-month % change, today's % change, trend series.
   - Holdings tier: the load-bearing one. Per holding, paired with **both** benchmarks (sector + cap), computed together as a single output: holding price/%, each benchmark's %, relative position (holding% − benchmark%), and an ahead/behind/in-line label against a threshold band. Use the generic benchmark shape (the verified join above is the prototype).
2. **Wire up `models/marts/`** — note `dbt_project.yml` already configures `marts: +materialized: table`, but the dir is empty, so `dbt` warns about an unused config path. The warning clears once the first mart model lands.
3. **Streamlit serve layer** — three-tier top-down layout. Deferred until gold exists.

## Open questions / things to watch

- **Cap axis semantics**: "vs IWM" = "vs small-caps broadly" (all sectors), not a size+sector peer set. Intentional (marginals), but note it in the README limitations.
- **README limitations section** worth writing: cap-weighted sector ETFs mean mega-caps partly benchmark themselves; large-cap-tilted benchmarks; classification inherits yfinance's labeling.
- **Ingestion is `WRITE_TRUNCATE`** (full refresh each run) — fine for now; incremental is a future concern.
- **Minor**: `ingest_fred.py` uses deprecated `datetime.utcnow()` (harmless warning).
- **Dev schema**: models build into `dbt_timurakhtemov` (dev target). Worth confirming the intended prod target schema before serve.

## How to work on this project

See the "Working style" section in `CLAUDE.md`: Socratic (surface decisions, user decides), verify against real data before baking values in, explain the "why" concisely, be honest about caveats, move fast on boilerplate. The user is learning AE as we build and holds the wheel on design calls.
