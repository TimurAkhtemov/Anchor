-- Per-ticker scalar returns, computed for every ticker (holdings + ETFs)
-- so the holdings mart can join the same source for both sides of a
-- comparison. All returns are measured to a single common as-of date
-- (max trading_date across the whole market calendar) so a holding and
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

-- Distinct market trading calendar; most-recent session = 1.
-- Anchored to the benchmark ETFs only: the liquid benchmark set DEFINES the
-- market calendar. A holding's oddball bar (e.g. a money-market NAV stamped
-- ahead of the market's last complete close) must not move the common
-- as-of date for everyone else.
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

-- Reference dates by trading-day offset from the common as-of date.
-- latest = 1, prior session = 2, ~1 month = 22 (21 sessions back),
-- ~1 year = 253 (252 sessions back).
ref_dates as (

    select
        max(if(days_ago = 1,   trading_date, null)) as date_latest,
        max(if(days_ago = 2,   trading_date, null)) as date_prior,
        max(if(days_ago = 22,  trading_date, null)) as date_1m,
        max(if(days_ago = 253, trading_date, null)) as date_1y
    from calendar

),

-- YTD baseline = last trading day of the previous calendar year.
ytd_base as (

    select max(c.trading_date) as date_ytd
    from calendar c
    cross join ref_dates r
    where extract(year from c.trading_date) < extract(year from r.date_latest)

),

-- Each ticker's close at exactly those reference dates.
closes as (

    select
        p.ticker,
        max(if(p.trading_date = r.date_latest, p.close_price, null)) as latest_close,
        max(if(p.trading_date = r.date_prior,  p.close_price, null)) as prior_close,
        max(if(p.trading_date = r.date_1m,     p.close_price, null)) as close_1m,
        max(if(p.trading_date = r.date_1y,     p.close_price, null)) as close_1y,
        max(if(p.trading_date = y.date_ytd,    p.close_price, null)) as close_ytd
    from prices p
    cross join ref_dates r
    cross join ytd_base y
    group by p.ticker

),

final as (

    select
        c.ticker,
        r.date_latest as as_of_date,
        c.latest_close,
        round((c.latest_close / c.prior_close - 1) * 100, 2) as daily_return_pct,
        round((c.latest_close / c.close_1m   - 1) * 100, 2) as return_1m_pct,
        round((c.latest_close / c.close_ytd  - 1) * 100, 2) as return_ytd_pct,
        round((c.latest_close / c.close_1y   - 1) * 100, 2) as return_1y_pct
    from closes c
    cross join ref_dates r

)

select * from final
