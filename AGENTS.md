# Repository Guidelines

## Project Structure & Module Organization

Anchor follows a bronze -> silver -> gold -> serve flow. Python ingestion lives in `ingestion/`; demo holdings are in `data/`, while real inputs belong in gitignored `data/private/`. The dbt project under `transformation/` contains staging, intermediate, and mart models, plus macros, seeds, snapshots, and SQL tests. The briefing generator, web bundle exporter, and bundle validation are in `app/`. The site is the Next.js static export in `web/` (read `web/AGENTS.md` first). Refresh runners and the LaunchAgent installer are in `scripts/`. `orchestration/` is the retired Dagster code location, kept as a record. Python tests are under `tests/`; design material belongs in `docs/`.

## Build, Test, and Development Commands

- `make ingest-holdings-demo`: load `data/sample_portfolio.csv` into the demo source.
- `make ingest`: refresh FRED and yfinance bronze tables in BigQuery.
- `make build-prod`: install dbt packages, build models, and test public prod datasets.
- `make refresh`: market ingestion, the public prod build, then the briefing and validated web bundle; load holdings separately when needed.
- `make ingest-holdings-real && make build-private`: load private inputs and build isolated `anchor_*_private` datasets.
- `python -m pytest tests/ -q`: run the Python tests (ingestion, briefing, bundle validation, refresh runners).
- `make dev-web`: run the site locally against the committed bundle.
- `make refresh-private` / `make private-status`: run or inspect the local real-portfolio refresh.

Run dbt commands from `transformation/`; dbt Fusion can mishandle seeds with `--project-dir`. Example: `dbt build --select marts`. CI uses dbt Core 1.11 and Python 3.12.

## Coding Style & Naming Conventions

Use 4-space indentation, small Python modules, `snake_case` names, and comments only for non-obvious behavior. No formatter is enforced; match nearby code. UI code should consume framed marts, not join raw sources. Name dbt models by layer: `stg_yfinance__prices.sql`, `int_ticker_returns.sql`, and `holdings_benchmarks.sql`. Colocate model contracts and tests in YAML.

## Testing Guidelines

Name pytest functions `test_<behavior>`. Preserve dbt grain, relationship, and contract tests; add singular guardrails under `transformation/tests/` for business invariants. Validate warehouse changes with `dbt build` and site changes with `cd web && npm run build && npm run test:e2e`. Privacy changes must keep the bundle validation and leak-scanner tests.

## Commit & Pull Request Guidelines

Follow the scoped history style: `feat(dbt): ...`, `fix(ingestion): ...`, `test(app+ci): ...`, or `docs: ...`. Keep commits focused. PRs should identify affected layers, configuration needs, validation commands, and screenshots for UI changes. Call out demo/private isolation impacts.

## Security & Configuration Tips

Never commit `.env`, service-account keys, brokerage data, or `data/private/`. BigQuery uses `GOOGLE_APPLICATION_CREDENTIALS`; FRED uses `FRED_API_KEY`. Keep local dbt profiles outside the repository. Public builds and snapshots use demo holdings; real holdings require `prod-private`.

## Current Deployment Decision

Anchor remains local-first for orchestration. Use `make dagster` for local runs; do not deploy or enable Dagster+ Serverless while the app has no public-user need that justifies its recurring cost. The completed Serverless implementation is preserved on `feat/dagster-serverless` at commit `90d5625` and is intentionally absent from `main`. Resume that branch only with renewed deployment authorization. Until then, do not add Dagster+ secrets, push its deployment workflow, enable cloud schedules, or publish snapshots through it.

The private exception is local-only and already authorized: `scripts/private_daily.py`
runs the real SnapTrade → `prod-private` pipeline under user-level macOS LaunchAgents,
and the real dashboard binds only to `127.0.0.1`. Preserve this separation. Never add a
private snapshot/web export, point the private runner at `prod`, or expose its dashboard
on a LAN/public interface. See `docs/private_daily_operations.md`.
