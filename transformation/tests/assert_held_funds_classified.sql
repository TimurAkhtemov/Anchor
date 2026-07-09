-- Guardrail: every held fund (quote_type ETF / MUTUALFUND) must have a row in
-- the fund-classification mapping. Without one its asset_class is null and it
-- would silently receive no benchmark. Fail the build loudly instead — the fix
-- is one seed row (demo) or one line in data/private/fund_classifications_real.csv.

select
    p.ticker,
    t.quote_type
from (select distinct ticker from {{ ref('stg_holdings__positions') }}) p
join {{ ref('stg_yfinance__tickers') }} t using (ticker)
where t.quote_type in ('ETF', 'MUTUALFUND')
  and p.ticker not in (select ticker from {{ ref('stg_holdings__fund_classifications') }})
