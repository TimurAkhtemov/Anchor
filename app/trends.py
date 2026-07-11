"""Pandas-only helpers for windowing dashboard trend data."""

from __future__ import annotations

import pandas as pd


def filter_trend_window(
    trend: pd.DataFrame,
    start_date,
    end_date,
    *,
    date_column: str = "trading_date",
) -> pd.DataFrame:
    """Return the points inside the inclusive date window, in input order.

    Render ordering belongs to the chart helpers (ui.py): they sort anyway
    because their first/last-point logic depends on it.
    """
    windowed = trend.copy()
    windowed[date_column] = pd.to_datetime(windowed[date_column])
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    mask = windowed[date_column].between(start, end, inclusive="both")
    return windowed.loc[mask]
