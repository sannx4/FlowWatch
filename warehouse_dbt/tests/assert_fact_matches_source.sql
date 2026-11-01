-- Strict source-to-fact identity and all NUMERIC values; any row returned fails.
with source_rows as (
    select * from {{ source('operational', 'credit_snapshots') }}
), fact_rows as (
    select * from {{ ref('fct_credit_period') }}
)
select coalesce(src.credit_snapshot_id, fact.credit_snapshot_id) as mismatched_snapshot_id
from source_rows src
full outer join fact_rows fact on fact.credit_snapshot_id = src.credit_snapshot_id
where src.credit_snapshot_id is null or fact.credit_snapshot_id is null
   or src.credit_id is distinct from fact.credit_id
   or src.end_of_period is distinct from fact.end_of_period
   or src.credit_status is distinct from fact.credit_status
   or src.last_disbursement_date is distinct from fact.last_disbursement_date
   or src.ingestion_run_id is distinct from fact.ingestion_run_id
   or src.source_checksum is distinct from fact.source_checksum
   or src.source_record_key is distinct from fact.source_record_key
   or src.created_at is distinct from fact.created_at
   or src.service_charge_rate is distinct from fact.service_charge_rate
   or src.original_principal_amount_usd is distinct from fact.original_principal_amount_usd
   or src.cancelled_amount_usd is distinct from fact.cancelled_amount_usd
   or src.undisbursed_amount_usd is distinct from fact.undisbursed_amount_usd
   or src.disbursed_amount_usd is distinct from fact.disbursed_amount_usd
   or src.repaid_to_ida_usd is distinct from fact.repaid_to_ida_usd
   or src.due_to_ida_usd is distinct from fact.due_to_ida_usd
   or src.exchange_adjustment_usd is distinct from fact.exchange_adjustment_usd
   or src.borrowers_obligation_usd is distinct from fact.borrowers_obligation_usd
   or src.sold_third_party_usd is distinct from fact.sold_third_party_usd
   or src.repaid_third_party_usd is distinct from fact.repaid_third_party_usd
   or src.due_third_party_usd is distinct from fact.due_third_party_usd
   or src.credits_held_usd is distinct from fact.credits_held_usd
