from datetime import date, timedelta

import pandas as pd
import pytest

from app.export_snapshot import TABLES
from app.snapshot_validation import SnapshotValidationError, allowed_tickers, validate_snapshot


def _write_valid_snapshot(path, as_of_date=None):
    ticker = next(t for t in allowed_tickers() if t != "CASH")
    frames = {table: pd.DataFrame({"value": [1]}) for table in TABLES}
    frames["as_of_calendar"] = pd.DataFrame({"as_of_date": [as_of_date or date.today()]})
    frames["portfolio_composition"] = pd.DataFrame({
        "ticker": [ticker],
        "valuation_source": ["market"],
        "return_1m_pct": [1.0],
        "return_ytd_pct": [2.0],
        "return_1y_pct": [3.0],
    })
    for table, frame in frames.items():
        frame.to_parquet(path / f"{table}.parquet", index=False)


def test_validate_snapshot_accepts_complete_demo_set(tmp_path):
    _write_valid_snapshot(tmp_path)
    counts = validate_snapshot(tmp_path)
    assert set(counts) == set(TABLES)


def test_validate_snapshot_rejects_private_ticker(tmp_path):
    _write_valid_snapshot(tmp_path)
    composition = pd.read_parquet(tmp_path / "portfolio_composition.parquet")
    composition.loc[0, "ticker"] = "PRIVATE_TICKER"
    composition.to_parquet(tmp_path / "portfolio_composition.parquet", index=False)
    with pytest.raises(SnapshotValidationError, match="non-demo"):
        validate_snapshot(tmp_path)


def test_validate_snapshot_rejects_stale_settled_date(tmp_path):
    today = date(2026, 7, 10)
    _write_valid_snapshot(tmp_path, today - timedelta(days=5))
    with pytest.raises(SnapshotValidationError, match="days old"):
        validate_snapshot(tmp_path, today=today)
