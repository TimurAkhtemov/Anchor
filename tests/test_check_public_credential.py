from google.api_core.exceptions import Forbidden, NotFound

from scripts.check_public_credential import PRIVATE, PUBLIC, check


class FakeClient:
    """Raises per-table errors; any table not listed is readable."""

    def __init__(self, errors=None):
        self.errors = errors or {}
        self.sql = []

    def query(self, sql):
        self.sql.append(sql)
        for table, exc in self.errors.items():
            if f"`{table}`" in sql:
                raise exc
        return self

    def result(self):
        return iter(())


def _denied_private():
    return {t: Forbidden("Access Denied: permission denied") for t in PRIVATE}


def test_correct_grants_return_no_problems():
    assert check(FakeClient(_denied_private())) == []


def test_readable_private_table_is_reported():
    errors = _denied_private()
    del errors["anchor-495115.raw_holdings.holdings_real"]
    problems = check(FakeClient(errors))
    assert len(problems) == 1
    assert "holdings_real" in problems[0]
    assert "readable" in problems[0]


def test_not_found_on_private_table_is_not_proven():
    errors = _denied_private()
    errors["anchor-495115.raw_yfinance_private.raw_yfinance_prices"] = NotFound("x")
    problems = check(FakeClient(errors))
    assert len(problems) == 1
    assert "raw_yfinance_private" in problems[0]
    assert "not proven" in problems[0]


def test_denied_public_table_is_reported():
    errors = _denied_private()
    errors["anchor-495115.raw_holdings.holdings_demo"] = Forbidden("nope")
    problems = check(FakeClient(errors))
    assert len(problems) == 1
    assert "holdings_demo" in problems[0]


def test_unexpected_error_is_reported_not_raised():
    errors = _denied_private()
    errors["anchor-495115.raw_fred.raw_fred_series"] = RuntimeError("boom")
    problems = check(FakeClient(errors))
    assert len(problems) == 1
    assert "boom" in problems[0]


def test_queries_fetch_no_rows():
    client = FakeClient(_denied_private())
    check(client)
    assert client.sql and all("limit 0" in s for s in client.sql)
    assert len(client.sql) == len(PRIVATE) + len(PUBLIC)
