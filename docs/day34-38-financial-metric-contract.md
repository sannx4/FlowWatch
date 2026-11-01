# Days 34–38 — Financial warehouse metric and grain contract

## Source, target and invariants

- Source: `flowwatch_historical_gate.public` Day33 canonical tables.
- dbt target: `flowwatch_historical_gate.fw_analytics`; never main `flowwatch`.
- Source identity: `credit_snapshot_id`, `credit_id`, `end_of_period`; one temporal snapshot per credit and period.
- `fct_credit_period`: one row per canonical snapshot, exactly matching all 13 source monetary / rate fields at PostgreSQL NUMERIC precision. Missing values remain NULL.
- Dimension references: project -> country -> region, credit -> project. Current descriptive values only; not SCD2.
- Immutable observation-level decisions are separate from unique canonical snapshots; never infer statistical independence from row count.
- Audits: exact fact/source parity, two-way cardinality, dimension keys, temporal uniqueness, lineage consistency, month-gap rules.

## Metric semantics

| Model field | Type | Semantics | Aggregation limitation |
|---|---|---|---|
| original_principal_amount_usd | NUMERIC(24,2) | Reported original principal | Do not sum across reporting months |
| disbursed_amount_usd | NUMERIC(24,2) | Source-reported cumulative / period-end disbursed amount | Stock-like; avoid period summation |
| undisbursed_amount_usd | NUMERIC(24,2) | Source-reported undisbursed amount at period end | Stock-like; avoid period summation |
| repaid_to_ida_usd | NUMERIC(24,2) | Source-reported repaid-to-IDA amount at period end | Stock-like; avoid period summation |
| borrowers_obligation_usd | NUMERIC(24,2) | Source-reported borrower obligation | Balance; no temporal sum |
| credits_held_usd | NUMERIC(24,2) | Source-reported credits held | Balance; no temporal sum |
| exchange_adjustment_usd | NUMERIC(24,2) | Source-reported exchange adjustment | Retain signed value; no unproven equality |
| service_charge_rate | NUMERIC(12,6) | Source-reported charge rate | Not additive |
| change_in_reported_disbursed_usd | NUMERIC | Difference between immediately previous **calendar-month** stock observations for same credit | Not an independently observed monthly cash flow |
| change_in_reported_undisbursed_usd | NUMERIC | Analogous adjacent-month difference | Not an actual release/cancellation flow |
| change_in_reported_repaid_to_ida_usd | NUMERIC | Analogous adjacent-month difference | Not guaranteed cash settlement |

If an earlier period does not exist, or calendar months are not adjacent, the change is NULL. Both compared stock values must also be non-null. No imputation, zero filling, hard-coded accounting identities, or assumption of positive-only changes is applied.

## Research exclusions

1. Row count alone cannot prove representative coverage, independent samples or forecasting maturity.
2. No release claims to measure maturity-aware 3/6/12 month label availability.
3. The World Bank source lacks an upstream transactionally consistent point-in-time pagination snapshot.
4. Source stock revisions/currency effects can change adjacent-month differences independently of cash movement.
5. Full 1.6M-source backfill, Parquet export, and leakage-safe forecast evaluation remain pending.
