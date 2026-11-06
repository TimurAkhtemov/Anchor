"""Export the prod marts + briefing as one JSON bundle for the web tour surface.

The immersive front-end (web/, see docs/immersive_briefing_design.md) is a static
Next.js app with no backend and no credentials — it renders whatever this export
committed. Privacy posture: the dataset is hardcoded to `anchor_marts`, so the web bundle is demo-only by
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
REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DATASET = "anchor_marts"
PRIVATE_DATASET = "anchor_marts_private"
MARTS_DATASET = PUBLIC_DATASET  # kept for existing importers
BUNDLE_PATH = REPO_ROOT / "web" / "public" / "data" / "anchor.json"
PRIVATE_OUT_DIR = REPO_ROOT / "var"

# Marts the web surface renders; the briefing row and trends ride alongside.
TABLES = [
    "as_of_calendar",
    "macro_regime",
    "macro_indicators",
    "sector_performance",
    "portfolio_composition",
    "holdings_benchmarks",
]


class BundlePrivacyError(RuntimeError):
    pass


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


def _check_output_path(out_path: Path, portfolio: str) -> str:
    """Return the marts dataset for `portfolio`, refusing unsafe combinations
    before any query runs. A real-portfolio bundle may only land under var/."""
    if portfolio == "demo":
        return PUBLIC_DATASET
    if portfolio != "real":
        raise BundlePrivacyError(f"unknown portfolio {portfolio!r}")
    resolved = out_path.resolve()
    if not resolved.is_relative_to(PRIVATE_OUT_DIR.resolve()):
        raise BundlePrivacyError(
            f"real-portfolio bundle must be written under {PRIVATE_OUT_DIR}, not {out_path}"
        )
    return PRIVATE_DATASET


def _series(df: pd.DataFrame, key: str, date_col: str, value_col: str) -> dict:
    df = df.sort_values([key, date_col])
    out: dict[str, list] = {}
    for k, d, v in zip(df[key], df[date_col].astype(str), df[value_col]):
        out.setdefault(str(k), []).append([d, round(float(v), 3)])
    return out


def _briefing(client, dataset: str, as_of_date: str) -> dict | None:
    from google.api_core.exceptions import NotFound

    try:
        df = client.query(f"select * from `{PROJECT}.{dataset}.copilot_briefing`").to_dataframe()
    except NotFound:
        return None
    if df.empty:
        return None
    row = _records(df)[0]
    if str(row["as_of_date"]) != str(as_of_date):
        return None
    return {
        "briefing_md": row["briefing_md"],
        "steps": json.loads(row["briefing_json"])["steps"] if row.get("briefing_json") else [],
        "sources": json.loads(row["sources"]) if row.get("sources") else [],
        "as_of_date": row["as_of_date"],
        "generated_at": row["generated_at"],
        "provider": row["provider"],
        "model": row["model"],
    }


def export_web(
    client: bigquery.Client, out_path: Path = BUNDLE_PATH, portfolio: str = "demo"
) -> dict[str, int]:
    """Write the web bundle, returning {section: row_count}. Injected client so
    the CLI and a future Dagster asset share one implementation."""
    dataset = _check_output_path(out_path, portfolio)
    counts: dict[str, int] = {}
    bundle: dict[str, object] = {"portfolio": portfolio}
    for table in TABLES:
        df = client.query(f"select * from `{PROJECT}.{dataset}.{table}`").to_dataframe()
        records = _records(df)
        # Singletons flatten to one object for ergonomic front-end access.
        bundle[table] = records[0] if table in ("as_of_calendar", "macro_regime") else records
        counts[table] = len(records)

    macro = client.query(f"select * from `{PROJECT}.{dataset}.macro_trend`").to_dataframe()
    bundle["macro_trend"] = _series(macro, "indicator_key", "observation_date", "value")
    ticker = client.query(f"select * from `{PROJECT}.{dataset}.ticker_trend`").to_dataframe()
    bundle["ticker_trend"] = _series(ticker, "ticker", "trading_date", "close_price")
    counts["macro_trend"] = len(macro)
    counts["ticker_trend"] = len(ticker)

    bundle["briefing"] = _briefing(client, dataset, bundle["as_of_calendar"]["as_of_date"])
    counts["briefing_steps"] = len(bundle["briefing"]["steps"]) if bundle["briefing"] else 0

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
