"""Export the prod marts + briefing as one JSON bundle for the web tour surface.

The immersive front-end (web/, see docs/immersive_briefing_design.md) is a static
Next.js app with no backend and no credentials — it renders whatever this export
committed. Same philosophy and privacy posture as the parquet snapshot: the
dataset is hardcoded to `anchor_marts`, so the web bundle is demo-only by
construction.

Run locally (needs BigQuery creds) after the briefing step:
    GOOGLE_APPLICATION_CREDENTIALS=~/.dbt/anchor-bigquery-key.json \
        python app/export_web.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from google.cloud import bigquery

PROJECT = "anchor-495115"
MARTS_DATASET = "anchor_marts"
BUNDLE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "anchor.json"

# Marts the tour page renders; the briefing row rides alongside them.
TABLES = [
    "as_of_calendar",
    "macro_regime",
    "macro_indicators",
    "sector_performance",
    "portfolio_composition",
    "holdings_benchmarks",
]


def _records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe records: dates to ISO strings, NaN to null."""
    df = df.copy()
    for col in df.columns:
        if str(df[col].dtype) in ("dbdate", "dbtime") or "datetime" in str(df[col].dtype):
            df[col] = df[col].astype(str)
    return [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def export_web(client: bigquery.Client, out_path: Path = BUNDLE_PATH) -> dict[str, int]:
    """Write the web bundle, returning {section: row_count}. Injected client so
    the CLI and a future Dagster asset share one implementation."""
    counts: dict[str, int] = {}
    bundle: dict[str, object] = {}
    for table in TABLES:
        df = client.query(
            f"select * from `{PROJECT}.{MARTS_DATASET}.{table}`"
        ).to_dataframe()
        records = _records(df)
        # Singletons flatten to one object for ergonomic front-end access.
        bundle[table] = records[0] if table in ("as_of_calendar", "macro_regime") else records
        counts[table] = len(records)

    briefing_df = client.query(
        f"select * from `{PROJECT}.{MARTS_DATASET}.copilot_briefing`"
    ).to_dataframe()
    row = _records(briefing_df)[0]
    bundle["briefing"] = {
        "briefing_md": row["briefing_md"],
        "steps": json.loads(row["briefing_json"])["steps"] if row.get("briefing_json") else [],
        "sources": json.loads(row["sources"]) if row.get("sources") else [],
        "as_of_date": row["as_of_date"],
        "generated_at": row["generated_at"],
        "provider": row["provider"],
        "model": row["model"],
    }
    counts["briefing_steps"] = len(bundle["briefing"]["steps"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=None, separators=(",", ":")))
    return counts


def main() -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT)
    counts = export_web(client)
    for section, n in counts.items():
        print(f"  {section:22s} {n:>5}")
    print(f"Web bundle written to {BUNDLE_PATH}")


if __name__ == "__main__":
    main()
