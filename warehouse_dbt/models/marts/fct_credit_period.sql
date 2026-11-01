-- Grain: precisely one credit_id + reporting period. Period-end stocks, NOT flows.
select s.credit_snapshot_id, s.credit_id, s.end_of_period,
       c.credit_number, c.project_pk, p.country_id,
       s.credit_status, s.last_disbursement_date,
       s.service_charge_rate,
       s.original_principal_amount_usd,
       s.cancelled_amount_usd,
       s.undisbursed_amount_usd,
       s.disbursed_amount_usd,
       s.repaid_to_ida_usd,
       s.due_to_ida_usd,
       s.exchange_adjustment_usd,
       s.borrowers_obligation_usd,
       s.sold_third_party_usd,
       s.repaid_third_party_usd,
       s.due_third_party_usd,
       s.credits_held_usd,
       s.ingestion_run_id, s.source_checksum, s.source_record_key, s.created_at
from {{ ref('stg_credit_snapshots') }} s
join {{ ref('dim_credit') }} c on c.credit_id = s.credit_id
join {{ ref('dim_project') }} p on p.project_pk = c.project_pk
join {{ ref('dim_country') }} country on country.country_id = p.country_id
