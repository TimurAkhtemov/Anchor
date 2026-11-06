# Private Daily Operations

_Status: the real portfolio moved from a localhost Streamlit app to the same Next.js
app as the public site, 2026-11-06. It is built on the Mac from private data and served
only on loopback. Real holdings stay private._

Anchor has two deliberately separate operating paths:

- **Public/demo:** the Dagster graph and GitHub Actions refresh, public marts, and the
  committed web bundle behind the public site.
- **Private/real:** a macOS user service that reads the user's SnapTrade Personal
  connection, refreshes shared public market data, builds only `prod-private`,
  generates the real briefing locally, and builds the same web app into gitignored
  `var/private_web`.

The private bundle and every private build live only under `var/`. The site binds only
to `127.0.0.1:8501`, the same address the Streamlit app used.

## Installed services

| Service | Behavior |
|---|---|
| `com.timurakhtemov.anchor.private-refresh` | Weekdays at 21:30 America/New_York: SnapTrade → FRED/yfinance → private dbt build → local briefing → private bundle → private site → atomic swap |
| `com.timurakhtemov.anchor.private-dashboard` | `venv/bin/python -m http.server 8501 --bind 127.0.0.1 --directory var/private_web/current`, serving <http://127.0.0.1:8501> while the user is logged in. It holds no secrets and reads no database. |

The refresh uses a non-blocking file lock, so a delayed run cannot overlap the
next invocation. Status is written atomically to
`var/private_daily_status.json`; it contains timestamps, stage names, and the
market as-of date only—never holdings or credentials.

The server resolves `current` per request, so a new build goes live with no restart.
Before the first build it answers 404 rather than crash-looping, so **after a first
install, run `make refresh-private` to have a page to serve.**

## Failure behavior

| What failed | State | Result |
|---|---|---|
| `private_briefing` (soft) | `degraded`, with `degraded_steps` listing it | Later steps still run and `last_success_at` updates. The site gets fresh numbers without narration, because the export emits `briefing: null` when the briefing's date differs from the market's. |
| Any other step, including `private_bundle` and `private_site` | `failed` | The run stops and `last_success_at` keeps its old value. `current` is untouched, so the last good site keeps serving. |
| Preflight (missing `npm`, `web/node_modules`, keys, runtime) | `failed` at `preflight` | No portfolio API call is attempted. |

The page itself shows staleness: the masthead line reads "Data through <date>, N days
ago". For the reason behind a stale page, use `make private-status`; the static site
does not read the status file.

`--skip-briefing` is a deliberate choice, not a failure, so that run records `success`.

A failed site build removes its partial directory. Its `next build` output goes to
`var/private_web/last_build_failure.log` (mode 0600), not the service logs, because a
failing page render could echo bundle values. The next successful build deletes it.

The build needs the network: `next/font/google` downloads fonts from Google, and no
cache survives between builds. Offline, the build fails hard and the last site serves.

## How the site is built

`scripts/private_web.py` runs `next build` in a throwaway copy of `web/` at
`var/private_web/work-<ts>`, because Next's `distDir` may not leave the project and
`next build` also rewrites `next-env.d.ts` and `tsconfig.json`. The copy excludes
`tests/`, `public/data/` (the demo bundle), `.env*`, and generated output, and gets an
APFS clone of `web/node_modules`. The result moves to `var/private_web/build-<ts>`, the
`current` symlink is repointed with `os.replace`, and the copy is deleted. Only the
current build and one previous build are kept.

Before the swap, the build must have produced all three pages and its masthead must
read "Private", so a build that fell back to demo data cannot go live at this address.

The copy contains an empty `.git` directory. Without it, Tailwind turns off gitignore
handling because `var/` is ignored, then scans `node_modules` and emits about 630 unused
utility classes.

## Setup and control

```bash
make bootstrap-private     # Python runtime, plus npm ci in web/
make probe-snaptrade       # read-only; does not write holdings
make refresh-private       # manual full private refresh
make private-status
make install-private-services
```

`make install-private-services` resolves `npm` from your shell and records it in the
refresh plist as `ANCHOR_NPM`, because LaunchAgents have a minimal `PATH`. Reinstall the
services if Node moves.

When another local model workload is active, skip only that invocation's
briefing while still refreshing the portfolio data:

```bash
./venv/bin/python scripts/private_daily.py refresh --skip-briefing
```

The installed schedule does not use that flag; normal post-close runs retain
the local briefing. To stop and remove both services:

```bash
make uninstall-private-services
```

Logs are local and gitignored under `var/logs/`. The private pipeline's own output holds
step names, row counts, and numbered (not named) tickers; the dashboard log holds request
lines, which are routes plus Next's opaque `_rsc` tokens. `next build` output is captured
rather than logged. For the real portfolio, a failed briefing validation logs that it
failed but not why, since those messages quote tickers, figures, and narration, and
numeric-audit warnings log only a count. SnapTrade transport errors are sanitized before
they reach these logs because raw SDK exceptions can include signed-request context.

## Privacy invariants

- SnapTrade uses read-only position endpoints and Personal API-key
  authentication; Personal requests omit the Commercial-only
  `userId`/`userSecret` fields.
- The dbt build is hard-pinned to `--target prod-private --vars
  '{holdings_source: real}'`.
- The real bundle and site live only under gitignored `var/private_web/`. Nothing real
  is written to `web/public/`, `web/out/`, `web/.next/`, `web/next-env.d.ts`, or
  `web/tsconfig.json`, including build caches, because the build never runs in `web/`.
- `app/export_web.py` refuses a real export whose path resolves outside `var/`, before
  any BigQuery client exists. `scripts/private_web.py` refuses a root or bundle outside
  `var/`, and any bundle that does not say `portfolio: real`.
- A real-portfolio build leaves `git status` clean, and temp files and npm's cache stay
  in the deleted workspace. The build gets a minimal environment with no refresh
  secrets, and Next telemetry is off.
- The private bundle is mode 0600 and `var/private_web` is mode 0700.
- The private briefing stays local. The `build_provider` guard is unchanged.
- The dashboard is localhost-only, not LAN-bound and not publicly hosted.
- `.env`, `data/private/`, `venv/`, `var/` (runtime status, logs, bundle, builds) are
  gitignored.

The Mac must be powered on and the user logged in for these user-level services
to run. `launchd` retains the calendar schedule, but this is intentionally not a
cloud availability guarantee.
