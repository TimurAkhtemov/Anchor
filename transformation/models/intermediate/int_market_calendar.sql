-- THE shared trading calendar: one row of reference dates that every horizon
-- comparison in the project anchors to. Derived from the benchmark-ETF set
-- only (the liquid benchmarks DEFINE the market calendar; a holding's oddball
-- bar must not move the as-of date for everyone else). Consumed by
-- int_ticker_returns (return windows) and the as_of_calendar mart, so the
-- serve layer windows sparklines over the IDENTICAL dates the returns were
-- computed over -- one calendar, no client-side re-derivation.

with prices as (

    select ticker, trading_date, close_price
    from {{ ref('stg_yfinance__prices') }}
    where close_price is not null

),

calendar as (

    select
        trading_date,
        row_number() over (order by trading_date desc) as days_ago
    from (
        select distinct trading_date
        from prices
        where ticker in (select etf_ticker from {{ ref('benchmark_etfs') }})
    )

),

ref_dates as (

    select
        max(if(days_ago = 1,   trading_date, null)) as as_of_date,
        max(if(days_ago = 2,   trading_date, null)) as date_prior,
        max(if(days_ago = 22,  trading_date, null)) as date_1m,
        max(if(days_ago = 253, trading_date, null)) as date_1y
    from calendar

),

ytd_base as (

    select max(c.trading_date) as date_ytd
    from calendar c
    cross join ref_dates r
    where extract(year from c.trading_date) < extract(year from r.as_of_date)

)

select
    r.as_of_date,
    r.date_prior,
    r.date_1m,
    y.date_ytd,
    r.date_1y
from ref_dates r
cross join ytd_base y
