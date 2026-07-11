"""Export the prod marts to a committed parquet snapshot.

The public Streamlit Community Cloud deploy can't hold GCP credentials, so the
deployed app reads this snapshot instead of querying BigQuery live (see the
source switch in data.py). This script is the bridge: it reads anchor_marts and
writes one parquet per mart into app/snapshot/.

Run locally (needs BigQuery creds) whenever the marts change:
    GOOGLE_APPLICATION_CREDENTIALS=~/.dbt/anchor-bigquery-key.json \
        python app/export_snapshot.py

In the ops capstone this is the terminal step of the scheduled job, downstream
of the marts: ingest -> dbt build --target prod -> export_snapshot -> git push.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pandas as pd
from google.cloud import bigquery

PROJECT = "anchor-495115"
MARTS_DATASET = "anchor_marts"
SNAPSHOT_DIR = Path(__file__).parent / "snapshot"

# The marts the dashboard reads (keep in sync with data.py's readers).
TABLES = [
    "macro_indicators",
    "macro_regime",
    "macro_trend",
    "sector_performance",
    "holdings_benchmarks",
    "portfolio_composition",
    "ticker_trend",
    "as_of_calendar",
]


def export_snapshot(
    client: bigquery.Client,
    destination_dir: Path = SNAPSHOT_DIR,
) -> dict[str, int]:
    """Read each prod mart and write it to app/snapshot/<table>.parquet, returning
    {table: row_count}. Takes an injected client so the standalone CLI and the
    Dagster snapshot asset share one implementation."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for table in TABLES:
        df = client.query(f"select * from `{PROJECT}.{MARTS_DATASET}.{table}`").to_dataframe()
        # BigQuery DATE columns arrive as the db-dtypes 'dbdate' extension type,
        # which embeds itself in the parquet metadata and then requires db-dtypes
        # to read back. Normalize to plain datetime64 so the deployed app needs
        # only pandas + pyarrow (no BigQuery stack, no creds).
        for col in df.columns:
            if str(df[col].dtype) in ("dbdate", "dbtime"):
                df[col] = pd.to_datetime(df[col])
        out = destination_dir / f"{table}.parquet"
        df.to_parquet(out, index=False)
        counts[table] = len(df)
    return counts


def promote_snapshot(source_dir: Path, destination_dir: Path = SNAPSHOT_DIR) -> None:
    """Replace the served parquet set only after all files validate."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    for table in TABLES:
        source = source_dir / f"{table}.parquet"
        destination = destination_dir / source.name
        temporary = destination.with_suffix(".parquet.next")
        shutil.copy2(source, temporary)
        temporary.replace(destination)


def export_snapshot_transactionally(client: bigquery.Client) -> dict[str, int]:
    """Standalone export helper that never leaves a partially refreshed set."""
    from app.snapshot_validation import validate_snapshot

    with tempfile.TemporaryDirectory(prefix="anchor-snapshot-") as temporary:
        staging_dir = Path(temporary)
        counts = export_snapshot(client, destination_dir=staging_dir)
        validate_snapshot(staging_dir)
        promote_snapshot(staging_dir)
    return counts


def main() -> None:
    client = bigquery.Client(project=PROJECT)
    counts = export_snapshot_transactionally(client)
    for table, n in counts.items():
        print(f"  {table:22s} {n:>5} rows -> app/snapshot/{table}.parquet")
    print(f"Snapshot written to {SNAPSHOT_DIR}")


if __name__ == "__main__":
    main()
