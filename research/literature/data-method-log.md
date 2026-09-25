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



