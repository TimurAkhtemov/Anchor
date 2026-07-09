-- One classified, valued row per held ticker (aggregated across accounts).
-- Classification: the maintained fund mapping is a true OVERRIDE — explicit
-- human classification wins over derivation, whatever the quote_type. The
-- derived fallback uses quote_type as the spine (EQUITY -> equity,
-- MONEYMARKET -> cash); funds have no derived class because no metadata
-- source can classify fund contents. cap_tier is computed ONLY for
-- individual equities — funds have null market_cap and must never inherit a
-- cap tier (the old `else 'Small'` bug).
-- Valuation is explicitly dual-source (valuation_source): market-valued rows
-- get quantity x latest close so weights stay fresh between imports;
-- source-valued rows keep the source's value.

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
        coalesce(
            f.asset_class,
            case
                when p.ticker = 'CASH'            then 'cash'
                when m.quote_type = 'MONEYMARKET' then 'cash'
                when m.quote_type = 'EQUITY'      then 'equity'
            end
        ) as asset_class,
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

sourced as (

    -- source-valued = the instrument can't be marked to market from public
    -- prices (cash NAV, plan-internal funds); the flag makes the fallback
    -- visible instead of incidental (the SPAXX lesson).
    select
        *,
        case
            when asset_class = 'cash'   then 'source'
            when latest_close is null   then 'source'
            else 'market'
        end as valuation_source
    from classified

),

valued as (

    select
        *,
        case
            when valuation_source = 'source' then coalesce(source_market_value, quantity)
            else round(quantity * latest_close, 2)
        end as market_value
    from sourced

)

select
    *,
    round(market_value / sum(market_value) over () * 100, 2) as weight_pct,
    case
        when asset_class != 'cash' and cost_basis_total > 0
        then round((market_value / cost_basis_total - 1) * 100, 2)
    end as unrealized_gain_pct
from valued
