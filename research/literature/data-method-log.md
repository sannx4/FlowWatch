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

## 2026-10-11 — Day 9: Explicit top/skip pagination contract

### Assumption

Complete temporal extraction requires deterministic traversal of the
source result set.

A pagination defect can silently duplicate or omit source observations,
which would change the effective temporal history used by later
forecasting and uncertainty-calibration experiments.

Pagination therefore belongs to the research data-integrity boundary,
not merely to convenience code.

### Observation

World Bank source pagination was moved into a reusable iterator built
on top of the hardened Day-8 HTTP client.

The paginator exposes, for every yielded page:

- page number;
- source offset;
- returned record count;
- source-reported total count;
- raw page bytes;
- request ID;
- HTTP status;
- attempts consumed;
- request duration;
- request URL;
- requested top;
- requested skip.

Pagination follows the deterministic local rule:

```text
page 1 -> skip = start_skip
page 2 -> skip = start_skip + page_size
page 3 -> skip = start_skip + 2 * page_size

## Day 10 — Ingestion run lifecycle and resume lineage

### Assumption

A reproducible ingestion pipeline requires a persistent execution identity for every
source-acquisition attempt.

Without run-level metadata, a failed fetch may be visible in application logs but
cannot be reliably connected to the source resource, code version, progress reached,
or a later recovery attempt.

### Observation

Introduced a persistent `ingestion_runs` model containing:

- `run_id`
- source dataset and resource identifiers
- `started_at`
- `completed_at`
- lifecycle `status`
- completed `pages`
- ingested `rows`
- `page_size`
- `code_version`
- `failure_reason`
- `resumed_from_run_id`
- `resume_from_page`
- `resume_from_offset`

The lifecycle is:

`RUNNING -> SUCCEEDED`

or:

`RUNNING -> FAILED`

A failed run is preserved as terminal historical evidence rather than being rewritten.

A resumed attempt creates a new ingestion run and points back to the failed run through
`resumed_from_run_id`.

PostgreSQL proof showed that a failed run remained queryable from a new database
session after the original session closed.

For a failed run that completed two pages at a page size of 100, the resumed run
recorded:

- `resume_from_page = 3`
- `resume_from_offset = 200`

This preserves the execution lineage between the failed attempt and the new attempt.

### Nearest related-work bucket

- reproducible data acquisition
- execution provenance
- ingestion observability
- failure recovery
- workflow lineage

### Validity threat

The Day 10 resume coordinates represent run-level progress metadata only.

They do not yet prove that every page counted as completed was durably persisted into
raw storage before the progress counter advanced.

A process failure between source retrieval and durable raw persistence could therefore
make the run-level boundary insufficient for exact crash recovery.

The stored `code_version` is also supplied by the caller and must remain tied to the
actual executed revision.

### Mitigation / follow-up

Day 11 adds checksums and manifests to strengthen source identity and reproducibility.

Later raw-storage work will preserve source payloads independently of operational
tables.

Day 31 will introduce durable checkpoint semantics where progress is advanced only
after the corresponding raw data has been successfully persisted.

Therefore, the Day 10 mechanism should be described as run-level resume lineage, not
as a durable crash-recovery checkpoint.

## Day 11 — Raw page manifests and byte-level checksums

### Assumption

Reproducible source acquisition requires an integrity identity for every fetched page
before business transformation changes its representation.

An ingestion run identifier alone establishes execution identity but does not establish
whether two source pages contained exactly the same bytes.

Therefore each source page needs a deterministic content digest tied to its run/page
metadata.

### Observation

FlowWatch now computes SHA-256 over the exact raw HTTP response bytes preserved by the
source client.

The checksum is calculated before downstream business transformation.

Each fetched page can be represented by a `raw_page_manifests` row containing:

- ingestion run ID;
- page number;
- source offset;
- requested page size;
- record count;
- source total count;
- payload size in bytes;
- SHA-256 digest;
- request ID;
- source URL;
- HTTP status;
- request attempt count;
- manifest timestamp.

The page-manifest service persists and commits this metadata before releasing a page
through its manifesting iterator.

Controlled tests showed that identical byte payloads produce identical SHA-256 digests.

A byte-level modification produces a different digest and fails manifest verification.

The live proof additionally re-downloads the same World Bank page twice and compares
the resulting raw-byte checksums when the source content is unchanged.

### Nearest related-work bucket

- data provenance
- reproducible data acquisition
- content-addressed data identity
- integrity verification
- raw-data lineage
- immutable-source manifests

### Validity threat

SHA-256 establishes byte-level identity, not semantic equivalence or source
authenticity.

Two JSON responses containing semantically equivalent values may produce different
checksums if whitespace, ordering or serialization changes.

Conversely, possession of a valid checksum does not prove that the World Bank was the
party that produced the bytes.

The Day 11 manifest also does not yet mean that the corresponding raw payload is
durably retained. A manifest could exist while the in-memory/raw response bytes have
not yet reached durable raw storage.

Therefore the manifest must not be interpreted as a durable crash/resume checkpoint.

### Mitigation / follow-up

The checksum definition is intentionally documented as SHA-256 of exact response bytes
rather than canonicalized JSON.

Later raw landing will store the unchanged payload together with this checksum and run
lineage.

Idempotent raw landing will use deterministic source identity and checksum evidence.

Durable checkpoint advancement will occur only after the corresponding raw page has
been successfully persisted.

Archive manifests will later verify that retained historical raw artifacts still match
their original checksums.

## Day 12 — Source-schema validation and rejected-record quarantine

### Assumption

Source parsing must be separated from business transformation so that malformed source
representations cannot silently change the canonical dataset.

A malformed date or numeric value should therefore produce explicit evidence of
rejection while allowing other valid records in the same page to continue through the
pipeline.

### Observation

FlowWatch now has a Pydantic-based source-record parser representing the currently
observed World Bank credit-record shape.

The parser explicitly handles the observed `DD-Mon-YYYY` date representation, native
JSON numeric values, numeric strings, and legitimate null values.

Financial values are represented as `Decimal` after parsing rather than binary floating
point.

Validation does not create canonical Region, Country, Project, Credit or Snapshot
objects. It only establishes whether a source record satisfies the current source
parsing contract.

Invalid records are converted into rejected-record envelopes containing page/run
lineage, the original raw record, the source page checksum, the source position and
machine-readable reason codes.

Controlled fixtures demonstrated that:

- a valid source-shaped record is accepted;
- an impossible date is rejected with `invalid_date`;
- malformed numeric text is rejected with `invalid_numeric`;
- rejected records retain their original payload;
- valid records in the same page continue processing rather than the entire page
  crashing.

### Nearest related-work bucket

- schema-on-read validation
- data contracts
- defensive data ingestion
- rejected-record quarantine / dead-letter handling
- reproducible preprocessing
- data-quality provenance

### Validity threat

The current parser is derived from the source representations observed so far and may
not capture all legitimate historical World Bank variations.

A strict parser can therefore create false rejections if older pages contain previously
unseen but valid date, numeric, nullability or field representations.

Conversely, allowing additive fields means an upstream field addition is preserved but
does not automatically imply that its semantics are understood.

A rejection reason is therefore evidence that a record violates the current parser,
not proof that the upstream observation itself is semantically invalid.

### Mitigation / follow-up

Rejected records preserve their exact raw values and lineage so parser decisions can be
audited and replayed.

Later source-variation analysis will test non-adjacent and larger pages before the
source contract is treated as stable.

Business-level quality rules remain separate from source-type parsing.

Persistent quarantine and remediation state will later allow corrected parsers to
reprocess rejected records without re-fetching the source.


## Day 13 — Failure injection and fail-closed ingestion policy

### Assumption

A reproducible research data platform must make failure semantics explicit rather than
assuming that successful-path unit tests imply reliable ingestion.

Transient transport failures, malformed source responses, invalid records, duplicate
source pages and persistence failures represent different failure classes and therefore
must not all receive the same recovery policy.

The intended policy is:

```text
transient transport fault -> bounded retry
record-level schema fault -> quarantine
invalid response / duplicate / persistence failure -> fail closed

## Day 14 — Ingestion CI gate

### Assumption

Source-ingestion reliability properties are not durable engineering evidence
unless they are re-executed automatically in a clean environment after code
changes.

Local developer tests alone may hide undeclared dependencies,
environment-specific behavior or regressions.

### Observation

FlowWatch now applies automated static and behavioral verification to the
Week-2 ingestion boundary.

Ruff checks code quality.

Mypy checks the ingestion and validation modules.

The ingestion/source-client and fault suites run with coverage reporting.

The complete pytest suite remains an independent regression gate.

Local Day-14 evidence currently consists of:

```text
72 unit/fault tests passed
72 full-suite tests passed
83% ingestion + validation coverage
mypy clean across 13 source files
