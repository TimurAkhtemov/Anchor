from pathlib import Path

import pytest

from scripts import private_services
from scripts.private_services import DASHBOARD_LABEL, REFRESH_LABEL, build_plists

NPM = "/custom/node/bin/npm"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _plists(tmp_path, npm=NPM):
    return build_plists(tmp_path, tmp_path / ".env", tmp_path / "private", npm=npm)


def test_launch_agents_are_private_and_weekday_only(tmp_path):
    refresh = _plists(tmp_path)[REFRESH_LABEL]

    assert refresh["ProgramArguments"][-1] == "refresh"
    assert [entry["Weekday"] for entry in refresh["StartCalendarInterval"]] == [1, 2, 3, 4, 5]  # launchd weekdays: 1 = Monday
    assert all(entry["Hour"] == 21 and entry["Minute"] == 30 for entry in refresh["StartCalendarInterval"])


def test_dashboard_binds_loopback_only(tmp_path):
    dashboard = _plists(tmp_path)[DASHBOARD_LABEL]
    args = dashboard["ProgramArguments"]

    assert args == [
        str(tmp_path / "venv" / "bin" / "python"),
        str(tmp_path / "scripts" / "private_static_server.py"),
        "8501",
        str(tmp_path / "var" / "private_web" / "current"),
    ]
    assert not any("streamlit" in arg for arg in args)
    assert "http.server" not in args, "the plain server does no Host check"
    # The bind address lives in the server script; its tests prove it serves loopback only.
    script = (REPO_ROOT / "scripts" / "private_static_server.py").read_text()
    assert '("127.0.0.1", port)' in script and "0.0.0.0" not in script
    assert dashboard["KeepAlive"] is True


def test_dashboard_needs_no_secrets_or_private_paths(tmp_path):
    dashboard_env = _plists(tmp_path)[DASHBOARD_LABEL]["EnvironmentVariables"]
    assert set(dashboard_env) == {"PATH"}


def test_npm_resolved_at_install_reaches_the_refresh_environment(tmp_path):
    refresh_env = _plists(tmp_path)[REFRESH_LABEL]["EnvironmentVariables"]
    assert refresh_env["ANCHOR_NPM"] == NPM
    # npm's shebang needs the node beside it, under launchd's minimal PATH.
    assert refresh_env["PATH"].split(":")[0] == "/custom/node/bin"


def test_homebrew_npm_does_not_duplicate_path_entries(tmp_path):
    refresh_env = _plists(tmp_path, npm="/opt/homebrew/bin/npm")[REFRESH_LABEL]["EnvironmentVariables"]
    entries = refresh_env["PATH"].split(":")
    assert entries.count("/opt/homebrew/bin") == 1


@pytest.fixture
def install_tree(tmp_path, monkeypatch):
    (tmp_path / "venv" / "bin").mkdir(parents=True)
    (tmp_path / "venv" / "bin" / "python").write_text("")
    (tmp_path / "web" / "node_modules").mkdir(parents=True)
    env_file = tmp_path / ".env"
    env_file.write_text("")

    def refuse(*args, **kwargs):
        raise AssertionError("launchctl must not run when install prerequisites are missing")

    monkeypatch.setattr(private_services, "_launchctl", refuse)
    return tmp_path, env_file


def test_install_refuses_without_npm(install_tree, monkeypatch, capsys):
    repo, env_file = install_tree
    monkeypatch.setattr(private_services.shutil, "which", lambda _: None)
    assert private_services.install(repo, env_file, repo / "private") == 1
    assert "npm" in capsys.readouterr().err


def test_install_refuses_without_node_modules(install_tree, monkeypatch, capsys):
    repo, env_file = install_tree
    monkeypatch.setattr(private_services.shutil, "which", lambda _: NPM)
    (repo / "web" / "node_modules").rmdir()
    assert private_services.install(repo, env_file, repo / "private") == 1
    assert "node_modules" in capsys.readouterr().err


def test_install_no_longer_requires_streamlit(install_tree, monkeypatch, tmp_path):
    repo, env_file = install_tree
    monkeypatch.setattr(private_services.shutil, "which", lambda _: NPM)
    monkeypatch.setattr(private_services.Path, "home", lambda: tmp_path / "home")
    calls = []
    monkeypatch.setattr(
        private_services, "_launchctl", lambda *args, **kwargs: calls.append(args)
    )
    assert private_services.install(repo, env_file, repo / "private") == 0
    assert calls, "install should bootstrap the agents"


def test_bootstrap_installs_web_dependencies():
    script = (REPO_ROOT / "scripts" / "bootstrap_private_ops.sh").read_text()
    assert " ci" in script and "web" in script
    assert "streamlit" not in script.lower()
