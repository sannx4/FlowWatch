# FlowWatch — Days 26–28: ETL Release Gate

Status: **PASS_DAY26_27_28_LOCAL_ETL_GATE** (observed locally when this script was executed).

- Test timestamp (UTC): 2026-10-31T06:44:36.574227+00:00
- Run ID: `554abdc8-190b-5d2a-bbf8-ff31bf8689c7`
- PostgreSQL database: `flowwatch_day28_gate`
- MongoDB database: `flowwatch_day28_gate_raw`
- Source provenance: `logical_windows_of_single_stored_page`
- Authentic source observations: 100
- Source pages/windows: 10
- No World Bank API calls were made by this gate.

| Attempt | Fetched | Raw | Accepted | Rejected | Inserted | Updated | Unchanged | Ignored | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 100 | 100 | 99 | 1 | 99 | 0 | 0 | 0 | PASS |
| 2 | 100 | 100 | 100 | 0 | 1 | 0 | 99 | 0 | PASS |
| 3 | 100 | 100 | 100 | 0 | 0 | 0 | 100 | 0 | PASS |

## Independent controls

- Immutable source SHA-256 verified on each replay: PASS.
- Per-source-record decision identity and canonical/quarantine FKs: PASS.
- Deliberately omitted decision fails reconciliation: True.
- Quarantined parser failure recovered from Mongo without source API: PASS.
- Third-pass duplicate-free replay: PASS.
- Temporal duplicate groups: 0.
- Unresolved quarantines: 0.

## Research threat and validity note

A missing, double-counted or silently rejected credit snapshot can change the
observed forecasting target distribution and residual calibration evidence.
Reconciliation therefore checks **record identity across independently derived
source manifest, Mongo storage and PostgreSQL decisions**, not just totals.
Test reference: `tests/unit/test_day26_reconcile.py` and
`tests/integration/test_day28_etl_gate.py`.

## Limitations

- The fixture-window mode is not a true independent 10-API-page source acquisition.
- The replay is a single-worker deterministic local gate; concurrent writers untested.
- Day25 legacy-parser failure is deliberately selected as a controlled test condition.
- This proves no unexplained loss for this tested run, not all future upstream inputs.
- CI migration upgrade/downgrade and isolated runners require a separate GitHub Actions run.
