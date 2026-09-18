"""Anchor Dagster code location — the Definitions object `dagster dev` loads.

The full pipeline as one asset graph:
    holdings_demo/FRED/yfinance (bronze) -> staging -> intermediate -> marts (dbt) -> snapshot

plus a daily post-close schedule over the whole graph (off by default; toggle in
the UI). v1 runs locally via `make dagster`; Dagster+ Serverless is the follow-up
for the unattended scheduled story.
"""
from dagster import (
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)

import os

from dagster import AssetSelection

from anchor_orchestration.dbt import anchor_dbt_assets, source_freshness
from anchor_orchestration.ingestion import (
    ingest_fred_asset,
    ingest_holdings_demo_asset,
    ingest_yfinance_asset,
)
from anchor_orchestration.resources import bigquery_resource, dbt_resource
from anchor_orchestration.snapshot import publish_snapshot_asset, snapshot_parquet


def schedule_default_status() -> DefaultScheduleStatus:
    return (
        DefaultScheduleStatus.RUNNING
        if os.environ.get("DAGSTER_CLOUD_DEPLOYMENT_NAME") == "prod"
        else DefaultScheduleStatus.STOPPED
    )

# Explicit public/demo selection: future private assets cannot silently enter the schedule.
DEMO_REFRESH_SELECTION = AssetSelection.assets(
    ingest_fred_asset,
    ingest_holdings_demo_asset,
    ingest_yfinance_asset,
    source_freshness,
    anchor_dbt_assets,
    snapshot_parquet,
    publish_snapshot_asset,
)
anchor_refresh_job = define_asset_job("anchor_refresh", selection=DEMO_REFRESH_SELECTION)

# Weekdays 18:30 ET: after the 16:00 close + time for EOD bars / FRED to settle.
daily_refresh_schedule = ScheduleDefinition(
    name="daily_refresh",
    job=anchor_refresh_job,
    cron_schedule="30 18 * * 1-5",
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
        snapshot_parquet,
        publish_snapshot_asset,
    ],
    jobs=[anchor_refresh_job],
    schedules=[daily_refresh_schedule],
    resources={"bigquery": bigquery_resource, "dbt": dbt_resource},
)
