"""Read-only audit: do the PUBLIC BigQuery datasets hold any ticker outside the demo universe?

    python scripts/audit_public_tables.py            # counts per table, offenders to var/
    python scripts/audit_public_tables.py --show     # also print the offenders (local only)

Scans every table in the public datasets for the ticker columns the bundle
validator knows (`TICKER_COLUMNS`) and reports distinct values outside
`allowed_tickers()`. Offending symbols are written to
`var/audit_public_tables.txt` (gitignored) so the operator can inspect them
locally; stdout carries counts only, because an offender may be a real holding
and this output gets pasted into chats and tickets.

`raw_holdings` is audited at the single table `holdings_demo`; the private
tables in that dataset and every `*_private` dataset are out of scope.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.bundle_validation import TICKER_COLUMNS, allowed_tickers  # noqa: E402

PROJECT = os.environ.get("ANCHOR_BQ_PROJECT", "anchor-495115")
PUBLIC_DATASETS = (
    "raw_yfinance",
    "raw_fred",
    "anchor_staging",
    "anchor_intermediate",
    "anchor_marts",
    "anchor_seeds",
    "anchor_snapshots",
    "dbt_ci",  # CI sandbox; the public credential can read it
)
PUBLIC_TABLES = (("raw_holdings", "holdings_demo"),)
REPORT_PATH = REPO_ROOT / "var" / "audit_public_tables.txt"


def ticker_columns(client, dataset: str, table: str) -> list[str]:
    schema = client.get_table(f"{PROJECT}.{dataset}.{table}").schema
    return [f.name for f in schema if f.name in TICKER_COLUMNS and f.field_type == "STRING"]


def offenders(client, dataset: str, table: str, column: str, allowed: set[str]) -> set[str]:
    sql = (
        f"select distinct upper(`{column}`) as t from `{PROJECT}.{dataset}.{table}` "
        f"where `{column}` is not null"
    )
    return {r.t for r in client.query(sql).result()} - allowed


def audit(client, allowed: set[str]) -> list[tuple[str, str, set[str]]]:
    """[(table_id, column, offenders)] for every ticker column in scope, including clean ones."""
    targets: list[tuple[str, str]] = []
    for ds in PUBLIC_DATASETS:
        try:
            targets += [(ds, t.table_id) for t in client.list_tables(f"{PROJECT}.{ds}")]
        except Exception as exc:  # noqa: BLE001 - a missing dataset is a finding, not a crash
            print(f"  {ds}: not listed ({type(exc).__name__})")
    targets += list(PUBLIC_TABLES)
    out = []
    for ds, table in targets:
        for col in ticker_columns(client, ds, table):
            out.append((f"{ds}.{table}", col, offenders(client, ds, table, col, allowed)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="print offenders to stdout (LOCAL ONLY)")
    args = ap.parse_args()

    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT)
    allowed = allowed_tickers()
    print(f"demo universe: {len(allowed)} tickers")
    results = audit(client, allowed)

    REPORT_PATH.parent.mkdir(exist_ok=True)
    lines = []
    dirty = 0
    for table_id, col, bad in results:
        status = "clean" if not bad else f"{len(bad)} outside the demo universe"
        print(f"  {table_id}.{col}: {status}")
        if bad:
            dirty += 1
            lines.append(f"{table_id}.{col}: {', '.join(sorted(bad))}")
            if args.show:
                print(f"      {', '.join(sorted(bad))}")
    REPORT_PATH.write_text("\n".join(lines) + ("\n" if lines else ""))
    try:
        os.chmod(REPORT_PATH, 0o600)
    except OSError:
        pass
    print(
        f"{len(results)} ticker columns checked, {dirty} with offenders; "
        f"details in {REPORT_PATH.relative_to(REPO_ROOT)}"
    )
    return 1 if dirty else 0


if __name__ == "__main__":
    sys.exit(main())
