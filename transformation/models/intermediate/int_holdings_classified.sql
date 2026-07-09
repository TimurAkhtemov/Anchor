-- One classified, valued row per held ticker (aggregated across accounts).
-- Classification: quote_type is the spine (EQUITY -> equity, MONEYMARKET ->
-- cash); funds (ETF/MUTUALFUND) come from the maintained mapping because no
-- metadata source can classify fund contents. cap_tier is computed ONLY for
-- individual equities — funds have null market_cap and must never inherit a
-- cap tier (the old `else 'Small'` bug).
-- Valuation: market_value = quantity x latest close so weights stay fresh
-- between imports; cash keeps its source value (fixed $1 NAV, no price series).

with positions as (

    select
        ticker,
        max(description)          as description,
        sum(quantity)             as quantity,
        sum(source_market_value)  as source_market_value,
        sum(cost_basis_total)     as cost_basis_total,
        max(as_of)                as as_of_date
    from {{ ref('stg_holdings__positions') }}
    group by ticker

),

meta as (

    select ticker, company_name, sector, market_cap, quote_type
    from {{ ref('stg_yfinance__tickers') }}

),

fund_classes as (

    select ticker, asset_class, sub_style
    from {{ ref('stg_holdings__fund_classifications') }}

),

latest_prices as (

    select ticker, latest_close
    from {{ ref('int_ticker_returns') }}

),

classified as (

    select
        p.ticker,
        coalesce(m.company_name, p.description) as display_name,
        m.sector,
        m.market_cap,
        m.quote_type,
        case
            when p.ticker = 'CASH'                       then 'cash'
            when m.quote_type = 'MONEYMARKET'            then 'cash'
            when m.quote_type = 'EQUITY'                 then 'equity'
            when m.quote_type in ('ETF', 'MUTUALFUND')   then f.asset_class
        end as asset_class,
        f.sub_style,
        case
            when m.quote_type = 'EQUITY' then
                case
                    when m.market_cap >= 10e9 then 'Large'
                    when m.market_cap >=  2e9 then 'Mid'
                    else 'Small'
                end
        end as cap_tier,
        p.quantity,
        p.source_market_value,
        p.cost_basis_total,
        p.as_of_date,
        r.latest_close
    from positions p
    left join meta          m using (ticker)
    left join fund_classes  f using (ticker)
    left join latest_prices r using (ticker)

),

valued as (

    select
        *,
        case
            when asset_class = 'cash' then coalesce(source_market_value, quantity)
            else round(quantity * latest_close, 2)
        end as market_value
    from classified

)

select
    *,
    round(market_value / sum(market_value) over () * 100, 2) as weight_pct,
    case
        when asset_class != 'cash' and cost_basis_total > 0
        then round((market_value / cost_basis_total - 1) * 100, 2)
    end as unrealized_gain_pct
from valued
