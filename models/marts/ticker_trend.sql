-- Long sparkline source: the most recent 30 trading sessions (bars) per
-- ticker. One row per ticker per trading_date; the serve layer shapes
-- these into a sparkline (a line, not bars). Covers every ticker so any
-- tier (holding or benchmark ETF) can render a trend.

with prices as (

    -- Exclude incomplete trailing bars (volume present, null OHLC) so the
    -- latest sparkline point is always a real close.
    select
        ticker,
        trading_date,
        close_price
    from {{ ref('stg_yfinance__prices') }}
    where close_price is not null

),

ranked as (

    select
        ticker,
        trading_date,
        close_price,
        row_number() over (partition by ticker order by trading_date desc) as days_ago
    from prices

)

select
    ticker,
    trading_date,
    close_price
from ranked
where days_ago <= 30
