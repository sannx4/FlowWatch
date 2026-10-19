# Day 23 — Entity upsert and correction policy

## Natural keys and dependency order

1. `regions.region_name`: immutable natural key, insert or no-op.
2. `countries.country_code`: country_name and region_id are mutable Type-1 fields.
3. `projects.project_id`: project_name and country_id are mutable Type-1 fields.
4. `credits.credit_number`: borrower, currency, project_pk and currently modelled dates may be updated in the entity table. Historical variation in entity-level fields remains a risk to address in the warehouse/temporal design.
5. `credit_snapshots(credit_id, end_of_period)`: the unique temporal grain; never insert two logical observations for one credit and reporting period.

All data writes use PostgreSQL `INSERT ... ON CONFLICT` with existing database unique constraints; a `WHERE ... IS DISTINCT FROM` clause avoids unnecessary writes when values are identical. The caller controls transaction boundaries. One complete batch must execute in one transaction. `SourceIdentity` carries the immutable MongoDB raw envelope identity; it is never regenerated from transformed data.

## Corrected upstream financial observations

Policy is selected for **each batch**:

| Policy | Changed snapshot business values | Effect |
|---|---|---|
| `reject` (default) | Raises `SnapshotCorrectionRequired` | Fail closed; transaction must rollback. |
| `ignore` | Preserves stored snapshot and its provenance | Only if the original value is explicitly authoritative. |
| `update` | Replaces changed snapshot values and provenance | Requires externally verified source precedence and operator approval. |

Identical business values are always a no-op, even if a page checksum changes because of unrelated records. The initial lineage remains attached to the stored snapshot. A changed business record with the same source_record_key is an integrity error rather than an independently sourced correction.

**Version-precedence limitation:** The current snapshot schema does not encode a source retrieval-version ordering key. A historical replay must not use `update` indiscriminately: a stale version could overwrite a newer correction. Later work should persist explicit source-version or precedence metadata and correction history. The Day-23 integration gate exercises `update` only with an intentionally modified in-memory copy inside a transaction that is *rolled back*. That copy is not genuine World Bank data.

## Exact decimal contract

Day-22 `recover_exact_source_record()` obtains base-10 literals from SHA-256-verified stored JSON bytes. The canonical converter rejects binary floats. Day-23 also rejects amounts which cannot be stored exactly in PostgreSQL `NUMERIC(24,2)` or service charges outside `NUMERIC(12,6)` precision. Do not silently round a financial observation without a documented, versioned measurement contract.

## Research integrity threat and reproducibility

Failure modes:

- Missing conflict keys inflate credit counts and effective sample size, causing overly confident bootstrap intervals when rows are treated as unique credits.
- Replaying older corrections over newer snapshots rewrites historic disbursement trajectories; this contaminates training labels and 3/6/12-month residual alignment.
- Updating a snapshot on a retry with unchanged business values changes audit metadata unnecessarily, weakening reproducibility.
- Rounding before feature creation can introduce systematic disbursement-ratio errors and misleading interval miscoverage near thresholds.

Evidence:

- `tests/unit/test_day23_upsert_contract.py` tests schema keys and exact numeric bounds.
- `scripts/day23_idempotency_gate.py` runs three committed passes on five real, checksum-verified Mongo records **in an isolated local test database**, asserts identical entity counts and snapshot IDs, and tests reject/ignore/update correction modes in a rolled-back simulation.
- `sql/day23_entity_evidence.sql` independently checks counts, duplicates and nullable source lineage.
- `reports/day23-entity-upsert-evidence.json` is created from *actual* local integration-gate execution; it must not be filled with invented results.

Day-23 evidence is a bounded source sample, not full-run data quality or source-version reconciliation. Durable quarantine is Day 25, run-level reconciliation is Day 26, and the multi-page ETL gate is Day 28.
