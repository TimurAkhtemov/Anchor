# Dagster+ Serverless operations

Anchor automates one settled weekday refresh at 18:30 America/New_York. It does not
poll intraday prices, schedule real holdings, or access SnapTrade.

## Deployment setup

The repository contains `dagster_cloud.yaml` and the Serverless PEX workflow at
`.github/workflows/dagster-plus-deploy.yml`. Before merging, configure these values;
doing so changes external services and must be explicitly authorized:

1. In GitHub Actions, set repository variable `DAGSTER_CLOUD_ORGANIZATION` and secret
   `DAGSTER_CLOUD_API_TOKEN`.
2. In the Dagster+ `prod` deployment, set:
   - `BQ_SA_KEY`: complete BigQuery service-account JSON, restricted to the existing
     raw ingestion and public `anchor_*` datasets.
   - `FRED_API_KEY`: FRED API key.
   - `SNAPSHOT_GITHUB_TOKEN`: fine-grained token restricted to this repository with
     Contents read/write.
   - Optional `SNAPSHOT_GITHUB_REPOSITORY` and `SNAPSHOT_GITHUB_BRANCH`; defaults are
     `TimurAkhtemov/Anchor` and `main`.
3. Leave `SNAPSHOT_PUBLISH_ENABLED` unset (production defaults true), or set it to
   `false` for the first controlled run. Branch deployments never publish regardless.
4. Configure a Dagster+ run-failure alert for `anchor_refresh` using an available
   free-tier destination. This UI setting is not encoded with a webhook secret here.

The deployment build uses an OAuth-shaped, connection-free profile only for `dbt
parse`. Runtime uses `orchestration/dbt_profiles/profiles.yml`, which exposes only the
public `prod` target and reads `BQ_SA_KEY`. There is no private target or real-holdings
variable in the code location.

## Verification and activation

Run locally before deployment:

```bash
python -m pytest tests/ -q
python -m compileall -q app ingestion orchestration
git diff --check
```

In a branch deployment, confirm Definitions load, the schedule is stopped, and a manual
`anchor_refresh` succeeds with publication reported as `disabled`. Inspect bronze row
counts, `source_freshness`, dbt checks, public-only dataset writes, snapshot row counts,
allowed tickers, and the settled `as_of_date`. No GitHub snapshot commit should appear.

For production activation, first run with `SNAPSHOT_PUBLISH_ENABLED=false`. After the
warehouse and snapshot checks pass, explicitly authorize enabling publication, remove
the override, and launch one controlled run. Verify one atomic `chore(snapshot)` commit,
the Streamlit redeploy, and the dashboard's settled-date caption. Then confirm the
weekday 18:30 ET schedule is running. Snapshot-only commits are ignored by the Dagster
deployment workflow, preventing a deployment loop.

## Routine operations and failures

- Upstream, dbt, validation, or publication failure leaves the previously published
  snapshot serving. Retry only after identifying the failed asset/check.
- A privacy or schema validation failure must not be bypassed. Inspect the public dbt
  target and demo holdings load before rerunning.
- GitHub branch-head conflicts are retried once and never force-pushed.
- If an incomplete yfinance bar survives the incremental staging merge, run a controlled
  `dbt build --select stg_yfinance__prices --full-refresh --target prod`, then rerun.
- The dashboard warns when its settled market date is more than four calendar days old,
  accommodating ordinary weekends and holidays without presenting an intraday signal.

## Rollback

1. Stop `daily_refresh` in Dagster+.
2. Disable publication with `SNAPSHOT_PUBLISH_ENABLED=false`.
3. Revert the last automated snapshot commit on `main`; do not force-push.
4. Revert the deployment code change and allow Serverless to redeploy.
5. Run a publication-disabled verification before re-enabling the schedule.

Rotate credentials in their GitHub or Dagster+ secret stores. Never commit keys, token
values, generated profiles, or private holdings.
