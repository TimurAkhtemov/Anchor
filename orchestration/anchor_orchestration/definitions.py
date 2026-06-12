"""Anchor Dagster code location — the Definitions object `dagster dev` loads.

Chunk 1: bronze ingestion assets only. The dbt assets (chunk 2) and the snapshot
asset + daily schedule (chunk 3) are layered into this same Definitions next.
"""
from dagster import Definitions

from anchor_orchestration.ingestion import ingest_fred_asset, ingest_yfinance_asset
from anchor_orchestration.resources import bigquery_resource

defs = Definitions(
    assets=[ingest_fred_asset, ingest_yfinance_asset],
    resources={"bigquery": bigquery_resource},
)
