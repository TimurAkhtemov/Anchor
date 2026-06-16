-- Macro tier display cards: one row per macro indicator with its current
-- value, 3-month delta, a direction arrow, and FRED metadata (title, units,
-- source_series_id) for the traceability footer. Read at the top of the
-- dashboard, above the regime banner. Grain: one row per indicator_key.

with ind as (

    select * from {{ ref('int_macro_indicators') }}

),

series as (

    select
        series_id,
        series_title,
        unit_of_measure,
        reporting_frequency
    from {{ ref('stg_fred__series') }}

)

select
    i.indicator_key,
    i.source_series_id,
    s.series_title,
    s.unit_of_measure,
    s.reporting_frequency,
    i.as_of_date,
    i.current_value,
    i.value_3mo_ago,
    i.delta_3mo,
    {{ three_way_state('i.delta_3mo', 0, 'up', 'down', 'flat') }} as direction
from ind i
left join series s on s.series_id = i.source_series_id
