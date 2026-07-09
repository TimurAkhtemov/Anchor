"""Anchor Dagster code location — the Definitions object `dagster dev` loads.

The full pipeline as one asset graph:
    holdings_demo/FRED/yfinance (bronze) -> staging -> intermediate -> marts (dbt) -> snapshot

plus a daily post-close schedule over the whole graph (off by default; toggle in
the UI). v1 runs locally via `make dagster`; Dagster+ Serverless is the follow-up
for the unattended scheduled story.
"""
from dagster import (
    AssetSelection,
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)

from anchor_orchestration.dbt import anchor_dbt_assets
from anchor_orchestration.ingestion import (
    ingest_fred_asset,
    ingest_holdings_demo_asset,
    ingest_yfinance_asset,
)
from anchor_orchestration.resources import bigquery_resource, dbt_resource
from anchor_orchestration.snapshot import snapshot_parquet

# One job over every asset — ingest -> dbt build -> snapshot, in dependency order.
anchor_refresh_job = define_asset_job("anchor_refresh", selection=AssetSelection.all())

# Weekdays 18:30 ET: after the 16:00 close + time for EOD bars / FRED to settle.
daily_refresh_schedule = ScheduleDefinition(
    name="daily_refresh",
    job=anchor_refresh_job,
    cron_schedule="30 18 * * 1-5",
    execution_timezone="America/New_York",
    default_status=DefaultScheduleStatus.STOPPED,
)

defs = Definitions(
    assets=[
        ingest_fred_asset,
        ingest_holdings_demo_asset,
        ingest_yfinance_asset,
        anchor_dbt_assets,
        snapshot_parquet,
    ],
    jobs=[anchor_refresh_job],
    schedules=[daily_refresh_schedule],
    resources={"bigquery": bigquery_resource, "dbt": dbt_resource},
)
