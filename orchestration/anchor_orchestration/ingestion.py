"""Bronze ingestion assets: FRED + yfinance -> BigQuery raw_* datasets.

Each source script writes two tables in one run, so each is modeled as a
@multi_asset with two outs — one node per raw table, 1:1 with the dbt sources
those tables feed. The asset keys (raw_fred_series, raw_fred_observations,
raw_yfinance_tickers, raw_yfinance_prices) are *exactly* the keys the dbt source
nodes resolve to, which is what stitches ingestion and dbt into one continuous
lineage graph (see the translator in dbt.py).

Invocation is in-process: the asset calls the importable ingest_*() function with
a client from the BigQueryResource and surfaces the returned row counts as
materialization metadata.
"""
from dagster import AssetOut, MaterializeResult, MetadataValue, multi_asset
from dagster_gcp import BigQueryResource

from ingestion.ingest_fred import ingest_fred
from ingestion.ingest_yfinance import ingest_yfinance


@multi_asset(
    name="ingest_fred",
    group_name="bronze",
    compute_kind="python",
    outs={
        "raw_fred_series": AssetOut(
            key="raw_fred_series",
            description="FRED series metadata (4 macro series) — raw_fred.raw_fred_series.",
        ),
        "raw_fred_observations": AssetOut(
            key="raw_fred_observations",
            description="FRED long-format observations — raw_fred.raw_fred_observations.",
        ),
    },
)
def ingest_fred_asset(context, bigquery: BigQueryResource):
    """Pull FRED series + observations into BigQuery (full refresh)."""
    with bigquery.get_client() as client:
        counts = ingest_fred(client)
    context.log.info(f"FRED ingestion wrote {counts}")
    yield MaterializeResult(
        asset_key="raw_fred_series",
        metadata={"rows": MetadataValue.int(counts["raw_fred_series"])},
    )
    yield MaterializeResult(
        asset_key="raw_fred_observations",
        metadata={"rows": MetadataValue.int(counts["raw_fred_observations"])},
    )


@multi_asset(
    name="ingest_yfinance",
    group_name="bronze",
    compute_kind="python",
    outs={
        "raw_yfinance_tickers": AssetOut(
            key="raw_yfinance_tickers",
            description="yfinance ticker metadata (sector + cap-style ETFs + holdings) — raw_yfinance.raw_yfinance_tickers.",
        ),
        "raw_yfinance_prices": AssetOut(
            key="raw_yfinance_prices",
            description="yfinance daily OHLCV bars (5y) — raw_yfinance.raw_yfinance_prices.",
        ),
    },
)
def ingest_yfinance_asset(context, bigquery: BigQueryResource):
    """Pull yfinance ticker metadata + 5y daily price bars into BigQuery (full refresh)."""
    with bigquery.get_client() as client:
        counts = ingest_yfinance(client)
    context.log.info(f"yfinance ingestion wrote {counts}")
    yield MaterializeResult(
        asset_key="raw_yfinance_tickers",
        metadata={"rows": MetadataValue.int(counts["raw_yfinance_tickers"])},
    )
    yield MaterializeResult(
        asset_key="raw_yfinance_prices",
        metadata={"rows": MetadataValue.int(counts["raw_yfinance_prices"])},
    )
