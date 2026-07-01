# Repository Guidelines

## Project Structure & Module Organization

Anchor is a macro-aware investment dashboard with a bronze -> silver -> gold -> serve flow. Source ingestion lives in `ingestion/` (`ingest_fred.py`, `ingest_yfinance.py`). The dbt project is under `transformation/`, with `models/staging/`, `models/intermediate/`, `models/marts/`, `macros/`, `seeds/`, and singular tests in `tests/`. Dagster orchestration lives in `orchestration/anchor_orchestration/`. The Streamlit app is in `app/`, with `app/data.py` as the data-source seam, `app/ui.py` for shared visuals, and committed parquet snapshots in `app/snapshot/`. Design notes and roadmap material belong in `docs/`.

## Build, Test, and Development Commands

- `make help`: list available pipeline targets.
- `make ingest`: load FRED and yfinance bronze tables into BigQuery.
- `make deps`: install dbt packages from `transformation/packages.yml`.
- `make build-prod`: run `dbt build --target prod` into the `anchor_*` datasets.
- `make snapshot`: export prod marts into `app/snapshot/`.
- `make refresh`: run ingestion, dbt build, and snapshot export.
- `streamlit run app/app.py`: run the dashboard locally.
- `make dagster`: launch the local Dagster UI at `localhost:3000`.

Run ad hoc dbt commands from `transformation/`, for example `dbt build --select marts`.

## Coding Style & Naming Conventions

Use Python 3.12 style with 4-space indentation, clear function names, and small modules. Keep UI reads behind `app/data.py`; the app should consume framed marts, not join raw sources. dbt models use layer prefixes: `stg_source__entity.sql`, `int_subject.sql`, and mart names such as `holdings_benchmarks.sql`. YAML files colocated with models document sources, tests, and model contracts.

## Testing Guidelines

The main quality gate is `dbt build`, which runs models and tests together. Preserve grain and relationship tests in schema YAML, and add singular guardrail tests under `transformation/tests/` when a business invariant must fail the build. For app changes, run `streamlit run app/app.py` and verify the dashboard still reads through the configured data source.

## Commit & Pull Request Guidelines

Git history uses short, scoped messages such as `chore(dbt): ...`, `docs(handoff): ...`, `ci: ...`, and `refactor: ...`. Keep commits focused on one concern. PRs should describe the pipeline surface touched, note required credentials or environment variables, include screenshots for dashboard UI changes, and mention the relevant validation command, usually `dbt build`, `make build-prod`, or `make refresh`.

## Security & Configuration Tips

Do not commit secrets or service-account keys. Ingestion and dbt expect `GOOGLE_APPLICATION_CREDENTIALS`; FRED ingestion expects `FRED_API_KEY`. CI profiles live in `ci/`, while local dbt profile configuration should stay outside the repo.
