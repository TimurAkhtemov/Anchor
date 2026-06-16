with source as (

    select * from {{ source('yfinance', 'raw_yfinance_tickers') }}

),

renamed as (

    select
        ticker,
        name as company_name,
        sector,
        industry,
        market_cap,
        exchange,
        currency,
        ingested_at as raw_ingested_at

    from source

)

select * from renamed
