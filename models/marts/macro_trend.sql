-- Macro sparkline source: the trailing N months of each indicator's series,
-- one row per indicator per observation_date. The FRED analog of ticker_trend.
-- Mixed-frequency safe: a fixed time WINDOW (not a row count), so daily series
-- (DFF/DGS10) carry more points than monthly ones (CPI/UNRATE) over the same
-- span. Inflation is the derived YoY trajectory, not the raw CPI level, to
-- match the inflation card's value.
--
-- Grain: one row per (indicator_key, observation_date).

with obs as (

    select
        series_id,
        observation_date,
        observation_value
    from {{ ref('stg_fred__observations') }}
    where observation_value is not null

),

as_of as (

    select series_id, max(observation_date) as as_of_date
    from obs
    group by series_id

),

-- level series pass through their value
levels as (

    select
        case o.series_id
            when 'DFF'    then 'fed_funds_rate'
            when 'DGS10'  then 'ten_year_yield'
            when 'UNRATE' then 'unemployment_rate'
        end as indicator_key,
        o.observation_date,
        round(o.observation_value, 2) as value
    from obs o
    join as_of a on a.series_id = o.series_id
    where o.series_id in ('DFF', 'DGS10', 'UNRATE')
      and o.observation_date >= date_sub(a.as_of_date, interval {{ var('macro_trend_months', 12) }} month)

),

-- inflation = CPI year-over-year trajectory (monthly series, so lag 12 = 12mo)
cpi_yoy as (

    select
        observation_date,
        observation_value / lag(observation_value, 12) over (order by observation_date) - 1 as yoy
    from obs
    where series_id = 'CPIAUCSL'

),

inflation as (

    select
        'inflation_yoy' as indicator_key,
        c.observation_date,
        round(c.yoy * 100, 2) as value
    from cpi_yoy c
    join as_of a on a.series_id = 'CPIAUCSL'
    where c.yoy is not null
      and c.observation_date >= date_sub(a.as_of_date, interval {{ var('macro_trend_months', 12) }} month)

)

select indicator_key, observation_date, value from levels
union all
select indicator_key, observation_date, value from inflation
