-- Normalizes the FRED macro series into one uniform row per *indicator*:
-- current value, value 3 months ago, and the 3-month delta. Mixed-frequency
-- safe — anchors are calendar dates (latest, -3mo, -12mo, -15mo) and each
-- value is the most recent observation on or before its anchor.
--
-- Inflation is special: CPIAUCSL is a price-index LEVEL, so the indicator is
-- the derived year-over-year rate (CPI_now / CPI_12mo_ago - 1), and its
-- "3 months ago" value is the YoY rate as of 3 months back. The level series
-- (fed funds, 10Y, unemployment) just pass through their value.
--
-- Grain: one row per indicator_key. Reused by macro_regime (now) and the
-- macro-tier display mart (later).

with obs as (

    select
        series_id,
        observation_date,
        observation_value
    from {{ ref('stg_fred__observations') }}
    where observation_value is not null

),

-- macro as-of date per series = its latest observation
latest as (

    select
        series_id,
        max(observation_date) as as_of_date
    from obs
    group by series_id

),

-- the calendar anchors we need values at, per series
anchor_targets as (

    select series_id, as_of_date, 'now'  as anchor, as_of_date                               as target_date from latest
    union all
    select series_id, as_of_date, '3mo',  date_sub(as_of_date, interval 3 month)  from latest
    union all
    select series_id, as_of_date, '12mo', date_sub(as_of_date, interval 12 month) from latest
    union all
    select series_id, as_of_date, '15mo', date_sub(as_of_date, interval 15 month) from latest

),

-- most recent observation on or before each anchor (as-of join)
asof_values as (

    select
        t.series_id,
        t.as_of_date,
        t.anchor,
        array_agg(o.observation_value order by o.observation_date desc limit 1)[offset(0)] as value
    from anchor_targets t
    join obs o
        on o.series_id = t.series_id
       and o.observation_date <= t.target_date
    group by t.series_id, t.as_of_date, t.anchor

),

pivoted as (

    select
        series_id,
        any_value(as_of_date) as as_of_date,
        max(if(anchor = 'now',  value, null)) as v_now,
        max(if(anchor = '3mo',  value, null)) as v_3mo,
        max(if(anchor = '12mo', value, null)) as v_12mo,
        max(if(anchor = '15mo', value, null)) as v_15mo
    from asof_values
    group by series_id

),

indicators as (

    -- Fed funds policy rate (level, %)
    select
        'fed_funds_rate'   as indicator_key,
        'DFF'              as source_series_id,
        as_of_date,
        round(v_now, 2)            as current_value,
        round(v_3mo, 2)            as value_3mo_ago,
        round(v_now - v_3mo, 2)    as delta_3mo
    from pivoted where series_id = 'DFF'

    union all

    -- 10-year Treasury yield (level, %) — for the macro tier + sector co-movement
    select
        'ten_year_yield', 'DGS10', as_of_date,
        round(v_now, 2), round(v_3mo, 2), round(v_now - v_3mo, 2)
    from pivoted where series_id = 'DGS10'

    union all

    -- Unemployment rate (level, %)
    select
        'unemployment_rate', 'UNRATE', as_of_date,
        round(v_now, 2), round(v_3mo, 2), round(v_now - v_3mo, 2)
    from pivoted where series_id = 'UNRATE'

    union all

    -- Inflation (derived YoY rate, %). current = YoY now, 3mo_ago = YoY then.
    select
        'inflation_yoy', 'CPIAUCSL', as_of_date,
        round((v_now / v_12mo - 1) * 100, 2)                                       as current_value,
        round((v_3mo / v_15mo - 1) * 100, 2)                                       as value_3mo_ago,
        round((v_now / v_12mo - 1) * 100 - (v_3mo / v_15mo - 1) * 100, 2)          as delta_3mo
    from pivoted where series_id = 'CPIAUCSL'

)

select * from indicators
