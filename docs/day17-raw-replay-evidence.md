# Day 17 — Raw Replay Evidence

## Objective

Prove the FlowWatch **replayability** invariant: selected PostgreSQL canonical snapshots can be reconstructed from retained MongoDB raw records without re-contacting the World Bank API. Replay must preserve source lineage and remain logically idempotent.

## Implementation and data path

```text
MongoDB raw_records
  -> RawRecordEnvelope.from_mongo_document(...)
  -> load_curated_record(...)
       -> existing transform_record(...)
       -> canonical PostgreSQL upserts
  -> credit_snapshots
```

The existing Day-16 ingestion envelope and PostgreSQL canonical loader are reused; no second transformation implementation was created.

| Artifact | Responsibility |
| --- | --- |
| `src/ingestion/raw_replay.py` | Select stored envelopes by run and optionally source key/limit; replay through existing curated loader. |
| `scripts/replay_raw.py` | Command-line interface for explicit or latest run and bounded selection. |
| `tests/integration/test_raw_replay.py` | Transactional delete, absence check, rebuild, lineage check, and repeat-replay proof. |

The new replay files did not match `worldbank_client`, `fetch_worldbank`, `requests`, or `httpx` in the static source search. This confirms the replay path has **no direct source-client dependency**; the integration proof uses retained MongoDB records. The CLI's `source_api_contacted=false` output is an implementation assertion, not an independently instrumented network trace.

## Verified command-line replay

Command:

```bat
python -m scripts.replay_raw --latest-run --limit 5
```

Observed on two separate executions:

```text
DAY 17 RAW REPLAY COMPLETE
run_id=f0e87dd0-001a-5447-bca9-27da56fa9575
selected_records=5
replayed_records=5
credit_snapshot_ids=[1, 2, 3, 4, 5]
source_api_contacted=false
```

The same five `source_record_key` values were returned on both executions, and the listed canonical snapshot IDs remained stable. This supports same-input logical idempotency for the checked sample.

## Transactional delete-and-rebuild proof

Test:

```text
tests/integration/test_raw_replay.py::test_delete_and_rebuild_curated_sample_from_mongo_raw
```

Proof sequence:

1. Read five distinct business observations from MongoDB `raw_records`.
2. Ensure the matching curated PostgreSQL snapshots exist within a transaction.
3. Delete those five curated snapshots and verify they are absent.
4. Reconstruct the five snapshots solely from stored Mongo raw envelopes.
5. Verify that each reconstructed snapshot exists and retains its `ingestion_run_id`, `source_checksum`, and `source_record_key`.
6. Replay the same envelopes again and verify the snapshot identities do not change.
7. Roll back the enclosing test transaction to restore the development database's prior logical state.

Executed with:

```bat
set FLOWWATCH_RUN_DAY17_INTEGRATION=1
python -m pytest tests\integration\test_raw_replay.py -q -s
```

Observed result:

```text
1 passed in 10371.86s (2:52:51)
```

The test confirms **correctness for the five-record proof sample**. It is not evidence of full-historical-backfill recovery, general throughput, or universal equivalence of all financial column values across all source versions.

## Verified quality gates

| Gate | Command | Observed result |
| --- | --- | --- |
| Lint | `ruff check src tests scripts` | All checks passed |
| Types | `mypy src\ingestion src\validation` | Success; 21 source files |
| Unit tests | `python -m pytest tests\unit -q` | 84 passed in 2.04s |
| Destructive replay integration | `python -m pytest tests\integration\test_raw_replay.py -q -s` (opt-in) | 1 passed in 10371.86s |
| Fast full suite | `python -m pytest -q` (opt-in disabled) | 89 passed, 5 skipped in 1.24s |
| Direct HTTP-import search | `findstr /S /N /I "worldbank_client fetch_worldbank requests httpx" src\ingestion\raw_replay.py scripts\replay_raw.py tests\integration\test_raw_replay.py` | No matches |

Note: The opt-in integration test was enabled for its dedicated run and disabled for the normal fast suite. The five skips in that normal suite should not be interpreted as additional integration successes.

## Research validity and potential bias

FlowWatch's later maturity-aware cross-horizon conformal experiments require stable source observations and point-in-time semantics. A faulty replay could bias the empirical study in several ways:

- **Omitted or duplicated snapshots:** changes the apparent reporting cadence, portfolio composition, and eligible 3-, 6-, and 12-month forecast origins.
- **Changed numeric/date transformations:** alters financial targets, features, maturity times, or nonconformity scores without any intentional research-method change.
- **Broken source lineage:** makes the dataset-to-raw-observation provenance chain unverifiable, undermining repeatability and claims about temporal data availability.
- **Inconsistent replay ordering or source-version policy:** may replace one business snapshot with a different upstream observation. A later full-backfill policy must explicitly define conflict resolution.

The Day-17 mitigation is to deserialize retained `RawRecordEnvelope` objects and reuse the same canonical loader as ingestion. The five-record transactional test is a reproducible regression reference for this guarantee; broader coverage is still needed for full-data recovery.

## Performance anomaly and open follow-up

The five-record destructive integration test took **10,371.86 seconds (2 hours, 52 minutes, 51 seconds)**. That is abnormal for this workload and is **not an acceptable demonstrated recovery time**. Root cause remains unmeasured; do not attribute it to MongoDB, PostgreSQL, or the network without profiling. Keep the test opt-in and investigate operation-level timings, query/lock waits, and connection behavior before incorporating it into CI or claiming recovery performance.

## Conclusion and evidence boundary

**Day-17 correctness proof: PASS for the sampled five records.** MongoDB-to-PostgreSQL replay, retained lineage, transactional delete/rebuild, and repeat-replay idempotency were verified. The command-line replay was also repeated successfully. **Performance: unresolved.** No full-backfill replay or measured throughput guarantee is claimed.
