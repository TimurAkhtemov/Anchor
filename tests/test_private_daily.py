from __future__ import annotations

import json
from pathlib import Path

import os

import pytest

from scripts import private_daily
from scripts.private_daily import PreflightError, Step, build_steps, preflight, refresh


PY = Path("/runtime/python")
DBT = Path("/runtime/dbt")


def test_steps_order(tmp_path):
    steps = build_steps(PY, DBT, tmp_path)
    assert [step.name for step in steps] == [
        "snaptrade_holdings",
        "fred",
        "market_prices",
        "private_marts",
        "private_briefing",
        "private_bundle",
        "private_site",
    ]
    assert [step.name for step in steps if step.soft] == ["private_briefing"]


def test_private_steps_only_export_the_real_world_to_var(tmp_path):
    steps = {step.name: " ".join(step.command) for step in build_steps(PY, DBT, tmp_path)}

    assert "--portfolio real" in steps["snaptrade_holdings"]
    assert "--target prod-private" in steps["private_marts"]
    assert '"holdings_source": "real"' in steps["private_marts"]
    assert "--portfolio real" in steps["private_briefing"]
    assert "app/export_web.py" in steps["private_bundle"]
    assert "--portfolio real" in steps["private_bundle"]
    assert "scripts/private_web.py build" in steps["private_site"]
    assert all("web/public" not in command for command in steps.values())
    assert all("export_snapshot" not in command for command in steps.values())


def test_private_market_step_uses_real_world(tmp_path):
    steps = build_steps(PY, DBT, tmp_path)
    market = next(step for step in steps if step.name == "market_prices")
    assert "--world real" in " ".join(market.command)


def test_private_steps_can_temporarily_skip_briefing(tmp_path):
    steps = build_steps(PY, DBT, tmp_path, include_briefing=False)
    commands = [" ".join(step.command) for step in steps]
    assert all("generate_briefing" not in command for command in commands)
    assert all("ollama" not in command.lower() for command in commands)
    # Fresh numbers still reach the site; the export emits briefing: null.
    assert [step.name for step in steps][-2:] == ["private_bundle", "private_site"]


def test_private_classifications_are_loaded_only_when_present(tmp_path):
    without = build_steps(PY, DBT, tmp_path)[0]
    assert "--fund-classifications" not in without.command

    classification = tmp_path / "fund_classifications_real.csv"
    classification.write_text("ticker,asset_class\nPRIVATE,equity\n")
    with_file = build_steps(PY, DBT, tmp_path)[0]
    assert with_file.command[-2:] == ("--fund-classifications", str(classification))


def test_step_defaults():
    step = Step("name", ("true",))
    assert step.cwd is None
    assert step.soft is False


@pytest.fixture
def runner(tmp_path, monkeypatch):
    """refresh() against real subprocesses, with `touch` standing in for later steps."""
    monkeypatch.setattr(private_daily, "VAR_DIR", tmp_path)
    monkeypatch.setattr(private_daily, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(private_daily, "LOCK_PATH", tmp_path / "lock")
    monkeypatch.setattr(private_daily, "preflight", lambda: (PY, DBT, tmp_path))
    monkeypatch.setattr(private_daily, "_private_data_as_of", lambda: "2026-11-05")

    def plan(*steps: Step) -> None:
        monkeypatch.setattr(private_daily, "build_steps", lambda *a, **k: list(steps))

    return plan, tmp_path


def _status(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "status.json").read_text())


def test_success_records_success(runner):
    plan, tmp = runner
    plan(Step("only", ("true",)))
    assert refresh() == 0
    status = _status(tmp)
    assert status["state"] == "success"
    assert status["last_success_at"] == status["finished_at"]
    assert status["data_as_of"] == "2026-11-05"
    assert "degraded_steps" not in status


def test_soft_failure_marks_degraded_and_continues(runner):
    plan, tmp = runner
    later = tmp / "later_ran"
    plan(
        Step("private_briefing", ("false",), soft=True),
        Step("private_site", ("touch", str(later))),
    )
    assert refresh() == 0
    assert later.exists(), "steps after a soft failure must still run"
    status = _status(tmp)
    assert status["state"] == "degraded"
    assert status["degraded_steps"] == ["private_briefing"]
    assert status["last_success_at"] == status["finished_at"]
    assert status["data_as_of"] == "2026-11-05"


def test_hard_failure_stops_and_marks_failed(runner):
    plan, tmp = runner
    later = tmp / "later_ran"
    (tmp / "status.json").write_text(
        json.dumps({"last_success_at": "earlier", "data_as_of": "2026-11-04"})
    )
    plan(
        Step("private_bundle", ("false",)),
        Step("private_site", ("touch", str(later))),
    )
    assert refresh() == 1
    assert not later.exists()
    status = _status(tmp)
    assert status["state"] == "failed"
    assert status["step"] == "private_bundle"
    assert status["last_success_at"] == "earlier"
    assert status["data_as_of"] == "2026-11-04"


def test_hard_failure_after_soft_failure_is_failed_not_degraded(runner):
    plan, tmp = runner
    plan(
        Step("private_briefing", ("false",), soft=True),
        Step("private_site", ("false",)),
    )
    assert refresh() == 1
    status = _status(tmp)
    assert status["state"] == "failed"
    assert status["step"] == "private_site"


@pytest.fixture
def ready_runtime(tmp_path, monkeypatch):
    """Every preflight input present, none read from the real checkout."""
    for name in ("env", "python", "dbt", "key", "npm"):
        (tmp_path / name).write_text("")
    web = tmp_path / "web"
    (web / "node_modules").mkdir(parents=True)
    monkeypatch.setattr(private_daily, "WEB_DIR", web)
    monkeypatch.setenv("ANCHOR_ENV_FILE", str(tmp_path / "env"))
    monkeypatch.setenv("ANCHOR_PYTHON", str(tmp_path / "python"))
    monkeypatch.setenv("ANCHOR_DBT", str(tmp_path / "dbt"))
    monkeypatch.setenv("ANCHOR_NPM", str(tmp_path / "npm"))
    monkeypatch.setenv("ANCHOR_PRIVATE_DATA_DIR", str(tmp_path / "private"))
    monkeypatch.setenv("ANCHOR_BRIEFING_PROVIDER", "ollama")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "key"))
    for key in private_daily.REQUIRED_NONEMPTY_ENV:
        monkeypatch.setenv(key, "x")
    monkeypatch.delenv("SNAPTRADE_USER_SECRET", raising=False)
    return tmp_path


def test_preflight_passes_with_npm_and_node_modules(ready_runtime):
    preflight()


def test_preflight_reports_missing_npm(ready_runtime, monkeypatch):
    monkeypatch.delenv("ANCHOR_NPM")
    monkeypatch.setattr(private_daily.shutil, "which", lambda _: None)
    with pytest.raises(PreflightError, match="npm"):
        preflight()


def test_preflight_reports_stale_npm_path(ready_runtime, monkeypatch):
    monkeypatch.setenv("ANCHOR_NPM", str(ready_runtime / "gone"))
    with pytest.raises(PreflightError, match="npm"):
        preflight()


def test_preflight_reports_missing_node_modules(ready_runtime):
    (ready_runtime / "web" / "node_modules").rmdir()
    with pytest.raises(PreflightError, match="bootstrap-private"):
        preflight()


@pytest.mark.parametrize("provider", ["llama-server", "ollama"])
def test_private_run_honours_a_local_provider(ready_runtime, monkeypatch, provider):
    monkeypatch.setenv("ANCHOR_BRIEFING_PROVIDER", provider)
    private_daily.configure_environment()
    assert os.environ["ANCHOR_BRIEFING_PROVIDER"] == provider


@pytest.mark.parametrize("provider", ["anthropic", "", "  "])
def test_private_run_forces_local_when_provider_is_not(ready_runtime, monkeypatch, provider):
    monkeypatch.setenv("ANCHOR_BRIEFING_PROVIDER", provider)
    private_daily.configure_environment()
    assert os.environ["ANCHOR_BRIEFING_PROVIDER"] == "ollama"
