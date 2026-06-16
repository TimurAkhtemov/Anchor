-- The load-bearing holdings-tier mart. Each holding is paired with BOTH
-- of its benchmarks (sector axis + cap-style axis) and the holding% and
-- benchmark% are computed together, so each pairing is a single output
-- row -- the serve layer never joins two independent cuts.
--
-- Grain: one row per (holding_ticker, benchmark_type).
-- Adding a third benchmark axis later is a seed row + a union branch, not
-- a rewrite (generic benchmark shape).

with holdings as (

    -- Holdings = the ingested universe minus the benchmark ETF set.
    -- (Future state: this becomes a dedicated `holdings` bronze table with
    -- quantity / cost basis; the anti-join is the current proxy.)
    -- sector / market_cap classification stays live from yfinance.
    select
        ticker as holding_ticker,
        company_name,
        sector,
        market_cap,
        case
            when market_cap >= 10e9 then 'Large'
            when market_cap >=  2e9 then 'Mid'
            else 'Small'
        end as cap_tier
    from {{ ref('stg_yfinance__tickers') }}
    where ticker not in (select etf_ticker from {{ ref('benchmark_etfs') }})

),

benchmarks as (

    select
        benchmark_type,
        lookup_key,
        etf_ticker,
        etf_name
    from {{ ref('benchmark_etfs') }}

),

-- One (holding, benchmark) pairing per axis. Sector axis joins on the
-- holding's live sector; cap-style axis joins on its derived cap tier.
holding_benchmarks as (

    select
        h.holding_ticker,
        h.company_name,
        h.sector,
        h.market_cap,
        h.cap_tier,
        b.benchmark_type,
        b.etf_ticker as benchmark_etf,
        b.etf_name   as benchmark_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'sector'
       and b.lookup_key = h.sector

    union all

    select
        h.holding_ticker,
        h.company_name,
        h.sector,
        h.market_cap,
        h.cap_tier,
        b.benchmark_type,
        b.etf_ticker,
        b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'cap_style'
       and b.lookup_key = h.cap_tier

),

returns as (

    select * from {{ ref('int_ticker_returns') }}

)

select
    hb.holding_ticker,
    hb.company_name,
    hb.sector,
    hb.market_cap,
    hb.cap_tier,
    hb.benchmark_type,
    hb.benchmark_etf,
    hb.benchmark_name,
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

from holding_benchmarks hb
join returns hr on hr.ticker = hb.holding_ticker
join returns br on br.ticker = hb.benchmark_etf
