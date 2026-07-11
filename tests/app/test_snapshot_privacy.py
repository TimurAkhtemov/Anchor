"""Snapshot-privacy invariant: the committed parquet snapshot the public deploy
serves must never contain a ticker outside the demo/benchmark universe.

This is the last line of defense behind the structural demo/private dbt split
(separate `anchor_*_private` datasets + the `assert_portfolio_isolation` build
hook) — if this test ever fires, a real-portfolio ticker made it into the
committed snapshot, which is the one artifact the public repo and live
Streamlit deploy actually serve.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from app import export_snapshot
from ingestion.holdings_csv import parse_fidelity_positions

REPO_ROOT = Path(__file__).parent.parent.parent
SNAPSHOT_DIR = REPO_ROOT / "app" / "snapshot"
SAMPLE_PORTFOLIO_CSV = REPO_ROOT / "data" / "sample_portfolio.csv"
BENCHMARK_ETFS_CSV = REPO_ROOT / "transformation" / "seeds" / "benchmark_etfs.csv"

# Every column, across every served mart, that can carry a ticker symbol.
TICKER_COLUMNS = ("ticker", "holding_ticker", "benchmark_etf", "etf_ticker")
COMPOSITION_RETURN_COLUMNS = {"return_1m_pct", "return_ytd_pct", "return_1y_pct"}


def _allowed_tickers() -> set[str]:
    """Demo portfolio tickers (parsed the same way the loader does) union every
    benchmark ETF the routing seed can point at, plus the 'CASH' pseudo-ticker
    staging assigns to symbol-less rows."""
    positions = parse_fidelity_positions(SAMPLE_PORTFOLIO_CSV.read_text())
    demo_tickers = {row["ticker"] for row in positions if row["ticker"]}

    with BENCHMARK_ETFS_CSV.open(newline="") as f:
        benchmark_etfs = {row["etf_ticker"] for row in csv.DictReader(f)}

    return demo_tickers | benchmark_etfs | {"CASH"}


def test_snapshot_contains_only_demo_and_benchmark_tickers():
    allowed = _allowed_tickers()
    assert allowed, "expected a non-empty demo/benchmark ticker universe"

    snapshot_files = sorted(SNAPSHOT_DIR.glob("*.parquet"))
    assert snapshot_files, f"no committed snapshot found under {SNAPSHOT_DIR}"

    offenders: dict[str, set[str]] = {}
    for path in snapshot_files:
        df = pd.read_parquet(path)
        for col in TICKER_COLUMNS:
            if col not in df.columns:
                continue
            bad = set(df[col].dropna().unique()) - allowed
            if bad:
                offenders.setdefault(path.name, set()).update(bad)

    assert not offenders, (
        "committed snapshot contains a non-demo ticker — privacy invariant "
        f"violated: {offenders}"
    )


def test_snapshot_files_exactly_match_exported_tables():
    actual = {path.stem for path in SNAPSHOT_DIR.glob("*.parquet")}
    assert actual == set(export_snapshot.TABLES)


def test_briefing_sources_tickers_are_demo_only():
    """The briefing's structured audit trail (`sources` JSON) is the enforceable
    privacy surface: every headline fed to the demo prompt must be about a
    demo/benchmark ticker. (The free-text briefing_md cannot be exhaustively
    scanned without false positives — the demo briefing is generated from demo
    marts by construction; this pins the part that is checkable.)"""
    df = pd.read_parquet(SNAPSHOT_DIR / "copilot_briefing.parquet")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["horizon"] == "all"
    sources = json.loads(row["sources"])
    tickers = {item["ticker"] for item in sources}
    assert tickers <= _allowed_tickers(), (
        f"briefing sources cite non-demo tickers: {tickers - _allowed_tickers()}"
    )


def test_portfolio_composition_snapshot_contains_horizon_returns():
    composition = pd.read_parquet(SNAPSHOT_DIR / "portfolio_composition.parquet")
    assert COMPOSITION_RETURN_COLUMNS <= set(composition.columns)

    # Column presence alone would pass even if the returns join silently broke
    # and shipped an all-NaN snapshot. Source-valued rows (cash/alts) have no
    # price series, so NaN is correct there — the population check belongs on
    # market-valued rows only.
    market_valued = composition[composition["valuation_source"] == "market"]
    assert not market_valued.empty

    # Keep 1m strict, but allow longer horizons to be sparse for future
    # market-valued holdings with shorter price histories.
    populated_returns = market_valued[sorted(COMPOSITION_RETURN_COLUMNS)].notna()
    assert populated_returns["return_1m_pct"].all()
    assert populated_returns[["return_ytd_pct", "return_1y_pct"]].any().all()
