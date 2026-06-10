-- Guardrail: every holding must resolve to BOTH benchmark axes
-- (sector + cap_style). The axis joins in holdings_benchmarks are inner
-- joins, so a holding whose live sector or cap tier doesn't map to a
-- benchmark_etfs seed row would silently lose that axis' row with no error.
-- This test fails the build instead, surfacing seed drift (e.g. a yfinance
-- taxonomy rename, or a new holding in an unmapped sector).
--
-- Encodes the current model's invariant: holdings are individual stocks,
-- each benchmarked on exactly the sector + cap_style axes. Revisit when
-- held ETFs enter the holdings universe (they carry a different axis set).

with expected_holdings as (

    select ticker as holding_ticker
    from {{ ref('stg_yfinance__tickers') }}
    where ticker not in (select etf_ticker from {{ ref('benchmark_etfs') }})

),

resolved as (

    select
        holding_ticker,
        count(distinct benchmark_type) as n_axes
    from {{ ref('holdings_benchmarks') }}
    group by holding_ticker

)

select
    e.holding_ticker,
    coalesce(r.n_axes, 0) as n_axes_resolved
from expected_holdings e
left join resolved r using (holding_ticker)
where coalesce(r.n_axes, 0) < 2
