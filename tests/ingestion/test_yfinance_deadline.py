import time

import pytest

from ingestion.ingest_yfinance import call_with_deadline, fetch_ticker_metadata


def test_returns_value_when_fast():
    assert call_with_deadline(lambda: 42, seconds=1) == 42


def test_reraises_callable_error():
    def boom():
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        call_with_deadline(boom, seconds=1)


def test_abandons_stalled_call():
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        call_with_deadline(lambda: time.sleep(5), seconds=0.2)
    assert time.monotonic() - started < 2


def test_metadata_fetch_gives_up_after_three_bounded_attempts(monkeypatch):
    # A stalled .info must cost ~3 deadlines + backoff, not the whole run.
    import ingestion.ingest_yfinance as mod

    class StalledTicker:
        def __init__(self, _):
            pass

        @property
        def info(self):
            time.sleep(5)

    monkeypatch.setattr(mod.yf, "Ticker", StalledTicker)
    monkeypatch.setattr(mod, "FETCH_DEADLINE_S", 0.1)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)  # skip the backoff
    started = time.monotonic()
    assert fetch_ticker_metadata("STALL") == {}
    assert time.monotonic() - started < 2
