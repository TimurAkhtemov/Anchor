with source as (

    select * from {{ source('fred', 'raw_fred_series') }}

),

renamed as (

    select
        series_id,
        title as series_title,
        frequency as reporting_frequency,
        units as unit_of_measure,
        seasonal_adjustment,
        last_updated as fred_last_updated_at,
        ingested_at as raw_ingested_at

    from source

)

select * from renamed
