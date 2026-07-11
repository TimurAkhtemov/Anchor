from __future__ import annotations

import pandas as pd

from app.trends import filter_trend_window


def test_filter_trend_window_is_inclusive_and_preserves_input_order():
    trend = pd.DataFrame(
        {
            "trading_date": [
                "2026-02-03",
                "2026-01-31",
                "2026-02-02",
                "2026-02-01",
                "2026-02-04",
            ],
            "close_price": [103.0, 99.0, 102.0, 101.0, 104.0],
        }
    )

    actual = filter_trend_window(trend, "2026-02-01", "2026-02-03")

    assert actual["trading_date"].tolist() == [
        pd.Timestamp("2026-02-03"),
        pd.Timestamp("2026-02-02"),
        pd.Timestamp("2026-02-01"),
    ]
    assert actual["close_price"].tolist() == [103.0, 102.0, 101.0]
