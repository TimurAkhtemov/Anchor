-- Serve-layer window endpoints — the same reference dates int_ticker_returns
-- uses to compute holding/benchmark returns. The app windows sparklines to
-- these dates so a trend line can never contradict the return% beside it.

select
    as_of_date,
    date_prior,
    date_1m,
    date_ytd,
    date_1y
from {{ ref('int_market_calendar') }}
