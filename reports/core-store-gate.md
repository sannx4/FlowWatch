\# FlowWatch — Core Store Release Gate



\*\*Milestone:\*\* Day 21 — Roles, Least Privilege and Core Gate

\*\*Date:\*\* 2026-10-19

\*\*Release candidate:\*\* v0.1-core

\*\*Gate status:\*\* PARTIAL PASS — release pending outstanding controls



\## 1. Objective



Verify that FlowWatch enforces PostgreSQL least-privilege boundaries, supports committed ingestion from existing MongoDB raw records, preserves source lineage, and prevents duplicate canonical snapshots during repeated ingestion.



\## 2. PostgreSQL Security



Five database roles exist:



| Role | Responsibility |

|---|---|

| flowwatch\_owner | Existing administrative account |

| flowwatch\_schema\_owner | Non-login application object owner |

| flowwatch\_migrator | Authorized migration execution |

| flowwatch\_ingestor | Restricted canonical ingestion |

| flowwatch\_api | Read-only canonical access |



\### Verified privilege boundaries



\- Migration role successfully created and altered a temporary test table.

\- Ingestion role successfully accessed canonical data.

\- Ingestion role could not create or alter schema objects.

\- API role successfully read canonical snapshots.

\- API role could not INSERT, UPDATE, or DELETE canonical data.

\- Independent ingestion and API authentication succeeded.

\- Privilege tests completed in a rolled-back transaction.



\*\*Evidence:\*\* `tests/integration/day21\_role\_privileges.sql`



\*\*Configuration:\*\* `sql/security/roles.sql`



\## 3. Reversible Integration Test



The Day-21 dry-run verification selected five existing MongoDB raw records and replayed them into PostgreSQL using `flowwatch\_ingestor`.



| Metric | Result |

|---|---:|

| Raw records selected | 5 |

| Accepted | 5 |

| Rejected | 0 |

| Canonical snapshots before | 100 |

| Canonical snapshots after first uncommitted replay | 100 |

| Canonical snapshots after second uncommitted replay | 100 |

| Duplicate rows added | 0 |

| Canonical snapshots after rollback | 100 |



The dry run confirmed restricted-role loading, source-lineage matching, and replay stability without persisting changes.



\*\*Evidence:\*\* `reports/day21-core-gate-dry-run.json`



\## 4. Committed Ingestion Test



A separate PostgreSQL database, `flowwatch\_day21\_gate`, was created for integration testing.



Its snapshot table was reset before the committed ingestion experiment.



Five previously stored World Bank records were selected from MongoDB and processed using the Day-20 quality-validation framework.



Source ingestion run:



`f0e87dd0-001a-5447-bca9-27da56fa9575`



\### Results



| Metric | Result |

|---|---:|

| Raw records selected | 5 |

| Accepted | 5 |

| Rejected | 0 |

| Warning conditions | 0 |

| Snapshots before first commit | 0 |

| Snapshots after first commit | 5 |

| Snapshots after second commit | 5 |

| Duplicates introduced by rerun | 0 |

| Distinct temporal identities | 5 |



The ingestion executed using `flowwatch\_ingestor`.



Both ingestion transactions committed successfully.



The second execution preserved the existing five logical snapshot identities without creating duplicate canonical records.



The original `flowwatch` database retained its 100 snapshots.



\*\*Evidence:\*\* `reports/day21-core-gate-committed.json`



\## 5. Reconciliation



For the selected five-record sample:



\*\*Input records = Accepted records + Rejected records\*\*



`5 = 5 + 0`



All five accepted records were successfully loaded into the isolated canonical database.



The sample therefore achieved complete record accounting.



This does not prove full-dataset reconciliation or durable quarantine of rejected records.



\## 6. Research-Integrity Assessment



FlowWatch's future forecasting experiments depend on preserving historical credit observations and their source lineage.



\### Risk: Duplicate snapshots



Repeated canonical observations could distort disbursement trajectories, temporal aggregates, and effective sample sizes.



\*\*Control:\*\* PostgreSQL temporal uniqueness constraints and duplicate-free ingestion rerun.



\*\*Evidence:\*\* Day-21 committed ingestion test.



\### Risk: Unauthorized canonical mutation



A compromised read-only service could alter financial histories, affecting research features and future forecast targets.



\*\*Control:\*\* Dedicated read-only PostgreSQL role and negative privilege tests.



\*\*Evidence:\*\* Day-21 PostgreSQL permission tests.



\### Risk: Missing observations



Unaccounted source records could introduce selection bias and artificial reporting gaps.



\*\*Control:\*\* Explicit input, accepted, and rejected counts.



\*\*Evidence:\*\* Five-record accounting check.



\*\*Limitation:\*\* Durable rejection storage and full-run reconciliation remain outstanding.



\### Risk: Incorrect source lineage



If canonical observations cannot be traced to their original source records, experiments cannot reliably reproduce historical financial inputs.



\*\*Control:\*\* Deterministic source-record keys, source checksums, and canonical lineage verification.



\*\*Evidence:\*\* Day-21 dry-run and committed integration checks.



\## 7. Outstanding Requirements



The following controls remain incomplete:



1\. Integrate the restricted PostgreSQL ingestion credentials into the standard production execution path.

2\. Demonstrate processing and durable accounting of rejected records.

3\. Persist quarantine records through the planned remediation workflow.

4\. Reconcile larger source batches and independent source runs.

5\. Complete the final regression and repository checks.



The current results establish a successful five-record core-store integration test, not full production readiness.



\## 8. Release Decision



\*\*Status: CONDITIONAL — DO NOT TAG YET\*\*



The following capabilities have passed:



\- PostgreSQL role separation.

\- Positive and negative database privilege tests.

\- Independent service-role authentication.

\- Restricted-role ingestion.

\- Committed canonical loading.

\- Duplicate-free rerun.

\- Source-lineage verification.

\- Complete accounting for the five-record valid sample.



The `v0.1-core` tag should be created only after the remaining required controls are either demonstrated or explicitly resolved through an approved release-scope decision.
