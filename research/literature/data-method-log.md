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
