-- No ROUND, FLOAT, COALESCE, or casts: preserve source NUMERIC precision and NULLs.
select credit_snapshot_id, credit_id, end_of_period, credit_status,
       service_charge_rate,
       original_principal_amount_usd,
       cancelled_amount_usd,
       undisbursed_amount_usd,
       disbursed_amount_usd,
       repaid_to_ida_usd,
       due_to_ida_usd,
       exchange_adjustment_usd,
       borrowers_obligation_usd,
       sold_third_party_usd,
       repaid_third_party_usd,
       due_third_party_usd,
       credits_held_usd,
       last_disbursement_date,
       ingestion_run_id, source_checksum, source_record_key, created_at
from {{ source('operational', 'credit_snapshots') }}
