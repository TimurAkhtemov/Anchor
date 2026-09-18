"""Serve-layer assets: validate, stage, and publish the public snapshot.

Downstream of the marts the dashboard reads, snapshot_parquet exports and validates
the complete demo set. publish_snapshot then advances main with one non-forced Git
commit, but only in the Dagster+ prod deployment.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dagster import AssetKey, EnvVar, MaterializeResult, MetadataValue, asset
from dagster_gcp import BigQueryResource

from app.export_snapshot import SNAPSHOT_DIR, TABLES, export_snapshot, promote_snapshot
from app.snapshot_validation import validate_snapshot
from app.snapshot_publication import publish_snapshot

# copilot_briefing is a serve-layer table written outside dbt by the local-LLM
# workflow. Export it with the other snapshot files, but do not invent a dbt
# asset dependency for it. Its own as_of_date remains visible in the sidebar.
_DBT_MART_TABLES = [table for table in TABLES if table != "copilot_briefing"]
_MART_DEPS = [AssetKey(["anchor_marts", table]) for table in _DBT_MART_TABLES] + [
    AssetKey("source_freshness")
]


@asset(
    name="snapshot_parquet",
    deps=_MART_DEPS,
    group_name="serve",
    compute_kind="python",
    description="Committed parquet snapshot of the marts the public Streamlit deploy serves.",
)
def snapshot_parquet(context, bigquery: BigQueryResource) -> MaterializeResult:
    with tempfile.TemporaryDirectory(prefix="anchor-snapshot-") as temporary:
        staging_dir = Path(temporary)
        with bigquery.get_client() as client:
            export_snapshot(client, destination_dir=staging_dir)
        counts = validate_snapshot(staging_dir)
        promote_snapshot(staging_dir)

    publication = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": context.run_id,
        "as_of_date": str(pd.to_datetime(
            pd.read_parquet(SNAPSHOT_DIR / "as_of_calendar.parquet").iloc[0]["as_of_date"]
        ).date()),
    }
    (SNAPSHOT_DIR / "publication.json").write_text(json.dumps(publication, indent=2) + "\n")
    context.log.info(f"Snapshot wrote {counts}")
    return MaterializeResult(
        metadata={
            "tables": len(counts),
            "total_rows": MetadataValue.int(sum(counts.values())),
            **{f"rows.{table}": MetadataValue.int(n) for table, n in counts.items()},
            "as_of_date": publication["as_of_date"],
        }
    )


@asset(
    name="publish_snapshot",
    deps=[AssetKey("snapshot_parquet")],
    group_name="serve",
    compute_kind="github",
    description="Atomically commit the validated demo snapshot to main in production only.",
)
def publish_snapshot_asset(context) -> MaterializeResult:
    deployment = os.environ.get("DAGSTER_CLOUD_DEPLOYMENT_NAME", "")
    enabled = deployment == "prod" and os.environ.get("SNAPSHOT_PUBLISH_ENABLED", "true").lower() == "true"
    if not enabled:
        context.log.info("Snapshot publication disabled outside the Dagster+ prod deployment")
        return MaterializeResult(metadata={"status": "disabled"})

    token = EnvVar("SNAPSHOT_GITHUB_TOKEN").get_value()
    result = publish_snapshot(
        SNAPSHOT_DIR,
        token=token,
        repository=os.environ.get("SNAPSHOT_GITHUB_REPOSITORY", "TimurAkhtemov/Anchor"),
        branch=os.environ.get("SNAPSHOT_GITHUB_BRANCH", "main"),
    )
    return MaterializeResult(
        metadata={
            "status": result.status,
            "files": result.files,
            "commit_sha": result.commit_sha or "",
        }
    )
