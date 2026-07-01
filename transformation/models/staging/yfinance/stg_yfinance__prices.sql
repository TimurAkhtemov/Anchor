{{
    config(
        materialized='incremental',
        unique_key=['ticker', 'trading_date'],
        incremental_strategy='merge',
        partition_by={
            'field': 'trading_date',
            'data_type': 'date',
            'granularity': 'day'
        },
        cluster_by=['ticker']
    )
}}

with source as (

    select * from {{ source('yfinance', 'raw_yfinance_prices') }}

    {% if is_incremental() %}
        where date >= date_sub((select max(trading_date) from {{ this }}), interval 7 day)
           or ticker not in (select distinct ticker from {{ this }})
    {% endif %}

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
