\# FlowWatch — Day 18 MongoDB Acceptance Report



\*\*Project:\*\* FlowWatch — Research-Grade Temporal Development-Finance Platform  

\*\*Milestone:\*\* Day 18 — Hot-Raw Retention Policy and MongoDB Usefulness Gate  

\*\*Verification date:\*\* 18 October 2026  

\*\*Acceptance status:\*\* PARTIAL — Verified core workflows; longitudinal source comparison pending



\---



\## 1. Objective



Day 18 evaluates MongoDB as FlowWatch's searchable recent raw-data store rather than a permanent archive.



The implementation must establish four guarantees:



1\. Raw source records cannot be authorized for deletion without independently verified archival evidence.

2\. PostgreSQL canonical observations remain traceable to their original MongoDB records.

3\. Retained raw records can be replayed into PostgreSQL without downloading the source again.

4\. MongoDB source records, collections, and indexes can be inspected to identify schema changes, data-quality risks, and unnecessary storage structures.



The permanent HDFS raw archive is planned for Day 94. Until that archive exists and is independently verified, raw deletion remains prohibited by the Day-18 retention policy.



\---



\## 2. MongoDB Environment and Source Identity



The MongoDB inspection successfully connected to the running database and retrieved real stored source records.



| Attribute | Verified value |

|---|---|

| Source dataset | `world\_bank\_ida\_statement\_of\_credits` |

| Source resource | `world\_bank\_sample\_day16` |

| Ingestion run | `f0e87dd0-001a-5447-bca9-27da56fa9575` |

| Stored runs in `raw\_records` | 1 |

| Raw records inspected | 100 |

| Distinct business identities | 100 |

| Duplicate business identities | 0 |

| Missing business identities | 0 |

| Duplicate source-record keys | 0 |



\*\*Finding:\*\* The selected 100-record sample contains no duplicate or missing business identities.



\*\*Limitation:\*\* Only one retained raw ingestion run is available. Cross-run source variation cannot yet be measured.



\---



\## 3. MongoDB Collection Inventory



The read-only MongoDB inspection identified five collections.



| Collection | Documents | Assessment |

|---|---:|---|

| `raw\_records` | 100 | Active raw-record lineage and replay storage |

| `raw\_pages` | 1 | Active raw-page storage |

| `ingestion\_runs` | 0 | Collection exists; run metadata persistence requires investigation |

| `day07\_raw\_records` | 100 | Legacy Day-7 collection; dependency review required |

| `day07\_raw\_payloads` | 1 | Legacy Day-7 collection; dependency review required |



\### Collection review decision



\*\*Retain:\*\* `raw\_records` and `raw\_pages` because the live trace, replay, and source-inspection workflows depend on retained raw information.



\*\*Investigate:\*\* `ingestion\_runs` because the collection contains no documents despite an existing completed sample run.



\*\*Defer removal:\*\* `day07\_raw\_records` and `day07\_raw\_payloads`. Their contents and dependencies must be reviewed before any deletion is considered.



No collections were deleted during Day 18.



\---



\## 4. MongoDB Index Audit



The inspection retrieved existing MongoDB indexes and examined representative query plans.



\### Raw-record indexes



\- `\_id\_`

\- `ix\_raw\_records\_run\_position`

\- `ix\_raw\_records\_source\_identity`

\- `ix\_raw\_records\_credit\_period`

\- `ux\_raw\_records\_run\_source\_key`



\### Raw-page indexes



\- `\_id\_`

\- `ix\_raw\_pages\_run\_page`

\- `ix\_raw\_pages\_source\_page`

\- `ix\_raw\_pages\_checksum`

\- `ux\_raw\_pages\_run\_source\_key`



\### Ingestion-run indexes



\- `\_id\_`

\- `ux\_ingestion\_runs\_run\_id`

\- `ix\_ingestion\_runs\_source\_started`



\### Query-plan verification



| Workload | Observed stages | Result |

|---|---|---|

| Raw-record lineage lookup | `FETCH,IXSCAN,LIMIT` | PASS |

| Raw-page lookup | `FETCH,IXSCAN,LIMIT` | PASS |



Both inspected lookups used an indexed execution plan rather than a collection scan.



\### TTL inspection



\*\*TTL indexes detected: 0\*\*



No automatic MongoDB TTL expiry was observed in the reported index inventory.



\### Index decision



The live evidence supports retaining the indexes involved in the tested lookups and protecting the unique indexes used for raw-data identity.



Other indexes require workload-specific review before a keep-or-remove decision.



No indexes were dropped during Day 18.



\---



\## 5. Workflow A — PostgreSQL-to-MongoDB Lineage



\*\*Status: PASS\*\*



Command executed:



`python -m scripts.trace\_lineage --credit-number "IDA00010" --end-of-period "2022-06-30"`



\### Verified observation



| Attribute | Value |

|---|---|

| Credit number | `IDA00010` |

| PostgreSQL snapshot ID | `1` |

| Canonical reporting period | `2022-06-30` |

| Original reporting period | `30-Jun-2022` |

| Country | Honduras |

| Project | Western Highway |

| Project ID | `P007335` |

| Ingestion run | `f0e87dd0-001a-5447-bca9-27da56fa9575` |



The PostgreSQL record reported:



\- `run\_id\_match = true`

\- `source\_checksum\_match = true`

\- `source\_record\_key\_match = true`



The overall lineage status was:



\*\*`MATCH`\*\*



\### Evidence



Source checksum:



`51a8ce3625d459d54beebf034f28b6aaddbc17dd6af66bde815ae10d227e4de0`



Source-record key:



`record:ef1f6c51f458cc7a9635482608dfc584740a5ef412b541f62975ad31ce162728`



\### Interpretation



The canonical PostgreSQL snapshot is traceable to its exact retained MongoDB source record.



The original reporting date is preserved in MongoDB while PostgreSQL contains its normalized representation.



This demonstrates that source normalization does not require discarding original source lineage.



\---



\## 6. Workflow B — Raw-to-Canonical Replay



\*\*Status: PASS\*\*



Command executed:



`python -m scripts.replay\_raw --latest-run --limit 5`



\### Observed result



| Measure | Value |

|---|---|

| Selected raw records | 5 |

| Replayed curated records | 5 |

| Ingestion run | `f0e87dd0-001a-5447-bca9-27da56fa9575` |

| Snapshot IDs | 1, 2, 3, 4, 5 |

| Source API contact | CLI reported `false` |



Repeated executions returned the same canonical snapshot identities.



The replay workflow uses retained raw envelopes and the existing canonical transformation and PostgreSQL loading logic.



\### Prior Day-17 destructive proof



The Day-17 integration test previously demonstrated:



1\. Selection of retained MongoDB records.

2\. Transactional deletion of selected PostgreSQL snapshots.

3\. Verification that the snapshots were absent.

4\. Reconstruction from stored MongoDB raw records.

5\. Preservation of ingestion-run IDs, checksums, and source-record keys.

6\. Idempotent behavior on a second replay.



\*\*Result:\*\* 1 passed in 10371.86 seconds.



\### Performance limitation



The destructive replay proof required approximately 2 hours and 53 minutes for five records.



Although correctness passed, this duration is operationally unacceptable and requires investigation.



This finding remains open.



\---



\## 7. Workflow C — Source-Drift Inspection



\*\*Status: PARTIAL — Single-run inspection verified; cross-run comparison unavailable\*\*



Command executed:



`python -m scripts.inspect\_mongo\_raw --limit 100`



\### Actual inspection status



`SINGLE\_RUN\_PROFILE\_ONLY`



\### Verified findings



\- 100 source records were examined.

\- 100 distinct business identities were found.

\- No duplicate business identities were detected.

\- No duplicate source-record keys were detected.

\- All sampled records contained `credit\_number`.

\- All sampled records contained `end\_of\_period`.

\- Source field-presence and data-type profiles were generated.



\### Data-quality observation



The `last\_disbursement\_date` field was present in all 100 records but contained `null` in all 100.



This demonstrates why field presence alone is insufficient to establish data completeness.



The sample also contains monetary values represented using different source data types, including integers, floating-point numbers, and strings across different fields.



Canonical transformation must continue to apply documented numerical parsing and precision rules.



\### Longitudinal comparison limitation



The MongoDB query for distinct stored ingestion-run IDs returned only:



`f0e87dd0-001a-5447-bca9-27da56fa9575`



A valid cross-run comparison requires at least two independently acquired, comparable source runs.



Therefore:



\- Single-run schema inspection: \*\*PASS\*\*

\- Source-profile generation: \*\*PASS\*\*

\- Source-drift comparison logic: \*\*UNIT TESTS PASS\*\*

\- Real longitudinal source-drift comparison: \*\*NOT VERIFIED\*\*



No artificial second acquisition is represented as a real World Bank source update.



\---



\## 8. Retention Safety Gate



\*\*Status: PASS — Application-level fail-closed policy\*\*



Command executed:



`python -m scripts.check\_raw\_retention --run-id f0e87dd0-001a-5447-bca9-27da56fa9575`



\### Actual result



\- `allowed = false`

\- `reason\_code = ARCHIVE\_MANIFEST\_MISSING`



The policy rejected the deletion request because no durable archive manifest exists.



Unit tests additionally verified rejection when a supplied manifest claimed archival verification.



\### Safety decision



No raw-deletion function was implemented during Day 18.



Deletion authorization is deliberately unavailable until the future HDFS archive verification process is implemented.



\### Enforcement limitation



This is an application-level authorization rule. It does not independently prevent a database administrator or another application with direct MongoDB deletion privileges from removing documents.



Database role restrictions and controlled destructive operations must be addressed before enabling any future raw cleanup.



\---



\## 9. Code Quality and Test Evidence



\### Ruff



Command:



`ruff check src tests scripts`



\*\*Result:\*\* All checks passed.



\### mypy



Command:



`mypy src\\ingestion src\\validation`



\*\*Result:\*\* Success — no issues found in 23 source files.



\### Day-18 unit tests



Command:



`python -m pytest tests\\unit\\test\_raw\_retention.py tests\\unit\\test\_mongo\_raw\_audit.py -q`



\*\*Result:\*\* 9 passed.



\### Full unit suite



Command:



`python -m pytest tests\\unit -q`



\*\*Result:\*\* 93 passed in 1.23 seconds.



\### Full regression suite



Command:



`python -m pytest -q`



\*\*Result:\*\* 98 passed, 5 skipped in 1.14 seconds.



\### Reproducible test references



\- `tests/unit/test\_raw\_retention.py`

\- `tests/unit/test\_mongo\_raw\_audit.py`

\- `tests/integration/test\_raw\_replay.py`

\- Existing Day-16 lineage integration tests



The expensive opt-in replay integration proof was not repeated as part of the Day-18 standard regression run.



\---



\## 10. Scientific Contribution and Validity Assessment



Day 18 establishes preservation controls for the raw observations underlying future development-finance forecasting and uncertainty-calibration experiments.



\### Threat 1 — Historical sample loss



Premature MongoDB deletion could remove observations before a durable historical archive exists.



The resulting data loss could alter:



\- Credit-level historical trajectories.

\- Reporting cadence and missingness patterns.

\- Valid forecast origins.

\- Availability of 3-, 6-, and 12-month targets.

\- The number and timing of matured forecast residuals.

\- Portfolio composition during apparent regime changes.



These changes could bias later empirical comparisons even when the forecasting and calibration algorithms remain unchanged.



\### Threat 2 — Source representation changes



Changes in field names, numerical types, date formats, or source values could alter canonical transformations.



Without versioned source lineage, a processing change could be mistaken for a genuine economic or portfolio shift.



\### Threat 3 — Incorrect cross-horizon conclusions



FlowWatch's central research question examines whether fresher short-horizon residual information improves long-horizon conformal calibration.



If raw history is incomplete or reconstructed inconsistently, the apparent dependence between short- and long-horizon errors could be distorted.



This could produce unsupported positive or negative findings about cross-horizon information transfer.



\### Reproducibility protection



Raw lineage and replay support the evidence chain:



Research result → Experiment → Dataset version → Canonical observation → Ingestion run → Original source record.



The retention policy protects the raw end of this chain until independently verified archival exists.



\*\*Scientific status:\*\* This is a research-integrity and reproducibility safeguard, not evidence that the proposed forecasting method improves predictive performance.



\---



\## 11. Outstanding Findings



| ID | Finding | Required follow-up |

|---|---|---|

| D18-01 | Only one retained raw ingestion run exists | Obtain a second independently acquired comparable run for longitudinal source inspection |

| D18-02 | `ingestion\_runs` contains zero documents | Investigate ingestion-run metadata persistence |

| D18-03 | Legacy Day-7 raw collections remain | Complete dependency and retention review before removal |

| D18-04 | Other indexes lack workload-specific acceptance evidence | Review actual query usage before deciding whether to remove them |

| D18-05 | Five-record destructive replay proof took approximately 2h53m | Investigate database, transaction, locking, and query performance |

| D18-06 | Retention enforcement is application-level | Establish restricted deletion privileges before destructive cleanup is introduced |

| D18-07 | No independently verified HDFS raw archive exists | Keep raw deletion disabled until the Day-94 archival gate |



\---



\## 12. Final Acceptance Decision



\*\*DAY 18: PARTIAL ACCEPTANCE\*\*



\### Verified



\- MongoDB collection inventory completed.

\- No TTL indexes detected.

\- Indexed raw lineage lookup confirmed.

\- Indexed raw-page lookup confirmed.

\- Real PostgreSQL-to-MongoDB lineage tracing succeeded.

\- Raw replay succeeded using five retained records.

\- Single-run source schema and quality inspection succeeded.

\- Retention logic denied deletion without an archive.

\- Fake archive-verification claims were rejected in unit tests.

\- Ruff, mypy, and regression tests passed.



\### Not yet verified



\- Actual longitudinal source-drift comparison across independent acquisition runs.

\- Complete usefulness justification for every retained secondary index.

\- Safe archival and authorized deletion.

\- Database-level enforcement against unauthorized raw deletion.



\### Engineering conclusion



MongoDB has demonstrated operational value for exact source lineage, raw-data replay, and source inspection.



The Day-18 fail-closed retention policy is functioning as designed.



However, the MongoDB usefulness gate remains partially open until longitudinal source comparison and remaining storage/index decisions are supported by actual evidence.



\*\*No raw data, collection, or index was deleted as part of Day 18.\*\*

