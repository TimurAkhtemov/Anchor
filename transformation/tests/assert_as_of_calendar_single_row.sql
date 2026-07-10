select count(*) as n from {{ ref('as_of_calendar') }} having count(*) != 1
