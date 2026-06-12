"""Serve-layer asset: export the prod marts to the committed parquet snapshot.

The terminal node of the graph. Downstream of the six marts the dashboard reads,
it runs app/export_snapshot.py's logic to refresh app/snapshot/*.parquet — the
files the public Streamlit deploy serves. Pushing the refreshed parquet to git to
update the live demo stays a manual step: Dagster materializes the files, not the
commit.
"""
from dagster import AssetKey, MaterializeResult, MetadataValue, asset
from dagster_gcp import BigQueryResource

from app.export_snapshot import TABLES, export_snapshot

# The snapshot reads exactly these six marts; keys carry the anchor_marts schema
# prefix dagster-dbt assigns, so this asset hangs directly off the mart nodes.
_MART_DEPS = [AssetKey(["anchor_marts", t]) for t in TABLES]


@asset(
    name="snapshot_parquet",
    deps=_MART_DEPS,
    group_name="serve",
    compute_kind="python",
    description="Committed parquet snapshot of the marts the public Streamlit deploy serves.",
)
def snapshot_parquet(context, bigquery: BigQueryResource) -> MaterializeResult:
    with bigquery.get_client() as client:
        counts = export_snapshot(client)
    context.log.info(f"Snapshot wrote {counts}")
    return MaterializeResult(
        metadata={
            "tables": len(counts),
            "total_rows": MetadataValue.int(sum(counts.values())),
            **{f"rows.{table}": MetadataValue.int(n) for table, n in counts.items()},
        }
    )
