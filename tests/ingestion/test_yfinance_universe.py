import logging
from types import SimpleNamespace

import pandas as pd
import pytest

from ingestion import ingest_yfinance as iy

REAL_TICKER = "ZZREALONLY"
DEMO_TICKER = "ZZDEMOONLY"


class FakeClient:
    def __init__(self):
        self.queries = []
        self.loaded = []

    def query(self, q):
        self.queries.append(q)
        ticker = REAL_TICKER if "holdings_real" in q else DEMO_TICKER
        return SimpleNamespace(result=lambda: [SimpleNamespace(ticker=ticker)])

    def dataset(self, name):
        return SimpleNamespace(table=lambda t: f"{name}.{t}", dataset_id=name)

    def get_dataset(self, ref):
        return ref

    def load_table_from_dataframe(self, df, table_ref, job_config=None):
        self.loaded.append(table_ref)
        return SimpleNamespace(result=lambda: None)


def test_demo_universe_never_queries_real_holdings():
    client = FakeClient()
    universe = iy.resolve_universe(client, "demo")
    assert DEMO_TICKER in universe and REAL_TICKER not in universe
    assert not any("holdings_real" in q for q in client.queries)


def test_real_universe_reads_only_real_holdings():
    client = FakeClient()
    universe = iy.resolve_universe(client, "real")
    assert REAL_TICKER in universe and DEMO_TICKER not in universe
    assert any("holdings_real" in q for q in client.queries)
    assert not any("holdings_demo" in q for q in client.queries)
    assert "SPY" in universe  # seed ETFs always included


def test_unknown_world_raises():
    with pytest.raises(ValueError):
        iy.resolve_universe(FakeClient(), "staging")
    with pytest.raises(ValueError):
        iy.ingest_yfinance(FakeClient(), "staging")


class _FakeTicker:
    def __init__(self, ticker):
        self.ticker = ticker

    @property
    def info(self):
        raise RuntimeError(f"boom for {self.ticker}")

    def history(self, period):
        idx = pd.DatetimeIndex(["2020-01-02"], name="Date")
        return pd.DataFrame(
            {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]},
            index=idx,
        )


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(iy.yf, "Ticker", _FakeTicker)
    monkeypatch.setattr(iy.time, "sleep", lambda s: None)


def test_ticker_list_is_never_logged_for_real_world(caplog, offline):
    caplog.set_level(logging.DEBUG)
    client = FakeClient()
    iy.ingest_yfinance(client, "real")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert REAL_TICKER not in text
    assert "SPY" not in text
    assert all(t.startswith("raw_yfinance_private.") for t in client.loaded)


def test_demo_world_logs_count_not_list_and_writes_demo_dataset(caplog, offline):
    caplog.set_level(logging.DEBUG)
    client = FakeClient()
    iy.ingest_yfinance(client, "demo")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "Resolved demo ticker universe:" in text
    assert "['" not in text  # no list dump
    assert all(t.startswith("raw_yfinance.") for t in client.loaded)
