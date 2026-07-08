-- Latest position batch for the selected portfolio (var holdings_source:
-- demo | real, default demo). Bronze appends every load with an as_of batch
-- date (position history banks for a future time-series milestone); staging
-- serves only the newest batch, deduped to the latest ingestion within it.

{% set holdings_table = 'holdings_real' if var('holdings_source', 'demo') == 'real' else 'holdings_demo' %}

with source as (

    select * from {{ source('holdings', holdings_table) }}

),

latest_batch as (

    select * from source
    where as_of = (select max(as_of) from source)

),

deduped as (

    select
        *,
        row_number() over (
            partition by account_number, coalesce(ticker, 'CASH')
            order by ingested_at desc
        ) as rn
    from latest_batch

)

select
    account_number,
    account_name,
    -- Cash-in-motion rows (e.g. Fidelity "Pending Activity") carry no symbol;
    -- give them a stable pseudo-ticker so every grain key is non-null.
    coalesce(ticker, 'CASH') as ticker,
    description,
    quantity,
    price        as source_price,
    market_value as source_market_value,
    cost_basis_total,
    as_of,
    source,
    ingested_at  as raw_ingested_at
from deduped
where rn = 1
