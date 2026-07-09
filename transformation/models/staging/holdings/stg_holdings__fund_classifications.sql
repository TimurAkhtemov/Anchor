-- Fund-classification mapping: which asset class a held fund (quote_type
-- ETF/MUTUALFUND) belongs to, plus its per-class sub_style (duration bucket
-- for bonds). Maintained by hand because no free source can classify fund
-- CONTENTS (verified: yfinance category is null for mutual funds; SnapTrade
-- security_type is just 'oef'; see docs/make_it_real_design.md appendix).
-- Demo funds = the committed seed; real funds = a private bronze table so no
-- fact about the real portfolio lives in the repo (decision 8).

with committed as (

    select
        ticker,
        asset_class,
        nullif(trim(coalesce(sub_style, '')), '') as sub_style
    from {{ ref('fund_classifications') }}

)

{% if var('holdings_source', 'demo') == 'real' %}

, private as (

    select
        ticker,
        asset_class,
        nullif(trim(coalesce(sub_style, '')), '') as sub_style
    from {{ source('holdings', 'fund_classifications_real') }}

)

select * from committed
union distinct
select * from private

{% else %}

select * from committed

{% endif %}
