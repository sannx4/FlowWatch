\# FlowWatch — Day 19 Canonical Integrity and Transaction Report



**Milestone:** Day 19 — Canonical Constraints and Transactional Loaders

**Date:** 19 October 2026

**Branch:** `day19-canonical-transactions`

**Migration:** `f7b19a2c4d63`

**Status:** Core integrity and transaction proofs passed; historical upsert policy requires further hardening.



\---



\## 1. Objective



Day 19 strengthens the canonical PostgreSQL layer by enforcing relational integrity, complete source lineage, unique snapshot identity, and atomic batch loading.



The purpose is to prevent incomplete or inconsistent canonical records from silently contaminating later financial analysis and forecasting experiments.



\## 2. Canonical Entity Relationships



FlowWatch uses five normalized operational tables:



Region → Country → Project → Credit → CreditSnapshot



The database enforces:



\- Country must reference an existing region.

\- Project must reference an existing country.

\- Credit must reference an existing project.

\- CreditSnapshot must reference an existing credit.

\- Credit numbers must be unique.

\- The combination of credit ID and reporting period must be unique.



These rules were already defined in the initial operational migration and were verified against PostgreSQL during Day 19.



\## 3. Entity-Level Versus Temporal Attributes



Entity-level attributes describe the identities and relatively stable properties of regions, countries, projects, and credits.



| Entity | Identity | Current attributes |

|---|---|---|

| Region | region\_name | Region identity |

| Country | country\_code | Country name, region reference |

| Project | project\_id | Project name, country reference |

| Credit | credit\_number | Project, borrower, currency, approval and agreement dates |



Temporal attributes describe a credit's financial state at a particular reporting period.



The `credit\_snapshots` table stores:



\- Reporting period

\- Credit status

\- Original principal

\- Disbursed amount

\- Undisbursed amount

\- Cancelled amount

\- Repayment amounts

\- Outstanding obligations

\- Service charge rate

\- Other period-specific financial values

\- Source lineage



**Design decision:** Financial state and credit status belong to the temporal snapshot rather than being overwritten on the credit entity.



**Limitation:** Some currently entity-level source attributes may change or be corrected over time. Day 20 must investigate actual source variation before claiming historical stability.



\## 4. Transactional Batch Loader



Implementation:



`src/loaders/postgres.py`



Function:



`load\_curated\_batch()`



The batch loader uses SQLAlchemy's `engine.begin()` to establish one transaction covering the entire batch.



On successful completion, PostgreSQL commits all changes.



If transformation, iteration, database execution, or an injected operation raises an exception, the transaction rolls back.



The loader reuses the existing Day-16 record transformation and canonical entity-upsert implementation.



\## 5. Upsert Rules and Current Limitations



The existing record loader processes entities in dependency order:



Region → Country → Project → Credit → CreditSnapshot



Current conflict targets:



| Table | Conflict identity |

|---|---|

| Region | region\_name |

| Country | country\_code |

| Project | project\_id |

| Credit | credit\_number |

| CreditSnapshot | credit\_id + end\_of\_period |



Current behavior:



\- New identities are inserted.

\- Existing identities are reused.

\- Supplied non-key attributes are updated on conflict.

\- Snapshot conflicts can update both financial values and lineage fields.

\- The batch transaction makes these inserts and updates atomic.



This behavior is effectively last-write-wins according to the order of database operations.



\### Research-integrity limitation



An updated source record may overwrite the previously stored canonical value for the same reporting period.



Therefore, canonical snapshot uniqueness alone does not provide immutable historical versioning.



Before a dataset is used for a locked research experiment, the project must preserve its exact source and transformation versions.



\### Follow-up



Day 20 must validate historical attribute behavior against real source variation.



Day 23 must strengthen and test deterministic upsert and correction handling, including how conflicting source versions are accepted, rejected, or preserved.



\## 6. Source-Lineage Integrity



Migration:



`alembic/versions/f7b19a2c4d63\_snapshot\_lineage\_completeness.py`



Added constraint:



`ck\_credit\_snapshots\_lineage\_complete`



The constraint allows:



1\. Complete lineage with all three fields present.

2\. Legacy snapshots with all three lineage fields NULL.



It rejects:



\- Missing ingestion-run ID when other lineage fields exist.

\- Missing source checksum when other lineage fields exist.

\- Missing source-record key when other lineage fields exist.

\- Blank source-record keys.



\### Production preflight



Before migration:



\- Total canonical snapshots: 100

\- Complete lineage: 100

\- Incomplete lineage: 0



After migration:



\- Total canonical snapshots: 100

\- New lineage constraint: installed



No existing canonical snapshots were lost.



\### Limitation



The all-NULL exception permits new records without lineage as well as historical legacy records. It must not be interpreted as proof that every future record is traceable.



Future ingestion policy must require full lineage for newly accepted records.



\## 7. Relational Constraint Tests



Integration test:



`tests/integration/test\_day19\_canonical\_integrity.py`



Observed results:



\- Orphan project rejected: PASS

\- Orphan credit rejected: PASS

\- Orphan snapshot rejected: PASS

\- Duplicate snapshot identity rejected: PASS

\- Mid-batch failure caused complete rollback: PASS



Result: 5 passed.



The tests used a dedicated database:



`flowwatch\_day19\_test`



\## 8. Transaction Tests



Unit test:



`tests/unit/test\_postgres\_batch\_transactions.py`



Verified:



\- Successful batch commits all changes.

\- Mid-batch exception rolls back inserts.

\- Failed update does not modify previously committed data.



Result: 3 passed.



The PostgreSQL integration test additionally verified that an injected exception after actual canonical record loading left no partial batch changes.



\## 9. Lineage Constraint Tests



Integration test:



`tests/integration/test\_day19\_lineage\_constraint.py`



Observed results:



\- Missing source checksum rejected.

\- Missing ingestion-run ID rejected.

\- Blank source-record key rejected.

\- Complete lineage accepted.

\- All-NULL legacy lineage accepted.



Result: 5 passed.



\## 10. Migration Reversibility



Initial revision:



`c6d4f18a92b7`



Day-19 revision:



`f7b19a2c4d63`



Verified:



1\. Upgrade to Day-19 revision succeeded.

2\. Downgrade to the previous revision succeeded.

3\. Re-upgrade to Day-19 revision succeeded.

4\. Lineage tests passed after re-upgrade.



All migration reversibility checks were performed on the isolated test database before the main database was upgraded.



\## 11. Regression and Quality Results



Ruff: All checks passed.



mypy: No issues found in 25 source files.



Unit tests: 96 passed.



Standard regression suite: 101 passed, 15 skipped.



The opt-in Day-19 integration tests were executed separately.



\### Performance observation



Five PostgreSQL canonical-integrity tests required 131.22 seconds.



Five lineage constraint tests completed in approximately six seconds.



The canonical-integrity runtime is an investigation item. Correctness passing does not establish acceptable database performance.



\## 12. Research — Threats to Scientific Validity



\### Threat A — Orphan financial records



If projects, credits, or snapshots can reference nonexistent parent entities, observations may become incorrectly attributed to countries, regions, or projects.



This can distort geographical comparisons and portfolio composition.



\### Threat B — Duplicate temporal observations



Multiple canonical snapshots representing the same credit and reporting period may inflate observation counts.



This can distort time-series features, reporting frequencies, and model evaluation.



It may also cause researchers to treat repeated observations as independent data.



\### Threat C — Partial batch commits



A failed ingestion that leaves partially committed records could introduce artificial reporting gaps or apparent changes in portfolio composition.



These errors may later appear to be genuine temporal distribution shifts.



\### Threat D — Missing lineage



Without complete source identifiers, researchers cannot reliably reproduce the original observation from retained raw data.



This threatens the reproducibility of forecasting and calibration experiments.



\### Threat E — Historical overwrites



A source correction or rerun that changes an existing canonical snapshot may alter previously used experimental data.



Without immutable dataset versions, a future experiment could produce different results even when its model configuration has not changed.



\## 13. Relationship to FlowWatch Research



FlowWatch investigates maturity-aware cross-horizon conformal calibration for 3-, 6-, and 12-month forecasting.



The canonical integrity rules protect the observations from which temporal targets, historical features, and matured residuals will later be constructed.



These controls help prevent data-pipeline errors from being mistaken for economic changes or cross-horizon predictive relationships.



They provide research infrastructure and reproducibility safeguards.



They do not establish predictive or statistical novelty.



\## 14. Final Assessment



**Verified:**



\- Canonical foreign-key enforcement.

\- Unique credit-period snapshot identity.

\- Atomic transactional loading.

\- Complete rollback following injected failure.

\- Source-lineage completeness constraint.

\- Migration upgrade, downgrade, and re-upgrade.

\- Preservation of the existing 100 canonical snapshots.

\- Ruff, mypy, unit tests, and standard regression tests.



**Remaining work:**



\- Strengthen and test historical upsert conflict handling.

\- Investigate changing entity attributes using real temporal source data.

\- Investigate slow PostgreSQL integration execution.

\- Enforce mandatory lineage for all new records without relying on the legacy exception.



**Conclusion:** Day-19 relational integrity, transaction atomicity, and source-lineage checks have passed. Historical correction and conflict-update semantics remain an explicitly documented limitation requiring further implementation and verification.
