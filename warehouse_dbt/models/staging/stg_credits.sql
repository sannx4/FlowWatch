select credit_id, credit_number, project_pk,
       borrower, currency_of_commitment, board_approval_date,
       agreement_signing_date, effective_date, first_repayment_date,
       last_repayment_date, closed_date
from {{ source('operational', 'credits') }}
