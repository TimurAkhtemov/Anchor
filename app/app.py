"""Anchor — a macro-aware personal investment dashboard.

The page is a single top-down read enforcing the product's core principle:
macro environment -> sector performance -> individual holdings. Each tier is
read in the context of the one above it, so the layout never lets you jump
straight to a stock without its macro + sector frame.
"""

import pandas as pd
import streamlit as st

import data
import ui

st.set_page_config(page_title="Anchor", page_icon="⚓", layout="wide")

# Friendly card labels and tooltips (mart keys are stable but not pretty).
MACRO_METADATA = {
    "fed_funds_rate": {
        "label": "Fed Funds Rate",
        "help": "The benchmark interest rate set by the Federal Reserve. When it rises, bank lending costs increase, driving up rates on mortgages, credit cards, and business loans to cool down spending."
    },
    "ten_year_yield": {
        "label": "10-Year Treasury",
        "help": "The interest rate paid on 10-year U.S. government debt. It serves as a benchmark for long-term lending rates and heavily influences how stock market valuations (especially tech) are discounted."
    },
    "inflation_yoy": {
        "label": "Inflation (YoY)",
        "help": "The year-over-year rate at which consumer prices are rising (based on the Consumer Price Index). High inflation shrinks consumer purchasing power."
    },
    "unemployment_rate": {
        "label": "Unemployment",
        "help": "The percentage of the labor force actively seeking work. Low unemployment signals a healthy consumer economy but can contribute to wage inflation."
    },
}

# Horizons exposed consistently across the sector + holdings marts.
HORIZONS = {"1 Month": "1m", "YTD": "ytd", "1 Year": "1y"}


def trend_for(ticker: str) -> pd.DataFrame:
    t = data.ticker_trend()
    return t[t["ticker"] == ticker]


# --- tier 1: macro -----------------------------------------------------------

def render_macro():
    regime = data.macro_regime()
    indicators = data.macro_indicators()
    trend = data.macro_trend()

    st.subheader("Macro environment")
    
    with st.expander("📚 Quick Guide: How to read the Macro environment"):
        st.markdown("""
        This section shows the **macro economic regime** of the U.S. economy. Understanding this is crucial because it sets the backdrop for stock market behavior:
        
        ### The Macro Indicators:
        - **Fed Funds Rate & 10-Year Treasury:** Benchmark interest rates. Rising rates increase borrowing costs for consumers and businesses, slowing down spending and stock market valuations.
        - **Inflation (YoY):** Shows how fast prices are rising. High inflation forces the Fed to raise interest rates to cool the economy.
        - **Unemployment Rate:** Reflects the strength of the jobs market. A very strong labor market supports consumer spending but can lead to inflation pressure.
        
        ### The Regime Chips & Their States:
        
        - **Rates:**
          - **`rising`**: Fed Funds Rate increased by **0.25 pp** or more over 3 months (at least one standard Fed rate hike).
          - **`easing`**: Fed Funds Rate decreased by **0.25 pp** or more over 3 months (at least one standard Fed rate cut).
          - **`steady`**: Changed by less than **0.25 pp** (rates are flat/unchanged).
        
        - **Inflation:**
          - **`rising`**: YoY Inflation increased by **0.30 pp** or more over 3 months (inflation heating up).
          - **`cooling`**: YoY Inflation decreased by **0.30 pp** or more over 3 months (inflation cooling down).
          - **`stable`**: Changed by less than **0.30 pp** (prices are steady).
          
        - **Labor:**
          - **`loosening`**: Unemployment Rate increased by **0.20 pp** or more over 3 months (more job seekers, hiring cooling).
          - **`tightening`**: Unemployment Rate decreased by **0.20 pp** or more over 3 months (fewer job seekers, job market heating).
          - **`stable`**: Changed by less than **0.20 pp** (labor market is steady).
        """)

    chips = (
        ui.regime_chip("Rates", regime["rates_state"])
        + ui.regime_chip("Inflation", regime["inflation_state"])
        + ui.regime_chip("Labor", regime["labor_state"])
    )
    st.markdown(
        f"<div style='margin:2px 0 4px'>{chips}</div>"
        f"<span style='color:{ui.SLATE};font-size:0.85rem'>as of {ui.fmt_date(regime['as_of_date'])}</span>",
        unsafe_allow_html=True,
    )

    cols = st.columns(len(indicators))
    for col, (_, row) in zip(cols, indicators.iterrows()):
        key = row["indicator_key"]
        meta = MACRO_METADATA.get(key, {"label": key, "help": ""})
        with col:
            with st.container(border=True):
                # delta_color off: a rising rate isn't "good/bad" — no green/red.
                st.metric(
                    label=meta["label"],
                    value=ui.pct(row["current_value"]),
                    delta=f"{row['delta_3mo']:+.2f} pp (3mo)",
                    delta_color="off",
                    help=meta["help"],
                )
                st.markdown(
                    f"<div style='color:{ui.SLATE}; font-size:0.78rem; font-weight: 500; margin-top: -10px; margin-bottom: 8px;'>"
                    f"3mo ago: {ui.pct(row['value_3mo_ago'])}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                series = trend[trend["indicator_key"] == row["indicator_key"]]
                if not series.empty:
                    st.altair_chart(
                        ui.macro_spark(series, row["direction"]),
                        use_container_width=True,
                    )


# --- tier 2: sectors ---------------------------------------------------------

def render_sectors(hkey: str, regime: pd.Series):
    sectors = data.sector_performance()
    ret_col = f"return_{hkey}_pct"

    st.subheader("Sectors")
    st.caption("Each sector ETF's return, its price trend, and how it co-moves with rates — read under the regime above.")

    for _, row in sectors.iterrows():
        c1, c2, c3, c4 = st.columns([2.4, 2, 1.3, 2.6])
        with c1:
            st.markdown(f"**{row['etf_ticker']}**  ·  {row['sector']}")
        with c2:
            tr = trend_for(row["etf_ticker"])
            if not tr.empty:
                st.altair_chart(ui.price_spark(tr), use_container_width=True)
        with c3:
            st.markdown(ui.colored(ui.pct(row[ret_col]), ui.ret_color(row[ret_col])), unsafe_allow_html=True)
        with c4:
            label = row["rate_comovement_label"]
            bits = [f"<span style='color:{ui.SLATE};font-size:0.85rem'>{label}</span>"]
            # Structural regime->sector link: tag sectors whose price tracks
            # rates, and (only when rates are actually moving) whether the
            # current regime is a tail- or headwind. Honest: silent when steady.
            if label != "rate-neutral":
                bits.append(ui.chip("rate-sensitive", fg=ui.TEAL, bg="#cffafe"))
                hint = _rate_hint(label, regime["rates_state"])
                if hint:
                    fg, bg = (ui.POS, "#dcfce7") if hint == "tailwind" else (ui.NEG, "#fee2e2")
                    bits.append(ui.chip(hint, fg=fg, bg=bg))
            st.markdown(" ".join(bits), unsafe_allow_html=True)


def _rate_hint(comove_label: str, rates_state: str) -> str:
    """Tail/headwind only when rates are moving; '' when steady (no signal)."""
    if rates_state == "steady":
        return ""
    moves_with = comove_label == "moves with rates"
    rising = rates_state == "rising"
    return "tailwind" if moves_with == rising else "headwind"


# --- tier 3: holdings --------------------------------------------------------

def render_holdings(hkey: str):
    hb = data.holdings_benchmarks()
    rel_col, lab_col = f"relative_{hkey}_pp", f"label_{hkey}"
    hold_col, bench_col = f"holding_{hkey}_pct", f"benchmark_{hkey}_pct"

    st.subheader("Holdings")
    st.caption("Each holding vs both of its benchmarks (its sector ETF and its cap-style ETF), read under the sectors above.")

    _render_rollup(hb, lab_col)

    for ticker, grp in hb.groupby("holding_ticker"):
        head = grp.iloc[0]
        with st.container(border=True):
            top_l, top_r = st.columns([3.2, 2])
            with top_l:
                st.markdown(
                    f"**{ticker}**  ·  {head['company_name']}  "
                    + ui.chip(head["sector"]) + " " + ui.chip(f"{head['cap_tier']}-cap"),
                    unsafe_allow_html=True,
                )
            with top_r:
                tr = trend_for(ticker)
                if not tr.empty:
                    st.altair_chart(ui.price_spark(tr), use_container_width=True)

            for _, b in grp.iterrows():
                axis = "Sector" if b["benchmark_type"] == "sector" else "Cap-style"
                c1, c2, c3 = st.columns([2.5, 3, 2])
                with c1:
                    st.markdown(f"{axis}: vs **{b['benchmark_etf']}**")
                with c2:
                    st.markdown(
                        f"{ui.pct(b[hold_col])} vs {ui.pct(b[bench_col])}  "
                        f"({ui.signed_pp(b[rel_col])})"
                    )
                with c3:
                    st.markdown(ui.pill(b[lab_col]), unsafe_allow_html=True)


def _render_rollup(hb: pd.DataFrame, lab_col: str):
    """Portfolio-level ahead/behind tally, per benchmark axis, at this horizon."""
    cols = st.columns(2)
    for col, (axis_key, axis_name) in zip(cols, [("sector", "Sector axis"), ("cap_style", "Cap-style axis")]):
        sub = hb[hb["benchmark_type"] == axis_key]
        counts = sub[lab_col].value_counts()
        parts = [
            f"{int(counts.get('ahead', 0))} ahead",
            f"{int(counts.get('behind', 0))} behind",
            f"{int(counts.get('in_line', 0))} in line",
        ]
        with col:
            st.markdown(
                f"<span style='color:{ui.SLATE};font-size:0.85rem'>{axis_name}: </span>"
                + ui.colored(parts[0], ui.POS) + "<span style='color:#cbd5e1'> · </span>"
                + ui.colored(parts[1], ui.NEG) + "<span style='color:#cbd5e1'> · </span>"
                + ui.colored(parts[2], ui.SLATE),
                unsafe_allow_html=True,
            )


# --- page --------------------------------------------------------------------

st.title("⚓ Anchor")
st.caption("Read top-down: macro environment → sectors → holdings.")

horizon = st.radio("Return horizon", list(HORIZONS), horizontal=True, index=0)
hkey = HORIZONS[horizon]

render_macro()
st.divider()
render_sectors(hkey, data.macro_regime())
st.divider()
render_holdings(hkey)
