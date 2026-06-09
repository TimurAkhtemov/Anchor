with source as (

    select * from {{ source('fred', 'raw_fred_observations') }}

),

renamed as (

    select
        series_id,
        date as observation_date,
        value as observation_value,
        ingested_at as raw_ingested_at

    from source

)

select * from renamed
