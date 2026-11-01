select credit_id, end_of_period, count(*) as duplicate_count
from {{ ref('fct_credit_period') }}
group by credit_id, end_of_period
having count(*) <> 1
