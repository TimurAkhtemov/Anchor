-- Guardrail: valuation_source = 'source' must be INTENTIONAL, not a silent
-- staleness leak. Only 'cash' (fixed $1 NAV, no price series) and 'alt'
-- (plan-internal instruments with no public price) are expected to be
-- source-valued. Any other asset class landing here means a normally-priced
-- instrument (equity, fixed_income, commodity) transiently has no yfinance
-- close — that must fail the build loudly instead of quietly going stale.

select ticker, asset_class, valuation_source
from {{ ref('portfolio_composition') }}
where valuation_source = 'source'
  and asset_class not in ('cash', 'alt')
