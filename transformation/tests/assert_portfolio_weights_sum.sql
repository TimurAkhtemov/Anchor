-- Weights are shares of one whole; if they don't sum to ~100 the valuation
-- or the window function broke. Tolerance absorbs per-row rounding.

select sum(weight_pct) as total_weight
from {{ ref('portfolio_composition') }}
having abs(sum(weight_pct) - 100) > 0.5
