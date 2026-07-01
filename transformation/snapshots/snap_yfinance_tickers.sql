{% snapshot snap_yfinance_tickers %}

{% set snapshot_schema = 'anchor_snapshots' if target.name == 'prod' else target.schema %}

{{
    config(
        target_schema=snapshot_schema,
        unique_key='ticker',
        strategy='check',
        check_cols=[
            'company_name',
            'sector',
            'industry',
            'market_cap',
            'exchange',
            'currency'
        ],
        invalidate_hard_deletes=True
    )
}}

select
    ticker,
    company_name,
    sector,
    industry,
    market_cap,
    exchange,
    currency,
    raw_ingested_at
from {{ ref('stg_yfinance__tickers') }}

{% endsnapshot %}
