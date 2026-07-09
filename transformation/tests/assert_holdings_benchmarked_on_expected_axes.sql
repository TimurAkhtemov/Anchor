-- Guardrail: every non-cash holding resolves the number of benchmark axes its
-- asset class prescribes (equity stock = 2, equity fund = 1, fixed income =
-- 1 + duration-if-mapped), where self-suppressed pairings (roots) count as
-- resolved. Commodity and alt holdings intentionally expect 0 axes (v1 has no
-- routing branch for them — the `else 0` below) and are display-only in
-- portfolio_composition; this guardrail is what keeps that "unbenchmarked"
-- state a deliberate no-op instead of a silently dropped comparison. Catches
-- seed drift, taxonomy renames, and unmapped sub_styles before they silently
-- drop a comparison.

with holdings as (

    select ticker, asset_class, quote_type, sub_style
    from {{ ref('int_holdings_classified') }}
    where asset_class is not null
      and asset_class != 'cash'

),

expected as (

    select
        ticker,
        case
            when quote_type = 'EQUITY'          then 2
            when asset_class = 'fixed_income'   then 1 + if(sub_style is not null, 1, 0)
            when asset_class = 'equity'         then 1
            else 0
        end as n_expected
    from holdings

),

routed as (

    select
        holding_ticker,
        countif(is_self) as n_self
    from {{ ref('int_benchmark_routing') }}
    group by holding_ticker

),

resolved as (

    select
        holding_ticker,
        count(distinct benchmark_type) as n_axes
    from {{ ref('holdings_benchmarks') }}
    group by holding_ticker

)

select
    e.ticker,
    e.n_expected,
    coalesce(r.n_axes, 0) as n_resolved,
    coalesce(s.n_self, 0) as n_self_suppressed
from expected e
left join resolved r on r.holding_ticker = e.ticker
left join routed   s on s.holding_ticker = e.ticker
where coalesce(r.n_axes, 0) + coalesce(s.n_self, 0) < e.n_expected
