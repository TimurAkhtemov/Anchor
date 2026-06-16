with source as (

    select * from {{ source('yfinance', 'raw_yfinance_prices') }}

),

renamed as (

    select
        ticker,
        date as trading_date,
        open as open_price,
        high as high_price,
        low as low_price,
        close as close_price,
        volume as trading_volume,
        ingested_at as raw_ingested_at

    from source

)

select * from renamed
