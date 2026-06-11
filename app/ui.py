"""Presentational helpers for the Anchor dashboard — the visual vocabulary
(colors, chips, badges, sparklines) shared across the three tiers so they read
as one product, not three. Pure formatting; no data access.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

# --- palette (mirrors .streamlit/config.toml) -------------------------------
TEAL = "#0e7490"
SLATE = "#64748b"
POS = "#16a34a"   # green — performance up
NEG = "#dc2626"   # red — performance down
# Direction hues for macro: orange = heating/up-pressure, blue = cooling/down,
# gray = neutral. Deliberately NOT green/red — macro is context, not good/bad.
UP = "#c2410c"
DOWN = "#0369a1"
FLAT = "#64748b"

DIR_COLOR = {"up": UP, "down": DOWN, "flat": FLAT}

# Regime-state coloring: orange = hot/tightening pressure, blue = cooling/easing
# pressure, gray = neutral. Economically coherent (hot vs cool), not a verdict.
_HOT = {"rising", "tightening"}
_COOL = {"easing", "cooling", "loosening"}

# ahead / behind / in_line pill styling (fg, bg).
_PILL = {
    "ahead": (POS, "#dcfce7"),
    "behind": (NEG, "#fee2e2"),
    "in_line": (SLATE, "#f1f5f9"),
}


# --- number formatting ------------------------------------------------------
def pct(x, digits=2):
    return "—" if pd.isna(x) else f"{x:.{digits}f}%"


def signed_pp(x, digits=2):
    return "—" if pd.isna(x) else f"{x:+.{digits}f} pp"


def fmt_date(x) -> str:
    """YYYY-MM-DD regardless of source dtype (BigQuery dbdate vs snapshot datetime64)."""
    return "—" if pd.isna(x) else str(pd.to_datetime(x).date())


def ret_color(x) -> str:
    if pd.isna(x):
        return SLATE
    return POS if x >= 0 else NEG


def colored(text, color, weight=600) -> str:
    return f"<span style='color:{color};font-weight:{weight}'>{text}</span>"


# --- inline HTML atoms ------------------------------------------------------
def chip(text, fg=SLATE, bg="#f1f5f9") -> str:
    """A neutral rounded tag for categorical attributes (sector, cap tier)."""
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 9px;"
        f"border-radius:8px;font-size:0.76rem;font-weight:500'>{text}</span>"
    )


def pill(label: str) -> str:
    """An ahead/behind/in_line status pill."""
    fg, bg = _PILL.get(label, (SLATE, "#f1f5f9"))
    text = label.replace("_", " ")
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 11px;"
        f"border-radius:999px;font-size:0.78rem;font-weight:600'>{text}</span>"
    )


def regime_chip(dimension: str, state: str) -> str:
    fg, bg = (UP, "#ffedd5") if state in _HOT else (DOWN, "#e0f2fe") if state in _COOL else (SLATE, "#f1f5f9")
    return (
        f"<span style='background:{bg};color:{fg};padding:4px 12px;border-radius:999px;"
        f"font-size:0.9rem;font-weight:600;margin-right:8px'>{dimension} · {state}</span>"
    )


# --- sparklines -------------------------------------------------------------
def _spark(df: pd.DataFrame, x: str, y: str, color: str, height: int = 46):
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:T", axis=None),
        y=alt.Y(f"{y}:Q", axis=None, scale=alt.Scale(zero=False)),
    )
    area = base.mark_area(color=color, opacity=0.12)
    line = base.mark_line(color=color, strokeWidth=1.6)
    return (area + line).properties(height=height).configure_view(strokeWidth=0)


def macro_spark(df: pd.DataFrame, direction: str):
    """Macro indicator trend, colored by direction (orange/blue/gray)."""
    return _spark(df, "observation_date", "value", DIR_COLOR.get(direction, FLAT))


def price_spark(df: pd.DataFrame):
    """Ticker price trend, colored green/red by net change over the window."""
    df = df.sort_values("trading_date")
    color = SLATE
    if len(df) >= 2:
        color = POS if df["close_price"].iloc[-1] >= df["close_price"].iloc[0] else NEG
    return _spark(df, "trading_date", "close_price", color)
