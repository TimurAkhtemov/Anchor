#!/usr/bin/env python3
"""Public (demo-world) refresh: briefing if there is a new settled date, then export.

The GitHub Actions workflow is only a trigger over `make public-refresh`; the logic
lives here so it is testable with fakes. Order of operations:

1. Read the settled as-of date from the prod marts (`anchor_marts.as_of_calendar`).
2. Generate a briefing only when the committed bundle lacks one for that date
   ("nothing new, nothing spent"). A briefing failure is logged and the numbers
   still publish, with a null briefing.
3. If nothing needs generating and the committed bundle is already at that date,
   skip the export entirely.
4. Otherwise export to a temp file beside the bundle, validate it, and only then
   `os.replace` it in. A failed export or validation leaves the committed bundle
   untouched. `changed` compares content, so a no-op run never produces a commit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Literal

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.bundle_validation import BundleValidationError, validate_bundle  # noqa: E402
from app.export_web import BUNDLE_PATH, PROJECT, PUBLIC_DATASET, export_web  # noqa: E402


@dataclass(frozen=True)
class RefreshResult:
    changed: bool
    as_of: str
    briefing_status: Literal["generated", "reused", "failed"]


BRIEFING_TIMEOUT_SECONDS = 900


def _parse_date(value) -> date:
    return date.fromisoformat(str(value)[:10])


def should_generate_briefing(mart_as_of: str, bundle: dict | None) -> bool:
    if not bundle:
        return True
    bundle_as_of = (bundle.get("as_of_calendar") or {}).get("as_of_date")
    if bundle_as_of is None:
        return True
    mart_date, bundle_date = _parse_date(mart_as_of), _parse_date(bundle_as_of)
    if mart_date < bundle_date:
        # Never spend a model call to publish older numbers over newer ones.
        raise BundleValidationError(
            f"mart as-of {mart_date} is older than the committed bundle's {bundle_date}"
        )
    return mart_date > bundle_date or not bundle.get("briefing")


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def _mart_as_of(client) -> str:
    df = client.query(f"select * from `{PROJECT}.{PUBLIC_DATASET}.as_of_calendar`").to_dataframe()
    return str(df.iloc[0]["as_of_date"])


def refresh(
    client,
    bundle_path: Path,
    run_briefing: Callable[[], None],
    today: date | None = None,
) -> RefreshResult:
    bundle_path = Path(bundle_path)
    old = _load(bundle_path)
    as_of = _mart_as_of(client)

    if not should_generate_briefing(as_of, old):
        # Re-check age so a stalled settled date goes red instead of looking like a holiday.
        validate_bundle(old, today=today)
        print(f"Bundle already at {as_of} with a briefing; nothing to do.")
        return RefreshResult(changed=False, as_of=as_of, briefing_status="reused")

    try:
        run_briefing()
        status = "generated"
    except Exception as exc:  # noqa: BLE001 - numbers still publish without a briefing
        print(f"WARNING: briefing failed, publishing numbers only: {exc}", file=sys.stderr)
        status = "failed"

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=bundle_path.parent, prefix=".anchor-", suffix=".json.tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        export_web(client, tmp)
        new = json.loads(tmp.read_text())
        validate_bundle(new, today=today)
        changed = new != old
        if changed:
            os.replace(tmp, bundle_path)
    finally:
        tmp.unlink(missing_ok=True)
    return RefreshResult(changed=changed, as_of=as_of, briefing_status=status)


def default_run_briefing() -> None:
    """Run the briefing CLI with the current interpreter; logs stream through."""
    # A hang raises TimeoutExpired, which `refresh` treats as a briefing failure.
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "app" / "generate_briefing.py"), "--portfolio", "demo"],
        check=True,
        timeout=BRIEFING_TIMEOUT_SECONDS,
    )


def make_client():
    from google.cloud import bigquery

    return bigquery.Client(project=PROJECT)


def main() -> None:
    result = refresh(make_client(), BUNDLE_PATH, default_run_briefing, today=date.today())
    print(
        f"as_of={result.as_of} changed={result.changed} briefing={result.briefing_status}"
    )
    if result.briefing_status == "failed":
        message = (
            f"Briefing failed for {result.as_of}; numbers published without one. "
            "The next run retries it."
        )
        print(f"::warning::{message}")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as handle:
                handle.write(f"**Warning:** {message}\n")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a") as handle:
            handle.write(f"changed={'true' if result.changed else 'false'}\n")
            handle.write(f"as_of={result.as_of}\n")
            handle.write(f"briefing={result.briefing_status}\n")


if __name__ == "__main__":
    main()
