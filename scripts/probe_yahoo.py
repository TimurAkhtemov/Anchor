"""Yahoo reachability probe: can this machine (e.g. a GitHub-hosted runner) reach Yahoo?

Uses only public tickers (benchmark ETFs + the committed demo portfolio), read from
files. No BigQuery, no credentials, no import of ingestion.ingest_yfinance.
Exits non-zero if more than 10% of tickers return no price rows.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingestion.holdings_csv import parse_fidelity_positions  # noqa: E402  (stdlib-only module)

BENCHMARKS_CSV = ROOT / "transformation" / "seeds" / "benchmark_etfs.csv"
DEMO_PORTFOLIO_CSV = ROOT / "data" / "sample_portfolio.csv"
NEWS_TICKERS = ("SPY", "AAPL", "XLK")
MAX_FAIL_FRACTION = 0.10


def public_tickers() -> set[str]:
    """Benchmark ETFs from the seed plus demo-portfolio tickers; files only."""
    with BENCHMARKS_CSV.open(newline="") as f:
        etfs = {(r["etf_ticker"] or "").strip() for r in csv.DictReader(f)}
    held = {p["ticker"] for p in parse_fidelity_positions(DEMO_PORTFOLIO_CSV.read_text())}
    return {t for t in etfs | held if t}


def probe_ticker(yf, ticker: str, with_news: bool) -> tuple[bool, str]:
    t = yf.Ticker(ticker)
    parts = []
    try:
        rows = len(t.history(period="5d"))
    except Exception as exc:  # noqa: BLE001 - diagnostic, report anything
        rows = 0
        parts.append(f"history_error={type(exc).__name__}: {exc}")
    parts.insert(0, f"rows={rows}")
    try:
        info = t.info or {}
        parts.append(f"info_keys={len(info)} quoteType={info.get('quoteType')}")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"info_error={type(exc).__name__}: {exc}")
    if with_news:
        try:
            parts.append(f"news={len(t.news or [])}")
        except Exception as exc:  # noqa: BLE001
            parts.append(f"news_error={type(exc).__name__}: {exc}")
    return rows > 0, " ".join(parts)


def main() -> int:
    import yfinance as yf

    tickers = sorted(public_tickers())
    failed = []
    for ticker in tickers:
        ok, detail = probe_ticker(yf, ticker, ticker in NEWS_TICKERS)
        print(f"{'OK  ' if ok else 'FAIL'} {ticker:8s} {detail}", flush=True)
        if not ok:
            failed.append(ticker)
    frac = len(failed) / len(tickers)
    print(f"\n{len(tickers) - len(failed)}/{len(tickers)} tickers returned prices; failed={failed}")
    if frac > MAX_FAIL_FRACTION:
        print(f"FAIL: {frac:.0%} without prices exceeds {MAX_FAIL_FRACTION:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
