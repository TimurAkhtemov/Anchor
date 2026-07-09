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

# Asset-class identity (allocation bar + class dots). Fixed assignment, never
# cycled; deliberately distinct from the reserved semantic colors (green/red =
# performance verdicts, orange/blue = macro direction). Palette validated for
# lightness / chroma / CVD separation / contrast (dataviz six-checks; 4 slots,
# validated 2026-07-09). "alt" is slate on purpose — an identity-less
# catch-all; its label carries the identity.
ASSET_CLASS_COLORS = {"equity": "#0d9488", "fixed_income": "#7c3aed", "commodity": "#db2777", "cash": "#b45309", "alt": "#64748b"}
ASSET_CLASS_LABELS = {"equity": "Equities", "fixed_income": "Fixed income", "commodity": "Commodities", "cash": "Cash", "alt": "Other"}

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


def money(x, digits=2) -> str:
    return "—" if pd.isna(x) else f"${x:,.{digits}f}"


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


def allocation_bar(alloc: pd.DataFrame):
    """One horizontal 100% stacked bar of portfolio weight by asset class.

    `alloc` columns: asset_class, weight_pct. Order and colors are fixed by
    ASSET_CLASS_COLORS (identity follows the class, never its rank).
    """
    order = [c for c in ASSET_CLASS_COLORS if c in set(alloc["asset_class"])]
    df = alloc.copy()
    df["label"] = df["asset_class"].map(ASSET_CLASS_LABELS)
    df["_order"] = df["asset_class"].map({c: i for i, c in enumerate(order)})
    return (
        alt.Chart(df)
        .mark_bar(height=20, stroke="#ffffff", strokeWidth=2)
        .encode(
            x=alt.X("weight_pct:Q", stack="normalize", axis=None),
            color=alt.Color(
                "asset_class:N",
                scale=alt.Scale(domain=order, range=[ASSET_CLASS_COLORS[c] for c in order]),
                legend=None,
            ),
            order=alt.Order("_order:Q"),
            tooltip=[
                alt.Tooltip("label:N", title="Asset class"),
                alt.Tooltip("weight_pct:Q", title="Weight (%)", format=".1f"),
            ],
        )
        .properties(height=20)
        .configure_view(strokeWidth=0)
    )


def class_dot(asset_class: str) -> str:
    """A small colored identity dot for the allocation legend line."""
    color = ASSET_CLASS_COLORS.get(asset_class, SLATE)
    return (
        f"<span style='display:inline-block;width:9px;height:9px;border-radius:50%;"
        f"background:{color};margin-right:5px'></span>"
    )
