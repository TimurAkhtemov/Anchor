-- three_way_state must treat a move of exactly the threshold as a change when
-- inclusive=true (the regime guide's "at least" wording), and keep the strict
-- dead-band by default. Returns the cases where the macro disagrees with `expected`.

with cases as (

    select 0.25 as delta, 0.25 as threshold, 'up'   as expected union all
    select -0.25,         0.25,              'down'             union all
    select 0.30,          0.3,               'up'               union all
    select -0.30,         0.3,               'down'             union all
    select 0.20,          0.2,               'up'               union all
    select -0.20,         0.2,               'down'             union all
    select 0.19,          0.2,               'mid'              union all
    select -0.19,         0.2,               'mid'

),

strict_cases as (

    select 0.20 as delta, 0.2 as threshold, 'mid' as expected union all
    select 0.0,           0.0,              'mid'

),

results as (

    select delta, threshold, expected, 'inclusive' as mode,
        {{ three_way_state('delta', 'threshold', 'up', 'down', 'mid', inclusive=true) }} as actual
    from cases

    union all

    select delta, threshold, expected, 'strict' as mode,
        {{ three_way_state('delta', 'threshold', 'up', 'down', 'mid') }} as actual
    from strict_cases

)

select * from results where actual != expected
