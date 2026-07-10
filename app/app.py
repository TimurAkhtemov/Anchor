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
from trends import filter_trend_window

st.set_page_config(page_title="Anchor", page_icon="⚓", layout="wide")

# CSS Injection for Outfit/Inter fonts and Glassmorphism effects
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<style>
/* Custom typography overrides */
html, body, [class*="css"], .stApp {
    font-family: 'Inter', sans-serif;
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

/* Glassmorphism containers */
div[data-testid="stVerticalBlock"] > div[style*="border: 1px solid"] {
    background: rgba(255, 255, 255, 0.45) !important;
    backdrop-filter: blur(12px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(12px) saturate(180%) !important;
    border: 1px solid rgba(148, 163, 184, 0.18) !important;
    box-shadow: 0 4px 12px 0 rgba(0, 0, 0, 0.03) !important;
    border-radius: 16px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    padding: 18px !important;
}

/* Hover effect on containers */
div[data-testid="stVerticalBlock"] > div[style*="border: 1px solid"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 20px 0 rgba(0, 0, 0, 0.05) !important;
    border-color: rgba(99, 102, 241, 0.3) !important; /* Soft indigo accent */
}

/* Dark mode overrides */
@media (prefers-color-scheme: dark) {
    div[data-testid="stVerticalBlock"] > div[style*="border: 1px solid"] {
        background: rgba(15, 23, 42, 0.45) !important;
        border: 1px solid rgba(148, 163, 184, 0.12) !important;
        box-shadow: 0 4px 12px 0 rgba(0, 0, 0, 0.15) !important;
    }
    div[data-testid="stVerticalBlock"] > div[style*="border: 1px solid"]:hover {
        box-shadow: 0 10px 20px 0 rgba(0, 0, 0, 0.25) !important;
        border-color: rgba(129, 140, 248, 0.3) !important;
    }
}
</style>
""", unsafe_allow_html=True)


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


def trend_for(ticker: str, hkey: str) -> pd.DataFrame:
    """Sparkline series windowed to the SAME reference dates the returns were
    computed over (as_of_calendar) -- the sparkline can never contradict the
    return% beside it."""
    cal = data.as_of_calendar()
    t = data.ticker_trend()
    df = t[t["ticker"] == ticker]
    if df.empty:
        return df
    return filter_trend_window(
        df,
        cal[f"date_{hkey}"],
        cal["as_of_date"],
    )


def macro_trend_for(indicator_key: str) -> pd.DataFrame:
    """Each macro indicator's full trailing series, exactly as the mart
    provides it (macro_trend holds ~12 months by design). Macro is context,
    not performance, so it does NOT follow the return-horizon selector — two
    of the four series are monthly, and a "1-month" window would degenerate
    to 1-2 points."""
    t = data.macro_trend()
    df = t[t["indicator_key"] == indicator_key].copy()
    if df.empty:
        return df
    df["observation_date"] = pd.to_datetime(df["observation_date"])
    return df.sort_values("observation_date")



# --- tier 1: macro -----------------------------------------------------------

def render_macro():
    regime = data.macro_regime()
    indicators = data.macro_indicators()

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
                series = macro_trend_for(row["indicator_key"])
                if not series.empty:
                    st.altair_chart(
                        ui.macro_spark(series, row["direction"]),
                        width="stretch",
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
            tr = trend_for(row["etf_ticker"], hkey)
            if not tr.empty:
                st.altair_chart(ui.price_spark(tr), width="stretch")
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

    st.subheader("Holdings")
    st.caption(
        "Your portfolio, sized by weight. Each holding is compared against the "
        "benchmarks appropriate to its asset class — read under the sectors and "
        "macro regime above."
    )

    # Render Donut and Active Performance Rollup grid side-by-side
    col1, col2 = st.columns([5, 5])
    with col1:
        _render_allocation_donut(comp)
    with col2:
        _render_rollup_grid(hb, lab_col)

    st.markdown("---")
    
    # Multi-select Asset Class filter — derived from ui.ASSET_CLASS_LABELS so
    # the filter options and the rest of the tier share one source of truth.
    CLASS_OPTIONS = {label: key for key, label in ui.ASSET_CLASS_LABELS.items()}
    selected_labels = st.multiselect(
        "Filter holdings by asset class:",
        options=list(CLASS_OPTIONS.keys()),
        default=list(CLASS_OPTIONS.keys())
    )
    selected_keys = [CLASS_OPTIONS[label] for label in selected_labels]

    horizon_label = next(k for k, v in HORIZONS.items() if v == hkey)
    # Render the entire data-grid inside a single unified card container
    with st.container(border=True):
        _render_table_header(horizon_label)
        
        for asset_class in ASSET_CLASS_ORDER:
            if asset_class not in selected_keys:
                continue
    
            grp = comp[comp["asset_class"] == asset_class]
            if grp.empty:
                continue
                
            # Category Group Header Row
            header_text = (
                ui.class_dot(asset_class)
                + f"&nbsp;<span style='font-weight:700; font-size:0.95rem; text-transform:capitalize;'>{ui.ASSET_CLASS_LABELS[asset_class]}</span>"
                + f"&nbsp;&nbsp;<span style='color:{ui.SLATE};font-size:0.8rem'>"
                f"· {grp['weight_pct'].sum():.1f}% of portfolio</span>"
            )
            st.markdown(
                f"<div style='background:rgba(148, 163, 184, 0.08); padding:6px 12px; margin: 4px 0 12px; border-radius:8px; border:1px solid rgba(148, 163, 184, 0.12);'>"
                f"{header_text}</div>",
                unsafe_allow_html=True
            )
            
            for _, h in grp.iterrows():
                _render_holding_row(h, hb, rel_col, lab_col, hkey)


def _render_allocation_donut(comp: pd.DataFrame):
    alloc = comp.groupby("asset_class", as_index=False)["weight_pct"].sum()
    st.altair_chart(ui.allocation_donut(alloc), width="stretch")



def _render_table_header(horizon_label: str):
    """Renders the grid table column headers."""
    col1, col2, col3, col4, col5 = st.columns([2.5, 1.8, 1.2, 3.0, 1.5])
    with col1:
        st.markdown("<span style='font-size: 0.8rem; font-weight: 700; color: rgba(148, 163, 184, 0.7); text-transform: uppercase; letter-spacing: 0.05em;'>Holding / Ticker</span>", unsafe_allow_html=True)
    with col2:
        st.markdown("<span style='font-size: 0.8rem; font-weight: 700; color: rgba(148, 163, 184, 0.7); text-transform: uppercase; letter-spacing: 0.05em;'>Market Value</span>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<span style='font-size: 0.8rem; font-weight: 700; color: rgba(148, 163, 184, 0.7); text-transform: uppercase; letter-spacing: 0.05em;'>Return ({horizon_label})</span>", unsafe_allow_html=True)
    with col4:
        st.markdown("<span style='font-size: 0.8rem; font-weight: 700; color: rgba(148, 163, 184, 0.7); text-transform: uppercase; letter-spacing: 0.05em;'>Active Benchmark Diff</span>", unsafe_allow_html=True)
    with col5:
        st.markdown(f"<span style='font-size: 0.8rem; font-weight: 700; color: rgba(148, 163, 184, 0.7); text-transform: uppercase; letter-spacing: 0.05em;'>Trend ({horizon_label})</span>", unsafe_allow_html=True)
    st.markdown("<hr style='margin: 4px 0 10px; border: none; border-top: 2px solid rgba(148, 163, 184, 0.2);'>", unsafe_allow_html=True)


def _render_holding_row(h, hb, rel_col, lab_col, hkey):
    """Renders a holding (or cash) as a compact, responsive table row."""
    # Cash rides the general path on purpose: empty benches -> "Not benchmarked",
    # no price series -> empty trend, and it earns the source-valued chip.
    # Sort benchmarks stably at the beginning so both columns can use it
    benches = hb[hb["holding_ticker"] == h["ticker"]].copy()
    axis_order = {axis: i for i, axis in enumerate(AXIS_LABELS)}
    benches["_axis_order"] = benches["benchmark_type"].map(axis_order)
    benches = benches.sort_values("_axis_order")

    col1, col2, col3, col4, col5 = st.columns([2.5, 1.8, 1.2, 3.0, 1.5])
    with col1:
        chips = []
        if not benches.empty and benches.iloc[0]["quote_type"] == "EQUITY":
            head = benches.iloc[0]
            if pd.notna(head["sector"]):
                chips.append(ui.chip(head["sector"]))
            if pd.notna(head["cap_tier"]):
                chips.append(ui.chip(f"{head['cap_tier']}-cap"))
        elif h["asset_class"] == "fixed_income" and pd.notna(h["sub_style"]):
            chips = [ui.chip(f"{h['sub_style']} duration")]
        if h["is_root"]:
            chips.append(ui.chip("market root", fg=ui.TEAL, bg="rgba(207, 250, 254, 0.4)"))
        # honest badge for anything not marked to market from public prices
        if h.get("valuation_source") == "source":
            chips.append(ui.chip("source-valued"))
            
        chip_html = " " + " ".join(chips) if chips else ""
        st.markdown(
            f"**{h['ticker']}**{chip_html}<br>"
            f"<span style='color:{ui.SLATE};font-size:0.78rem'>{h['description']}</span>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"**{ui.money(h['market_value'])}**<br>"
            f"<span style='color:{ui.SLATE};font-size:0.78rem'>{h['weight_pct']:.1f}% weight</span>",
            unsafe_allow_html=True,
        )
    with col3:
        # .get: a live mart built before the return_* columns must degrade
        # to "—", not crash the tier
        holding_return = h.get(f"return_{hkey}_pct")
        rendered_return = (
            ui.colored(ui.pct(holding_return), ui.ret_color(holding_return))
            if pd.notna(holding_return)
            else "—"
        )
        st.markdown(f"<div style='margin-top: 8px;'>{rendered_return}</div>", unsafe_allow_html=True)
    with col4:
        bench_htmls = []
        for _, b in benches.iterrows():
            axis = AXIS_LABELS.get(b["benchmark_type"], b["benchmark_type"])
            rel_diff = b[rel_col]
            diff_str = ui.signed_pp(rel_diff)
            bench_htmls.append(
                f"<div style='font-size:0.8rem; margin-bottom: 2px;'>"
                f"<span style='color:{ui.SLATE}; font-weight: 500;'>{axis}:</span> vs {b['benchmark_etf']} "
                f"({ui.colored(diff_str, ui.ret_color(rel_diff))}) "
                f"{ui.pill(b[lab_col])}"
                f"</div>"
            )
        if h["is_root"] and benches.empty:
            bench_htmls.append(f"<span style='color:{ui.SLATE};font-size:0.78rem'>Market reference root</span>")
        elif benches.empty:
            bench_htmls.append(f"<span style='color:{ui.SLATE};font-size:0.78rem'>Not benchmarked</span>")
            
        st.markdown("<div style='margin-top: 2px;'>" + "".join(bench_htmls) + "</div>", unsafe_allow_html=True)
    with col5:
        tr = trend_for(h["ticker"], hkey)
        if not tr.empty:
            has_dual = False
            if not benches.empty and not h["is_root"]:
                bench_ticker = benches.iloc[0]["benchmark_etf"]
                bench_tr = trend_for(bench_ticker, hkey)
                if not bench_tr.empty:
                    st.altair_chart(ui.dual_price_spark(tr, bench_tr, height=45), width="stretch")
                    has_dual = True
            if not has_dual:
                st.altair_chart(ui.price_spark(tr, height=45), width="stretch")


    st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid rgba(148, 163, 184, 0.12);'>", unsafe_allow_html=True)



def _render_rollup_grid(hb: pd.DataFrame, lab_col: str):
    """Ahead/behind tally per benchmark axis present in the portfolio, rendered as a list grid."""
    axes = [a for a in AXIS_LABELS if a in set(hb["benchmark_type"])]
    
    html = "<div style='display:flex; flex-direction:column; gap:6px;'>"
    for axis_key in axes:
        sub = hb[hb["benchmark_type"] == axis_key]
        counts = sub[lab_col].value_counts()
        
        ahead_cnt = int(counts.get("ahead", 0))
        behind_cnt = int(counts.get("behind", 0))
        inline_cnt = int(counts.get("in_line", 0))
        
        # Build the HTML row on a single flat string to avoid Markdown block parsing
        html += (
            f'<div style="display:flex; justify-content:space-between; align-items:center; padding:6px 10px; background:rgba(148, 163, 184, 0.05); border-radius:10px; border:1px solid rgba(148, 163, 184, 0.12);">'
            f'<span style="font-weight:600; font-size:0.85rem;">{AXIS_LABELS[axis_key]} Axis</span>'
            f'<div style="display:flex; gap:4px;">'
            f'<span style="background:rgba(22, 163, 74, 0.12); color:{ui.POS}; padding:1px 6px; border-radius:10px; font-size:0.72rem; font-weight:600;">{ahead_cnt} ahead</span>'
            f'<span style="background:rgba(220, 38, 38, 0.12); color:{ui.NEG}; padding:1px 6px; border-radius:10px; font-size:0.72rem; font-weight:600;">{behind_cnt} behind</span>'
            f'<span style="background:rgba(100, 116, 139, 0.12); color:{ui.SLATE}; padding:1px 6px; border-radius:10px; font-size:0.72rem; font-weight:600;">{inline_cnt} in line</span>'
            f'</div></div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)




# --- page --------------------------------------------------------------------

st.title("⚓ Anchor")
st.caption("Read top-down: macro environment → sectors → holdings.")

horizon = st.radio("Return horizon", list(HORIZONS), horizontal=True, index=0)
hkey = HORIZONS[horizon]

# --- sidebar copilot ---------------------------------------------------------
# Deterministic v0 of the roadmap's AI portfolio analyst: every line below is
# computed from the marts at the CURRENT horizon selection, never hardcoded.
with st.sidebar:
    st.title("⚓ Anchor Copilot")
    st.caption("AI-powered portfolio analyst & market context guide.")
    st.markdown("---")

    regime = data.macro_regime()
    comp = data.portfolio_composition()
    hb = data.holdings_benchmarks()
    rel_col = f"relative_{hkey}_pp"

    briefing = [
        f"<p style='font-size:0.85rem; margin-bottom: 8px;'>"
        f"🧭 <strong>Regime</strong>: {regime['regime_summary']}.</p>"
    ]

    alloc = comp.groupby("asset_class", as_index=False)["weight_pct"].sum()
    alloc_map = dict(zip(alloc["asset_class"], alloc["weight_pct"]))
    alloc_bits = [
        f"{ui.ASSET_CLASS_LABELS[k]} {alloc_map[k]:.1f}%"
        for k in ASSET_CLASS_ORDER
        if k in alloc_map
    ]
    if alloc_bits:
        briefing.append(
            f"<p style='font-size:0.85rem; margin-bottom: 8px;'>"
            f"📊 <strong>Allocation</strong>: {' · '.join(alloc_bits)}.</p>"
        )

    valid_hb = hb.dropna(subset=[rel_col])
    if not valid_hb.empty:
        leader = valid_hb.loc[valid_hb[rel_col].idxmax()]
        laggard = valid_hb.loc[valid_hb[rel_col].idxmin()]
        briefing.append(
            f"<p style='font-size:0.85rem; margin-bottom: 8px;'>"
            f"🟢 <strong>Leader</strong>: {leader['holding_ticker']} vs {leader['benchmark_etf']}: "
            f"{ui.signed_pp(leader[rel_col])}.</p>"
        )
        if not laggard.equals(leader):
            briefing.append(
                f"<p style='font-size:0.85rem; margin-bottom: 8px;'>"
                f"🔴 <strong>Laggard</strong>: {laggard['holding_ticker']} vs {laggard['benchmark_etf']}: "
                f"{ui.signed_pp(laggard[rel_col])}.</p>"
            )

    commodities = comp[comp["asset_class"] == "commodity"]
    for _, row in commodities.iterrows():
        briefing.append(
            f"<p style='font-size:0.85rem; margin-bottom: 8px;'>"
            f"🔍 <strong>Commodities</strong>: {row['ticker']} sits at "
            f"{ui.pct(row['unrealized_gain_pct'])} since purchase.</p>"
        )

    briefing.append(
        f"<p style='font-size:0.72rem; color:{ui.SLATE}; margin-bottom:0; margin-top:12px;'>"
        f"Deterministic briefing (v0) — LLM analysis is on the roadmap.</p>"
    )

    st.markdown(
        "<div style='background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.2); "
        "padding: 16px; border-radius: 12px; margin-bottom: 20px;'>"
        "<h4 style='margin-top:0; color:#818cf8; font-size:1.05rem;'>💡 Daily Portfolio Briefing</h4>"
        + "".join(briefing) +
        "</div>",
        unsafe_allow_html=True,
    )

    # Interactive chat input box — not wired up yet.
    st.chat_input("Ask Copilot about your portfolio...", disabled=True)
    st.caption("Chat coming soon")


render_macro()
st.divider()
render_sectors(hkey, data.macro_regime())
st.divider()
render_holdings(hkey)
