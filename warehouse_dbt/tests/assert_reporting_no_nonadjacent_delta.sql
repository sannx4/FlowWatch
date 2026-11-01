select credit_snapshot_id
from {{ ref('mart_credit_period_metrics') }}
where (not is_consecutive_month)
  and (change_in_reported_disbursed_usd is not null
    or change_in_reported_undisbursed_usd is not null
    or change_in_reported_repaid_to_ida_usd is not null)
