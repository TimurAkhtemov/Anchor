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

# ahead / behind / in_line pill styling (fg, bg) using semi-translucent colors
# so they render perfectly on both light and dark backgrounds.
_PILL = {
    "ahead": (POS, "rgba(22, 163, 74, 0.14)"),
    "behind": (NEG, "rgba(220, 38, 38, 0.14)"),
    "in_line": (SLATE, "rgba(100, 116, 139, 0.14)"),
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
def chip(text, fg="currentColor", bg="rgba(100, 116, 139, 0.12)") -> str:
    """A neutral rounded tag for categorical attributes (sector, cap tier)."""
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 9px;"
        f"border-radius:8px;font-size:0.76rem;font-weight:500;border: 1px solid rgba(148, 163, 184, 0.15);'>{text}</span>"
    )


def pill(label: str) -> str:
    """An ahead/behind/in_line status pill."""
    fg, bg = _PILL.get(label, (SLATE, "rgba(100, 116, 139, 0.12)"))
    text = label.replace("_", " ")
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 11px;"
        f"border-radius:999px;font-size:0.78rem;font-weight:600'>{text}</span>"
    )


def regime_chip(dimension: str, state: str) -> str:
    if state in _HOT:
        fg, bg = UP, "rgba(194, 65, 12, 0.15)"
    elif state in _COOL:
        fg, bg = DOWN, "rgba(3, 105, 161, 0.15)"
    else:
        fg, bg = "currentColor", "rgba(100, 116, 139, 0.12)"
    return (
        f"<span style='background:{bg};color:{fg};padding:4px 12px;border-radius:999px;"
        f"font-size:0.9rem;font-weight:600;margin-right:8px;border: 1px solid rgba(148, 163, 184, 0.15);'>{dimension} · {state}</span>"
    )



# --- sparklines -------------------------------------------------------------
def _spark(df: pd.DataFrame, x: str, y: str, color: str, height: int = 46):
    min_val = float(df[y].min())
    max_val = float(df[y].max())
    padding = (max_val - min_val) * 0.08 if max_val != min_val else 1.0
    domain = [min_val - padding, max_val + padding]

    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:T", axis=None),
        y=alt.Y(f"{y}:Q", axis=None, scale=alt.Scale(zero=False, domain=domain)),
    )
    line = base.mark_line(color=color, strokeWidth=1.8, interpolate="monotone")
    return line.properties(height=height).configure_view(strokeWidth=0)


def macro_spark(df: pd.DataFrame, direction: str):
    """Macro indicator trend, colored by direction (orange/blue/gray)."""
    df = df.sort_values("observation_date")
    return _spark(df, "observation_date", "value", DIR_COLOR.get(direction, FLAT))


def price_spark(df: pd.DataFrame, height: int = 46):
    """Ticker price trend, colored green/red by net change over the window."""
    df = df.sort_values("trading_date")
    color = SLATE
    if len(df) >= 2:
        color = POS if df["close_price"].iloc[-1] >= df["close_price"].iloc[0] else NEG
    return _spark(df, "trading_date", "close_price", color, height=height)



def dual_price_spark(holding_df: pd.DataFrame, benchmark_df: pd.DataFrame, height: int = 60):
    """Normalized dual-trend sparkline: holding solid vs. benchmark dashed.
    
    Both series are normalized to start at 0% on their first day of the window.
    The holding line is colored green if its final return beat the benchmark, 
    otherwise red.
    """
    h_df = holding_df.sort_values("trading_date").copy()
    b_df = benchmark_df.sort_values("trading_date").copy()
    
    if len(h_df) < 2 or len(b_df) < 2:
        return price_spark(holding_df, height=height)
        
    h_first = h_df["close_price"].iloc[0]
    h_df["normalized_return"] = (h_df["close_price"] / h_first - 1) * 100
    
    b_first = b_df["close_price"].iloc[0]
    b_df["normalized_return"] = (b_df["close_price"] / b_first - 1) * 100
    
    # Color coding based on whether the holding beat the benchmark
    h_final = h_df["normalized_return"].iloc[-1]
    b_final = b_df["normalized_return"].iloc[-1]
    color = POS if h_final >= b_final else NEG
    
    # Calculate shared y-domain
    min_val = min(h_df["normalized_return"].min(), b_df["normalized_return"].min())
    max_val = max(h_df["normalized_return"].max(), b_df["normalized_return"].max())
    padding = (max_val - min_val) * 0.08 if max_val != min_val else 1.0
    domain = [min_val - padding, max_val + padding]
    
    # Layer 1: Holding Area
    h_base = alt.Chart(h_df).encode(
        x=alt.X("trading_date:T", axis=None),
        y=alt.Y("normalized_return:Q", axis=None, scale=alt.Scale(zero=False, domain=domain)),
    )
    h_area = h_base.mark_area(color=color, opacity=0.08)
    h_line = h_base.mark_line(color=color, strokeWidth=2.2, interpolate="monotone")
    
    # Layer 2: Benchmark Line (dashed, slate)
    b_base = alt.Chart(b_df).encode(
        x=alt.X("trading_date:T", axis=None),
        y=alt.Y("normalized_return:Q", axis=None, scale=alt.Scale(zero=False, domain=domain)),
    )
    b_line = b_base.mark_line(color="#64748b", strokeWidth=1.5, strokeDash=[5, 3], interpolate="monotone")
    
    return (h_area + h_line + b_line).properties(height=height).configure_view(strokeWidth=0)



def allocation_donut(alloc: pd.DataFrame, height: int = 150):
    """A clean, premium donut chart of portfolio allocation by asset class.
    
    `alloc` columns: asset_class, weight_pct.
    """
    order = [c for c in ASSET_CLASS_COLORS if c in set(alloc["asset_class"])]
    df = alloc.copy()
    df["label"] = df["asset_class"].map(ASSET_CLASS_LABELS)
    df["_order"] = df["asset_class"].map({c: i for i, c in enumerate(order)})
    colors = [ASSET_CLASS_COLORS[c] for c in order]
    
    chart = alt.Chart(df).mark_arc(innerRadius=42, stroke="#ffffff", strokeWidth=2).encode(
        theta=alt.Theta("weight_pct:Q"),
        color=alt.Color(
            "label:N",
            scale=alt.Scale(domain=[ASSET_CLASS_LABELS[c] for c in order], range=colors),
            legend=alt.Legend(
                orient="right",
                title=None,
                labelFontSize=11,
                symbolType="circle"
            )
        ),
        order=alt.Order("_order:Q"),
        tooltip=[
            alt.Tooltip("label:N", title="Asset Class"),
            alt.Tooltip("weight_pct:Q", title="Weight (%)", format=".1f")
        ]
    ).properties(height=height)
    
    return chart.configure_view(strokeWidth=0)



def class_dot(asset_class: str) -> str:
    """A small colored identity dot for the allocation legend line."""
    color = ASSET_CLASS_COLORS.get(asset_class, SLATE)
    return (
        f"<span style='display:inline-block;width:9px;height:9px;border-radius:50%;"
        f"background:{color};margin-right:5px'></span>"
    )
