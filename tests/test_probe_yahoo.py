from scripts.probe_yahoo import public_tickers


def test_public_tickers_unions_benchmarks_and_demo_holdings():
    tickers = public_tickers()
    assert "SPY" in tickers  # benchmark ETF
    assert "AAPL" in tickers  # demo holding
    assert None not in tickers
    assert "" not in tickers
