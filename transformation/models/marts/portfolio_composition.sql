-- The sizing mart: one row per held ticker INCLUDING cash and root holdings,
-- with live market value, portfolio weight, and unrealized gain. This is the
-- holding-vs-whole-portfolio relationship, computed in gold per the core
-- principle. is_root marks a holding whose only routed benchmark was itself
-- (held SPY on the market axis) — it IS the reference point, so it displays
-- with no comparison rather than a meaningless holding-vs-itself row.

with holdings as (

    select * from {{ ref('int_holdings_classified') }}

),

routing_summary as (

    select
        holding_ticker,
        countif(not is_self) as n_benchmarks,
        countif(is_self)     as n_self
    from {{ ref('int_benchmark_routing') }}
    group by holding_ticker

)

select
    h.ticker,
    h.display_name       as description,
    h.asset_class,
    h.quote_type,
    h.sub_style,
    h.quantity,
    h.latest_close,
    h.market_value,
    h.weight_pct,
    h.cost_basis_total   as cost_basis,
    h.unrealized_gain_pct,
    coalesce(r.n_self, 0) > 0 and coalesce(r.n_benchmarks, 0) = 0 as is_root,
    h.as_of_date
from holdings h
left join routing_summary r on r.holding_ticker = h.ticker
