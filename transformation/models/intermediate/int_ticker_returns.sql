-- Per-ticker scalar returns, computed for every ticker (holdings + ETFs)
-- so the holdings mart can join the same source for both sides of a
-- comparison. All returns are measured to a single common as-of date, sourced
-- from int_market_calendar (the shared trading calendar), so a holding and
-- its benchmark are always compared over the identical window.

with prices as (

    -- Exclude incomplete bars (yfinance can return a trailing session with
    -- volume but null OHLC before its adjusted prices finalize). This anchors
    -- the common as-of date to the latest *complete* session.
    select
        ticker,
        trading_date,
        close_price
    from {{ ref('stg_yfinance__prices') }}
    where close_price is not null

),

-- Shared reference dates: as_of, prior session, ~1 month, YTD baseline, ~1 year.
ref_dates as (

    select * from {{ ref('int_market_calendar') }}

),

-- Each ticker's close at exactly those reference dates.
closes as (

    select
        p.ticker,
        max(if(p.trading_date = r.as_of_date, p.close_price, null)) as latest_close,
        max(if(p.trading_date = r.date_prior,  p.close_price, null)) as prior_close,
        max(if(p.trading_date = r.date_1m,     p.close_price, null)) as close_1m,
        max(if(p.trading_date = r.date_1y,     p.close_price, null)) as close_1y,
        max(if(p.trading_date = r.date_ytd,    p.close_price, null)) as close_ytd
    from prices p
    cross join ref_dates r
    group by p.ticker

),

final as (

    select
        c.ticker,
        r.as_of_date as as_of_date,
        c.latest_close,
        round((c.latest_close / c.prior_close - 1) * 100, 2) as daily_return_pct,
        round((c.latest_close / c.close_1m   - 1) * 100, 2) as return_1m_pct,
        round((c.latest_close / c.close_ytd  - 1) * 100, 2) as return_ytd_pct,
        round((c.latest_close / c.close_1y   - 1) * 100, 2) as return_1y_pct
    from closes c
    cross join ref_dates r

)

select * from final
