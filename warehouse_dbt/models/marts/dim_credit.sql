select c.credit_id, c.credit_number, c.project_pk,
       c.borrower, c.currency_of_commitment,
       c.board_approval_date, c.agreement_signing_date,
       c.effective_date, c.first_repayment_date, c.last_repayment_date, c.closed_date
from {{ ref('stg_credits') }} c
