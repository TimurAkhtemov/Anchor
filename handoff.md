# Anchor — Session Handoff

_Last updated: 2026-06-10. The **`README.md` is now the canonical project doc** —
architecture, model map, design decisions, limitations, roadmap. Read it first.
This file is just the lean "current state + what's next" pointer. Also see
`CLAUDE.md` (working style) and `docs/` (deferred roadmaps)._

## State of the world

**Bronze → silver → gold is complete, tested, and green — `dbt build` = 92/92.**
The full `macro → sector → holdings` spine is built and verified against real data.

Gold marts (all in `models/marts/`):
- **Macro:** `macro_indicators` (cards), `macro_trend` (sparklines), `macro_regime` (regime banner)
- **Sector:** `sector_performance` (+ `int_sector_rate_comovement`)
- **Holdings:** `holdings_benchmarks` (two-axis, the load-bearing one)
- **Shared:** `ticker_trend`, `int_ticker_returns`, `int_macro_indicators`

Bronze→silver was already live (FRED 4 series / 44,979 obs; yfinance 14 tickers /
17,570 bars) and remains green. Models build into dev schema `dbt_timurakhtemov`.

## Next steps (in order)

1. **Streamlit serve layer** — the only remaining piece of the original arc. Three-tier
   top-down layout reading directly from the six marts. Macro cards + regime banner on
   top, sectors (with co-movement) beneath, holdings (two-axis, ahead/behind) at the
   bottom. Sparklines come from `macro_trend` / `ticker_trend`.
2. **Roadmap items (designed, not built)** — see `docs/`:
   - `docs/multi_asset_benchmarking.md` — held ETFs + bonds (asset-class-aware axes).
   - `docs/ingestion_roadmap.md` — freshness/source strategy (EOD API, post-close schedule).
   - Dynamic holdings ingestion (`holdings` bronze table) replacing the static watchlist.

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
