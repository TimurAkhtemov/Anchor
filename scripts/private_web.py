#!/usr/bin/env python3
"""Build the real portfolio's static site under var/ and swap it in atomically.

Next's `distDir` may not leave the project (its own doc calls `../build` invalid)
and `next build` writes `.next/`, `out/`, `next-env.d.ts`, and `tsconfig.json`
relative to the project. So the project moves instead: each build runs in a
throwaway copy of `web/` at `var/private_web/work-<ts>`, which is what keeps real
data out of `web/` and its build caches. The result lands at `build-<ts>` and the
`current` symlink, which the localhost server reads, is repointed in one syscall.
A failed build never touches `current`, so the last good site keeps serving.

Holdings stay out of the service logs: `next build` output is captured rather
than inherited, because a failing page render can echo bundle values.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VAR_DIR = REPO_ROOT / "var"
WEB_DIR = REPO_ROOT / "web"
PRIVATE_ROOT = VAR_DIR / "private_web"
BUNDLE_PATH = PRIVATE_ROOT / "anchor.json"
FAILURE_LOG = "last_build_failure.log"
BUILD_TIMEOUT_SECONDS = 600
PAGES = ("index.html", "reading/index.html", "text/index.html")

# Anything generated, test-only, or environment-specific stays behind. The real
# dependency tree arrives separately as a clone.
_NOT_COPIED = shutil.ignore_patterns(
    "node_modules",
    ".next",
    "out",
    "test-results",
    "playwright-report",
    "tests",
    "*.tsbuildinfo",
    "next-env.d.ts",
    ".env*",
    ".vercel",
)


class SiteBuildError(RuntimeError):
    """The private site was not built; `current` was left as it was."""


def _require_under_var(path: Path, label: str) -> None:
    if not path.resolve().is_relative_to(VAR_DIR.resolve()):
        raise SiteBuildError(f"{label} must be under {VAR_DIR}, not {path}")


def _check_bundle(bundle_path: Path) -> None:
    try:
        portfolio = json.loads(bundle_path.read_text()).get("portfolio")
    except FileNotFoundError:
        raise SiteBuildError(f"private bundle not found: {bundle_path}") from None
    except json.JSONDecodeError:
        raise SiteBuildError(f"private bundle is not valid JSON: {bundle_path}") from None
    if portfolio != "real":
        raise SiteBuildError(
            f"expected a real-portfolio bundle, found portfolio={portfolio!r}"
        )


def _resolve_npm() -> str:
    npm = os.environ.get("ANCHOR_NPM") or shutil.which("npm")
    if not npm:
        raise SiteBuildError("npm not found; set ANCHOR_NPM or reinstall the services")
    return npm


def _prepare_workspace(workspace: Path) -> None:
    shutil.copytree(WEB_DIR, workspace, ignore=_NOT_COPIED, symlinks=True)
    # The site renders from ANCHOR_BUNDLE_PATH and nothing fetches /data/anchor.json,
    # so a private build has no reason to carry the demo bundle at all.
    shutil.rmtree(workspace / "public" / "data", ignore_errors=True)
    # Tailwind drops gitignore handling for a base inside an ignored path, and would
    # scan node_modules (var/ is ignored). This marker makes the copy its own boundary.
    (workspace / ".git").mkdir()
    (workspace / "tmp").mkdir()
    # A clone, not a symlink: Turbopack refuses links out of its root, and any write
    # a tool makes to node_modules/.cache stays in the workspace.
    clone = subprocess.run(
        ("cp", "-c", "-R", str(WEB_DIR / "node_modules"), str(workspace / "node_modules")),
        check=False,
    )
    if clone.returncode:
        raise SiteBuildError(f"could not clone web/node_modules (exit {clone.returncode})")


def _build_env(workspace: Path, bundle_path: Path) -> dict[str, str]:
    """Only what the build needs: the refresh's secrets have no business here, and
    temp files and npm's logs stay in the workspace, where they are deleted."""
    env = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    return {
        **env,
        "ANCHOR_BUNDLE_PATH": str(bundle_path.resolve()),
        "NEXT_TELEMETRY_DISABLED": "1",
        "TMPDIR": str(workspace / "tmp"),
        "npm_config_cache": str(workspace / "tmp" / "npm"),
    }


def _run_next_build(npm: str, workspace: Path, bundle_path: Path, root: Path) -> None:
    failure_log = root / FAILURE_LOG
    try:
        result = subprocess.run(
            (npm, "run", "build"),
            cwd=workspace,
            env=_build_env(workspace, bundle_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            check=False,
            timeout=BUILD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        # A hung build would hold the refresh lock and make later runs look "already running".
        partial = exc.stdout
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        failure_log.touch(mode=0o600, exist_ok=True)
        failure_log.write_text(partial or "")
        raise SiteBuildError(
            f"next build timed out after {BUILD_TIMEOUT_SECONDS}s; output kept in {failure_log}"
        ) from None
    if result.returncode:
        # Beside the bundle, under the same protection, and not in the service logs.
        failure_log.touch(mode=0o600, exist_ok=True)
        failure_log.write_text(result.stdout or "")
        raise SiteBuildError(
            f"next build exited {result.returncode}; output kept in {failure_log}"
        )
    failure_log.unlink(missing_ok=True)


def _verify_output(out: Path) -> None:
    """The masthead proves the page rendered from the private bundle. A build that
    silently fell back to demo data must not appear at the private address."""
    for page in PAGES:
        if not (out / page).is_file():
            raise SiteBuildError(f"next build did not produce {page}")
    home = (out / "index.html").read_text()
    if "Private" not in home or "Demo portfolio" in home:
        raise SiteBuildError("masthead does not read Private; refusing to go live")


def _swap_current(root: Path, build: Path) -> None:
    temporary = root / f".current.{os.getpid()}"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(build.name)
    os.replace(temporary, root / "current")


def _prune(root: Path, keep: set[str]) -> None:
    for pattern in ("build-*", "work-*"):
        for path in root.glob(pattern):
            if path.name not in keep:
                shutil.rmtree(path, ignore_errors=True)


def build_private_site(bundle_path: Path, root: Path = PRIVATE_ROOT) -> Path:
    """Build `bundle_path` into `root/build-<ts>` and point `root/current` at it."""
    _require_under_var(root, "private site root")
    _require_under_var(bundle_path, "private bundle")
    _check_bundle(bundle_path)
    npm = _resolve_npm()

    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    workspace = root / f"work-{stamp}"
    build = root / f"build-{stamp}"
    current = root / "current"
    previous = os.readlink(current) if current.is_symlink() else None
    try:
        _prepare_workspace(workspace)
        _run_next_build(npm, workspace, bundle_path, root)
        _verify_output(workspace / "out")
        (workspace / "out").rename(build)
        _swap_current(root, build)
    except BaseException:
        shutil.rmtree(build, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    _prune(root, {build.name, previous} if previous else {build.name})
    return build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build",))
    args = parser.parse_args(argv)
    if args.command == "build":
        try:
            build = build_private_site(BUNDLE_PATH, PRIVATE_ROOT)
        except SiteBuildError as exc:
            print(f"private site build failed: {exc}", file=sys.stderr, flush=True)
            return 1
        print(f"private site live: {build.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
