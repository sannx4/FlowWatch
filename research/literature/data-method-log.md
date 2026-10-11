\# FlowWatch Data / Method Evidence Log



\## 2026-09-25 — Day 4: Operational Schema Design



\### Assumption



Repeated rows with the same `credit\_number` but different `end\_of\_period` values represent temporal states of one persistent credit rather than separate credit entities.



\### Observation



The schema therefore separates persistent entities into `regions`, `countries`, `projects`, and `credits`, while time-varying observations are stored in `credit\_snapshots`.



The development environment also demonstrated that live upstream API access cannot be assumed to be continuously available.



\### Nearest Related-Work Bucket



\* temporal data modeling;

\* point-in-time data systems;

\* reproducible ML data engineering;

\* source lineage and provenance.



\### Validity Threat



The initial 100-row sample is not sufficient to prove that every apparently static source attribute remains stable throughout the full historical dataset.



Fields described as “most recent” may change retrospectively. Incorrect classification could destroy historical state or create temporal leakage in later forecasting experiments.



\### Mitigation



Potentially unstable attributes are explicitly marked `DEFERRED`.



Wider non-adjacent historical samples will be profiled before the production schema is frozen.



Later ingestion stages will preserve raw source records, checksums, and ingestion-run lineage so results can be reproduced without depending entirely on live-source availability.



## Day 5 — Production Schema and Migration Lifecycle

### Assumption

The operational database schema must be reproducible from version-controlled migrations rather than from a developer's manually configured local database.

### Observation

The canonical schema is represented through SQLAlchemy metadata and applied through Alembic migrations to a containerized PostgreSQL instance with persistent storage and explicit health checks.

A fresh database can be upgraded to the current schema, downgraded one revision, and upgraded again without manual DDL.

### Nearest Related-Work Bucket

- reproducible data infrastructure;
- schema evolution;
- research data provenance;
- temporal database engineering.

### Validity Threat

A technically reproducible schema does not guarantee that the chosen business constraints correctly represent the full World Bank historical dataset.

Overly strict constraints could reject legitimate historical records, while overly permissive constraints could admit invalid records and bias later research datasets.

### Mitigation

Day 5 enforces structural invariants only where the semantics are sufficiently clear.

More domain-specific temporal and data-quality rules remain subject to later validation against wider historical source data.


## 2026-10-11 — Day 6: Raw-Store Infrastructure, CI and Correlated Logging

### Assumption

Reliable research infrastructure requires failures and processing events to be observable and traceable across components rather than inferred from terminal output after an experiment has completed.

### Observation

FlowWatch now has separate PostgreSQL and MongoDB services with explicit health checks and persistent storage.

A common structured JSON logging interface carries correlation metadata including `run_id`, `request_id`, component, status, and duration.

A minimal CI gate executes static checks and tests on proposed repository changes.

### Nearest Related-Work Bucket

- research reproducibility;
- data provenance and lineage;
- distributed-system observability;
- automated software quality gates.

### Validity Threat

Structured logging and CI provide evidence that declared checks execute, but they do not prove that all future pipeline failures will be detected or that lineage is complete.

Similarly, a healthy MongoDB process proves service readiness only; it does not establish that the future raw-data model preserves source semantics correctly.

### Mitigation

All later components will reuse the shared correlation fields rather than defining incompatible logging conventions.

MongoDB raw-document semantics, indexes, source envelopes, replay behavior, and lineage acceptance tests are deferred until the dedicated raw-lineage phase.

CI will be expanded incrementally as migrations, ingestion, integration testing, data contracts, and research-integrity checks are introduced.

## 2026-10-11 — Day 7: Real-data vertical slice and focused research charter

### Assumption

Research results are only defensible if canonical temporal observations
can be traced to the exact raw evidence from which they were produced.

The operational schema must also retain sufficient event-time
information to later construct forecast origins and horizon-specific
maturity logic.

### Observation

A fresh World Bank API request returned a source population count of
1,612,290 records.

The Day-7 experiment selected 100 real source records.

The selected records represented 100 reporting-period snapshots of one
credit (`IDA00010`), belonging to one project, one country and one
region.

The exact API-response bytes were preserved in MongoDB.

The 100 source records were also retained individually before
transformation.

A minimal deterministic transform populated the normalized PostgreSQL
operational schema.

Observed counts were:

- regions: 1
- countries: 1
- projects: 1
- credits: 1
- credit_snapshots: 100
- Mongo raw records: 100
- Mongo raw payloads: 1

One PostgreSQL snapshot was successfully traced to the matching MongoDB
source record through `ingestion_run_id`, `source_record_key`, and
`source_checksum`.

The PostgreSQL and MongoDB record checksums matched.

The MongoDB whole-response bytes also reproduced the expected source
SHA-256 checksum.

`credit_snapshots.end_of_period` was sufficient to construct candidate
3-, 6- and 12-month target dates.

### Scientific Relevance

The result establishes the minimum temporal and provenance foundation
required for later conformal experiments.

It does not establish research novelty.

The focused research hypothesis remains whether already-matured
short-horizon residuals contain useful information about unresolved
longer-horizon calibration errors.

### Nearest Related-Work Buckets

- adaptive conformal prediction under shift;
- change-point conformal adaptation;
- online conformal prediction;
- multi-horizon calibration;
- non-exchangeable panel data;
- delayed or incomplete feedback;
- label-unavailable calibration;
- coverage-efficiency optimization.

### Validity Threats

The 100-row sample contains only one credit, project, country and
region.

It therefore cannot establish:

- cross-credit generality;
- cross-country behaviour;
- realistic null-pattern diversity;
- full schema stability;
- cross-horizon residual dependence;
- distribution-shift behaviour.

Calendar addition to `end_of_period` only produces candidate target
dates. It does not yet define the correct observed-snapshot lookup rule.

For example, adding three months to 30-Apr produces 30-Jul even though a
monthly reporting series may contain 31-Jul.

Actual maturity and label availability therefore require a dedicated
policy.

The Day-7 implementation also performs sequential database operations
and required approximately 130.9 seconds for 100 records.

This is correctness evidence, not production throughput evidence.

### Mitigation

Later ingestion work will validate the source across broader pages and
the complete history.

The production ingestion-run and raw-envelope models will replace the
minimal Day-7 scaffolding.

The research-data phase will explicitly implement:

- forecast origin;
- target lookup;
- reporting-gap handling;
- matures_at;
- label_available_at;
- evidence eligibility.

A later focused literature gate will attempt to falsify the provisional
cross-horizon gap before MACH-CP development.

No paper-level claim will be based on the Week-1 sample alone.


That scope is consistent with the roadmap: Day 8 is specifically the hardened client, while pagination, run tracking, checksums, validation/quarantine, and broader failure injection are deliberately assigned to later days. :chatgpt-content-reference{index="1"}

After the smoke test and the two explicit fault tests, send me their output. Then we’ll do the final Day-8 Git/PR gate.
