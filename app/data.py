"""Data-access seam for the Anchor dashboard.

The UI imports the get-functions below and never knows where the bytes come
from. Today every read is a live BigQuery query against the prod marts
(`anchor_marts`), cached so the app hits the warehouse once per TTL instead of
on every Streamlit rerun. The eventual public deploy swaps `SOURCE` to a
committed snapshot file — a change confined to this module, with zero UI edits.
This mirrors the gold layer's own contract: callers get relationship-framed
DataFrames, never raw joins.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

# --- source config ----------------------------------------------------------
PROJECT = "anchor-495115"
# demo (default) reads the public contract; ANCHOR_PORTFOLIO=real points the
# live-BigQuery path at the private mirror. The snapshot path is demo-only by
# construction (the exporter only knows anchor_marts).
PORTFOLIO = os.environ.get("ANCHOR_PORTFOLIO", "demo")
MARTS_DATASET = "anchor_marts_private" if PORTFOLIO == "real" else "anchor_marts"
SNAPSHOT_DIR = Path(__file__).parent / "snapshot"
_KEY_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    str(Path.home() / ".dbt" / "anchor-bigquery-key.json"),
)


def _resolve_source() -> str:
    """Pick the data backend.

    "bigquery" = live reads from the prod marts. "snapshot" = read the committed
    parquet files (app/snapshot/) — what the public deploy uses, since Streamlit
    Community Cloud has no GCP creds. Auto-detect: live when a SA key is present
    (local dev), snapshot otherwise (the cloud), with an explicit env override.
    """
    explicit = os.environ.get("ANCHOR_SOURCE")
    if explicit:
        return explicit
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or Path(_KEY_PATH).exists():
        return "bigquery"
    return "snapshot"


SOURCE = _resolve_source()

if PORTFOLIO == "real" and SOURCE == "snapshot":
    raise RuntimeError(
        "ANCHOR_PORTFOLIO=real requires live BigQuery access; the committed "
        "snapshot is demo-only by design."
    )

# Marts refresh post-close (daily), never intraday — an hour TTL is plenty and
# keeps repeated reruns off the warehouse.
CACHE_TTL = 60 * 60


@st.cache_resource
def _client():
    """One authenticated BigQuery client for the app's lifetime."""
    from google.cloud import bigquery
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(_KEY_PATH)
    return bigquery.Client(project=PROJECT, credentials=creds)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _read(table: str) -> pd.DataFrame:
    """Read one mart. The single choke point the source switch lives behind."""
    if SOURCE == "bigquery":
        sql = f"select * from `{PROJECT}.{MARTS_DATASET}.{table}`"
        return _client().query(sql).to_dataframe()
    if SOURCE == "snapshot":
        return pd.read_parquet(SNAPSHOT_DIR / f"{table}.parquet")
    raise ValueError(f"unknown ANCHOR_SOURCE {SOURCE!r} (expected 'bigquery' or 'snapshot')")


# --- tier readers (the UI's vocabulary) -------------------------------------
# Stable left-to-right display order for the macro cards: policy -> market rate
# -> inflation -> labor. The mart is unordered (4 rows); ordering is a serve
# concern, not a modeling one.
_MACRO_ORDER = ["fed_funds_rate", "ten_year_yield", "inflation_yoy", "unemployment_rate"]


def macro_indicators() -> pd.DataFrame:
    df = _read("macro_indicators").copy()
    df["_order"] = df["indicator_key"].map({k: i for i, k in enumerate(_MACRO_ORDER)})
    return df.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def macro_regime() -> pd.Series:
    """The singleton regime row, as a Series for easy field access."""
    return _read("macro_regime").iloc[0]


def as_of_calendar() -> pd.Series:
    """The singleton shared trading-calendar row, as a Series for easy field access."""
    return _read("as_of_calendar").iloc[0]


def macro_trend() -> pd.DataFrame:
    return _read("macro_trend")


def sector_performance() -> pd.DataFrame:
    return _read("sector_performance").sort_values("return_1m_pct", ascending=False)


def holdings_benchmarks() -> pd.DataFrame:
    return _read("holdings_benchmarks")


def ticker_trend() -> pd.DataFrame:
    return _read("ticker_trend")


def portfolio_composition() -> pd.DataFrame:
    return _read("portfolio_composition").sort_values("weight_pct", ascending=False)
