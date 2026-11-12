from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.bundle_validation import BundleValidationError, allowed_tickers
from app.export_web import export_web
from scripts.public_refresh import (
    RefreshResult,
    default_run_briefing,
    main,
    refresh,
    should_generate_briefing,
)

TODAY = date(2026, 9, 8)
OLD = "2026-09-03"
NEW = "2026-09-04"
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "public-refresh.yml"


class _Result:
    def __init__(self, df):
        self._df = df

    def to_dataframe(self):
        return self._df


class FakeClient:
    """Serves a valid demo world as of `as_of`; the briefing row is dated `briefing_date`."""

    def __init__(self, as_of=NEW, briefing_date=None, ticker="SPY"):
        self.as_of = as_of
        self.briefing_date = briefing_date
        self.ticker = ticker

    def query(self, sql):
        table = re.search(r"\.(\w+)`", sql).group(1)
        t = self.ticker
        if table == "copilot_briefing":
            if self.briefing_date is None:
                return _Result(pd.DataFrame())
            return _Result(pd.DataFrame([{
                "briefing_md": "hi",
                "briefing_json": json.dumps({"steps": []}),
                "sources": "[]",
                "as_of_date": self.briefing_date,
                "generated_at": "2026-09-04T10:00:00",
                "provider": "anthropic",
                "model": "m",
            }]))
        if table in ("as_of_calendar", "macro_regime"):
            return _Result(pd.DataFrame([{"as_of_date": self.as_of}]))
        if table == "macro_indicators":
            return _Result(pd.DataFrame([{"indicator_key": "dff"}]))
        if table == "sector_performance":
            return _Result(pd.DataFrame([{"etf_ticker": t}]))
        if table == "portfolio_composition":
            return _Result(pd.DataFrame([{"ticker": t}]))
        if table == "holdings_benchmarks":
            return _Result(pd.DataFrame([{"holding_ticker": t, "benchmark_etf": t}]))
        if table == "macro_trend":
            return _Result(pd.DataFrame({
                "indicator_key": ["dff"], "observation_date": ["2026-09-01"], "value": [4.0],
            }))
        if table == "ticker_trend":
            return _Result(pd.DataFrame({
                "ticker": [t], "trading_date": ["2026-09-01"], "close_price": [1.0],
            }))
        raise AssertionError(sql)


class Briefing:
    """Fake run_briefing; on success the fake client's briefing row catches up."""

    def __init__(self, client, fail=False):
        self.client, self.fail, self.calls = client, fail, 0

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model down")
        self.client.briefing_date = self.client.as_of


def _write_bundle(path, as_of, briefing=True):
    client = FakeClient(as_of=as_of, briefing_date=as_of if briefing else None)
    export_web(client, path)


def test_should_generate_briefing_rules():
    assert should_generate_briefing(NEW, None)
    assert should_generate_briefing(NEW, {"as_of_calendar": {"as_of_date": OLD}, "briefing": {"x": 1}})
    assert should_generate_briefing(NEW, {"as_of_calendar": {"as_of_date": NEW}, "briefing": None})
    assert not should_generate_briefing(NEW, {"as_of_calendar": {"as_of_date": NEW}, "briefing": {"x": 1}})


def test_older_mart_date_fails(tmp_path):
    with pytest.raises(BundleValidationError, match="older"):
        should_generate_briefing(OLD, {"as_of_calendar": {"as_of_date": NEW}, "briefing": {"x": 1}})
    path = tmp_path / "anchor.json"
    _write_bundle(path, NEW)
    before = path.read_bytes()
    client = FakeClient(as_of=OLD, briefing_date=OLD)
    run = Briefing(client)
    with pytest.raises(BundleValidationError, match="older"):
        refresh(client, path, run, today=TODAY)
    assert run.calls == 0
    assert path.read_bytes() == before


def test_new_date_generates_briefing(tmp_path):
    path = tmp_path / "anchor.json"
    _write_bundle(path, OLD)
    client = FakeClient(as_of=NEW)
    run = Briefing(client)
    result = refresh(client, path, run, today=TODAY)
    assert run.calls == 1
    assert result == RefreshResult(changed=True, as_of=NEW, briefing_status="generated")
    bundle = json.loads(path.read_text())
    assert bundle["as_of_calendar"]["as_of_date"] == NEW
    assert bundle["briefing"]["as_of_date"] == NEW


def test_same_date_with_briefing_spends_nothing(tmp_path):
    path = tmp_path / "anchor.json"
    _write_bundle(path, NEW)
    before = path.read_bytes()
    client = FakeClient(as_of=NEW, briefing_date=NEW)
    run = Briefing(client)
    result = refresh(client, path, run, today=TODAY)
    assert run.calls == 0
    assert result == RefreshResult(changed=False, as_of=NEW, briefing_status="reused")
    assert path.read_bytes() == before


def test_same_date_past_age_limit_fails(tmp_path):
    path = tmp_path / "anchor.json"
    _write_bundle(path, NEW)
    before = path.read_bytes()
    client = FakeClient(as_of=NEW, briefing_date=NEW)
    run = Briefing(client)
    with pytest.raises(BundleValidationError, match="days old"):
        refresh(client, path, run, today=date(2026, 12, 1))
    assert run.calls == 0
    assert path.read_bytes() == before


def test_same_date_without_briefing_retries(tmp_path):
    path = tmp_path / "anchor.json"
    _write_bundle(path, NEW, briefing=False)
    client = FakeClient(as_of=NEW)
    run = Briefing(client)
    result = refresh(client, path, run, today=TODAY)
    assert run.calls == 1
    assert result.changed and result.briefing_status == "generated"
    assert json.loads(path.read_text())["briefing"] is not None


def test_briefing_failure_still_publishes_numbers(tmp_path):
    path = tmp_path / "anchor.json"
    _write_bundle(path, OLD)
    client = FakeClient(as_of=NEW)
    result = refresh(client, path, Briefing(client, fail=True), today=TODAY)
    assert result == RefreshResult(changed=True, as_of=NEW, briefing_status="failed")
    bundle = json.loads(path.read_text())
    assert bundle["as_of_calendar"]["as_of_date"] == NEW
    assert bundle["briefing"] is None


def test_repeated_failed_retry_is_unchanged(tmp_path):
    path = tmp_path / "anchor.json"
    _write_bundle(path, NEW, briefing=False)
    before = path.read_bytes()
    client = FakeClient(as_of=NEW)
    result = refresh(client, path, Briefing(client, fail=True), today=TODAY)
    assert result == RefreshResult(changed=False, as_of=NEW, briefing_status="failed")
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["anchor.json"]


def test_validation_failure_writes_nothing(tmp_path):
    path = tmp_path / "anchor.json"
    _write_bundle(path, OLD)
    before = path.read_bytes()
    client = FakeClient(as_of=NEW, ticker="ZZZZ")  # not a demo ticker
    assert "ZZZZ" not in allowed_tickers()
    with pytest.raises(BundleValidationError):
        refresh(client, path, Briefing(client), today=TODAY)
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["anchor.json"]


def test_export_failure_keeps_old_bundle(tmp_path):
    path = tmp_path / "anchor.json"
    _write_bundle(path, OLD)
    before = path.read_bytes()

    class Broken(FakeClient):
        def query(self, sql):
            if "macro_trend" in sql:
                raise RuntimeError("bigquery down")
            return super().query(sql)

    client = Broken(as_of=NEW)
    with pytest.raises(RuntimeError, match="bigquery down"):
        refresh(client, path, Briefing(client), today=TODAY)
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["anchor.json"]


def test_first_run_without_bundle_creates_it(tmp_path):
    path = tmp_path / "data" / "anchor.json"
    client = FakeClient(as_of=NEW)
    result = refresh(client, path, Briefing(client), today=TODAY)
    assert result.changed and path.exists()


def test_main_writes_github_output(tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    client = FakeClient(as_of=NEW)
    monkeypatch.setattr("scripts.public_refresh.make_client", lambda: client)
    monkeypatch.setattr("scripts.public_refresh.default_run_briefing", Briefing(client))
    monkeypatch.setattr("scripts.public_refresh.BUNDLE_PATH", tmp_path / "anchor.json")
    monkeypatch.setattr("scripts.public_refresh.date", type("D", (), {"today": staticmethod(lambda: TODAY)}))
    main()
    text = out.read_text()
    assert "changed=true" in text and f"as_of={NEW}" in text


def test_workflow_never_touches_real_world():
    text = WORKFLOW.read_text()
    for forbidden in ("--world real", "SNAPTRADE", "holdings_real", "prod-private", "build-private"):
        assert forbidden not in text
    assert "publish" in text and "2-6" in text
    assert "git add web/public/data/anchor.json" in text
    assert "--force" not in text


def test_briefing_subprocess_has_a_timeout(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("scripts.public_refresh.subprocess.run", fake_run)
    with pytest.raises(subprocess.TimeoutExpired):
        default_run_briefing()
    assert seen["timeout"] == 900


def test_briefing_timeout_still_publishes_numbers(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("scripts.public_refresh.subprocess.run", fake_run)
    path = tmp_path / "anchor.json"
    _write_bundle(path, OLD)
    result = refresh(FakeClient(as_of=NEW), path, default_run_briefing, today=TODAY)
    assert result == RefreshResult(changed=True, as_of=NEW, briefing_status="failed")
    assert json.loads(path.read_text())["as_of_calendar"]["as_of_date"] == NEW


def _main_with_failed_briefing(tmp_path, monkeypatch):
    client = FakeClient(as_of=NEW)
    monkeypatch.setattr("scripts.public_refresh.make_client", lambda: client)
    monkeypatch.setattr("scripts.public_refresh.default_run_briefing", Briefing(client, fail=True))
    monkeypatch.setattr("scripts.public_refresh.BUNDLE_PATH", tmp_path / "anchor.json")
    monkeypatch.setattr("scripts.public_refresh.date", type("D", (), {"today": staticmethod(lambda: TODAY)}))
    main()


def test_failed_briefing_emits_a_workflow_warning(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    _main_with_failed_briefing(tmp_path, monkeypatch)
    assert "::warning::" in capsys.readouterr().out


def test_failed_briefing_writes_the_step_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    _main_with_failed_briefing(tmp_path, monkeypatch)
    assert "Briefing failed" in summary.read_text()


def test_successful_briefing_emits_no_warning(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    client = FakeClient(as_of=NEW)
    monkeypatch.setattr("scripts.public_refresh.make_client", lambda: client)
    monkeypatch.setattr("scripts.public_refresh.default_run_briefing", Briefing(client))
    monkeypatch.setattr("scripts.public_refresh.BUNDLE_PATH", tmp_path / "anchor.json")
    monkeypatch.setattr("scripts.public_refresh.date", type("D", (), {"today": staticmethod(lambda: TODAY)}))
    main()
    assert "::warning::" not in capsys.readouterr().out
    assert not summary.exists()


def test_workflow_secrets_are_step_scoped_and_key_removed_before_node():
    text = WORKFLOW.read_text()
    steps_at = text.index("    steps:")
    assert "secrets." not in text[:steps_at], "no secret may be set at workflow or job level"
    assert "secrets." in text[steps_at:]
    removal = text.index("rm -f /tmp/anchor-bq-key.json")
    node = text.index("actions/setup-node")
    assert removal < node
    assert text.index("make public-refresh") < removal
    # nothing after the removal step may see a secret either, except the commit step's
    # GITHUB_TOKEN, which only that step's `git push` receives (step-scoped env)
    commit = text.index("- name: Commit bundle")
    assert "secrets." not in text[removal:commit]
    assert text[commit:].count("secrets.") == 1
    assert "secrets.GITHUB_TOKEN" in text[commit:]


def test_checkout_does_not_persist_the_token():
    """npm install scripts and Playwright must not find a token in .git/config."""
    text = WORKFLOW.read_text()
    checkout = text.index("actions/checkout@")
    assert "persist-credentials: false" in text[checkout:checkout + 200]
