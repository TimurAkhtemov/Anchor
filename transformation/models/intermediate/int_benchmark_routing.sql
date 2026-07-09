-- Resolve each non-cash holding to its benchmark set, per asset class.
-- Axes (lookup_key = the holding attribute the axis routes on):
--   equity stock  -> sector (sector name) + cap_style (cap tier)
--   equity fund   -> market ('equity')
--   fixed income  -> bond_market ('fixed_income') + duration (sub_style, if set)
-- Self-pairings (held SPY routed to SPY) are FLAGGED here, filtered by the
-- mart, and surfaced as is_root in portfolio_composition. Cash never routes.

with holdings as (

    select ticker, sector, cap_tier, quote_type, asset_class, sub_style
    from {{ ref('int_holdings_classified') }}
    where asset_class is not null
      and asset_class != 'cash'

),

benchmarks as (

    select benchmark_type, lookup_key, etf_ticker, etf_name
    from {{ ref('benchmark_etfs') }}

),

routed as (

    -- equity stocks: sector axis
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'sector'
       and h.quote_type = 'EQUITY'
       and b.lookup_key = h.sector

    union all

    -- equity stocks: cap-style axis
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'cap_style'
       and h.quote_type = 'EQUITY'
       and b.lookup_key = h.cap_tier

    union all

    -- held equity funds: market axis ("did it beat the index?")
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'market'
       and h.asset_class = 'equity'
       and h.quote_type in ('ETF', 'MUTUALFUND')
       and b.lookup_key = 'equity'

    union all

    -- fixed income: broad bond-market axis
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'bond_market'
       and h.asset_class = 'fixed_income'
       and b.lookup_key = 'fixed_income'

    union all

    -- fixed income: duration axis (only when the mapping assigns a bucket;
    -- the explicit null guard encodes the spec rule "null sub_style = skip
    -- the axis", not just the join's incidental null-rejection)
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'duration'
       and h.asset_class = 'fixed_income'
       and b.lookup_key = h.sub_style
    where h.sub_style is not null
)

select
    ticker              as holding_ticker,
    benchmark_type,
    etf_ticker          as benchmark_etf,
    etf_name            as benchmark_name,
    ticker = etf_ticker as is_self
from routed
