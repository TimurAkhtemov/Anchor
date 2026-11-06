from __future__ import annotations

from datetime import date

import pytest

from app.bundle_validation import (
    MAX_SETTLED_AGE_DAYS,
    BundleValidationError,
    allowed_tickers,
    validate_bundle,
)

TODAY = date(2026, 9, 8)


def _bundle():
    t = next(t for t in sorted(allowed_tickers()) if t != "CASH")
    return {
        "portfolio": "demo",
        "as_of_calendar": {"as_of_date": "2026-09-04"},
        "macro_regime": {"as_of_date": "2026-09-04"},
        "macro_indicators": [{"indicator_key": "x"}],
        "sector_performance": [{"etf_ticker": t}],
        "portfolio_composition": [{"ticker": t}],
        "holdings_benchmarks": [{"holding_ticker": t, "benchmark_etf": t}],
        "macro_trend": {"dff": [["2026-09-01", 4.0]]},
        "ticker_trend": {t: [["2026-09-01", 1.0]]},
        "briefing": {
            "sources": [{"ticker": t}],
            "steps": [{"target": {"kind": "holding", "key": t}}],
        },
    }


def test_accepts_valid_bundle():
    assert validate_bundle(_bundle(), today=TODAY)


def test_accepts_null_briefing():
    b = _bundle()
    b["briefing"] = None
    validate_bundle(b, today=TODAY)


def test_rejects_private_ticker_in_composition():
    b = _bundle()
    b["portfolio_composition"][0]["ticker"] = "PRIVATE"
    with pytest.raises(BundleValidationError):
        validate_bundle(b, today=TODAY)


def test_rejects_private_ticker_only_in_ticker_trend():
    b = _bundle()
    b["ticker_trend"]["PRIVATE"] = [["2026-09-01", 1.0]]
    with pytest.raises(BundleValidationError, match="PRIVATE"):
        validate_bundle(b, today=TODAY)


def test_rejects_private_ticker_in_briefing():
    b = _bundle()
    b["briefing"]["sources"][0]["ticker"] = "PRIVATE"
    with pytest.raises(BundleValidationError):
        validate_bundle(b, today=TODAY)


def test_stale_date_boundary():
    b = _bundle()
    assert MAX_SETTLED_AGE_DAYS == 4
    b["as_of_calendar"]["as_of_date"] = "2026-09-04"  # 4 days
    validate_bundle(b, today=TODAY)
    b["as_of_calendar"]["as_of_date"] = "2026-09-03"  # 5 days
    with pytest.raises(BundleValidationError):
        validate_bundle(b, today=TODAY)


def test_rejects_non_demo_portfolio():
    b = _bundle()
    b["portfolio"] = "real"
    with pytest.raises(BundleValidationError):
        validate_bundle(b, today=TODAY)


def test_rejects_empty_required_section():
    b = _bundle()
    b["portfolio_composition"] = []
    with pytest.raises(BundleValidationError):
        validate_bundle(b, today=TODAY)
