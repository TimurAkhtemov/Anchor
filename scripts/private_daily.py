#!/usr/bin/env python3
"""Run Anchor's private portfolio pipeline locally and record safe status.

This runner is intentionally separate from the public/demo Dagster graph. It
pulls read-only brokerage positions through SnapTrade, refreshes shared market
data, builds only the ``prod-private`` dbt target, and normally generates the
private briefing through local Ollama. ``--skip-briefing`` provides a temporary
maintenance escape hatch when another local model workload is active. The
runner never exports a parquet or web bundle.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VAR_DIR = REPO_ROOT / "var"
STATUS_PATH = VAR_DIR / "private_daily_status.json"
LOCK_PATH = VAR_DIR / "private_daily.lock"
REQUIRED_NONEMPTY_ENV = (
    "FRED_API_KEY",
    "SNAPTRADE_CLIENT_ID",
    "SNAPTRADE_CONSUMER_KEY",
)


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    cwd: Path = REPO_ROOT


class PreflightError(RuntimeError):
    """The local runtime is incomplete; no portfolio API call was attempted."""


class StepError(RuntimeError):
    """A named pipeline step failed without exposing its raw command payload."""

    def __init__(self, step: str, returncode: int):
        super().__init__(f"{step} failed with exit code {returncode}")
        self.step = step
        self.returncode = returncode


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.chmod(temp_path, 0o600)
    temp_path.replace(path)


def configure_environment() -> tuple[Path, Path, Path, Path]:
    """Load the local secret file and return resolved runtime paths."""
    from dotenv import load_dotenv

    env_file = Path(os.environ.get("ANCHOR_ENV_FILE", REPO_ROOT / ".env")).expanduser()
    load_dotenv(env_file, override=False)

    python = Path(os.environ.get("ANCHOR_PYTHON", REPO_ROOT / "venv" / "bin" / "python"))
    dbt = Path(os.environ.get("ANCHOR_DBT", Path.home() / ".local" / "bin" / "dbt"))
    keyfile = Path(
        os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS",
            Path.home() / ".dbt" / "anchor-bigquery-key.json",
        )
    ).expanduser()
    private_dir = Path(
        os.environ.get("ANCHOR_PRIVATE_DATA_DIR", REPO_ROOT / "data" / "private")
    ).expanduser()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(keyfile)
    # Real holdings are local-only even if the user's general .env selects a
    # cloud provider for the demo world.
    os.environ["ANCHOR_BRIEFING_PROVIDER"] = "ollama"
    return env_file, python, dbt, private_dir


def preflight() -> tuple[Path, Path, Path]:
    env_file, python, dbt, private_dir = configure_environment()
    missing = [key for key in REQUIRED_NONEMPTY_ENV if not os.environ.get(key)]
    # Personal keys omit user credentials. Commercial mode is inferred from a
    # non-empty user secret and then requires its paired user id.
    if os.environ.get("SNAPTRADE_USER_SECRET") and not os.environ.get("SNAPTRADE_USER_ID"):
        missing.append("SNAPTRADE_USER_ID")
    problems: list[str] = []
    if not env_file.is_file():
        problems.append(f"environment file not found: {env_file}")
    if missing:
        problems.append("missing environment keys: " + ", ".join(missing))
    if not python.is_file():
        problems.append(f"private runtime not found: {python}")
    if not dbt.is_file():
        problems.append(f"dbt executable not found: {dbt}")
    keyfile = Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    if not keyfile.is_file():
        problems.append(f"BigQuery keyfile not found: {keyfile}")
    if problems:
        raise PreflightError("; ".join(problems))
    return python, dbt, private_dir


def build_steps(
    python: Path, dbt: Path, private_dir: Path, *, include_briefing: bool = True
) -> list[Step]:
    holdings = [
        str(python),
        "ingestion/ingest_holdings.py",
        "--from-snaptrade",
        "--portfolio",
        "real",
    ]
    classifications = private_dir / "fund_classifications_real.csv"
    if classifications.is_file():
        holdings.extend(("--fund-classifications", str(classifications)))

    steps = [
        Step("snaptrade_holdings", tuple(holdings)),
        Step("fred", (str(python), "ingestion/ingest_fred.py")),
        Step("market_prices", (str(python), "ingestion/ingest_yfinance.py")),
        Step(
            "private_marts",
            (
                str(dbt),
                "build",
                "--target",
                "prod-private",
                "--vars",
                '{"holdings_source": "real"}',
            ),
            REPO_ROOT / "transformation",
        ),
    ]
    if include_briefing:
        steps.append(
            Step(
                "private_briefing",
                (str(python), "app/generate_briefing.py", "--portfolio", "real"),
            )
        )
    return steps


def _run_step(step: Step) -> None:
    print(f"[{_now()}] START {step.name}", flush=True)
    result = subprocess.run(step.command, cwd=step.cwd, env=os.environ.copy(), check=False)
    if result.returncode:
        raise StepError(step.name, result.returncode)
    print(f"[{_now()}] OK {step.name}", flush=True)


def _private_data_as_of() -> str | None:
    """Read only the private mart's market date; no holding values leave BQ."""
    try:
        from google.cloud import bigquery

        client = bigquery.Client.from_service_account_json(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"], project="anchor-495115"
        )
        rows = list(
            client.query(
                "select as_of_date from `anchor-495115.anchor_marts_private.as_of_calendar` limit 1"
            ).result()
        )
        return str(rows[0].as_of_date) if rows else None
    except Exception:
        # Status reporting must never turn a successful data refresh into a
        # failed one. The dashboard still exposes mart-level as-of dates.
        return None


def refresh(*, skip_briefing: bool = False) -> int:
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("private refresh already running; skipped", flush=True)
            return 0

        previous = _load_json(STATUS_PATH)
        started_at = _now()
        current_step = "preflight"
        _write_json(
            STATUS_PATH,
            {
                "state": "running",
                "step": current_step,
                "started_at": started_at,
                "last_success_at": previous.get("last_success_at"),
                "data_as_of": previous.get("data_as_of"),
            },
        )
        try:
            python, dbt, private_dir = preflight()
            for step in build_steps(
                python, dbt, private_dir, include_briefing=not skip_briefing
            ):
                current_step = step.name
                status = _load_json(STATUS_PATH)
                status["step"] = current_step
                _write_json(STATUS_PATH, status)
                _run_step(step)
        except (PreflightError, StepError) as exc:
            failed = {
                "state": "failed",
                "step": getattr(exc, "step", current_step),
                "started_at": started_at,
                "finished_at": _now(),
                "last_success_at": previous.get("last_success_at"),
                "data_as_of": previous.get("data_as_of"),
                "error": str(exc),
            }
            _write_json(STATUS_PATH, failed)
            print(f"private refresh failed: {exc}", file=sys.stderr, flush=True)
            return 1
        except KeyboardInterrupt:
            _write_json(
                STATUS_PATH,
                {
                    "state": "failed",
                    "step": current_step,
                    "started_at": started_at,
                    "finished_at": _now(),
                    "last_success_at": previous.get("last_success_at"),
                    "data_as_of": previous.get("data_as_of"),
                    "error": "refresh interrupted",
                },
            )
            print("private refresh interrupted", file=sys.stderr, flush=True)
            return 130

        finished_at = _now()
        _write_json(
            STATUS_PATH,
            {
                "state": "success",
                "step": "complete",
                "started_at": started_at,
                "finished_at": finished_at,
                "last_success_at": finished_at,
                "data_as_of": _private_data_as_of(),
            },
        )
        print(f"[{finished_at}] private refresh complete", flush=True)
        return 0


def probe_snaptrade() -> int:
    python, _dbt, _private_dir = preflight()
    result = subprocess.run(
        (
            str(python),
            "-c",
            "from ingestion.ingest_holdings import fetch_snaptrade_positions; "
            "\ntry:\n fetch_snaptrade_positions(); print('SnapTrade read-only connection OK')"
            "\nexcept RuntimeError as exc:\n print(str(exc)); raise SystemExit(1)",
        ),
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        check=False,
    )
    return result.returncode


def print_status() -> int:
    status = _load_json(STATUS_PATH)
    if not status:
        print("No private refresh has run from this checkout yet.")
        return 1
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "probe-snaptrade", "refresh", "status"))
    parser.add_argument(
        "--skip-briefing",
        action="store_true",
        help="run the data pipeline without an Ollama call for this invocation",
    )
    args = parser.parse_args()
    if args.command == "check":
        preflight()
        print("Private operations preflight OK")
        return 0
    if args.command == "probe-snaptrade":
        return probe_snaptrade()
    if args.command == "refresh":
        return refresh(skip_briefing=args.skip_briefing)
    return print_status()


if __name__ == "__main__":
    raise SystemExit(main())
