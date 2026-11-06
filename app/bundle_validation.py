"""Privacy, completeness, and settled-data checks for the public web bundle."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion.holdings_csv import parse_fidelity_positions

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PORTFOLIO_CSV = REPO_ROOT / "data" / "sample_portfolio.csv"
BENCHMARK_ETFS_CSV = REPO_ROOT / "transformation" / "seeds" / "benchmark_etfs.csv"
TICKER_COLUMNS = ("ticker", "holding_ticker", "benchmark_etf", "etf_ticker")
MAX_SETTLED_AGE_DAYS = 4

_REQUIRED_SECTIONS = (
    "macro_indicators",
    "sector_performance",
    "portfolio_composition",
    "holdings_benchmarks",
)


class BundleValidationError(ValueError):
    pass


def allowed_tickers() -> set[str]:
    positions = parse_fidelity_positions(SAMPLE_PORTFOLIO_CSV.read_text())
    tickers = {row["ticker"] for row in positions if row["ticker"]}
    with BENCHMARK_ETFS_CSV.open(newline="") as source:
        tickers.update(row["etf_ticker"] for row in csv.DictReader(source))
    return tickers | {"CASH"}


def _bundle_tickers(bundle: dict) -> set[str]:
    seen: set[str] = set()
    for section, rows in bundle.items():
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    seen.update(
                        str(row[c]) for c in TICKER_COLUMNS if row.get(c) is not None
                    )
    seen.update(bundle.get("ticker_trend") or {})
    briefing = bundle.get("briefing")
    if briefing:
        seen.update(s["ticker"] for s in briefing.get("sources", []) if s.get("ticker"))
        seen.update(
            step["target"]["key"]
            for step in briefing.get("steps", [])
            if step["target"].get("kind") == "holding" and step["target"].get("key")
        )
    return seen


def validate_bundle(bundle: dict, today: date | None = None) -> dict[str, int]:
    if bundle.get("portfolio") != "demo":
        raise BundleValidationError("public bundle must be portfolio 'demo'")

    counts: dict[str, int] = {}
    for section in _REQUIRED_SECTIONS:
        rows = bundle.get(section)
        if not rows:
            raise BundleValidationError(f"required bundle section is empty: {section}")
        counts[section] = len(rows)
    counts["ticker_trend"] = len(bundle.get("ticker_trend") or {})
    counts["macro_trend"] = len(bundle.get("macro_trend") or {})

    bad = _bundle_tickers(bundle) - allowed_tickers()
    if bad:
        raise BundleValidationError(f"non-demo tickers in public bundle: {sorted(bad)}")

    calendar = bundle.get("as_of_calendar") or {}
    if "as_of_date" not in calendar:
        raise BundleValidationError("as_of_calendar must contain as_of_date")
    as_of = pd.to_datetime(calendar["as_of_date"]).date()
    age_days = ((today or date.today()) - as_of).days
    if age_days < 0 or age_days > MAX_SETTLED_AGE_DAYS:
        raise BundleValidationError(
            f"settled market date {as_of} is {age_days} days old; "
            f"allowed range is 0-{MAX_SETTLED_AGE_DAYS}"
        )
    return counts
