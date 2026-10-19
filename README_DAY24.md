# FlowWatch — Day 24: COPY / staging bulk snapshot ingestion

## Included deliverables

- `src/loaders/day24_bulk.py`: psycopg3 COPY-to-temp-stage, set-based snapshot
  merge, inherited Day-23 entity resolution and correction policy.
- `scripts/day24_bulk_benchmark.py`: bounded real-source benchmark vs Day-23
  reference; rollback-safe parity/evidence gates.
- `tests/unit/test_day24_bulk_contract.py`: static type/precision/identity
  contracts and duplicate rejection.
- `sql/day24_bulk_evidence.sql`: read-only PostgreSQL evidence queries.
- `docs/day24-bulk-loader-research.md`: methodology + scientific-validity risks.

## Prerequisites

1. **Day-23 PR is merged into `main`.** Confirm before creating branch.
2. Local PostgreSQL 17 via Compose, service `postgres`; MongoDB is NOT used by
   this offline-fixture benchmark.
3. Python 3.12, SQLAlchemy 2.x and psycopg3 (`postgresql+psycopg`).
4. A real checked-in World Bank sample at `data/raw/world_bank_sample.json`
   containing at least 100 records. Smaller samples may use `--sizes 5 25 50`
   or `--sizes 5 25`.
5. Working `flowwatch_ingestor` role with SELECT/INSERT/UPDATE and PostgreSQL
   TEMP permissions in an isolated database.

## Git branch

```bat
cd /d E:\flowwatch\FlowWatch
.venv\Scripts\activate
git switch main
git pull --ff-only origin main
git switch -c day24-snapshot-copy-bulk-load
```

## Installation

Download ZIP and save in `%USERPROFILE%\Downloads`, then in CMD:

```bat
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%USERPROFILE%\Downloads\FlowWatch_Day24_Snapshot_Bulk_Load.zip' -DestinationPath '.' -Force"
```

Verify files before DB steps:

```bat
python -m py_compile src\loaders\day24_bulk.py scripts\day24_bulk_benchmark.py
python -m ruff check src tests scripts
python -m mypy src\loaders\day24_bulk.py scripts\day24_bulk_benchmark.py
python -m pytest -q tests\unit\test_day24_bulk_contract.py
python -m pytest -q
```

## Prepare isolated database (ONE TIME)

First check whether it exists. Never reset the `flowwatch` database:

```bat
docker compose exec -T postgres psql -X -U flowwatch_owner -d postgres -At -c "SELECT datname FROM pg_database WHERE datname='flowwatch_day24_gate';"
```

If absent, clone the main DB as an isolated benchmark DB (no write to main):

```bat
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d postgres -c "CREATE DATABASE flowwatch_day24_gate WITH TEMPLATE flowwatch OWNER flowwatch_owner;"
```

**Only after independently confirming this is the isolated database**, clear
its snapshot rows to ensure the benchmark measures actual cold INSERTs:

```bat
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d flowwatch_day24_gate -c "TRUNCATE TABLE public.credit_snapshots RESTART IDENTITY;"
```

Confirm source and target DB:

```bat
docker compose exec -T postgres psql -X -U flowwatch_owner -d flowwatch_day24_gate -At -c "SELECT current_database(),COUNT(*) FROM public.credit_snapshots;"
```

Expected: `flowwatch_day24_gate|0`. If the test DB exists, check its contents
and provenance before any destructive operation.

## Run the benchmark

```bat
python -m scripts.day24_bulk_benchmark --sizes 5 25 50 100 --repeats 3
```

The CLI prompts for `flowwatch_ingestor` password. It refuses a non-local
PostgreSQL host, wrong DB/role, or a test DB containing any snapshots.

It executes **both** methods for each size and each repetition from an
identical starting state, compares canonical business/lineage/parent values,
checks correction policies and three-repeat bulk idempotency, and rolls back
all writes. It reports measured medians and creates:

`benchmarks/day24/initial-ingestion-benchmark.json`

If you have fewer than 100 real source records, change batch sizes accordingly.
The benchmark deliberately does not expand a small sample using duplicates or
synthetic records.

## Post-run read-only verification

```bat
docker compose exec -T postgres psql -X -U flowwatch_owner -d flowwatch_day24_gate -At -c "SELECT current_database(),COUNT(*) FROM public.credit_snapshots;"
type benchmarks\day24\initial-ingestion-benchmark.json
git status --short
```

Expected DB count remains zero because all trials are rolled back.

## Limitations

- End-to-end performance may **not** favor COPY for tiny batches; benchmark
  reports actual values.
- Only the snapshot phase uses COPY; entity upserts remain Day-23-oriented.
- No production cutover, source API request, Mongo writes, persistent benchmark
  row or schema migration occurs on Day 24.
- This run uses an offline, **real World Bank JSON fixture** with a documented
  SHA; its benchmark-only lineage must not be confused with MongoDB lineage.
- A controlled correction probe modifies test input in memory **only** and
  unconditionally rolls back any effects.
