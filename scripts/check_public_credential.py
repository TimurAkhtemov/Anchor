#!/usr/bin/env python3
"""Prove the public refresh credential cannot read private data.

Run with ``GOOGLE_APPLICATION_CREDENTIALS`` pointing at the public service
account's key. Each probe is a zero-row query (``limit 0``), so no row data is
ever fetched. Private tables must answer ``permission denied``; public tables
must be readable. ``NotFound`` on a private table proves nothing (the grant
was never tested), so it is reported as a problem too. Exits non-zero on any
problem.
"""

from __future__ import annotations

import os
import sys

from google.api_core.exceptions import Forbidden, NotFound

PROJECT = "anchor-495115"

# Must be denied. Dataset-level privates use a known table inside the dataset.
PRIVATE = [
    f"{PROJECT}.raw_holdings.holdings_real",
    f"{PROJECT}.raw_holdings.fund_classifications_real",
    f"{PROJECT}.raw_yfinance_private.raw_yfinance_prices",
    f"{PROJECT}.anchor_marts_private.as_of_calendar",
]

# Must be readable.
PUBLIC = [
    f"{PROJECT}.raw_holdings.holdings_demo",
    f"{PROJECT}.raw_yfinance.raw_yfinance_prices",
    f"{PROJECT}.raw_fred.raw_fred_series",
    f"{PROJECT}.anchor_marts.as_of_calendar",
]


def _probe(client, table: str) -> None:
    client.query(f"select 1 from `{table}` limit 0").result()


def check(client) -> list[str]:
    """Return the problems found; an empty list means the credential is narrow enough."""
    problems: list[str] = []

    for table in PRIVATE:
        try:
            _probe(client, table)
        except Forbidden:
            continue
        except NotFound:
            problems.append(f"{table}: not found, so the denial is not proven")
        except Exception as exc:  # report, never crash
            problems.append(f"{table}: unexpected {type(exc).__name__}: {exc}")
        else:
            problems.append(f"{table}: readable, but must be permission denied")

    for table in PUBLIC:
        try:
            _probe(client, table)
        except Forbidden:
            problems.append(f"{table}: permission denied, but must be readable")
        except Exception as exc:
            problems.append(f"{table}: unexpected {type(exc).__name__}: {exc}")

    return problems


def main() -> int:
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print("GOOGLE_APPLICATION_CREDENTIALS is not set", file=sys.stderr)
        return 2

    from google.cloud import bigquery

    problems = check(bigquery.Client(project=PROJECT))
    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    if problems:
        return 1
    print("OK: public credential is denied on all private data and reads all public data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
