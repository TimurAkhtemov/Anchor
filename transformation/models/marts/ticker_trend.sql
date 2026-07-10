-- Long sparkline source: the trailing 260 trading sessions (bars) per
-- ticker -- enough to cover the 1-year horizon window with margin. One row
-- per ticker per trading_date; the serve layer shapes these into a
-- sparkline (a line, not bars). Covers every ticker so any tier (holding or
-- benchmark ETF) can render a trend.

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

),

-- Scope to this world's universe: held tickers + benchmark ETFs. Demo marts
-- (and therefore the public snapshot) must never mention a real-portfolio
-- ticker; the scoping inherits the world from stg_holdings__positions.
universe as (

    select ticker from {{ ref('stg_holdings__positions') }}
    where ticker != 'CASH'

    union distinct

    select etf_ticker as ticker from {{ ref('benchmark_etfs') }}

)

select
    ticker,
    trading_date,
    close_price
from ranked
where days_ago <= 260
  and ticker in (select ticker from universe)
