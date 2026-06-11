# Dynamic Holdings Ingestion & Fidelity Connection

_Status: exploratory / deferred. Nothing built. Captured 2026-06-11. This is the
"make it real" capstone — replacing the static watchlist with real holdings. Couples
tightly to `docs/multi_asset_benchmarking.md` (real portfolios force multi-asset) and
relates to `docs/ingestion_roadmap.md` (price-data freshness)._

## Goal

Replace the static 6-stock watchlist with **dynamic, real holdings** feeding a
`holdings` bronze table the gold layer joins against. Two surfaces, deliberately split:

- **Demo / public** — a committed **sample portfolio** seed. What the publicly deployed
  dashboard shows. No real financial data in the repo or the public URL.
- **Real / private** — the user's actual Fidelity holdings, kept **private** (local, or
  behind auth). Never committed; never shown on the public deploy.

The holdings *source* must be swappable (sample seed ⇄ real connection) via config/env,
so the same models serve both.

## Connection research verdict (2026-06)

Fidelity has **no official public API** for retail brokerage accounts, so "connect
Fidelity" means an aggregator or a manual export. Researched options:

| Path | Fidelity support | Cost for this use | Verdict |
|---|---|---|---|
| **CSV export** | Native (Fidelity positions export) | Free | **v1** — zero integration/auth risk, real data today |
| **SnapTrade** | **GA (US) 2026-05-11**, read-only | **Free**: 1 connected user, up to 5 connections, personal use | **Live path** — purpose-built for reading brokerage positions |
| **Plaid Investments** | Gated (Growth/Custom plan + ~8wk delay); contentious Fidelity history | Higher tier / delay | Avoid for Fidelity |
| MX / Yodlee | enterprise | — | overkill |

**Chosen path: CSV-export first → SnapTrade for the live connected version.** SnapTrade
is read-only (we only need positions, not trading), Fidelity is GA, and the free tier
is exactly "one personal user, a few accounts."

## Phased plan

1. **Phase A — CSV import (v1).** A small loader parses a Fidelity positions CSV into the
   `holdings` bronze table. Proves the dynamic-holdings + multi-asset model with *real*
   numbers, no OAuth. Also doubles as the demo path (a sample CSV/seed).
2. **Phase B — SnapTrade live connection.** OAuth-style connect flow → pull positions via
   SnapTrade's holdings endpoint → land in `holdings` bronze. Auto-syncable.
3. **Phase C — demo/real split hardening.** Config/env toggle; public deploy pinned to the
   sample portfolio, real data private.

## `holdings` bronze schema (reserve multi-asset columns from day one)

- `account` — source account id/label (supports multiple accounts later)
- `ticker` — security symbol
- `quantity`, `cost_basis`, `market_value`
- `asset_class` — equity / fixed_income / commodity / cash / alt _(see multi-asset doc)_
- `quote_type` — yfinance `quoteType` (EQUITY/ETF/BOND/…) or aggregator-provided
- `as_of` / `ingested_at`
- `source` — `sample` | `csv` | `snaptrade`

Reserving `asset_class` + `quote_type` now means multi-asset is a routing change, not a
schema migration later.

## The coupling: real holdings force multi-asset

A real Fidelity portfolio will contain **ETFs, probably bonds, and cash** — which
immediately breaks the single-equity assumption in `holdings_benchmarks` and trips the
latent `cap_tier` null→'Small' bug. So **Fidelity + dynamic holdings + multi-asset ship
together** as one milestone, not three. Sequence: land real holdings → handle held
ETFs (market axis) → handle bonds (duration/credit) → cash/commodities as balances.

## Security (non-negotiable)

- **Never commit** brokerage credentials, SnapTrade `userSecret`/client secret, or any
  real holdings data. `.env` / a secret manager only; verify `.gitignore` covers them.
- Public repo + public deploy show **sample data only**.
- SnapTrade stores the broker auth; we hold a per-user secret — treat it like a password.

## Open decisions (lock when we build)

1. CSV-only forever, or invest in the SnapTrade live flow? (Live is the bigger flex.)
2. Where does "real" run — fully local, or a private/authed deploy separate from the public demo?
3. Multiple accounts (brokerage + IRA) now, or single-account v1?
4. Cost basis / quantity: surface position sizing in gold (weighting), or keep gold
   price-return-only and let sizing live in the serve layer?
