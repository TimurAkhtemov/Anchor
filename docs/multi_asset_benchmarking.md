# Multi-Asset Benchmarking & Holding Taxonomy

_Status: **superseded 2026-07-01** — the open decisions below are resolved in `docs/make_it_real_design.md` (the locked build spec). Kept as design history. Originally captured 2026-06-10. See also `docs/ingestion_roadmap.md` and `CLAUDE.md` (benchmarking design)._

## The realization

The current `holdings_benchmarks` mart assumes **every holding is an individual
equity**, benchmarked on sector × cap. Real portfolios — especially those of the
calm, long-term investor Anchor is for — hold **equity ETFs, bonds/bond ETFs, cash,
and commodities**, not just single stocks. Benchmarking must become
**asset-class-aware**.

## Unifying principle

**Benchmark a holding against the thing one notch broader / more diversified than
it — but the AXES are asset-class-specific** (the marginals that define that asset
class's risk). A stock is a point in (sector × cap); a thematic ETF is already a
basket whose honest comparison is the broad market; a bond's risk lives on entirely
different axes (duration, credit).

## Asset-class axis map

_(verify all tickers + yfinance `category` strings against live data before baking —
project rule: classification is live from yfinance and uses Yahoo's taxonomy.)_

| Holding | Risk axes (marginals) | Benchmark instruments | Broad benchmark |
|---|---|---|---|
| Equity — single stock | sector × cap | SPDR sector ETFs; SPY/MDY/IWM | SPY / VTI |
| Equity — thematic/sector ETF (QTUM, XLK held) | already a basket | (optional category axis) | **SPY** ("beat the index?") |
| Equity — broad ETF (SPY/VTI held) | *is* the market | — (root; show return + trend) | — |
| **Fixed income — bond / bond ETF** | **duration × credit** | duration: SHY/IEI/IEF/TLT · credit: GOVT/LQD/HYG/MUB/TIP | **AGG / BND** |
| Commodity / alt (GLD, IBIT, REIT) | own category | — | vs category, or none |
| Cash / money market (SGOV/BIL/cash) | — | — | risk-free / T-bill yield, or none |

## The generic design still holds (no gold rewrite)

`benchmark_type` already namespaces axes (`sector`, `cap_style`). Each new asset
class = new `benchmark_type` values + seed rows + asset-class routing:
- Held equity ETF → `market` (→ SPY).
- Bond → `duration` (→ SHY/IEI/TLT), `credit` (→ GOVT/LQD/HYG), and/or `bond_market` (→ AGG).
Adding an asset class is data + a routing rule, not a model rewrite. Same payoff as
the two-axis equity design.

## Product nuance: the middle tier generalizes

Anchor's spine is **macro → context → holdings**.
- For **equities**, the context tier = **sectors** (the current "sector tier" is the
  *equity instance* of a more general context tier).
- For **bonds**, there is no equity sector; the context is the **rate / credit /
  curve environment**.
- The **macro tier fits every asset class** — it's the shared root all holdings read
  against.

## Bonds are the strongest showcase of the macro→holdings thesis

We already ingest **DGS10** (10-year) and **DFF** (fed funds). These *directly* drive
bond prices via duration ("rates +50bps → long-duration TLT −X%"). The macro→holding
causal link is tighter and cleaner for fixed income than for equities — the asset
class that looks like an add-on is where "read holdings in the context of macro"
demonstrates best. Worth prioritizing fixed income right after equity-complete.

## Classification gets richer

Beyond instrument type, the holdings bronze + tickers staging will need:
- `quote_type` — yfinance `quoteType`: `EQUITY` / `ETF` / `MUTUALFUND` / `BOND` /
  `CRYPTOCURRENCY` / … (clean signal for instrument form; better than inferring from
  null sector).
- `asset_class` — `equity` / `fixed_income` / `commodity` / `cash` / `alt`. For
  **funds this is derived from the messy `category` field**, not a clean attribute →
  fragile, must verify. May warrant a maintained `ticker → asset_class` seed for
  funds rather than trusting `category`.
- `sub_style` — the per-asset-class axis values (sector, cap tier, duration, credit).

Latent bug to fix when this lands: `cap_tier`'s `case … else 'Small'` mislabels any
null-`market_cap` holding (i.e. every ETF/bond) as Small-cap. Non-equities must not
receive a cap tier at all.

## Scope recommendation (phased)

1. **Phase 1 — equity-complete (near term):** single stocks (done) + held equity ETFs
   via the `market` axis. Smallest step; keeps the current model clean.
2. **Phase 2 — fixed income:** best macro-tier showcase. duration × credit (or just
   `vs AGG` for a v1), asset-class routing, bond-ETF seed rows.
3. **Phase 3 — commodities / cash:** show as balances; benchmark optional.

Multi-asset arrives with **dynamic holdings ingestion** (real mixed portfolios), so
the bronze schema should reserve `asset_class` + `quote_type` from the start.

## Open decisions (lock when we build)

1. Does Anchor benchmark cash / commodities at all, or just display balances?
2. Bond axes for v1: full duration × credit, or just `vs AGG` (broad)?
3. Fund `asset_class` classification: trust yfinance `category`, or maintain a
   `ticker → asset_class` seed for reliability/auditability?
4. Does the held broad-market ETF (SPY) get a benchmark, or is it explicitly the root?
