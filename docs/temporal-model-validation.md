\# FlowWatch — Temporal Model Validation



\*\*Milestone:\*\* Day 20 — Temporal Snapshot Semantics and Data-Quality Invariants



\*\*Data source:\*\* World Bank credit-finance dataset



\*\*Dataset ID:\*\* `DS00976`



\*\*Resource ID:\*\* `RS00906`



\*\*Status:\*\* Temporal design supported by sampled real-source evidence; full historical validity remains subject to further testing.



\---



\## 1. Objective



FlowWatch must preserve how financial observations change over time.



A credit may appear repeatedly in the World Bank dataset with different reporting periods, credit statuses, financial amounts, and descriptive attributes.



The purpose of Day 20 is to determine:



1\. What uniquely identifies a financial snapshot.

2\. Which attributes are historical and which describe current entities.

3\. Whether real source data supports these modeling decisions.

4\. Which data-quality conditions should cause rejection.

5\. Which financial anomalies should generate warnings.

6\. How these decisions affect reproducibility and later forecasting research.



The implementation must avoid silently discarding historical observations or introducing information from later periods into earlier analysis.



\## 2. Source Inspection Method



A read-only inspection queried six non-adjacent World Bank API pages.



| Page | Offset | Requested records |

|---|---:|---:|

| 1 | 0 | 100 |

| 2 | 100 | 100 |

| 3 | 500 | 100 |

| 4 | 700 | 100 |

| 5 | 2,000 | 100 |

| 6 | 5,000 | 100 |



Total records inspected: \*\*600\*\*



Evidence artifact:



`reports/day20-temporal-source-inspection.json`



Implementation:



`scripts/inspect\_temporal\_source.py`



The report records source request references, page offsets, checksums, and observed attribute variation.



\### Sampling limitations



The sample does not represent a complete scan of the source.



The six independent HTTP requests are not guaranteed to represent one atomic upstream data version.



Consequently, findings describe the observations returned during the inspection rather than the complete historical World Bank dataset.



\## 3. Canonical Temporal Identity



The canonical snapshot identity is:



`(credit\_number, end\_of\_period)`



A credit can legitimately have multiple snapshots if their reporting periods differ.



Two observations with the same credit number and reporting period represent the same logical temporal identity under the current canonical model.



\### Observed source results



| Measurement | Result |

|---|---:|

| Records inspected | 600 |

| Distinct credit numbers | 6 |

| Distinct credit-period identities | 600 |

| Repeated credit-period identities | 0 |

| Conflicting repeated identities | 0 |



All 600 sampled records had distinct credit-period identities.



This supports using the credit-period pair as the canonical snapshot key for the inspected records.



It does not prove uniqueness across the entire source.



\### Database enforcement



PostgreSQL stores the snapshot identity using the relationship:



`credit\_snapshots.credit\_id → credits.credit\_id`



The unique constraint applies to:



`(credit\_id, end\_of\_period)`



The application-level temporal scanner uses:



`(credit\_number, end\_of\_period)`



These represent the same logical identity when each credit number uniquely identifies one canonical credit.



\### Duplicate policy



The Day-20 temporal scanner distinguishes:



\- Identical repeated identities.

\- Repeated identities containing conflicting source content.

\- Legitimate observations from different periods.



The current policy accepts the first valid observation within one scanner run and rejects later occurrences of the same identity.



A duplicate rejection preserves the repeated raw record, source lineage, quality-rule ID, and reference to the first observation.



The scanner operates in memory and is scoped to one run.



Cross-run source corrections and durable historical versions require a separate policy.



\## 4. Real Temporal Variation



\### 4.1 Credit status



The sampled records contain \*\*five credits with multiple observed credit-status values\*\*.



Examples include:



| Credit | Observed status values |

|---|---|

| IDA00010 | Repaid, Fully Repaid |

| IDA00160 | Repaid, Fully Repaid |

| IDA00210 | Repaying, Repaid, Fully Repaid |



The evidence establishes that one credit can be associated with multiple status values across its observed reporting records.



It does not, by itself, establish the chronological direction of each transition because the summary reports sets of observed values.



\### Design decision



\*\*Store `credit\_status` in `credit\_snapshots`.\*\*



Do not maintain only a latest-status field and use that value to reconstruct historical credit states.



A latest-only implementation could incorrectly assign a future status to an earlier reporting period.



That would threaten point-in-time correctness during forecasting.



\### 4.2 Borrower information



Two sampled credits contain more than one borrower name.



Examples:



\*\*IDA00160\*\*



\- MINISTRY OF ECONOMIC AFFAIRS

\- Ministry of Finance and Economic Affairs



\*\*IDA01470\*\*



\- Ministre de l'Economie, des Finances et

\- Ministre des Finances du Budget et de la



These differences could represent organizational changes, source corrections, or naming differences.



They do not yet establish that the borrower should be modeled as a historical dimension.



\### Design decision



Retain the existing canonical entity mapping while treating changing borrower names as an unresolved historical-attribute question.



Do not introduce a Type-2 history table without evidence that separate historical versions have a meaningful interpretation.



For research features that depend on borrower identity, historical availability and attribution must be verified before use.



\### 4.3 Region information



One sampled credit, `IDA01470`, contains multiple region strings:



\- AFRICA

\- AFRICA EAST

\- EASTERN AND SOUTHERN AFRICA

\- Eastern and Southern Africa



These differences may reflect geographical classification changes, administrative renaming, inconsistent normalization, or source corrections.



They must not automatically be interpreted as actual geographic movement.



\### Design decision



Retain the current region/country relationships for the canonical operational model.



Flag historical region attribution as a modeling limitation.



Do not use current region assignments as unquestioned historical attributes in retrospective subgroup evaluation.



\### 4.4 Project identifiers



No changing project ID was observed for any of the six sampled credits.



This supports retaining project identifiers as entity-level attributes for the current sample.



It does not establish their global immutability.



\## 5. Entity Attributes Versus Snapshot Attributes



The current FlowWatch model uses five canonical entity types:



Region → Country → Project → Credit → CreditSnapshot



\### Entity-level information



Entity tables maintain identities and currently modeled descriptive relationships:



\- Region identity

\- Country identity and region relationship

\- Project identity and country relationship

\- Credit identity and project relationship

\- Borrower and other credit-level descriptors



These fields should not automatically be assumed historically constant.



\### Snapshot-level information



The snapshot table represents the state of one credit at one reporting period.



Examples include:



\- Reporting period

\- Credit status

\- Original principal amount

\- Disbursed amount

\- Undisbursed amount

\- Cancelled amount

\- Outstanding financial amounts

\- Repayment-related financial amounts

\- Service charge information

\- Source lineage



\### Core design decision



\*\*Financial state and credit status remain associated with the reporting-period snapshot.\*\*



This preserves multiple observations for the same credit rather than collapsing its history into a single current-state record.



\## 6. Historical Correction Policy and Limitations



The existing canonical loader supports conflict-based updates of non-key attributes.



Therefore, an incoming record with an existing credit-period identity may replace financial values and lineage already stored for that identity.



The Day-20 scanner prevents duplicate identities within its own run, but it does not provide an immutable historical version store.



These are separate concerns:



\*\*Temporal snapshots:\*\* Preserve different reporting periods.



\*\*Historical source versions:\*\* Preserve different source versions of the same reporting-period observation.



FlowWatch currently supports the first through its canonical schema.



The second requires additional correction/versioning policy work.



Before locking a research dataset, its exact underlying source versions must be reproducible.



\## 7. Financial Source Profiling



A second read-only inspection examined numeric fields, date relationships, and selected financial comparisons across the same six page offsets.



Implementation:



`scripts/profile\_day20\_quality.py`



Evidence:



`reports/day20-financial-date-profile.json`



\### Observed results



\- 600 source records inspected.

\- 600 successfully parsed.

\- Zero parsing failures.

\- No negative monetary values observed in the inspected sample.

\- Three records with disbursement greater than original principal.

\- Four records with financial components differing from original principal.



The absence of negative values in a sample is not evidence that all negative financial values are invalid.



In particular, financial adjustments may require different treatment from ordinary positive balances.



\## 8. Financial Anomaly Examples



Three observations have disbursed amounts exceeding their original principal.



| Credit | Reporting date | Original principal (USD) | Disbursed (USD) |

|---|---|---:|---:|

| IDA00060 | 2016-10-31 | 2,200,000.00 | 2,627,709.48 |

| IDA00210 | 2016-10-31 | 15,000,000.00 | 18,086,117.32 |

| IDA00610 | 2016-10-31 | 10,000,000.00 | 12,063,443.31 |



Four observations also fail the diagnostic comparison:



`disbursed + undisbursed + cancelled = original principal`



The affected credits are:



\- IDA00060

\- IDA00160

\- IDA00210

\- IDA00610



There are four distinct affected records and seven warning conditions, because three records trigger two warnings each.



All four records share the reporting date `2016-10-31`.



The reason for this concentration has not yet been established.



\### Design decision



Do not reject these records solely because they fail the financial diagnostic comparisons.



The accounting relationships and the effects of historical adjustments require additional source-level verification.



The Day-20 engine emits warnings and retains the original observations.



\## 9. Date-Quality Semantics



The source parser recognizes World Bank dates in the form:



`DD-Mon-YYYY`



The reporting date is required.



Other supported source dates may be absent.



Malformed dates are rejected during source parsing.



The Day-20 quality engine additionally checks these chronological relationships:



1\. Board approval versus agreement signing.

2\. First repayment versus last repayment.

3\. Most recent effective date versus most recent closing date.



The observed sample contained no reversals in these tested relationships.



Unexpected ordering is implemented as a warning rather than a rejection because the source may contain legitimate corrections or exceptions.



\## 10. Quality Validation Architecture



The integrated quality service processes source records in the following order:



```text

Raw World Bank source record

&#x20;           |

&#x20;           v

Source schema validation

&#x20;           |

&#x20;           +-- Invalid -> Rejection + rule ID + raw lineage

&#x20;           |

&#x20;           v

Temporal identity validation

&#x20;           |

&#x20;           +-- Duplicate -> Rejection + rule ID + raw lineage

&#x20;           |

&#x20;           v

Financial and date diagnostics

&#x20;           |

&#x20;           +-- Warning -> Accepted + warning + raw lineage

&#x20;           |

&#x20;           +-- Clean -> Accepted

```



Implementation:



\- `src/quality/rules.py`

\- `src/quality/validator.py`

\- `src/quality/temporal.py`

\- `src/quality/invariants.py`



The quality-rule catalog is documented separately:



`docs/quality-rule-catalog.md`



\## 11. Real-Data Quality Validation



The complete integrated quality engine was executed against six non-adjacent World Bank source pages.



Implementation:



`scripts/validate\_day20\_live\_quality.py`



Evidence:



`reports/day20-live-quality-validation.json`



\### Results



| Metric | Result |

|---|---:|

| Inspected records | 600 |

| Accepted records | 600 |

| Rejected records | 0 |

| Records with warnings | 4 |

| Total warning conditions | 7 |

| DQ-AMOUNT-002 | 3 |

| DQ-CROSS-001 | 4 |



No record was discarded due to the observed financial anomalies.



All warnings retained their source references and original raw records.



The inspection used a local UUID to associate its records.



That UUID must not be confused with a persisted production ingestion-run record.



\## 12. Research-Validity Analysis



FlowWatch's focused research investigates maturity-aware cross-horizon conformal calibration for 3-, 6-, and 12-month development-finance forecasts.



The quality and temporal modeling decisions affect the validity of that research.



\### Threat 1 — Historical status leakage



If an earlier snapshot is assigned a later credit status, forecasting features may contain information unavailable at the forecast origin.



\*\*Potential effect:\*\* Artificially optimistic forecasting and uncertainty-calibration performance.



\*\*Control:\*\* Preserve credit status by reporting period and enforce point-in-time feature construction in the later research pipeline.



\### Threat 2 — Duplicate temporal observations



Repeated credit-period identities can inflate observation counts and distort the apparent frequency of historical changes.



\*\*Potential effect:\*\* Biased financial aggregates, training weights, and uncertainty estimates.



\*\*Control:\*\* Enforce canonical identity uniqueness and test duplicate handling across non-adjacent pages.



\### Threat 3 — Selective exclusion of unusual financial values



Rejecting all observations whose disbursement exceeds original principal could selectively exclude particular credits, financial states, or reporting dates.



\*\*Potential effect:\*\* A distorted empirical population and misleading estimates of predictive performance under temporal change.



\*\*Control:\*\* Retain uncertain accounting anomalies as warnings until their meaning is verified.



\### Threat 4 — Historical attribute reassignment



If borrower or region assignments are overwritten with their latest values, retrospective group analyses may use labels that were not accurate or available historically.



\*\*Potential effect:\*\* Misleading regional or institutional subgroup results.



\*\*Control:\*\* Treat historical entity attribution as unresolved; verify the source's effective dating before using these attributes in historical research features.



\### Threat 5 — Reporting date versus information availability



`end\_of\_period` describes the reporting period of an observation.



It does not necessarily prove when that observation became accessible to an analyst.



\*\*Potential effect:\*\* Backtests may consume data before it was actually available.



\*\*Control:\*\* Later point-in-time features and maturity-ledger logic must distinguish observation dates, source availability, forecast issue times, and label maturity.



\### Threat 6 — Historical source corrections



Upserting a corrected record may change previously stored historical values.



\*\*Potential effect:\*\* Experiments may become irreproducible if they cannot recover the original dataset version.



\*\*Control:\*\* Preserve source lineage, record exact dataset versions, and finalize corrected-source handling before locking research datasets.



\## 13. Reproducible Evidence



\### Source inspection



```text

python -m scripts.inspect\_temporal\_source

```



\### Financial/date profiling



```text

python -m scripts.profile\_day20\_quality

```



\### Integrated quality validation



```text

python -m scripts.validate\_day20\_live\_quality

```



\### Quality tests



```text

python -m pytest tests\\quality -v

```



Observed quality test result:



\*\*29 passed\*\*



\### Static analysis



```text

ruff check src\\quality tests\\quality

mypy src\\quality

```



Observed results:



\- Ruff: passed.

\- mypy: passed across five source files.



Live-source inspection results may change if the World Bank updates the dataset.



\## 14. Remaining Engineering Work



Day-20 results establish useful evidence but do not complete the entire data-validity problem.



Remaining work includes:



1\. Complete historical extraction and wider variation analysis.

2\. Cross-run deterministic correction handling.

3\. Durable quarantine and warning persistence.

4\. Explicit production ingestion integration.

5\. Source-level verification of financial accounting relationships.

6\. Historical entity-attribute attribution.

7\. Source availability-time and correction-time modeling.

8\. Research dataset versioning and point-in-time validation.



The full source backfill and research-feasibility audit are scheduled for later milestones.



\## 15. Conclusion



The inspected World Bank data supports representing financial observations as credit-period snapshots.



Real source variation demonstrates that credit status must not be treated as a single immutable credit attribute.



The Day-20 quality engine distinguishes definitive source-validation failures from financial and chronological anomalies requiring investigation.



The integrated live inspection accepted all 600 sampled observations, flagged four records, and recorded seven financial warning conditions without discarding those records.



These findings support the current temporal design and establish reproducible engineering evidence.



They do not prove global source uniqueness, universal financial accounting identities, complete historical point-in-time correctness, or the suitability of the entire dataset for the proposed 3-, 6-, and 12-month forecasting research.



Those questions remain subject to subsequent data-validity and research gates.
