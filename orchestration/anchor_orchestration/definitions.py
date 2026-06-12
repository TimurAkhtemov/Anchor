"""Anchor Dagster code location — the Definitions object `dagster dev` loads.

Chunks 1-2: bronze ingestion assets + dbt assets (one continuous lineage graph,
bronze -> staging -> intermediate -> marts). The snapshot asset + daily schedule
(chunk 3) are layered into this same Definitions next.
"""
from dagster import Definitions

from anchor_orchestration.dbt import anchor_dbt_assets
from anchor_orchestration.ingestion import ingest_fred_asset, ingest_yfinance_asset
from anchor_orchestration.resources import bigquery_resource, dbt_resource

defs = Definitions(
    assets=[ingest_fred_asset, ingest_yfinance_asset, anchor_dbt_assets],
    resources={"bigquery": bigquery_resource, "dbt": dbt_resource},
)
