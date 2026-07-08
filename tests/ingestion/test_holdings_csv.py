from pathlib import Path

from ingestion.holdings_csv import clean_symbol, parse_fidelity_positions, to_number

SAMPLE = Path(__file__).parent.parent.parent / "data" / "sample_portfolio.csv"


def test_to_number_strips_currency_formatting():
    assert to_number("$4,200.00") == 4200.0
    assert to_number("+$1,200.00") == 1200.0
    assert to_number("(123.45)") == -123.45
    assert to_number("--") is None
    assert to_number("") is None
    assert to_number(None) is None


def test_clean_symbol_strips_moneymarket_stars():
    assert clean_symbol("SPAXX**") == "SPAXX"
    assert clean_symbol(" AAPL ") == "AAPL"


def test_clean_symbol_rejects_non_symbols():
    assert clean_symbol("Pending Activity") is None
    assert clean_symbol("") is None
    assert clean_symbol(None) is None


def test_parse_sample_portfolio():
    rows = parse_fidelity_positions(SAMPLE.read_text())
    # 14 position rows survive; 2 disclaimer lines are dropped.
    assert len(rows) == 14

    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    assert aapl["account_number"] == "Z12345678"
    assert aapl["quantity"] == 20.0
    assert aapl["market_value"] == 4200.0
    assert aapl["cost_basis_total"] == 3000.0

    # SPAXX stars stripped; appears in both accounts.
    assert sum(1 for r in rows if r["ticker"] == "SPAXX") == 2

    pending = next(r for r in rows if r["ticker"] is None)
    assert pending["description"] == "Pending Activity"
    assert pending["market_value"] == 150.25
