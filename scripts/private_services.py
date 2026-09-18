#!/usr/bin/env python3
"""Install or remove Anchor's local-only macOS background services."""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
REFRESH_LABEL = "com.timurakhtemov.anchor.private-refresh"
DASHBOARD_LABEL = "com.timurakhtemov.anchor.private-dashboard"


def _environment(repo: Path, env_file: Path, private_data_dir: Path) -> dict[str, str]:
    return {
        "ANCHOR_ENV_FILE": str(env_file),
        "ANCHOR_PRIVATE_DATA_DIR": str(private_data_dir),
        "ANCHOR_PYTHON": str(repo / "venv" / "bin" / "python"),
        "ANCHOR_DBT": str(Path.home() / ".local" / "bin" / "dbt"),
        "GOOGLE_APPLICATION_CREDENTIALS": str(
            Path.home() / ".dbt" / "anchor-bigquery-key.json"
        ),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    }


def build_plists(
    repo: Path,
    env_file: Path,
    private_data_dir: Path,
    *,
    hour: int = 18,
    minute: int = 30,
) -> dict[str, dict]:
    env = _environment(repo, env_file, private_data_dir)
    log_dir = repo / "var" / "logs"
    refresh = {
        "Label": REFRESH_LABEL,
        "ProgramArguments": [
            str(repo / "venv" / "bin" / "python"),
            str(repo / "scripts" / "private_daily.py"),
            "refresh",
        ],
        "WorkingDirectory": str(repo),
        "EnvironmentVariables": env,
        "StartCalendarInterval": [
            {"Weekday": weekday, "Hour": hour, "Minute": minute}
            for weekday in range(2, 7)  # Monday through Friday
        ],
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / "private_refresh.out.log"),
        "StandardErrorPath": str(log_dir / "private_refresh.err.log"),
    }
    dashboard_env = {
        **env,
        "ANCHOR_PORTFOLIO": "real",
        "ANCHOR_SOURCE": "bigquery",
        "ANCHOR_PRIVATE_STATUS_PATH": str(repo / "var" / "private_daily_status.json"),
    }
    dashboard = {
        "Label": DASHBOARD_LABEL,
        "ProgramArguments": [
            str(repo / "venv" / "bin" / "streamlit"),
            "run",
            str(repo / "app" / "app.py"),
            "--server.headless=true",
            "--server.address=127.0.0.1",
            "--server.port=8501",
        ],
        "WorkingDirectory": str(repo),
        "EnvironmentVariables": dashboard_env,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Interactive",
        "ThrottleInterval": 10,
        "StandardOutPath": str(log_dir / "private_dashboard.out.log"),
        "StandardErrorPath": str(log_dir / "private_dashboard.err.log"),
    }
    return {REFRESH_LABEL: refresh, DASHBOARD_LABEL: dashboard}


def _write_plist(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        plistlib.dump(payload, handle, sort_keys=True)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _launchctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(("launchctl", *args), check=check, text=True)


def install(repo: Path, env_file: Path, private_data_dir: Path) -> int:
    python = repo / "venv" / "bin" / "python"
    streamlit = repo / "venv" / "bin" / "streamlit"
    missing = [path for path in (python, streamlit, env_file) if not path.is_file()]
    if missing:
        print("Cannot install; missing: " + ", ".join(map(str, missing)), file=sys.stderr)
        return 1

    (repo / "var" / "logs").mkdir(parents=True, exist_ok=True)
    agents = Path.home() / "Library" / "LaunchAgents"
    domain = f"gui/{os.getuid()}"
    for label, payload in build_plists(repo, env_file, private_data_dir).items():
        path = agents / f"{label}.plist"
        _launchctl("bootout", domain, str(path), check=False)
        _write_plist(path, payload)
        _launchctl("bootstrap", domain, str(path))
        _launchctl("enable", f"{domain}/{label}")
        print(f"installed {label}")
    return 0


def uninstall() -> int:
    agents = Path.home() / "Library" / "LaunchAgents"
    domain = f"gui/{os.getuid()}"
    for label in (REFRESH_LABEL, DASHBOARD_LABEL):
        path = agents / f"{label}.plist"
        _launchctl("bootout", domain, str(path), check=False)
        if path.exists():
            path.unlink()
        print(f"removed {label}")
    return 0


def status() -> int:
    domain = f"gui/{os.getuid()}"
    code = 0
    for label in (REFRESH_LABEL, DASHBOARD_LABEL):
        result = _launchctl("print", f"{domain}/{label}", check=False)
        state = "loaded" if result.returncode == 0 else "not loaded"
        print(f"{label}: {state}")
        code |= result.returncode != 0
    return int(bool(code))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "status", "uninstall"))
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument(
        "--private-data-dir", type=Path, default=REPO_ROOT / "data" / "private"
    )
    args = parser.parse_args()
    if args.command == "install":
        return install(args.repo.resolve(), args.env_file.expanduser(), args.private_data_dir.expanduser())
    if args.command == "uninstall":
        return uninstall()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
