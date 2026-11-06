"""Privacy, completeness, and settled-data checks for public snapshots."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app.export_snapshot import TABLES
from app.bundle_validation import MAX_SETTLED_AGE_DAYS, TICKER_COLUMNS, allowed_tickers

__all__ = ["MAX_SETTLED_AGE_DAYS", "TICKER_COLUMNS", "allowed_tickers", "SnapshotValidationError", "validate_snapshot"]


class SnapshotValidationError(ValueError):
    pass


def validate_snapshot(snapshot_dir: Path, today: date | None = None) -> dict[str, int]:
    expected = {f"{table}.parquet" for table in TABLES}
    actual = {path.name for path in snapshot_dir.glob("*.parquet")}
    if actual != expected:
        raise SnapshotValidationError(
            f"snapshot file set mismatch: missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )

    allowed = allowed_tickers()
    counts: dict[str, int] = {}
    frames: dict[str, pd.DataFrame] = {}
    offenders: dict[str, set[str]] = {}
    for table in TABLES:
        frame = pd.read_parquet(snapshot_dir / f"{table}.parquet")
        frames[table] = frame
        counts[table] = len(frame)
        if table in {"macro_indicators", "macro_regime", "sector_performance", "portfolio_composition", "as_of_calendar"} and frame.empty:
            raise SnapshotValidationError(f"required snapshot table is empty: {table}")
        for column in TICKER_COLUMNS:
            if column in frame:
                bad = set(frame[column].dropna().astype(str).unique()) - allowed
                if bad:
                    offenders.setdefault(table, set()).update(bad)
    if offenders:
        raise SnapshotValidationError(f"non-demo tickers in public snapshot: {offenders}")

    calendar = frames["as_of_calendar"]
    if len(calendar) != 1 or "as_of_date" not in calendar:
        raise SnapshotValidationError("as_of_calendar must contain one as_of_date row")
    as_of_date = pd.to_datetime(calendar.iloc[0]["as_of_date"]).date()
    age_days = ((today or date.today()) - as_of_date).days
    if age_days < 0 or age_days > MAX_SETTLED_AGE_DAYS:
        raise SnapshotValidationError(
            f"settled market date {as_of_date} is {age_days} days old; "
            f"allowed range is 0-{MAX_SETTLED_AGE_DAYS}"
        )

    composition = frames["portfolio_composition"]
    required_returns = {"return_1m_pct", "return_ytd_pct", "return_1y_pct"}
    if not required_returns <= set(composition):
        raise SnapshotValidationError("portfolio composition is missing return horizons")
    market = composition[composition["valuation_source"] == "market"]
    if market.empty or market["return_1m_pct"].isna().any():
        raise SnapshotValidationError("market-valued holdings require populated 1m returns")
    return counts
