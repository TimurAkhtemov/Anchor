"""Web-bundle privacy invariant: web/public/data/anchor.json is the committed
artifact the public deploy serves — it must never contain a ticker outside the
demo/benchmark universe."""
from __future__ import annotations

import json
from pathlib import Path

from app.bundle_validation import allowed_tickers

BUNDLE = Path(__file__).parent.parent.parent / "web" / "public" / "data" / "anchor.json"


def _bundle() -> dict:
    return json.loads(BUNDLE.read_text())


def test_web_bundle_contains_only_demo_and_benchmark_tickers():
    bundle = _bundle()
    allowed = allowed_tickers()
    seen = {row["ticker"] for row in bundle["portfolio_composition"]}
    seen |= {row["holding_ticker"] for row in bundle["holdings_benchmarks"]}
    seen |= {row["benchmark_etf"] for row in bundle["holdings_benchmarks"]}
    seen |= {row["etf_ticker"] for row in bundle["sector_performance"]}
    seen |= set(bundle.get("ticker_trend", {}))
    briefing = bundle.get("briefing")
    if briefing:
        seen |= {item["ticker"] for item in briefing["sources"]}
        seen |= {
            step["target"]["key"]
            for step in briefing["steps"]
            if step["target"]["kind"] == "holding"
        }
    offenders = {t for t in seen if t} - allowed
    assert not offenders, f"web bundle contains non-demo tickers: {offenders}"


def test_web_bundle_carries_a_valid_tour():
    briefing = _bundle()["briefing"]
    if briefing is None:
        return  # a stale or missing briefing exports null by design
    assert briefing["steps"], "bundle shipped without a tour script"
    assert briefing["steps"][0]["target"]["kind"] == "regime"
    assert briefing["briefing_md"]
    for step in briefing["steps"]:
        for ref in step["headline_refs"]:
            assert 0 <= ref < len(briefing["sources"])


def test_web_bundle_is_demo_and_carries_trends():
    bundle = _bundle()
    assert bundle["portfolio"] == "demo"
    assert bundle["macro_trend"] and bundle["ticker_trend"]
    for series in bundle["ticker_trend"].values():
        assert [d for d, _ in series] == sorted(d for d, _ in series)
