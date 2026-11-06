"""Anchor Dagster code location — the Definitions object `dagster dev` loads.

The full pipeline as one asset graph:
    holdings_demo/FRED/yfinance (bronze) -> staging -> intermediate -> marts (dbt) -> web_bundle

plus a daily post-close schedule over the whole graph (off by default; toggle in
the UI). Runs locally via `make dagster`; the public unattended refresh is the
GitHub Actions workflow, not this schedule.
"""
from dagster import (
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)

from dagster import AssetSelection

from anchor_orchestration.dbt import anchor_dbt_assets, source_freshness
from anchor_orchestration.ingestion import (
    ingest_fred_asset,
    ingest_holdings_demo_asset,
    ingest_yfinance_asset,
)
from anchor_orchestration.resources import bigquery_resource, dbt_resource
from anchor_orchestration.web_bundle import web_bundle


def schedule_default_status() -> DefaultScheduleStatus:
    # Dagster is a local learning graph; the unattended run is the GitHub Actions public refresh.
    return DefaultScheduleStatus.STOPPED

# Explicit public/demo selection: future private assets cannot silently enter the schedule.
DEMO_REFRESH_SELECTION = AssetSelection.assets(
    ingest_fred_asset,
    ingest_holdings_demo_asset,
    ingest_yfinance_asset,
    source_freshness,
    anchor_dbt_assets,
    web_bundle,
)
anchor_refresh_job = define_asset_job("anchor_refresh", selection=DEMO_REFRESH_SELECTION)

# Weekdays 21:30 ET: after the 16:00 close + time for EOD bars, mutual-fund NAVs
# and FRED to settle (matches SESSION_SETTLED_ET in ingestion/ingest_yfinance.py).
daily_refresh_schedule = ScheduleDefinition(
    name="daily_refresh",
    job=anchor_refresh_job,
    cron_schedule="30 21 * * 1-5",
    execution_timezone="America/New_York",
    default_status=schedule_default_status(),
)

defs = Definitions(
    assets=[
        ingest_fred_asset,
        ingest_holdings_demo_asset,
        ingest_yfinance_asset,
        anchor_dbt_assets,
        source_freshness,
        web_bundle,
    ],
    jobs=[anchor_refresh_job],
    schedules=[daily_refresh_schedule],
    resources={"bigquery": bigquery_resource, "dbt": dbt_resource},
)
