-- Realized co-movement of each sector ETF with interest rates: the trailing
-- correlation between the ETF's daily return and the daily change in the
-- 10-year Treasury yield (DGS10). This is descriptive of a recent window --
-- NOT a structural sensitivity claim or a forecast. Positive => the sector
-- tended to rise on days yields rose; negative => it fell when yields rose
-- (rate-sensitive in the inverse sense).
--
-- Grain: one row per sector ETF.

with sector_etfs as (

    select etf_ticker
    from {{ ref('benchmark_etfs') }}
    where benchmark_type = 'sector'

),

-- daily returns for the sector ETFs we actually ingest
sector_returns as (

    select
        p.ticker,
        p.trading_date,
        p.close_price / lag(p.close_price) over (
            partition by p.ticker order by p.trading_date
        ) - 1 as daily_return
    from {{ ref('stg_yfinance__prices') }} p
    join sector_etfs s on s.etf_ticker = p.ticker
    where p.close_price is not null

),

-- daily change in the 10-year yield
rate_change as (

    select
        observation_date,
        observation_value - lag(observation_value) over (
            order by observation_date
        ) as delta_10y
    from {{ ref('stg_fred__observations') }}
    where series_id = 'DGS10'
      and observation_value is not null

),

-- align sector returns to same-day rate changes; rank for the trailing window
aligned as (

    select
        sr.ticker,
        sr.daily_return,
        rc.delta_10y,
        row_number() over (partition by sr.ticker order by sr.trading_date desc) as days_ago
    from sector_returns sr
    join rate_change rc on rc.observation_date = sr.trading_date
    where sr.daily_return is not null
      and rc.delta_10y is not null

)

select
    ticker as etf_ticker,
    count(*) as n_obs,
    round(corr(daily_return, delta_10y), 3) as rate_comovement
from aligned
where days_ago <= {{ var('comovement_window_days', 60) }}
group by ticker
