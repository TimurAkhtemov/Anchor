-- The regime statement: a one-row characterization of the current macro
-- environment, synthesized from the rate / inflation / labor indicators.
-- Each dimension's 3-month delta is classified into a directional state with
-- a tunable dead-band (the regime_*_threshold_pp vars). The sector tier reads
-- this as the context banner its sectors are displayed under.
--
-- Labor semantics: a RISING unemployment rate = a LOOSENING labor market
-- (and falling unemployment = tightening), so the up/down labels are inverted
-- relative to the raw delta.
--
-- Grain: exactly one row (the pivot aggregates with no group by).

with ind as (

    select * from {{ ref('int_macro_indicators') }}

),

pivoted as (

    select
        max(as_of_date) as as_of_date,
        max(if(indicator_key = 'fed_funds_rate',    current_value, null)) as fed_funds_rate,
        max(if(indicator_key = 'fed_funds_rate',    delta_3mo,     null)) as fed_funds_delta_3mo,
        max(if(indicator_key = 'inflation_yoy',     current_value, null)) as inflation_yoy,
        max(if(indicator_key = 'inflation_yoy',     delta_3mo,     null)) as inflation_delta_3mo,
        max(if(indicator_key = 'unemployment_rate', current_value, null)) as unemployment_rate,
        max(if(indicator_key = 'unemployment_rate', delta_3mo,     null)) as unemployment_delta_3mo
    from ind

),

stated as (

    select
        *,
        {{ three_way_state('fed_funds_delta_3mo', var('regime_rate_threshold_pp'), 'rising', 'easing', 'steady') }} as rates_state,
        {{ three_way_state('inflation_delta_3mo', var('regime_inflation_threshold_pp'), 'rising', 'cooling', 'stable') }} as inflation_state,
        {{ three_way_state('unemployment_delta_3mo', var('regime_labor_threshold_pp'), 'loosening', 'tightening', 'stable') }} as labor_state
    from pivoted

)

select
    as_of_date,
    fed_funds_rate,
    fed_funds_delta_3mo,
    rates_state,
    inflation_yoy,
    inflation_delta_3mo,
    inflation_state,
    unemployment_rate,
    unemployment_delta_3mo,
    labor_state,
    concat(
        'Rates ', rates_state,
        ', inflation ', inflation_state,
        ', labor ', labor_state
    ) as regime_summary
from stated
