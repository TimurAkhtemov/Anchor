# Private Daily Operations

_Status: shipped locally 2026-08-04. Real holdings stay private; the public/demo
Dagster graph and committed snapshots are unchanged._

Anchor has two deliberately separate operating paths:

- **Public/demo:** the existing Dagster graph, public marts, committed snapshot,
  and public Streamlit deployment.
- **Private/real:** a macOS user service that reads the user's SnapTrade Personal
  connection, refreshes shared public market data, builds only
  `prod-private`, and generates the real briefing locally.

The private runner never writes a parquet snapshot or web bundle. The dashboard
binds only to `127.0.0.1:8501` and reads `anchor_marts_private` directly.

## Installed services

| Service | Behavior |
|---|---|
| `com.timurakhtemov.anchor.private-refresh` | Weekdays at 18:30 America/New_York: SnapTrade → FRED/yfinance → private dbt build → local briefing |
| `com.timurakhtemov.anchor.private-dashboard` | Keeps the real Streamlit dashboard available at <http://127.0.0.1:8501> while the user is logged in |

The refresh uses a non-blocking file lock, so a delayed run cannot overlap the
next invocation. Status is written atomically to
`var/private_daily_status.json`; it contains timestamps, stage names, and the
market as-of date only—never holdings or credentials. The real dashboard shows
that status and continues displaying the last successful marts after a failed
refresh.

## Setup and control

```bash
make bootstrap-private
make probe-snaptrade       # read-only; does not write holdings
make refresh-private       # manual full private refresh
make private-status
make install-private-services
```

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

Logs are local and gitignored under `var/logs/`. SnapTrade transport errors are
sanitized before they reach these logs because raw SDK exceptions can include
signed-request context.

## Privacy invariants

- SnapTrade uses read-only position endpoints and Personal API-key
  authentication; Personal requests omit the Commercial-only
  `userId`/`userSecret` fields.
- The dbt build is hard-pinned to `--target prod-private --vars
  '{holdings_source: real}'`.
- No private snapshot or web export appears in the runner.
- The dashboard is localhost-only, not LAN-bound and not publicly hosted.
- `.env`, `data/private/`, `venv/`, runtime status, and logs are gitignored.

The Mac must be powered on and the user logged in for these user-level services
to run. `launchd` retains the calendar schedule, but this is intentionally not a
cloud availability guarantee.
