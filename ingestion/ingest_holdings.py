"""Load portfolio holdings into the raw_holdings BigQuery dataset.

One loader, multiple transports, one schema:
  --from-csv <path>      parse a Fidelity positions export (or the committed
                         demo sample, which is in the same format)
  --from-snaptrade       pull live positions via SnapTrade (added later)

--portfolio demo|real routes to holdings_demo / holdings_real. Loads APPEND
with an as_of batch date so position history accumulates from day one;
staging reads the latest as_of. --fund-classifications lands the private
fund-classification CSV (real funds only) as a truncate-and-replace table.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

try:
    from ingestion.holdings_csv import parse_fidelity_positions
except ModuleNotFoundError:  # direct script run: ingestion/ itself is on sys.path, the repo root is not
    from holdings_csv import parse_fidelity_positions

logger = logging.getLogger(__name__)

PROJECT_ID = "anchor-495115"
DATASET_ID = "raw_holdings"
KEYFILE_PATH = "/Users/timurakhtemov/.dbt/anchor-bigquery-key.json"
SAMPLE_CSV_PATH = str(Path(__file__).parent.parent / "data" / "sample_portfolio.csv")

_HOLDINGS_SCHEMA = [
    bigquery.SchemaField("account_number", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("account_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("ticker", "STRING", mode="NULLABLE"),  # null = cash-like row
    bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("quantity", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("price", "FLOAT", mode="NULLABLE"),          # audit only
    bigquery.SchemaField("market_value", "FLOAT", mode="NULLABLE"),   # audit only; gold recomputes
    bigquery.SchemaField("cost_basis_total", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("as_of", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),  # sample | csv | snaptrade
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
]

_CLASSIFICATIONS_SCHEMA = [
    bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("asset_class", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("sub_style", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
]


def build_bigquery_client():
    """Keyfile locally, ADC elsewhere — same pattern as the other ingesters."""
    if os.path.exists(KEYFILE_PATH):
        return bigquery.Client.from_service_account_json(KEYFILE_PATH, project=PROJECT_ID)
    return bigquery.Client(project=PROJECT_ID)


def _ensure_dataset(bq_client) -> None:
    dataset_ref = bq_client.dataset(DATASET_ID)
    try:
        bq_client.get_dataset(dataset_ref)
    except Exception:
        ds = bigquery.Dataset(dataset_ref)
        ds.location = "US"
        bq_client.create_dataset(ds, timeout=30)
        logger.info(f"Created dataset {PROJECT_ID}.{DATASET_ID}")


def ingest_holdings_csv(bq_client, csv_path: str, portfolio: str, as_of: date | None = None) -> int:
    """Parse a Fidelity-format CSV and APPEND it to holdings_<portfolio>."""
    if portfolio not in ("demo", "real"):
        raise ValueError(f"portfolio must be demo|real, got {portfolio!r}")
    rows = parse_fidelity_positions(Path(csv_path).read_text())
    if not rows:
        raise RuntimeError(f"no positions parsed from {csv_path}")

    df = pd.DataFrame(rows)
    df["as_of"] = as_of or date.today()
    df["source"] = "sample" if portfolio == "demo" else "csv"
    df["ingested_at"] = datetime.now(UTC)

    _ensure_dataset(bq_client)
    table = f"holdings_{portfolio}"
    job_config = bigquery.LoadJobConfig(
        schema=_HOLDINGS_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    bq_client.load_table_from_dataframe(
        df, bq_client.dataset(DATASET_ID).table(table), job_config=job_config
    ).result()
    logger.info(f"Appended {len(df)} rows to {PROJECT_ID}.{DATASET_ID}.{table}")
    return len(df)


def ingest_fund_classifications(bq_client, csv_path: str) -> int:
    """Land the PRIVATE fund-classification CSV (real funds) — truncate & replace."""
    df = pd.read_csv(csv_path)
    expected = {"ticker", "asset_class"}
    if not expected.issubset(df.columns):
        raise ValueError(f"{csv_path} must have columns ticker,asset_class[,sub_style]")
    if "sub_style" not in df.columns:
        df["sub_style"] = None
    df = df[["ticker", "asset_class", "sub_style"]].copy()
    df["ingested_at"] = datetime.now(UTC)

    _ensure_dataset(bq_client)
    job_config = bigquery.LoadJobConfig(
        schema=_CLASSIFICATIONS_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    bq_client.load_table_from_dataframe(
        df, bq_client.dataset(DATASET_ID).table("fund_classifications_real"), job_config=job_config
    ).result()
    logger.info(f"Loaded {len(df)} fund classifications (private)")
    return len(df)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-csv", metavar="PATH", help="Fidelity positions export to load")
    ap.add_argument("--portfolio", choices=["demo", "real"], required=True)
    ap.add_argument("--as-of", type=date.fromisoformat, default=None,
                    help="batch date (default: today)")
    ap.add_argument("--fund-classifications", metavar="PATH", default=None,
                    help="also load this private fund-classification CSV")
    args = ap.parse_args()

    client = build_bigquery_client()
    if args.from_csv:
        ingest_holdings_csv(client, args.from_csv, args.portfolio, args.as_of)
    else:
        ap.error("--from-csv is required (SnapTrade mode arrives in a later task)")
    if args.fund_classifications:
        ingest_fund_classifications(client, args.fund_classifications)


if __name__ == "__main__":
    main()
