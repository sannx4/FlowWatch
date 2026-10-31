# Days 26–28: reconciliation, CI, multi-page release method

## Scientific and engineering boundary

The innovation under investigation in FlowWatch is *not* ETL. Data plumbing is a
measurement instrument for later maturity-aware cross-horizon calibration.
**If ingestion silently loses or duplicates financial observations, the residual
sample, reporting-gap distribution, effective number of independent credits,
and eventual calibration coverage become biased.**

## Day26: independently grounded accounting

Three separately observed sets participate in each reconciliation:

1. Source manifest keys: the actual record slots enumerated from checksum-
   identified page source data (`manifest_keys`).
2. Raw keys: persisted Mongo `raw_records` queried after landing, not inferred
   from the source file or from an earlier counter (`raw_keys`).
3. Decision keys: durable PostgreSQL `etl_record_decisions`, keyed by `(run_id,
   attempt_no, source_record_key)`, each linking to an accepted canonical
   snapshot or a quarantined rejected source identity.

For each attempt `fetched == raw_stored == accepted + rejected` and
`accepted == inserted + updated + unchanged + ignored`. Critically, set
identity comparison precedes all count checks. A substitute raw key cannot
pass merely because the totals match. A missing decision causes the
PostgreSQL transaction to abort. Both PostgreSQL `CHECK` and FK constraints
backstop the Python gate.

The decision outcomes describe *this attempt*, not lifetime records. Prior
attempts remain immutable after subsequent replay. Quarantine status changes
across attempts; the source input does not.

## Day27: isolated CI contract

The workflow runs **three separate jobs**: fast lint/unit, PostgreSQL migration
upgrade/downgrade/re-upgrade with an intentionally invalid revision, and the
PostgreSQL+MongoDB integration gate. The broken revision is created only inside
a disposable temporary script tree. It must fail; its preceding CREATE TABLE
must roll back; the head must remain the expected Day26 revision.

CI contains **only ephemeral credentials**. No production secrets, database,
external API access, or modifying the user's existing MongoDB collections.
The actual workflows must run green on GitHub before declaring Day27 complete.

## Day28: source fidelity and ten-page distinction

With `--source-file` (default), 100 real World Bank observations are partitioned
into **ten logical windows**, each referencing the **same checksum-verified
original JSON page bytes**. Every window has a unique `page_number` and subset
of original `record_index` values. This tests bounded multi-page processing
and replay, but is **not evidence of ten actual upstream API pages**. Neither
values nor reporting dates are synthesized.

With `--pages-dir`, the gate instead consumes sorted, independently retained
JSON page files (minimum ten), recording each one's own SHA-256 checksum and
source index. This mode is required for a strict externally acquired
multi-page claim, using `--require-true-pages`.

Raw pages and record envelopes are stored only in `flowwatch_day28_gate_raw`;
canonical data, quarantine events and reconciliation ledgers are stored only
in `flowwatch_day28_gate`. A single known legacy BSON float incompatibility is
selected as an *injected parser-version test*, **not** labeled corrupt source.
All remaining records are rehydrated exactly from raw page bytes.

The three attempts (each committed separately) are:

- Attempt 1: `N−1` inserted, `1` rejected, `0` silently lost.
- Attempt 2: `1` newly inserted after offline remediation; `N−1` unchanged;
  quarantine state becomes RESOLVED with retry count 1.
- Attempt 3: `0` inserted, `N` unchanged, stable temporal identities.

Negative control: remove one decision inside a database savepoint and demand
`ReconciliationError`. The savepoint is rolled back so the test never changes
stored acceptance evidence. Published rows preserve exact source keys,
checksums, run IDs and decimal precision.

## Reproduction references

- `tests/unit/test_day26_reconcile.py`: missing/duplicate/source-key mismatch.
- `tests/unit/test_day28_offline_pages.py`: page windows, source hash and
  deterministic run identity.
- `tests/integration/test_day28_etl_gate.py`: independent SQL+Mongo assertions.
- `.github/workflows/etl-days26-28.yml`: separate jobs and injected failure.
- `scripts/day27_migration_failure_probe.py`: copied bad revision and rollback.
- `reports/day28-etl-gate.json`: machine-readable evidence on success.
- `reports/etl-gate.md`: generated human report with measured counts.

## Limitations and future gates

- Single-writer integration; concurrent ingestion update ordering is open.
- Original 100 records represent one credit; no inference about full-data
  independent-credit sample size or research feasibility.
- Ten logical windows of one page do not prove ten independently paginated API
  responses. This limitation is shown in the generated report.
- Source precedence for changed upstream observations remains an explicit
  policy; these tests exercise immutable replay and valid parser remediation.
- Day28 uses a dedicated raw-landing gate path to avoid modifying the existing
  ingestion entrypoints before a reviewed cutover. Production Airflow wiring
  and full historical backfill remain later roadmap milestones.
