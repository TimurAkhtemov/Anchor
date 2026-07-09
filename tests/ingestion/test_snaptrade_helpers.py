from ingestion.ingest_holdings import _usd_cash_total


def test_usd_only_sums_correctly():
    balances = [
        {"cash": 100.0, "currency": {"code": "USD"}},
        {"cash": 50.5, "currency": {"code": "USD"}},
    ]
    assert _usd_cash_total(balances) == 150.5


def test_mixed_usd_and_cad_counts_usd_only():
    balances = [
        {"cash": 100.0, "currency": {"code": "USD"}},
        {"cash": 75.0, "currency": {"code": "CAD"}},
    ]
    assert _usd_cash_total(balances) == 100.0


def test_string_currency_form_is_handled():
    balances = [{"cash": 200.0, "currency": "USD"}]
    assert _usd_cash_total(balances) == 200.0


def test_missing_currency_assumes_account_currency_and_counts():
    balances = [{"cash": 42.0}]
    assert _usd_cash_total(balances) == 42.0


def test_empty_list_returns_zero():
    assert _usd_cash_total([]) == 0.0
