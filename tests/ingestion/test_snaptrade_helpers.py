import sys
import types

import pytest

from ingestion.ingest_holdings import (
    _normalize_snaptrade_position,
    _snaptrade_user_kwargs,
    _usd_cash_total,
    fetch_snaptrade_positions,
)


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


def test_personal_auth_omits_user_fields(monkeypatch):
    monkeypatch.setenv("SNAPTRADE_USER_ID", "legacy-user")
    monkeypatch.setenv("SNAPTRADE_USER_SECRET", "")
    assert _snaptrade_user_kwargs() == {}


def test_commercial_auth_includes_user_fields(monkeypatch):
    monkeypatch.setenv("SNAPTRADE_USER_ID", "app-user")
    monkeypatch.setenv("SNAPTRADE_USER_SECRET", "secret")
    assert _snaptrade_user_kwargs() == {"user_id": "app-user", "user_secret": "secret"}


def test_unified_position_payload_normalizes_instrument_and_cost_basis():
    row = _normalize_snaptrade_position(
        {
            "instrument": {
                "kind": "stock",
                "symbol": "EXAMPLE",
                "raw_symbol": "EXAMPLE",
                "description": "Example Corp",
            },
            "units": "2.5",
            "price": "40.00",
            "cost_basis": "32.00",
            "cash_equivalent": False,
        },
        "account-1",
        "Brokerage",
    )
    assert row == {
        "account_number": "account-1",
        "account_name": "Brokerage",
        "ticker": "EXAMPLE",
        "description": "Example Corp",
        "quantity": 2.5,
        "price": 40.0,
        "market_value": 100.0,
        "cost_basis_total": 80.0,
    }


def test_position_without_instrument_identity_fails_closed():
    with pytest.raises(RuntimeError, match="refusing cash fallback"):
        _normalize_snaptrade_position(
            {"instrument": {}, "units": "2", "price": "10"},
            "account-1",
            "Brokerage",
        )


def test_snaptrade_transport_failure_is_sanitized(monkeypatch):
    from urllib3.exceptions import MaxRetryError

    secret_url = "https://api.snaptrade.test/accounts?userSecret=do-not-log"

    class Accounts:
        def list_user_accounts(self, **_kwargs):
            raise MaxRetryError(None, secret_url, "offline")

    class SnapTrade:
        def __init__(self, **_kwargs):
            self.account_information = Accounts()

    class SnapTradeAuth:
        @staticmethod
        def personal_api_key(**kwargs):
            return kwargs

        @staticmethod
        def commercial_api_key(**kwargs):
            return kwargs

    fake_sdk = types.ModuleType("snaptrade_client")
    fake_sdk.SnapTrade = SnapTrade
    fake_sdk.SnapTradeAuth = SnapTradeAuth
    fake_exceptions = types.ModuleType("snaptrade_client.exceptions")
    fake_exceptions.OpenApiException = type("OpenApiException", (Exception,), {})
    monkeypatch.setitem(sys.modules, "snaptrade_client", fake_sdk)
    monkeypatch.setitem(sys.modules, "snaptrade_client.exceptions", fake_exceptions)
    monkeypatch.setenv("SNAPTRADE_CLIENT_ID", "client")
    monkeypatch.setenv("SNAPTRADE_CONSUMER_KEY", "consumer")
    monkeypatch.setenv("SNAPTRADE_USER_ID", "user")
    monkeypatch.setenv("SNAPTRADE_USER_SECRET", "secret")

    with pytest.raises(RuntimeError) as exc_info:
        fetch_snaptrade_positions()

    message = str(exc_info.value)
    assert "MaxRetryError" in message
    assert "do-not-log" not in message
    assert secret_url not in message
