\# FlowWatch — Data-Quality Rule Catalog



\*\*Milestone:\*\* Day 20 — Temporal Snapshot Semantics and Data-Quality Invariants

\*\*Status:\*\* Implemented and validated on a sampled source dataset

\*\*Authoritative implementation:\*\* `src/quality/rules.py`



\## 1. Purpose



This document defines the machine-readable quality rules applied to World Bank credit observations in FlowWatch.



The quality framework separates definitive source-validation failures from financial and temporal conditions that require further investigation.



The primary objective is to protect canonical data integrity without introducing unnecessary selection bias into subsequent financial forecasting and uncertainty-calibration experiments.



\## 2. Quality Policy



FlowWatch currently recognizes two rule severities.



\*\*REJECT\*\*



The observation violates a source-schema requirement or repeats an already accepted credit-period identity within the same inspection run.



A rejected observation retains the original record, the relevant quality-rule ID, and available source lineage.



\*\*WARNING\*\*



The observation passes source validation but contains a suspicious financial or chronological relationship.



The observation remains accepted. Warning metadata records the condition and the original source lineage.



A warning does not establish that the World Bank record is erroneous.



\## 3. Machine-Readable Rule Catalog



| Rule ID | Condition | Severity |

|---|---|---|

| DQ-SRC-001 | Source record is not a JSON object | REJECT |

| DQ-SRC-002 | Source field fails general schema validation | REJECT |

| DQ-ID-001 | Missing or invalid credit number | REJECT |

| DQ-ID-002 | Missing or invalid project ID | REJECT |

| DQ-ID-003 | Invalid required country or region identifier | REJECT |

| DQ-TEMP-001 | Missing or invalid reporting-period date | REJECT |

| DQ-TEMP-002 | Identical credit-period record repeats within an inspection run | REJECT |

| DQ-TEMP-003 | Conflicting source content repeats for the same credit-period identity | REJECT |

| DQ-DATE-001 | Invalid optional source date | REJECT |

| DQ-DATE-002 | Unexpected chronological relationship | WARNING |

| DQ-AMOUNT-001 | Invalid or non-finite financial numeric value | REJECT |

| DQ-AMOUNT-002 | Disbursed amount exceeds original principal | WARNING |

| DQ-CROSS-001 | Financial components differ from original principal | WARNING |

| DQ-SCHEMA-001 | Invalid integer-valued source field | REJECT |



Rule identifiers are defined in the `QualityRuleId` enumeration. Rule descriptions are maintained in `RULE\_CATALOG`.



Changes to identifier meanings must be treated as versioned data-contract changes.



\## 4. Temporal Identity Rules



The canonical temporal identity is:



`(credit\_number, end\_of\_period)`



The same credit may legitimately appear in multiple reporting periods.



Within one scanner instance:



\- The first valid observation for a credit-period identity is accepted.

\- A repeated identity with identical canonicalized raw JSON is rejected under `DQ-TEMP-002`.

\- A repeated identity with different canonicalized raw JSON is rejected under `DQ-TEMP-003`.



The rejection contains the original repeated payload and a reference to the first observation.



The first-observation policy applies only within the scanner's current run.



It is not a historical correction policy and does not guarantee durable deduplication across different runs.



\*\*Implementation:\*\* `src/quality/temporal.py`



\*\*Tests:\*\* `tests/quality/test\_temporal\_identity.py`



\## 5. Source Numeric Rules



The existing source parser uses Python `Decimal` for financial fields.



`DQ-AMOUNT-001` rejects invalid numeric representations, including non-finite values such as infinity.



Negative monetary values are not universally rejected.



The source may contain legitimate accounting adjustments, and the current sample is insufficient to establish a universal nonnegative constraint.



The existing PostgreSQL schema may independently enforce additional constraints on particular fields. Those constraints are separate from this quality-rule catalog.



\*\*Implementation:\*\* `src/validation/source\_record.py`



\*\*Tests:\*\* `tests/quality/test\_warning\_pipeline.py`



\## 6. Financial Warning Rules



\### DQ-AMOUNT-002 — Disbursement exceeds original principal



Condition:



`disbursed\_amount\_us\_ > original\_principal\_amount\_us\_`



Both values must be present.



\*\*Severity:\*\* WARNING



The rule reports the original and disbursed amounts.



It does not automatically reject the observation because exchange-rate effects, source corrections, or other accounting conventions have not yet been ruled out.



\### DQ-CROSS-001 — Financial component discrepancy



Diagnostic comparison:



`disbursed + undisbursed + cancelled - original\_principal`



All four values must be present.



A warning is generated when the absolute difference exceeds:



`0.01 USD`



This is an initial diagnostic tolerance, not an authoritative World Bank accounting rule.



The comparison should not be interpreted as a universally valid financial identity until verified against source documentation and representative historical data.



\*\*Implementation:\*\* `src/quality/invariants.py`



\*\*Tests:\*\* `tests/quality/test\_invariants.py`



\## 7. Date Rules



The existing source parser accepts the World Bank source date representation:



`DD-Mon-YYYY`



The reporting-period date is required.



Other recognized dates may be NULL.



Invalid date representations produce rejection rules.



The following chronological relationships are checked as non-blocking diagnostics:



| Earlier date | Later date |

|---|---|

| Board approval | Agreement signing |

| First repayment | Last repayment |

| Most recent effective date | Most recent closing date |



If both dates are present and the earlier date is later than the expected subsequent date, the engine emits `DQ-DATE-002`.



These checks are warnings because source corrections and special operational circumstances may require investigation.



\## 8. Rejection-Lineage Contract



A quality rejection retains:



\- Ingestion or inspection run ID

\- Page number

\- Page offset

\- Record index within the page

\- Absolute source-record offset

\- Source page checksum

\- Original raw record

\- Existing source-validation reasons

\- Day-20 quality-rule IDs

\- Rejection timestamp



Temporal duplicate rejections additionally reference the first observed identity.



The Day-20 live inspection uses an inspection-specific UUID. This identifier is not a persisted production ingestion-run record.



\## 9. Warning-Lineage Contract



A financial or date warning retains:



\- Quality-rule ID

\- Observed field values

\- Credit number

\- Reporting period

\- Run ID

\- Page number and offset

\- Record index and source-record offset

\- Source page checksum

\- Original raw record



A single accepted observation can generate multiple warning conditions.



Consequently, the number of warning conditions may exceed the number of records with warnings.



\## 10. Real World Bank Validation Evidence



\*\*Inspection method:\*\* Six non-adjacent API pages, with 100 records requested per page.



Offsets:



`0, 100, 500, 700, 2000, 5000`



\### Observed results



| Metric | Value |

|---|---:|

| Records inspected | 600 |

| Accepted | 600 |

| Rejected | 0 |

| Records with warnings | 4 |

| Total warning conditions | 7 |

| DQ-AMOUNT-002 | 3 |

| DQ-CROSS-001 | 4 |



\### Flagged credits



| Credit | Reporting period | Rules |

|---|---|---|

| IDA00060 | 2016-10-31 | DQ-AMOUNT-002, DQ-CROSS-001 |

| IDA00160 | 2016-10-31 | DQ-CROSS-001 |

| IDA00210 | 2016-10-31 | DQ-AMOUNT-002, DQ-CROSS-001 |

| IDA00610 | 2016-10-31 | DQ-AMOUNT-002, DQ-CROSS-001 |



All four records remain accepted.



The common reporting date warrants further investigation but does not establish a common cause.



\*\*Evidence:\*\* `reports/day20-live-quality-validation.json`



\## 11. Research-Validity Implications



Incorrect rejection of unusual financial observations can alter the training and evaluation population.



Potential consequences include:



\- Biased portfolio summaries

\- Distorted historical financial trajectories

\- Artificial temporal gaps

\- Changed forecasting targets and residuals

\- Misleading estimates of distribution shift

\- Invalid comparisons between independent-horizon and cross-horizon calibration methods



For FlowWatch's focused research, exclusion decisions must be traceable and reproducible.



Warning-based retention prevents unverified accounting assumptions from silently removing observations.



It does not guarantee that the underlying financial figures are correct.



\## 12. Reproducible Tests



Run:



```text

python -m pytest tests\\quality -v

```



Observed result:



\*\*29 passed\*\*



Additional quality checks:



```text

ruff check src\\quality tests\\quality

mypy src\\quality

```



Real-source inspection:



```text

python -m scripts.validate\_day20\_live\_quality

```



Evidence-producing scripts:



\- `scripts/inspect\_temporal\_source.py`

\- `scripts/profile\_day20\_quality.py`

\- `scripts/validate\_day20\_live\_quality.py`



Live-source requests require network access, and upstream changes may affect their results.



\## 13. Current Limitations



1\. Only 600 source observations across six credits were inspected in this Day-20 sample.

2\. Independent HTTP requests do not provide a guaranteed atomic upstream snapshot.

3\. Temporal duplicate detection currently uses in-memory state scoped to one run.

4\. The new quality engine has not yet replaced the existing production ingestion entry point.

5\. Financial warnings are not yet stored in a durable quality-event table.

6\. Quarantine persistence and remediation are scheduled for Day 25.

7\. Cross-run historical correction handling remains part of the Day-23 policy work.

8\. Financial comparison rules have not been certified against authoritative source accounting definitions.

9\. The inspection report provides source-page checksums and raw-record evidence, but does not by itself constitute an immutable archived source snapshot.



\## 14. Engineering Decision



The Day-20 quality framework uses strict validation for demonstrably invalid source representations and non-blocking warnings for uncertain financial relationships.



Every rejection receives a stable rule ID and retains available source lineage.



Every financial warning retains the source observation rather than silently removing it.



The implementation is verified through unit tests and a read-only live-source inspection. Production-path integration and durable event persistence remain separate future milestones.
