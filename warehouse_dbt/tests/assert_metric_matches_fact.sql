-- A reporting view is never allowed to silently alter financial stock numbers.
select coalesce(f.credit_snapshot_id, m.credit_snapshot_id) as mismatched_snapshot_id
from {{ ref('fct_credit_period') }} f
full outer join {{ ref('mart_credit_period_metrics') }} m
    on f.credit_snapshot_id = m.credit_snapshot_id
where f.credit_snapshot_id is null or m.credit_snapshot_id is null
  or f.credit_id is distinct from m.credit_id
  or f.end_of_period is distinct from m.end_of_period
  or f.original_principal_amount_usd is distinct from m.original_principal_amount_usd
  or f.cancelled_amount_usd is distinct from m.cancelled_amount_usd
  or f.disbursed_amount_usd is distinct from m.disbursed_amount_usd
  or f.undisbursed_amount_usd is distinct from m.undisbursed_amount_usd
  or f.repaid_to_ida_usd is distinct from m.repaid_to_ida_usd
  or f.due_to_ida_usd is distinct from m.due_to_ida_usd
  or f.borrowers_obligation_usd is distinct from m.borrowers_obligation_usd
  or f.credits_held_usd is distinct from m.credits_held_usd
  or f.exchange_adjustment_usd is distinct from m.exchange_adjustment_usd
