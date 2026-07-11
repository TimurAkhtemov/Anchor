# Repository Guidelines

## Project Structure & Module Organization

Anchor follows a bronze -> silver -> gold -> serve flow. Python ingestion lives in `ingestion/`; demo holdings are in `data/`, while real inputs belong in gitignored `data/private/`. The dbt project under `transformation/` contains staging, intermediate, and mart models, plus macros, seeds, snapshots, and SQL tests. Dagster assets live in `orchestration/anchor_orchestration/`. The Streamlit app is in `app/`: data access stays behind `data.py`, shared visuals in `ui.py`, and committed demo parquet files in `snapshot/`. Python tests are under `tests/`; design material belongs in `docs/`.

## Build, Test, and Development Commands

- `make ingest-holdings-demo`: load `data/sample_portfolio.csv` into the demo source.
- `make ingest`: refresh FRED and yfinance bronze tables in BigQuery.
- `make build-prod`: install dbt packages, build models, and test public prod datasets.
- `make refresh`: run market ingestion, the public prod build, and snapshot export; load holdings separately when needed.
- `make ingest-holdings-real && make build-private`: load private inputs and build isolated `anchor_*_private` datasets.
- `python -m pytest tests/ -q`: run ingestion helper and snapshot-privacy tests.
- `make run-demo` / `make run-real`: launch Streamlit in demo or private mode.
- `make dagster`: launch the asset graph at `http://localhost:3000`.

Run dbt commands from `transformation/`; dbt Fusion can mishandle seeds with `--project-dir`. Example: `dbt build --select marts`. CI uses dbt Core 1.11 and Python 3.12.

## Coding Style & Naming Conventions

Use 4-space indentation, small Python modules, `snake_case` names, and comments only for non-obvious behavior. No formatter is enforced; match nearby code. UI code should consume framed marts, not join raw sources. Name dbt models by layer: `stg_yfinance__prices.sql`, `int_ticker_returns.sql`, and `holdings_benchmarks.sql`. Colocate model contracts and tests in YAML.

## Testing Guidelines

Name pytest functions `test_<behavior>`. Preserve dbt grain, relationship, and contract tests; add singular guardrails under `transformation/tests/` for business invariants. Validate warehouse changes with `dbt build` and dashboard changes in snapshot/demo plus affected live modes. Privacy changes must retain the committed-snapshot test.

## Commit & Pull Request Guidelines

Follow the scoped history style: `feat(dbt): ...`, `fix(ingestion): ...`, `test(app+ci): ...`, or `docs: ...`. Keep commits focused. PRs should identify affected layers, configuration needs, validation commands, and screenshots for UI changes. Call out demo/private isolation impacts.

## Security & Configuration Tips

Never commit `.env`, service-account keys, brokerage data, or `data/private/`. BigQuery uses `GOOGLE_APPLICATION_CREDENTIALS`; FRED uses `FRED_API_KEY`. Keep local dbt profiles outside the repository. Public builds and snapshots use demo holdings; real holdings require `prod-private`.

## Current Deployment Decision

Anchor remains local-first for orchestration. Use `make dagster` for local runs; do not deploy or enable Dagster+ Serverless while the app has no public-user need that justifies its recurring cost. The completed Serverless implementation is preserved on `feat/dagster-serverless` at commit `90d5625` and is intentionally absent from `main`. Resume that branch only with renewed deployment authorization. Until then, do not add Dagster+ secrets, push its deployment workflow, enable cloud schedules, or publish snapshots through it.
