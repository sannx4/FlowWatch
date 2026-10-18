

\# FlowWatch — MongoDB Hot-Raw Retention Policy



\*\*Milestone:\*\* Day 18 — Hot-Raw Retention and MongoDB Usefulness Gate  

\*\*Status:\*\* Implemented — Raw deletion prohibited  

\*\*Archive milestone:\*\* Day 94 (HDFS)



\## 1. Purpose



MongoDB serves as FlowWatch's searchable recent raw-data and lineage store.



It preserves original World Bank source records, ingestion identifiers, source checksums, and retrieval metadata.



MongoDB is not intended to serve as the permanent historical archive. A durable HDFS-based raw archive is planned for Day 94.



Until that archive has been implemented and independently verified, raw data must not be deleted.



\## 2. Protected MongoDB Collections



\### raw\_records



Stores original source records together with:



\- Ingestion run ID

\- Source-record key

\- Original source payload

\- Source checksum

\- Record checksum

\- Page and record position

\- Retrieval timestamp

\- Dataset and resource identifiers

\- Parser version



Required for lineage tracing, raw replay, and source inspection.



\### raw\_pages



Stores original source pages and associated metadata.



Required for page-level integrity verification and future archival.



\### ingestion\_runs



Intended to store source acquisition and ingestion-run metadata.



\*\*Observed Day-18 status:\*\* The collection exists but currently contains zero documents.



Run-metadata persistence requires investigation.



\### Legacy Collections



The following collections were also observed:



\- `day07\_raw\_records`: 100 documents

\- `day07\_raw\_payloads`: 1 document



These are retained pending dependency and archival-safety review.



No collections will be deleted during Day 18.



\## 3. Raw Retention Policy



\### Rule R1 — No deletion without an archive



Raw MongoDB documents must remain available until a durable archive exists.



\### Rule R2 — Archive verification is mandatory



A manifest must be independently verified against actual archived objects.



A JSON field such as `archive\_verified=true` is not sufficient evidence.



\### Rule R3 — Integrity preservation



The archive must preserve:



\- Original source payloads

\- Source checksums

\- Record identifiers

\- Ingestion-run identifiers

\- Page identifiers

\- Source retrieval metadata



\### Rule R4 — Recovery verification



Before authorizing any future deletion, a selected canonical dataset must be successfully reconstructed from archived raw data.



\### Rule R5 — Fail-closed authorization



If an archive is missing, incomplete, corrupted, unverifiable, or unavailable, deletion must be denied.



\### Rule R6 — No automatic expiration



Protected raw collections must not be subject to automatic TTL-based deletion without a verified archive and an approved retention procedure.



\### Rule R7 — Auditable deletion



Future deletion operations must require explicit authorization, least-privilege database access, and recorded audit evidence.



\## 4. Day-18 Retention Implementation



Module:



`src/ingestion/raw\_retention.py`



CLI:



`scripts/check\_raw\_retention.py`



Verification command:



```text

python -m scripts.check\_raw\_retention --run-id f0e87dd0-001a-5447-bca9-27da56fa9575

```



Actual result:



```json

{

&#x20; "run\_id": "f0e87dd0-001a-5447-bca9-27da56fa9575",

&#x20; "allowed": false,

&#x20; "reason\_code": "ARCHIVE\_MANIFEST\_MISSING",

&#x20; "reason": "No durable archive manifest exists. MongoDB raw data must be retained until independently verified archival is implemented on Day 94."

}

```



\*\*Result: PASS\*\*



The implementation also rejects untrusted manifests that claim archival verification.



No destructive cleanup operation is provided.



This is currently an application-level safety gate. Database-level permission restrictions remain necessary to prevent direct deletion by other clients.



\## 5. MongoDB Index Review



Day-18 inspection command:



```text

python -m scripts.inspect\_mongo\_raw --limit 100

```



\### Verified Findings



\- Raw records inspected: 100

\- Distinct business identities: 100

\- Duplicate business identities: 0

\- Duplicate source-record keys: 0

\- TTL indexes: 0



\### Query-Plan Evidence



Raw-record lineage lookup:



`FETCH,IXSCAN,LIMIT`



Raw-page lookup:



`FETCH,IXSCAN,LIMIT`



Both inspected queries use indexed access.



\### Index Policy



Unique indexes supporting idempotency must be preserved.



Indexes supporting demonstrated lineage, replay, and inspection workloads should be retained.



Other indexes must be reviewed against actual query usage before removal.



No indexes were removed during Day 18.



\## 6. MongoDB Usefulness Gate



MongoDB must demonstrate three real workflows.



\### Workflow A — Lineage Tracing



Command:



```text

python -m scripts.trace\_lineage --credit-number "IDA00010" --end-of-period "2022-06-30"

```



Verified results:



\- PostgreSQL snapshot ID: 1

\- MongoDB raw record located

\- Ingestion run ID matched

\- Source checksum matched

\- Source-record key matched

\- Overall lineage status: MATCH



\*\*Status: PASS\*\*



\### Workflow B — Raw Replay



Command:



```text

python -m scripts.replay\_raw --latest-run --limit 5

```



Verified results:



\- Five MongoDB raw records selected

\- Five records replayed

\- PostgreSQL snapshot IDs: 1, 2, 3, 4, 5

\- Repeated replay preserved canonical identity

\- Replay CLI reported no World Bank API contact



\*\*Status: PASS\*\*



\### Workflow C — Source-Drift Inspection



Command:



```text

python -m scripts.inspect\_mongo\_raw --limit 100

```



Verified results:



\- Source-field profile generated

\- Source data types inspected

\- Field-presence statistics generated

\- Business identities checked

\- Duplicate source keys checked

\- MongoDB collections and indexes inventoried



\*\*Status: SINGLE\_RUN\_PROFILE\_ONLY\*\*



Only one independently stored ingestion run exists:



`f0e87dd0-001a-5447-bca9-27da56fa9575`



Therefore, actual longitudinal source-drift comparison has not yet been verified.



The cross-run comparison logic has unit-test coverage, but that is not equivalent to demonstrating real source drift across two acquisition runs.



\## 7. Research Integrity and Scientific Validity



FlowWatch investigates maturity-aware cross-horizon conformal calibration for multi-horizon development-finance forecasting.



Raw-data retention and reproducibility are important to the validity of those experiments.



\### Risk A — Historical observation loss



Premature deletion could remove historical observations and alter:



\- Temporal data coverage

\- Reporting cadence

\- Credit-level sample composition

\- Forecast-origin eligibility

\- Three-, six-, and twelve-month targets

\- Availability of matured forecast residuals



This could bias future model evaluation.



\### Risk B — Source-schema changes



Field-name, numeric-type, date-format, or missingness changes may alter canonical transformations.



Without source inspection, these changes could be confused with genuine temporal distribution shifts.



\### Risk C — Cross-horizon calibration bias



Incomplete historical observations could distort the relationships between matured short-horizon errors and later long-horizon errors.



This could affect the empirical conclusions of RQ1–RQ3.



\### Reproducibility Requirement



Every future research result must remain traceable through:



```text

Research result

&#x20;   |

&#x20;   v

Experiment

&#x20;   |

&#x20;   v

Dataset version

&#x20;   |

&#x20;   v

Canonical observation

&#x20;   |

&#x20;   v

Ingestion run

&#x20;   |

&#x20;   v

Original raw source record

```



\## 8. Reproducible Tests



Relevant tests:



\- `tests/unit/test\_raw\_retention.py`

\- `tests/unit/test\_mongo\_raw\_audit.py`

\- `tests/integration/test\_raw\_replay.py`



Day-18 verification results:



\- Day-18 unit tests: 9 passed

\- Full unit suite: 93 passed

\- Full test suite: 98 passed, 5 skipped

\- Ruff: Passed

\- mypy: Passed across 23 source files



\## 9. Outstanding Work



1\. Acquire a second independent source run for real longitudinal drift comparison.

2\. Investigate the empty `ingestion\_runs` collection.

3\. Review dependencies on legacy Day-7 collections.

4\. Establish workload evidence for remaining secondary indexes.

5\. Investigate the unusually slow Day-17 destructive replay test.

6\. Implement and verify HDFS archival on Day 94.

7\. Introduce database-level deletion permissions and audit controls before enabling any cleanup.



\## 10. Final Policy Decision



\*\*Raw deletion: PROHIBITED\*\*



MongoDB continues to serve as the searchable recent raw-lineage store.



The retention gate has been verified to deny deletion without a durable archive manifest.



Lineage tracing and raw replay have been verified against real stored records.



Single-run source inspection has been verified, but longitudinal source-drift comparison remains pending.



No raw records, collections, or indexes were deleted.



\*\*Day-18 acceptance status: PARTIAL — Core workflows verified; cross-run comparison pending.\*\*



