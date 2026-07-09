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

AXIS_LABELS = {
    "sector": "Sector",
    "cap_style": "Cap-style",
    "market": "Market",
    "bond_market": "Bond market",
    "duration": "Duration",
}
# Reading order within the tier: growth assets, then rate-driven, then cash.
ASSET_CLASS_ORDER = ["equity", "fixed_income", "commodity", "alt", "cash"]


def render_holdings(hkey: str):
    comp = data.portfolio_composition()
    hb = data.holdings_benchmarks()
    rel_col, lab_col = f"relative_{hkey}_pp", f"label_{hkey}"
    hold_col, bench_col = f"holding_{hkey}_pct", f"benchmark_{hkey}_pct"

    st.subheader("Holdings")
    st.caption(
        "Your portfolio, sized by weight. Each holding is compared against the "
        "benchmarks appropriate to its asset class — read under the sectors and "
        "macro regime above."
    )

    _render_allocation(comp)
    _render_rollup(hb, lab_col)

    for asset_class in ASSET_CLASS_ORDER:
        grp = comp[comp["asset_class"] == asset_class]
        if grp.empty:
            continue
        st.markdown(
            ui.class_dot(asset_class)
            + f"<span style='font-weight:700'>{ui.ASSET_CLASS_LABELS[asset_class]}</span>"
            + f"<span style='color:{ui.SLATE};font-size:0.85rem'>"
            f" · {grp['weight_pct'].sum():.1f}% of portfolio</span>",
            unsafe_allow_html=True,
        )
        for _, h in grp.iterrows():
            if asset_class == "cash":
                _render_cash_row(h)
            else:
                _render_holding_card(h, hb, hold_col, bench_col, rel_col, lab_col)


def _render_allocation(comp: pd.DataFrame):
    alloc = comp.groupby("asset_class", as_index=False)["weight_pct"].sum()
    st.altair_chart(ui.allocation_bar(alloc), use_container_width=True)
    legend = "&nbsp;&nbsp;".join(
        ui.class_dot(row["asset_class"])
        + f"{ui.ASSET_CLASS_LABELS[row['asset_class']]} {row['weight_pct']:.1f}%"
        for _, row in alloc.sort_values("weight_pct", ascending=False).iterrows()
    )
    st.markdown(
        f"<div style='font-size:0.85rem;color:{ui.SLATE};margin:-6px 0 10px'>{legend}</div>",
        unsafe_allow_html=True,
    )


def _render_holding_card(h, hb, hold_col, bench_col, rel_col, lab_col):
    with st.container(border=True):
        top_l, top_r = st.columns([3.2, 2])
        with top_l:
            # equities: sector + cap chips (from the benchmark row, which carries
            # the classification); bond funds: duration chip; roots: root badge
            benches = hb[hb["holding_ticker"] == h["ticker"]]
            chips = []
            if not benches.empty and benches.iloc[0]["quote_type"] == "EQUITY":
                head = benches.iloc[0]
                chips = [ui.chip(head["sector"]), ui.chip(f"{head['cap_tier']}-cap")]
            elif h["asset_class"] == "fixed_income" and pd.notna(h["sub_style"]):
                chips = [ui.chip(f"{h['sub_style']} duration")]
            if h["is_root"]:
                chips.append(ui.chip("market root", fg=ui.TEAL, bg="#cffafe"))
            # honest badge for anything not marked to market from public prices
            if h.get("valuation_source") == "source":
                chips.append(ui.chip("source-valued"))
            st.markdown(
                f"**{h['ticker']}**  ·  {h['description']}  " + " ".join(chips),
                unsafe_allow_html=True,
            )
            gain = (
                ui.colored(ui.pct(h["unrealized_gain_pct"]), ui.ret_color(h["unrealized_gain_pct"]))
                if pd.notna(h["unrealized_gain_pct"])
                else "—"
            )
            st.markdown(
                f"<span style='color:{ui.SLATE};font-size:0.85rem'>"
                f"{h['weight_pct']:.1f}% of portfolio · {ui.money(h['market_value'])} · "
                f"since purchase: </span>{gain}",
                unsafe_allow_html=True,
            )
        with top_r:
            tr = trend_for(h["ticker"])
            if not tr.empty:
                st.altair_chart(ui.price_spark(tr), use_container_width=True)

        # Render axes in a stable order (AXIS_LABELS' order) — the mart's row
        # order isn't guaranteed, and rows reshuffling between refreshes reads
        # as a bug even when the data hasn't changed.
        benches = hb[hb["holding_ticker"] == h["ticker"]].copy()
        axis_order = {axis: i for i, axis in enumerate(AXIS_LABELS)}
        benches["_axis_order"] = benches["benchmark_type"].map(axis_order)
        benches = benches.sort_values("_axis_order")
        for _, b in benches.iterrows():
            axis = AXIS_LABELS.get(b["benchmark_type"], b["benchmark_type"])
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
        if h["is_root"] and benches.empty:
            st.markdown(
                f"<span style='color:{ui.SLATE};font-size:0.85rem'>This holding is the "
                f"market reference point — other holdings are compared against it.</span>",
                unsafe_allow_html=True,
            )
        elif benches.empty:
            st.markdown(
                f"<span style='color:{ui.SLATE};font-size:0.85rem'>Not benchmarked — "
                f"v1 displays this asset class without a comparison.</span>",
                unsafe_allow_html=True,
            )


def _render_cash_row(h):
    with st.container(border=True):
        c1, c2 = st.columns([4, 2])
        with c1:
            st.markdown(f"**{h['ticker']}**  ·  {h['description']}")
        with c2:
            st.markdown(
                f"{ui.money(h['market_value'])}"
                f"<span style='color:{ui.SLATE};font-size:0.85rem'> · "
                f"{h['weight_pct']:.1f}% of portfolio</span>",
                unsafe_allow_html=True,
            )


def _render_rollup(hb: pd.DataFrame, lab_col: str):
    """Ahead/behind tally per benchmark axis present in the portfolio."""
    axes = [a for a in AXIS_LABELS if a in set(hb["benchmark_type"])]
    cols = st.columns(max(len(axes), 1))
    for col, axis_key in zip(cols, axes):
        sub = hb[hb["benchmark_type"] == axis_key]
        counts = sub[lab_col].value_counts()
        with col:
            st.markdown(
                f"<span style='color:{ui.SLATE};font-size:0.85rem'>{AXIS_LABELS[axis_key]} axis: </span>"
                + ui.colored(f"{int(counts.get('ahead', 0))} ahead", ui.POS)
                + "<span style='color:#cbd5e1'> · </span>"
                + ui.colored(f"{int(counts.get('behind', 0))} behind", ui.NEG)
                + "<span style='color:#cbd5e1'> · </span>"
                + ui.colored(f"{int(counts.get('in_line', 0))} in line", ui.SLATE),
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
