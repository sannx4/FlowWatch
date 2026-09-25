## 9. Source-to-Canonical Field Mapping

Each World Bank source field receives one explicit classification:

* `MAPPED` — persisted directly in the operational model.
* `DERIVED` — reproducible from another retained field.
* `DEFERRED` — temporal semantics require broader historical validation.
* `EXCLUDED` — intentionally omitted with a documented reason.

| Source field                    | Decision | Destination                                           | Rationale                                               |
| ------------------------------- | -------- | ----------------------------------------------------- | ------------------------------------------------------- |
| `region`                        | MAPPED   | `regions.region_name`                                 | Region descriptor                                       |
| `country_code`                  | MAPPED   | `countries.country_code`                              | Natural country identifier                              |
| `country`                       | MAPPED   | `countries.country_name`                              | Country name                                            |
| `project_id`                    | MAPPED   | `projects.project_id`                                 | World Bank project identifier                           |
| `project_name`                  | MAPPED   | `projects.project_name`                               | Project descriptor                                      |
| `credit_number`                 | MAPPED   | `credits.credit_number`                               | Natural credit identifier                               |
| `borrower`                      | MAPPED   | `credits.borrower`                                    | Credit-level descriptor, subject to temporal validation |
| `currency_of_commitment`        | MAPPED   | `credits.currency_of_commitment`                      | Commitment currency                                     |
| `board_approval_date`           | MAPPED   | `credits.board_approval_date`                         | Lifecycle date                                          |
| `agreement_signing_date`        | MAPPED   | `credits.agreement_signing_date`                      | Lifecycle date                                          |
| `effective_date_most_recent`    | DEFERRED | provisional `credits.effective_date`                  | “Most recent” semantics may change retrospectively      |
| `first_repayment_date`          | MAPPED   | `credits.first_repayment_date`                        | Lifecycle date                                          |
| `last_repayment_date`           | MAPPED   | `credits.last_repayment_date`                         | Lifecycle date                                          |
| `closed_date_most_recent`       | DEFERRED | provisional `credits.closed_date`                     | Requires temporal-stability validation                  |
| `end_of_period`                 | MAPPED   | `credit_snapshots.end_of_period`                      | Defines historical snapshot time                        |
| `credit_status`                 | MAPPED   | `credit_snapshots.credit_status`                      | Time-varying credit state                               |
| `service_charge_rate`           | MAPPED   | `credit_snapshots.service_charge_rate`                | Snapshot-level financial state                          |
| `original_principal_amount_us_` | MAPPED   | `credit_snapshots.original_principal_amount_usd`      | Historical financial measure                            |
| `cancelled_amount_us_`          | MAPPED   | `credit_snapshots.cancelled_amount_usd`               | Historical financial measure                            |
| `undisbursed_amount_us_`        | MAPPED   | `credit_snapshots.undisbursed_amount_usd`             | Historical financial measure                            |
| `disbursed_amount_us_`          | MAPPED   | `credit_snapshots.disbursed_amount_usd`               | Historical financial measure                            |
| `repaid_to_ida_us_`             | MAPPED   | `credit_snapshots.repaid_to_ida_usd`                  | Historical financial measure                            |
| `due_to_ida_us_`                | MAPPED   | `credit_snapshots.due_to_ida_usd`                     | Historical financial measure                            |
| `exchange_adjustment_us_`       | MAPPED   | `credit_snapshots.exchange_adjustment_usd`            | Historical financial measure                            |
| `borrowers_obligation_us_`      | MAPPED   | `credit_snapshots.borrowers_obligation_usd`           | Historical financial measure                            |
| `sold_3rd_party_us_`            | MAPPED   | `credit_snapshots.sold_third_party_usd`               | Historical financial measure                            |
| `repaid_3rd_party_us_`          | MAPPED   | `credit_snapshots.repaid_third_party_usd`             | Historical financial measure                            |
| `due_3rd_party_us_`             | MAPPED   | `credit_snapshots.due_third_party_usd`                | Historical financial measure                            |
| `credits_held_us_`              | MAPPED   | `credit_snapshots.credits_held_usd`                   | Historical financial measure                            |
| `last_disbursement_date`        | DEFERRED | provisional `credit_snapshots.last_disbursement_date` | Must verify historical behavior                         |
| approval fiscal-year field      | DERIVED  | not persisted initially                               | Derivable from approval date                            |
| approval calendar-year field    | DERIVED  | not persisted initially                               | Derivable from `board_approval_date`                    |

### Verification Status

This mapping is provisional and based on the Day-3 exploration plus the known World Bank source schema.

Final verification against the exact locally reproduced 100-record raw sample remains pending because the upstream World Bank API was unavailable during Day 4.

No source field may remain without an explicit mapping, derivation, deferment, or exclusion decision once raw-sample access is restored.
