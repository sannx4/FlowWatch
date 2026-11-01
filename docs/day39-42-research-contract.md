# Research dataset and temporal maturity contract — FlowWatch V7

## Grain and scope

The export grain is **one canonical snapshot per accepted source observation
in one named Day33 publication**. We require 1:1 identity for this release.
In other historical runs, duplicate canonical keys or quarantined records
must be handled with an updated versioned export policy instead of silently
collapsing source observations into independent rows.

The 3,000-row bounded acquisition is not a random/representative sample of
the 1,612,290 source count. The API pagination has no stated point-in-time
consistency guarantee; later pages may reflect a changing source.

## Financial meaning

- Source balances and cumulative amounts are recorded financial measures,
  **not independently verified cash flows**. No invented accounting identity.
- `NUMERIC(24,2)` and `NUMERIC(12,6)` are exported as Arrow Decimal128, never
  Python floats. NULL remains NULL. Negative values are diagnostic counts and
  not blanket errors. Keep the original source fields and the source checksum.
- Parent dimensions such as project/country are current canonical attributes,
  not historical slowly changing dimensions. Do not use them as as-of facts
  without independent historical validation.

## Monthly structural eligibility, not labels

- Each credit has a set of observed reporting months. Multiple dates in one
  credit/month fail the gate: they would make month-level interpretation
  ambiguous. We **do not** forward-fill missing months.
- For an anchor month `t`, a structural horizon `h` (3, 6, 12) is counted
  only if every month `t+1..t+h` is available.
- `feature_mature_12m_windows` additionally requires each `t-11..t` month
  to be observed: this is a **12-month contiguous-history proxy**.
- These counts do **not** demonstrate that the future measurement constitutes
  a well-defined target, that the borrower has matured, or that a deployable
  prediction can be evaluated. Subsequent research must define outcomes and
  finalize data-release lag, sampling constraints, censoring and horizon-aware
  maturity policies.
- For an actual time split, a labeled training example may only be admitted
  if its **label end date has occurred by the training cutoff**. Use a
  horizon-aware purge/embargo and calibrate/evaluate on disjoint time blocks.
  Do not randomly split adjacent observations across train and test.
- Snapshot attributes may be updated after the reporting period; current
  canonical and warehouse state is **not** a point-in-time feature store.
  No zero-leakage claim is possible without as-of metadata/version history.

## Reproducibility and cross-layer gate

The runner enforces named DB and role, Day33 source ledger balances,
Day34 source/fact/mart cardinality, 13 financial fields with NULL-safe SQL
`IS DISTINCT FROM` parity, source record key and checksum parity, unique
observations, and a read-only repeatable-read transaction.

Logical hash is calculated over named fields, in stable credit/date/snapshot
ordering, distinguishing Decimal values from strings. A versioned directory
contains `credit_period.parquet`, `audit.json`, and `manifest.json` with file
byte hashes and row counts. Existing files are hash-checked and read back;
they are never overwritten automatically. This is **bounded reproducibility**
for a specific canonical snapshot, not proof of an unchanging external source.

## Outstanding work beyond Day 1

- Full-source streaming beyond the 10,000-row bounded gate.
- Proven point-in-time acquisition and historical as-of dimension/versioning.
- Feature/label definitions with leakage tests and independent holdouts.
- 3/6/12-month causal forecasting baselines and cross-horizon uncertainty
  estimation (planned for Day 4).
- Remote object-store/DVC/MLflow registration (planned for Day 5).
- Hadoop/Hive archive and scale benchmarking (planned for Day 6).
