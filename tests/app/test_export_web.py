from __future__ import annotations

import json
import re
import stat

import pandas as pd
import pytest
from google.api_core.exceptions import NotFound

from app import export_web
from app.export_web import BUNDLE_PATH, BundlePrivacyError, export_web as run_export

AS_OF = "2026-09-04"


class _Result:
    def __init__(self, df):
        self._df = df

    def to_dataframe(self):
        return self._df


class FakeClient:
    def __init__(self, briefing="ok", briefing_date=AS_OF):
        self.queries: list[str] = []
        self.briefing = briefing
        self.briefing_date = briefing_date

    def query(self, sql):
        self.queries.append(sql)
        table = re.search(r"\.(\w+)`", sql).group(1)
        if table == "copilot_briefing":
            if self.briefing == "missing":
                raise NotFound("no table")
            if self.briefing == "empty":
                return _Result(pd.DataFrame())
            return _Result(pd.DataFrame([{
                "briefing_md": "hi",
                "briefing_json": json.dumps({"steps": []}),
                "sources": "[]",
                "as_of_date": self.briefing_date,
                "generated_at": "2026-09-04T10:00:00",
                "provider": "ollama",
                "model": "m",
            }]))
        if table in ("as_of_calendar", "macro_regime"):
            return _Result(pd.DataFrame([{"as_of_date": AS_OF}]))
        if table == "macro_trend":
            return _Result(pd.DataFrame({
                "indicator_key": ["dff", "dff"],
                "observation_date": ["2026-09-02", "2026-09-01"],
                "value": [5.0, 4.0],
            }))
        if table == "ticker_trend":
            return _Result(pd.DataFrame({
                "ticker": ["SPY", "SPY"],
                "trading_date": ["2026-09-02", "2026-09-01"],
                "close_price": [100.123456, 99.0],
            }))
        return _Result(pd.DataFrame({"x": [1]}))


def test_real_portfolio_refuses_public_path():
    client = FakeClient()
    with pytest.raises(BundlePrivacyError):
        run_export(client, BUNDLE_PATH, portfolio="real")
    assert client.queries == []


def test_real_portfolio_requires_var_dir(tmp_path):
    client = FakeClient()
    with pytest.raises(BundlePrivacyError):
        run_export(client, tmp_path / "x.json", portfolio="real")
    assert client.queries == []


def test_real_reads_private_dataset():
    out = export_web.REPO_ROOT / "var" / "test-bundle" / "anchor.json"
    client = FakeClient()
    try:
        run_export(client, out, portfolio="real")
        assert client.queries
        assert all("anchor_marts_private" in q for q in client.queries)
        assert json.loads(out.read_text())["portfolio"] == "real"
    finally:
        out.unlink(missing_ok=True)
        out.parent.rmdir()


def test_demo_reads_public_dataset(tmp_path):
    client = FakeClient()
    run_export(client, tmp_path / "b.json")
    assert client.queries
    assert not any("_private" in q for q in client.queries)


def test_trends_sorted_ascending_and_rounded(tmp_path):
    out = tmp_path / "b.json"
    run_export(FakeClient(), out)
    b = json.loads(out.read_text())
    assert b["portfolio"] == "demo"
    assert b["macro_trend"]["dff"] == [["2026-09-01", 4.0], ["2026-09-02", 5.0]]
    assert b["ticker_trend"]["SPY"] == [["2026-09-01", 99.0], ["2026-09-02", 100.123]]


def test_matching_briefing_is_kept(tmp_path):
    out = tmp_path / "b.json"
    run_export(FakeClient(), out)
    assert json.loads(out.read_text())["briefing"]["briefing_md"] == "hi"


def test_stale_briefing_exports_null(tmp_path):
    out = tmp_path / "b.json"
    counts = run_export(FakeClient(briefing_date="2026-09-03"), out)
    assert json.loads(out.read_text())["briefing"] is None
    assert counts["briefing_steps"] == 0


@pytest.mark.parametrize("mode", ["missing", "empty"])
def test_missing_briefing_table_exports_null(tmp_path, mode):
    out = tmp_path / "b.json"
    run_export(FakeClient(briefing=mode), out)
    assert json.loads(out.read_text())["briefing"] is None


def test_real_bundle_is_owner_only():
    out = export_web.REPO_ROOT / "var" / "test-bundle-mode" / "anchor.json"
    try:
        run_export(FakeClient(), out, portfolio="real")
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
    finally:
        out.unlink(missing_ok=True)
        out.parent.rmdir()


@pytest.fixture
def cli(monkeypatch):
    """main() with BigQuery replaced; the list records every client constructed."""
    from google.cloud import bigquery

    constructed: list[FakeClient] = []

    def make_client(**_kwargs):
        constructed.append(FakeClient())
        return constructed[-1]

    monkeypatch.setattr(bigquery, "Client", make_client)
    return constructed


def _record_export(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []

    def record(client, out_path, portfolio):
        calls.append((out_path, portfolio))
        return {"as_of_calendar": 1}

    monkeypatch.setattr(export_web, "export_web", record)
    return calls


def test_cli_real_defaults_to_the_private_path(cli, monkeypatch):
    calls = _record_export(monkeypatch)
    export_web.main(["--portfolio", "real"])
    assert calls == [
        (export_web.REPO_ROOT / "var" / "private_web" / "anchor.json", "real")
    ]


def test_cli_defaults_to_the_demo_bundle(cli, monkeypatch):
    calls = _record_export(monkeypatch)
    export_web.main([])
    assert calls == [(BUNDLE_PATH, "demo")]


def test_cli_out_overrides_the_path(cli, monkeypatch, tmp_path):
    calls = _record_export(monkeypatch)
    export_web.main(["--out", str(tmp_path / "b.json")])
    assert calls == [(tmp_path / "b.json", "demo")]


def test_cli_refuses_real_on_the_public_path_before_any_client(cli):
    with pytest.raises(BundlePrivacyError):
        export_web.main(["--portfolio", "real", "--out", str(BUNDLE_PATH)])
    assert cli == []


def test_cli_prints_counts_not_holdings(cli, tmp_path, capsys):
    export_web.main(["--out", str(tmp_path / "b.json")])
    printed = capsys.readouterr().out
    assert "ticker_trend" in printed  # the section's name and its row count
    assert "SPY" not in printed
