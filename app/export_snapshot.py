"""Export the prod marts to a committed parquet snapshot.

The public Streamlit Community Cloud deploy can't hold GCP credentials, so the
deployed app reads this snapshot instead of querying BigQuery live (see the
source switch in data.py). This script is the bridge: it reads anchor_marts and
writes one parquet per mart into app/snapshot/.

Run locally (needs BigQuery creds) whenever the marts change:
    GOOGLE_APPLICATION_CREDENTIALS=~/.dbt/anchor-bigquery-key.json \
        python app/export_snapshot.py

In the eventual ops capstone this becomes one step of the scheduled job:
    ingest -> dbt build --target prod -> export_snapshot -> git push -> redeploy.
"""

from __future__ import annotations

from pathlib import Path

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
    "ticker_trend",
]


def main() -> None:
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    client = bigquery.Client(project=PROJECT)
    for table in TABLES:
        df = client.query(f"select * from `{PROJECT}.{MARTS_DATASET}.{table}`").to_dataframe()
        # BigQuery DATE columns arrive as the db-dtypes 'dbdate' extension type,
        # which embeds itself in the parquet metadata and then requires db-dtypes
        # to read back. Normalize to plain datetime64 so the deployed app needs
        # only pandas + pyarrow (no BigQuery stack, no creds).
        for col in df.columns:
            if str(df[col].dtype) in ("dbdate", "dbtime"):
                df[col] = pd.to_datetime(df[col])
        out = SNAPSHOT_DIR / f"{table}.parquet"
        df.to_parquet(out, index=False)
        print(f"  {table:22s} {len(df):>5} rows -> {out.relative_to(SNAPSHOT_DIR.parent.parent)}")
    print(f"Snapshot written to {SNAPSHOT_DIR}")


if __name__ == "__main__":
    main()
