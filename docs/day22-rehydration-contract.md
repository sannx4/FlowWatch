# Day 22 — Exact raw-source recovery contract

## Why this adapter exists

Existing MongoDB `raw_records.payload` financial fields may contain Python binary floats even when the authoritative page was originally a JSON byte stream. Converting an already-decoded float to `Decimal(str(value))` is not a proof that the original base-10 value was retained. The checksum-verified `raw_pages.raw_bytes` is the authoritative input for exact textual recovery.

## Operation (no writes)

1. Select a stored raw-record envelope with run ID, page number, page offset, record index, source checksum, and original payload.
2. Locate the corresponding `raw_pages` document by **all** page identifiers, including its source checksum.
3. Recompute SHA-256 of its `raw_bytes` and compare with the envelope's `source_checksum` (fail closed on mismatch).
4. Confirm that `json.loads(raw_bytes)['data'][record_index]` equals the **stored** raw-record payload, without modifying it.
5. Parse the verified page again with `json.loads(raw_bytes, parse_float=Decimal)` to preserve source decimal literals, then map that record using `transform_canonical_record`.
6. Preserve the original raw envelope and its immutable source lineage. The corrected values are a *derived representation*; they are not rewritten into the historical MongoDB envelope.

## Boundaries and research-integrity risk

- Decimal recovery preserves numeric literals in the original JSON **bytes**. It cannot undo rounding by the remote API before serialization.
- Existing PostgreSQL snapshot values are **not** repaired merely by running this audit. Rebuild/backfill and target `NUMERIC` precision must be checked in a separate, controlled acceptance test.
- A difference between `Decimal(str(stored_float))` and `Decimal(source_token)` is recorded as a source-precision discrepancy, not silently rounded away.
- A mismatched page checksum or stored-envelope payload aborts the audit rather than guessing record identity.
- Inaccurate historical disbursement amounts would bias cumulative ratios and residuals for 3/6/12-month forecasting, potentially changing worst-window conformal coverage and invalidating research comparisons.

## Reproducible verification

- `python -m pytest -q tests/unit/test_day22_rehydration.py`
- `python -m scripts.day22_raw_precision_audit --limit 5`
- `reports/day22-raw-precision-audit.json`

**No source API calls, MongoDB writes, or PostgreSQL writes are performed by this audit.** The existing production loader continues using the Day-7 transform until a separate loader/backfill PR demonstrates exact-value compatibility.
