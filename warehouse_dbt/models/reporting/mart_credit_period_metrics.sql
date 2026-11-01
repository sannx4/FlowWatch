-- Stock observations are not summed across time. Changes are not verified cash flows.
with ordered as (
    select f.*,
           lag(end_of_period) over (partition by credit_id order by end_of_period) as previous_period,
           lag(disbursed_amount_usd) over (partition by credit_id order by end_of_period) as previous_disbursed_usd,
           lag(undisbursed_amount_usd) over (partition by credit_id order by end_of_period) as previous_undisbursed_usd,
           lag(repaid_to_ida_usd) over (partition by credit_id order by end_of_period) as previous_repaid_to_ida_usd
    from {{ ref('fct_credit_period') }} f
), intervals as (
    select *,
           coalesce(date_trunc('month', previous_period) =
                    date_trunc('month', end_of_period) - interval '1 month', false)
                    as is_consecutive_month
    from ordered
)
select credit_snapshot_id, credit_id, credit_number, country_id, end_of_period,
       previous_period, is_consecutive_month,
       original_principal_amount_usd, cancelled_amount_usd,
       disbursed_amount_usd, undisbursed_amount_usd,
       repaid_to_ida_usd, due_to_ida_usd, borrowers_obligation_usd,
       credits_held_usd, exchange_adjustment_usd,
       case when is_consecutive_month and disbursed_amount_usd is not null
                and previous_disbursed_usd is not null
            then disbursed_amount_usd - previous_disbursed_usd end
            as change_in_reported_disbursed_usd,
       case when is_consecutive_month and undisbursed_amount_usd is not null
                and previous_undisbursed_usd is not null
            then undisbursed_amount_usd - previous_undisbursed_usd end
            as change_in_reported_undisbursed_usd,
       case when is_consecutive_month and repaid_to_ida_usd is not null
                and previous_repaid_to_ida_usd is not null
            then repaid_to_ida_usd - previous_repaid_to_ida_usd end
            as change_in_reported_repaid_to_ida_usd,
       ingestion_run_id, source_checksum, source_record_key
from intervals
