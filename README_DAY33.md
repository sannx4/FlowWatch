# FlowWatch V7 Day-1 — Day 33 historical canonical publication gate

This package adds a **bounded, fail-closed** promotion of your already verified
World Bank historical raw records into the existing FlowWatch PostgreSQL
canonical model. It **does not** contain dbt or Parquet yet.

## Tested scope and prerequisites

- Starts from branch `v7-day1-financial-warehouse`, whose parent includes merged
  PR #23 and Alembic head `d29b00000001`.
- Existing historical PostgreSQL `flowwatch_historical_gate` and MongoDB
  `flowwatch_historical_gate_raw` contain the three-page backfill from Day29–32.
- No request is made to the World Bank API during canonical publication.
- A separate new Alembic migration `d33c00000001` creates an immutable
  source-observation publication summary and decision ledger.
- Uses the pre-existing Day23 strict canonical upsert helper (row-by-row), Day25
  quarantine helper, Day26 `require_partition`-style identity accounting, Day29
  checkpoint table, and unchanged Mongo raw envelopes.
- The original `flowwatch` database is **not touched**. Database identity and
  `flowwatch_ingestor` role are hard-checked on every invocation.
- Read-only preflight is the default. `--apply` is mandatory to write.
- Missing or inconsistent raw source evidence blocks publication; corrupted
  source bytes are **never** converted into a routine quarantine rejection.
- The current gate deliberately caps ingestion at 10,000 source observations.

## 1. Install from downloaded zip (Windows CMD)

From `E:\flowwatch\FlowWatch` on `v7-day1-financial-warehouse`:

```bat
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%USERPROFILE%\Downloads\FlowWatch_V7_Day33_Canonical_Gate.zip' -DestinationPath 'E:\flowwatch\FlowWatch' -Force"
python -m scripts.day33_update_ci_head
python -m alembic heads
python -m ruff check src tests scripts
python -m mypy src\warehouse\historical_contracts.py src\warehouse\historical_canonical.py
python -m pytest -q
```

Expected Alembic head: `d33c00000001`. These checks run without writing to
PostgreSQL. The CI helper updates only the `alembic upgrade head` assertion;
explicit Day26 rollback checks remain unchanged.

## 2. Upgrade **only** the historical gate DB

```bat
cmd /C "set POSTGRES_DB=flowwatch_historical_gate&& python -m alembic upgrade head"
docker compose exec -T postgres psql -X -U flowwatch_owner -d flowwatch_historical_gate -c "SELECT version_num, to_regclass('public.historical_canonical_publications'), to_regclass('public.historical_canonical_decisions') FROM alembic_version;"
```

Expected revision: `d33c00000001` and both table names non-null. The
migration grants the existing `flowwatch_ingestor` only the privileges needed
for isolated canonical tables, quarantine and publication ledgers.

**DO NOT run the migration against the production/main `flowwatch` DB.**

## 3. Verify the 3,000-row source *without* writing canonical data

Use the first completed source-run UUID:

```bat
python -m scripts.day33_historical_canonical --run-id 241490b7-5d6e-4392-b351-f6308118cf98
```

Expected: JSON with `PASS_CANONICAL_PREFLIGHT`, `source_records: 3000`, a
**date-parsed** temporal profile, and counts of valid/invalid candidates. This
is a preview; `canonical_loaded: false`.

If the preflight fails (source mismatch, unexpected page count, checksum), do
**not** apply. Investigate and preserve original raw evidence.

## 4. Authorize a canonical publication (only after valid preflight)

```bat
python -m scripts.day33_historical_canonical --run-id 241490b7-5d6e-4392-b351-f6308118cf98 --apply
```

A successful run reports `PASS_CANONICAL_PUBLICATION` and counts whose sum
equals the 3,000 raw observations. The canonical writes, immutable observation
decisions, optional quarantines and summary commit atomically.

If the run reports a validation or source-correction conflict, it fails and
**all canonical DB writes are rolled back**. Review the underlying issue first.
Only if you explicitly accept *partial* publication should you run:

```bat
python -m scripts.day33_historical_canonical --run-id 241490b7-5d6e-4392-b351-f6308118cf98 --apply --allow-quarantine
```

This records rejected source observations in Day25 quarantine and publishes
accepted observations with a balanced immutable ledger. Never choose this
option just to get a green status without reviewing the rejected data.

## 5. Verify replay

```bat
python -m scripts.day33_historical_canonical --run-id 241490b7-5d6e-4392-b351-f6308118cf98 --apply
```

Expected `PASS_EXISTING_CANONICAL_PUBLICATION` with `reused: true`. No new
publication or canonical insertion should occur.

Run the full source audit again:

```bat
python -m scripts.day29_32_checkpoint_audit --run-id 241490b7-5d6e-4392-b351-f6308118cf98
```

Existing source bytes must remain unaffected.

## Verification and limitations

Local package checks: Python compilation and pure-contract unit tests passed.
**No live PostgreSQL/MongoDB integration was performed in the packaging
environment**. On Windows, the new code must pass Ruff/mypy/full pytest and
the read-only/source-gate checks before trusting its publication results.

This is a **bounded, row-wise canonical promotion**, not a full historical
backfill, representative sample, statistical-independence claim, maturity-aware
forecast dataset, dbt warehouse, or published Parquet artifact. A later release
will add warehouse models, temporal-leakage assessment and dataset versioning.
