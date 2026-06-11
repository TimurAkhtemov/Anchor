"""Anchor — a macro-aware personal investment dashboard.

The page is a single top-down read enforcing the product's core principle:
macro environment -> sector performance -> individual holdings. Each tier is
read in the context of the one above it, so the layout never lets you jump
straight to a stock without its macro + sector frame.
"""

import altair as alt
import pandas as pd
import streamlit as st

import data

st.set_page_config(page_title="Anchor", page_icon="⚓", layout="wide")

# --- small display helpers ---------------------------------------------------

# Friendly card labels (mart keys are stable but not pretty).
MACRO_LABELS = {
    "fed_funds_rate": "Fed Funds Rate",
    "ten_year_yield": "10-Year Treasury",
    "inflation_yoy": "Inflation (YoY)",
    "unemployment_rate": "Unemployment",
}

# Horizons the data exposes consistently across the sector + holdings marts.
# (Daily exists too but is noisy and uses a different column shape — omitted.)
HORIZONS = {"1 Month": "1m", "YTD": "ytd", "1 Year": "1y"}

LABEL_COLOR = {"ahead": "green", "behind": "red", "in_line": "gray"}


def pct(x, digits=2):
    return "—" if pd.isna(x) else f"{x:.{digits}f}%"


def signed_pp(x, digits=2):
    return "—" if pd.isna(x) else f"{x:+.{digits}f} pp"


def sparkline(df: pd.DataFrame, x: str, y: str, color: str = "#4c78a8"):
    """A tiny axis-less trend line for inline use in a card."""
    return (
        alt.Chart(df)
        .mark_line(color=color, strokeWidth=2)
        .encode(
            x=alt.X(f"{x}:T", axis=None),
            y=alt.Y(f"{y}:Q", axis=None, scale=alt.Scale(zero=False)),
        )
        .properties(height=50)
        .configure_view(strokeWidth=0)
    )


# --- tier 1: macro -----------------------------------------------------------

def render_macro():
    regime = data.macro_regime()
    indicators = data.macro_indicators()
    trend = data.macro_trend()

    st.subheader("Macro environment")
    st.markdown(
        f"### {regime['regime_summary']}"
        f"\n<span style='color:gray'>as of {regime['as_of_date']}</span>",
        unsafe_allow_html=True,
    )

    cols = st.columns(len(indicators))
    for col, (_, row) in zip(cols, indicators.iterrows()):
        with col:
            label = MACRO_LABELS.get(row["indicator_key"], row["indicator_key"])
            # delta_color off: macro is context, not performance — a rising
            # rate isn't "good/bad", so no misleading green/red arrows.
            st.metric(
                label=label,
                value=pct(row["current_value"]),
                delta=f"{row['delta_3mo']:+.2f} pp (3mo)",
                delta_color="off",
            )
            series = trend[trend["indicator_key"] == row["indicator_key"]]
            if not series.empty:
                st.altair_chart(
                    sparkline(series, "observation_date", "value"),
                    use_container_width=True,
                )


# --- tier 2: sectors ---------------------------------------------------------

def render_sectors(hkey: str):
    sectors = data.sector_performance()
    ret_col = f"return_{hkey}_pct"

    st.subheader("Sectors")
    st.caption("Each sector ETF's return and how it has been moving with rates — read under the regime above.")

    for _, row in sectors.iterrows():
        c1, c2, c3 = st.columns([3, 1.5, 2.5])
        with c1:
            st.markdown(f"**{row['etf_ticker']}** · {row['sector']}")
        with c2:
            st.markdown(pct(row[ret_col]))
        with c3:
            st.markdown(f"<span style='color:gray'>{row['rate_comovement_label']}</span>", unsafe_allow_html=True)


# --- tier 3: holdings --------------------------------------------------------

def render_holdings(hkey: str):
    hb = data.holdings_benchmarks()
    rel_col, lab_col = f"relative_{hkey}_pp", f"label_{hkey}"
    hold_col, bench_col = f"holding_{hkey}_pct", f"benchmark_{hkey}_pct"

    st.subheader("Holdings")
    st.caption("Each holding vs both of its benchmarks (its sector ETF and its cap-style ETF), read under the sectors above.")

    for ticker, grp in hb.groupby("holding_ticker"):
        head = grp.iloc[0]
        with st.container(border=True):
            st.markdown(
                f"**{ticker}** · {head['company_name']}  "
                f"<span style='color:gray'>· {head['sector']} · {head['cap_tier']}-cap</span>",
                unsafe_allow_html=True,
            )
            for _, b in grp.iterrows():
                axis = "Sector" if b["benchmark_type"] == "sector" else "Cap-style"
                color = LABEL_COLOR.get(b[lab_col], "gray")
                label = b[lab_col].replace("_", " ")
                c1, c2, c3 = st.columns([2.5, 3, 2])
                with c1:
                    st.markdown(f"{axis}: vs **{b['benchmark_etf']}**")
                with c2:
                    st.markdown(f"{pct(b[hold_col])} vs {pct(b[bench_col])}  ({signed_pp(b[rel_col])})")
                with c3:
                    st.markdown(f":{color}[{label}]")


# --- page --------------------------------------------------------------------

st.title("⚓ Anchor")
st.caption("Read top-down: macro environment → sectors → holdings.")

horizon = st.radio("Return horizon", list(HORIZONS), horizontal=True, index=0)
hkey = HORIZONS[horizon]

render_macro()
st.divider()
render_sectors(hkey)
st.divider()
render_holdings(hkey)
