# FlowWatch V7 Day 1 — Days 29–32 Historical Backfill (first delivery)

This **first delivery** covers real independent World Bank source pages, bounded
parallel HTTP extraction, exact raw MongoDB landing, durable PostgreSQL page
checkpoints, and interrupted-run recovery. It **does not yet** promote raw
records to canonical tables, build a dbt warehouse, or export Parquet.

## Hard safety boundaries

- All PostgreSQL writes by the new CLI require database
  `flowwatch_historical_gate` and role `flowwatch_ingestor`.
- All new MongoDB raw writes use database `flowwatch_historical_gate_raw`.
- The default CLI refuses API calls without `--live`.
- The default is a **three-page bounded test** at 1,000 records/page;
  `--max-pages 0` additionally requires `--full-history`.
- No `DROP DATABASE`, destructive table cleanup, or source-record deletion.
- Do not run Alembic against `flowwatch`, `flowwatch_day28_gate`, or any main
  application DB when installing this experimental migration.

## 1. Install the package

From Windows CMD in `E:\flowwatch\FlowWatch` after downloading the ZIP:

```bat
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%USERPROFILE%\Downloads\FlowWatch_V7_Day1_Historical_Backfill.zip' -DestinationPath 'E:\flowwatch\FlowWatch' -Force"
python -m scripts.day29_32_update_ci_head
python -m alembic heads
python -m ruff check src tests scripts
python -m pytest -q tests\unit\test_day29_historical_plan.py
python -m pytest -q
```

Expected Alembic head after extraction: `d29b00000001`.

## 2. CI head revision compatibility

The older `.github/workflows/etl-days26-28.yml` job asserts the prior Alembic
head (`d26e00260001`) following `python -m alembic upgrade head`. This will
fail after the new revision is added. Modify **only that first assertion** to
`d29b00000001`. The subsequent two assertions follow explicit `upgrade
 d26e00260001` commands and must remain unchanged.

Run this safe local update before committing the new migration:

```bat
python -m scripts.day29_32_update_ci_head
```

The script checks its target step before replacing the assertion and is
idempotent. A dedicated backfill CI job and full dbt CI will be delivered with
the warehouse stage; current unit tests validate pure planning but cannot
substitute for live-service tests.

## 3. Create an isolated PostgreSQL database

```bat
docker compose ps
docker compose exec -T postgres psql -X -U flowwatch_owner -d postgres -At -c "SELECT datname FROM pg_database WHERE datname='flowwatch_historical_gate';"
```

If this database does not exist, create it **once**:

```bat
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d postgres -c "CREATE DATABASE flowwatch_historical_gate OWNER flowwatch_owner;"
```

Apply the entire migration chain to that database only:

```bat
cmd /C "set POSTGRES_DB=flowwatch_historical_gate&& python -m alembic upgrade head"
```

If Alembic does not target this database, stop. Its env.py currently uses
`load_dotenv()` without override, which respects explicit process variables.

Verify before writing:

```bat
docker compose exec -T postgres psql -X -U flowwatch_owner -d flowwatch_historical_gate -c "SELECT version_num, to_regclass('public.historical_backfill_runs'), to_regclass('public.historical_backfill_pages') FROM alembic_version;"
```

Expected version: `d29b00000001` and two non-null table names.

The migrations grant `flowwatch_ingestor` read/write on the two checkpoint
tables. This raw-only extraction does not need to grant that role UPDATE/DELETE
on immutable Day-26 reconciliation ledgers.

## 4. Real independent-page extraction (initial three-page gate)

Your existing `.env` MongoDB connection will be used, but the destination
MongoDB database is hard-coded to `flowwatch_historical_gate_raw`.

```bat
python -m scripts.day29_32_historical_backfill --live --page-size 1000 --max-pages 3 --workers 2
```

Enter the PostgreSQL `flowwatch_ingestor` password when prompted. Record the
printed `BACKFILL RUN ID` UUID. The first run makes **real HTTP requests** to
World Bank and stores each independent raw response, not logical fixture
windows. HTTP retry, timeout, validation, and backoff reuse the existing
`WorldBankClient`.

If upstream returns an error, the CLI exits nonzero and records FAILED status.
Do not assume data availability; API access and page-size support have not been
verified by the assistant in your Windows environment.

## 5. Re-run without fetching completed pages

Replace `UUID_FROM_FIRST_RUN` with the value printed in step 4:

```bat
python -m scripts.day29_32_historical_backfill --live --run-id UUID_FROM_FIRST_RUN --page-size 1000 --max-pages 3 --workers 2
```

Expected: `REUSED_COMMITTED_PAGE` for each page, followed by a result with
`pages_fetched_this_execution: 0`. Existing page evidence is independently
validated against MongoDB. If a prior process stopped after Mongo wrote a page
but before PostgreSQL committed it, the resume path commits the checkpoint
without fetching that page again.

Recover a lost run ID:

```bat
python -m scripts.day29_32_historical_backfill --list-runs
```

## 6. Fault injection: isolated *new* run, do not alter the successful run

```bat
python -m scripts.day29_32_historical_backfill --live --page-size 1000 --max-pages 3 --workers 2 --fail-after-pages 1
```

The process must exit nonzero with `INJECTED_FAILURE_AFTER_COMMITTED_PAGE`.
Record the UUID, and resume **without** the failure argument:

```bat
python -m scripts.day29_32_historical_backfill --live --run-id FAULT_RUN_UUID --page-size 1000 --max-pages 3 --workers 2
```

The already committed first page should not be fetched again. Confirm the
source remains stable; if source totals changed the run fails closed.

## 7. Read-only cross-store audit

```bat
python -m scripts.day29_32_checkpoint_audit --run-id UUID_FROM_FIRST_RUN
```

This reports count parity, distinct credits, reporting dates and per-field
presence/missingness. It is a source variation audit, **not an ML-feasibility
claim**.

## 8. Full history — only after the bounded gate is green

A truly uncapped capture is explicitly opt-in:

```bat
python -m scripts.day29_32_historical_backfill --live --page-size 1000 --max-pages 0 --full-history --workers 2
```

Do not start this before confirming API quotas, source stability and MongoDB
storage capacity. It may ingest a large number of records; the current raw
loader uses per-record upserts and still needs a full-scale benchmark.

## Gate and research limitations

- A constant API `total_count` does **not** guarantee a point-in-time snapshot.
  Upstream insertions/deletions or ordering changes between requests can shift
  page boundaries even when total_count stays unchanged. Research validation
  must detect missing/duplicate credit-period identities downstream.
- This release verifies raw-only persistence. No claim of complete canonical
  promotion, dbt models, ML labels, or Parquet release is made.
- High-volume throughput, kill-process fault recovery, and live HTTP access
  require execution on the user's machine or CI and have **not** yet been run
  by the assistant against the actual World Bank endpoint.
- Do not publish as a complete historical data release before the core-vs-source
  and warehouse-vs-core reconciliation gates are built and passed.
