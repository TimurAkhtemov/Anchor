-- The load-bearing holdings-tier mart. Each holding is paired with its
-- asset-class-appropriate benchmarks (routing in int_benchmark_routing) and
-- the holding% / benchmark% are computed together, so each pairing is a
-- single output row — the serve layer never joins two independent cuts.
--
-- Grain: one row per (holding_ticker, benchmark_type). Cash never appears
-- (no benchmark); root holdings (self-pairings, e.g. held SPY) are filtered
-- here and flagged in portfolio_composition instead.

with routing as (

    select * from {{ ref('int_benchmark_routing') }}
    where not is_self

),

holdings as (

    select * from {{ ref('int_holdings_classified') }}

),

returns as (

    select * from {{ ref('int_ticker_returns') }}

)

select
    r.holding_ticker,
    h.display_name as company_name,
    h.asset_class,
    h.quote_type,
    h.sector,
    h.market_cap,
    h.cap_tier,
    h.weight_pct,
    r.benchmark_type,
    r.benchmark_etf,
    r.benchmark_name,
    hr.as_of_date,
    hr.latest_close as holding_close,
    br.latest_close as benchmark_close,

    -- Daily
    hr.daily_return_pct as holding_daily_pct,
    br.daily_return_pct as benchmark_daily_pct,
    round(hr.daily_return_pct - br.daily_return_pct, 2) as relative_daily_pp,
    {{ ahead_behind('hr.daily_return_pct - br.daily_return_pct') }} as label_daily,

    -- 1 month (default horizon)
    hr.return_1m_pct as holding_1m_pct,
    br.return_1m_pct as benchmark_1m_pct,
    round(hr.return_1m_pct - br.return_1m_pct, 2) as relative_1m_pp,
    {{ ahead_behind('hr.return_1m_pct - br.return_1m_pct') }} as label_1m,

    -- YTD
    hr.return_ytd_pct as holding_ytd_pct,
    br.return_ytd_pct as benchmark_ytd_pct,
    round(hr.return_ytd_pct - br.return_ytd_pct, 2) as relative_ytd_pp,
    {{ ahead_behind('hr.return_ytd_pct - br.return_ytd_pct') }} as label_ytd,

    -- 1 year
    hr.return_1y_pct as holding_1y_pct,
    br.return_1y_pct as benchmark_1y_pct,
    round(hr.return_1y_pct - br.return_1y_pct, 2) as relative_1y_pp,
    {{ ahead_behind('hr.return_1y_pct - br.return_1y_pct') }} as label_1y

from routing r
join holdings h  on h.ticker  = r.holding_ticker
join returns  hr on hr.ticker = r.holding_ticker
join returns  br on br.ticker = r.benchmark_etf
