-- Sector tier: each ingested SPDR sector ETF's performance, plus its recent
-- co-movement with the 10-year yield. Read underneath the macro_regime banner
-- (a singleton the UI renders above this list) and above the holdings tier.
--
-- All 11 SPDR sector ETFs are ingested (the yfinance universe derives from the
-- benchmark_etfs seed ∪ held tickers), so this mart is a complete sector map,
-- not scoped to current holdings' sectors.
--
-- Grain: one row per sector ETF.

with sector_etfs as (

    select
        etf_ticker,
        lookup_key as sector,
        etf_name
    from {{ ref('benchmark_etfs') }}
    where benchmark_type = 'sector'

),

returns as (

    select * from {{ ref('int_ticker_returns') }}

),

comovement as (

    select * from {{ ref('int_sector_rate_comovement') }}

)

select
    s.sector,
    s.etf_ticker,
    s.etf_name,
    r.as_of_date,
    r.latest_close as current_price,
    r.daily_return_pct,
    r.return_1m_pct,
    r.return_ytd_pct,
    r.return_1y_pct,
    c.rate_comovement,
    c.n_obs as comovement_n_obs,
    {{ three_way_state('c.rate_comovement', var('comovement_threshold'), 'moves with rates', 'moves against rates', 'rate-neutral') }} as rate_comovement_label
from sector_etfs s
join returns r on r.ticker = s.etf_ticker
left join comovement c on c.etf_ticker = s.etf_ticker
