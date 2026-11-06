"""The private site build: everything real stays under var/, the swap is atomic,
and a failed build leaves the last good site serving."""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts import private_web
from scripts.private_web import SiteBuildError, build_private_site

GOOD_PAGE = "<html><body>Anchor · Private</body></html>"
DEMO_PAGE = "<html><body>Anchor · Demo portfolio</body></html>"
PAGES = ("index.html", "reading/index.html", "text/index.html")


class FakeRun:
    """Stands in for subprocess.run: `cp` clones, `npm run build` writes out/."""

    def __init__(
        self,
        page: str = GOOD_PAGE,
        returncode: int = 0,
        output: str = "Route (app)",
        hang: bool = False,
    ):
        self.hang = hang
        self.page = page
        self.returncode = returncode
        self.output = output
        self.build_calls: list[dict] = []
        self.calls = 0

    def __call__(self, command, **kwargs):
        self.calls += 1
        if command[0] == "cp":
            Path(command[-1]).mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0)
        cwd = Path(kwargs["cwd"])
        self.build_calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": kwargs["env"],
                "timeout": kwargs.get("timeout"),
                "listing": {p.name for p in cwd.iterdir()},
                "has_demo_bundle": (cwd / "public" / "data").exists(),
            }
        )
        for page in PAGES:
            target = cwd / "out" / page
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.page)
        if self.hang:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial output")
        return subprocess.CompletedProcess(command, self.returncode, stdout=self.output)


def _snapshot(directory: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in directory.rglob("*")}


@pytest.fixture
def env(tmp_path, monkeypatch):
    var = tmp_path / "var"
    web = tmp_path / "web"
    for rel in (
        "src/app/page.tsx",
        "public/data/anchor.json",
        "next.config.ts",
        "package.json",
        ".gitignore",
        "node_modules/next/index.js",
        ".next/cache/stale",
        "out/index.html",
        "next-env.d.ts",
        "tsconfig.tsbuildinfo",
        "tests/x.spec.ts",
        ".env.local",
    ):
        path = web / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    bundle = var / "private_web" / "anchor.json"
    bundle.parent.mkdir(parents=True)
    bundle.write_text(json.dumps({"portfolio": "real"}))
    monkeypatch.setattr(private_web, "VAR_DIR", var)
    monkeypatch.setattr(private_web, "WEB_DIR", web)
    monkeypatch.setenv("ANCHOR_NPM", "/runtime/npm")
    monkeypatch.setenv("FRED_API_KEY", "secret-value")
    return {"var": var, "web": web, "root": var / "private_web", "bundle": bundle}


def _use(monkeypatch, fake: FakeRun) -> FakeRun:
    monkeypatch.setattr(private_web.subprocess, "run", fake)
    return fake


def _builds(root: Path) -> list[str]:
    return sorted(p.name for p in root.glob("build-*"))


def test_build_repoints_current_to_the_new_build(env, monkeypatch):
    _use(monkeypatch, FakeRun())
    build = build_private_site(env["bundle"], env["root"])
    current = env["root"] / "current"
    assert current.is_symlink()
    assert os.readlink(current) == build.name  # relative, so it survives a move
    assert build.parent == env["root"] and build.name.startswith("build-")
    assert (current / "index.html").read_text() == GOOD_PAGE
    assert (current / "reading" / "index.html").is_file()
    assert not list(env["root"].glob(".current*")), "temp symlink left behind"
    assert not list(env["root"].glob("work-*")), "build workspace left behind"


def test_failed_build_keeps_current_symlink(env, monkeypatch):
    _use(monkeypatch, FakeRun())
    good = build_private_site(env["bundle"], env["root"])
    _use(monkeypatch, FakeRun(returncode=1))
    with pytest.raises(SiteBuildError):
        build_private_site(env["bundle"], env["root"])
    assert os.readlink(env["root"] / "current") == good.name
    assert _builds(env["root"]) == [good.name], "partial build not removed"
    assert not list(env["root"].glob("work-*"))
    assert (env["root"] / "current" / "index.html").read_text() == GOOD_PAGE


def test_hung_build_times_out_and_keeps_current(env, monkeypatch):
    _use(monkeypatch, FakeRun())
    good = build_private_site(env["bundle"], env["root"])
    fake = _use(monkeypatch, FakeRun(hang=True))
    with pytest.raises(SiteBuildError, match="timed out"):
        build_private_site(env["bundle"], env["root"])
    assert fake.build_calls[0]["timeout"] == 600
    assert os.readlink(env["root"] / "current") == good.name
    assert _builds(env["root"]) == [good.name], "partial build not removed"
    assert not list(env["root"].glob("work-*"))
    assert (env["root"] / "last_build_failure.log").read_text() == "partial output"


def test_failed_first_build_leaves_no_current(env, monkeypatch):
    _use(monkeypatch, FakeRun(returncode=1))
    with pytest.raises(SiteBuildError):
        build_private_site(env["bundle"], env["root"])
    assert not (env["root"] / "current").is_symlink()
    assert _builds(env["root"]) == []


def test_page_rendered_as_demo_never_goes_live(env, monkeypatch):
    """A build that ignored the private bundle would present demo numbers at the
    private address, so it fails before the swap."""
    _use(monkeypatch, FakeRun())
    good = build_private_site(env["bundle"], env["root"])
    _use(monkeypatch, FakeRun(page=DEMO_PAGE))
    with pytest.raises(SiteBuildError, match="masthead"):
        build_private_site(env["bundle"], env["root"])
    assert os.readlink(env["root"] / "current") == good.name
    assert _builds(env["root"]) == [good.name]


def test_only_current_and_one_previous_build_are_kept(env, monkeypatch):
    _use(monkeypatch, FakeRun())
    stale_work = env["root"] / "work-crashed"
    stale_work.mkdir()
    first = build_private_site(env["bundle"], env["root"])
    second = build_private_site(env["bundle"], env["root"])
    assert _builds(env["root"]) == sorted([first.name, second.name])
    third = build_private_site(env["bundle"], env["root"])
    assert _builds(env["root"]) == sorted([second.name, third.name])
    assert os.readlink(env["root"] / "current") == third.name
    assert not stale_work.exists()
    assert env["bundle"].is_file(), "the bundle is not a build; pruning must keep it"


def test_build_paths_stay_under_var(env, monkeypatch):
    fake = _use(monkeypatch, FakeRun())
    before = _snapshot(env["web"])
    build_private_site(env["bundle"], env["root"])
    call = fake.build_calls[0]

    assert call["command"] == ("/runtime/npm", "run", "build")
    # distDir may not leave the project, so the project itself moves: dist output
    # is <cwd>/.next and <cwd>/out, both under var/.
    assert call["cwd"].is_relative_to(env["var"])
    assert Path(call["env"]["ANCHOR_BUNDLE_PATH"]) == env["bundle"].resolve()
    assert Path(call["env"]["TMPDIR"]).is_relative_to(env["var"])
    assert Path(call["env"]["npm_config_cache"]).is_relative_to(env["var"])
    assert "ANCHOR_DIST_DIR" not in call["env"]
    assert _snapshot(env["web"]) == before, "the build touched web/"


def test_build_env_is_minimal(env, monkeypatch):
    fake = _use(monkeypatch, FakeRun())
    build_private_site(env["bundle"], env["root"])
    build_env = fake.build_calls[0]["env"]
    assert "FRED_API_KEY" not in build_env
    assert build_env["NEXT_TELEMETRY_DISABLED"] == "1"


def test_workspace_is_a_clean_source_copy(env, monkeypatch):
    fake = _use(monkeypatch, FakeRun())
    build_private_site(env["bundle"], env["root"])
    call = fake.build_calls[0]
    assert {"src", "package.json", "next.config.ts", "node_modules"} <= call["listing"]
    for excluded in (".next", "out", "next-env.d.ts", "tsconfig.tsbuildinfo", "tests", ".env.local"):
        assert excluded not in call["listing"], excluded
    assert call["has_demo_bundle"] is False, "public/data has no place in a private build"
    # Tailwind turns gitignore handling off for a base inside an ignored path and
    # then scans node_modules; a .git marker makes the copy its own boundary.
    assert {".git", ".gitignore"} <= call["listing"]


@pytest.mark.parametrize("target", ["root", "bundle"])
def test_paths_outside_var_are_refused(env, monkeypatch, tmp_path, target):
    fake = _use(monkeypatch, FakeRun())
    outside = tmp_path / "web" / "public"
    if target == "root":
        args = (env["bundle"], outside)
    else:
        leaked = outside / "anchor.json"
        leaked.write_text(json.dumps({"portfolio": "real"}))
        args = (leaked, env["root"])
    with pytest.raises(SiteBuildError, match="var"):
        build_private_site(*args)
    assert fake.calls == 0


def test_symlink_escaping_var_is_refused(env, monkeypatch, tmp_path):
    fake = _use(monkeypatch, FakeRun())
    escape = env["var"] / "escape"
    escape.symlink_to(tmp_path / "web" / "public")
    with pytest.raises(SiteBuildError, match="var"):
        build_private_site(env["bundle"], escape)
    assert fake.calls == 0


def test_demo_bundle_is_refused(env, monkeypatch):
    fake = _use(monkeypatch, FakeRun())
    env["bundle"].write_text(json.dumps({"portfolio": "demo"}))
    with pytest.raises(SiteBuildError, match="real"):
        build_private_site(env["bundle"], env["root"])
    assert fake.calls == 0


def test_missing_bundle_is_a_clean_failure(env, monkeypatch):
    _use(monkeypatch, FakeRun())
    env["bundle"].unlink()
    with pytest.raises(SiteBuildError, match="not found"):
        build_private_site(env["bundle"], env["root"])


def test_missing_npm_is_a_clean_failure(env, monkeypatch):
    fake = _use(monkeypatch, FakeRun())
    monkeypatch.delenv("ANCHOR_NPM")
    monkeypatch.setattr(private_web.shutil, "which", lambda _: None)
    with pytest.raises(SiteBuildError, match="npm"):
        build_private_site(env["bundle"], env["root"])
    assert fake.calls == 0


def test_build_output_never_reaches_the_service_logs(env, monkeypatch, capfd):
    """A failing page render can echo bundle values, and stdout/stderr here are
    the LaunchAgent's log files. The output stays beside the bundle instead."""
    _use(monkeypatch, FakeRun(returncode=1, output="Error rendering ZZPRIVATE row"))
    with pytest.raises(SiteBuildError) as caught:
        build_private_site(env["bundle"], env["root"])
    assert "ZZPRIVATE" not in str(caught.value)
    streams = capfd.readouterr()
    assert "ZZPRIVATE" not in streams.out + streams.err
    kept = env["root"] / "last_build_failure.log"
    assert "ZZPRIVATE" in kept.read_text()
    assert stat.S_IMODE(kept.stat().st_mode) == 0o600


def test_success_clears_the_failure_output(env, monkeypatch):
    _use(monkeypatch, FakeRun(returncode=1))
    with pytest.raises(SiteBuildError):
        build_private_site(env["bundle"], env["root"])
    _use(monkeypatch, FakeRun())
    build_private_site(env["bundle"], env["root"])
    assert not (env["root"] / "last_build_failure.log").exists()


def test_main_reports_failure_without_a_traceback(env, monkeypatch, capsys):
    monkeypatch.setattr(private_web, "BUNDLE_PATH", env["bundle"])
    monkeypatch.setattr(private_web, "PRIVATE_ROOT", env["root"])
    _use(monkeypatch, FakeRun(returncode=1))
    assert private_web.main(["build"]) == 1
    assert "failed" in capsys.readouterr().err


def test_main_builds_the_default_bundle(env, monkeypatch, capsys):
    monkeypatch.setattr(private_web, "BUNDLE_PATH", env["bundle"])
    monkeypatch.setattr(private_web, "PRIVATE_ROOT", env["root"])
    _use(monkeypatch, FakeRun())
    assert private_web.main(["build"]) == 0
    assert (env["root"] / "current" / "index.html").is_file()
    assert "build-" in capsys.readouterr().out
