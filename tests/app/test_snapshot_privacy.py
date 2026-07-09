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
from pathlib import Path

import pandas as pd

from ingestion.holdings_csv import parse_fidelity_positions

REPO_ROOT = Path(__file__).parent.parent.parent
SNAPSHOT_DIR = REPO_ROOT / "app" / "snapshot"
SAMPLE_PORTFOLIO_CSV = REPO_ROOT / "data" / "sample_portfolio.csv"
BENCHMARK_ETFS_CSV = REPO_ROOT / "transformation" / "seeds" / "benchmark_etfs.csv"

# Every column, across every served mart, that can carry a ticker symbol.
TICKER_COLUMNS = ("ticker", "holding_ticker", "benchmark_etf", "etf_ticker")


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
