# FlowWatch Day 25 — Durable quarantine + offline remediation

**Prerequisite:** merge the Day-24 PR and create branch `day25-quarantine-remediation`; keep existing MongoDB original raw records and the Day-22/23 transformation modules. The acceptance gate writes ONLY `flowwatch_day25_gate` as `flowwatch_ingestor` and reads MongoDB; it never contacts World Bank. **Do not run DDL or replay against `flowwatch`.**

## Contents

- `sql/operational/day25_quarantine.sql`: idempotent isolated-gate DDL + restricted grants.
- `scripts/day25_install_migration.py`: generates a real Alembic revision using current repository head and the SQL above; writes a migration file, does not touch any DB.
- `src/quality/day25_quarantine.py`: typed source locator, idempotent rejection ledger, state transitions.
- `scripts/day25_common.py`: isolated DB guard and password prompt.
- `scripts/day25_quarantine_gate.py`: genuine stored legacy-parser failure and final verification.
- `scripts/day25_replay_quarantine.py`: replay persisted quarantine ID from checksum-verified MongoDB source bytes.
- `tests/unit/test_day25_quarantine.py`: contract tests.
- `docs/day25-quarantine-research.md`: validity and limitations.

## Windows CMD — sequence

Start from `(venv) E:\flowwatch\FlowWatch>`.

### 1. Static and unit tests

```bat
python -m py_compile src\quality\day25_quarantine.py scripts\day25_common.py scripts\day25_quarantine_gate.py scripts\day25_replay_quarantine.py scripts\day25_install_migration.py
python -m ruff check src tests scripts
python -m mypy src\quality\day25_quarantine.py scripts\day25_common.py scripts\day25_quarantine_gate.py scripts\day25_replay_quarantine.py scripts\day25_install_migration.py
python -m pytest -q tests\unit\test_day25_quarantine.py
python -m pytest -q
```

Stop and share any failure before altering the database.

### 2. Generate Alembic revision (source control artifact only)

```bat
python -m scripts.day25_install_migration
python -m alembic heads
```

**Review the generated migration** and commit it with Day25. Its parent revision is your actual Alembic head, not a guessed hash. The isolated test uses the SQL directly to avoid changing `flowwatch`'s Alembic version table. Do not run `alembic upgrade head` against production/main in this test.

### 3. Create isolated test database

Check existence first:

```bat
docker compose exec -T postgres psql -X -U flowwatch_owner -d postgres -At -c "SELECT datname FROM pg_database WHERE datname='flowwatch_day25_gate';"
```

If no output, create from existing core:

```bat
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d postgres -c "CREATE DATABASE flowwatch_day25_gate WITH TEMPLATE flowwatch OWNER flowwatch_owner;"
```

If already present, inspect it; **do not automatically reset pre-existing quarantine evidence**. Once confirmed to be the isolated test database, clear only its snapshots:

```bat
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d flowwatch_day25_gate -c "TRUNCATE TABLE public.credit_snapshots RESTART IDENTITY;"
```

Apply DDL through container input redirection (Windows CMD host file):

```bat
type sql\operational\day25_quarantine.sql | docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d flowwatch_day25_gate
```

Check table and empty snapshot count:

```bat
docker compose exec -T postgres psql -X -U flowwatch_owner -d flowwatch_day25_gate -At -c "SELECT current_database(), (SELECT count(*) FROM public.credit_snapshots), (SELECT count(*) FROM public.source_quarantine);"
```

If applying on a pre-existing quarantine gate database, the last count may be nonzero; stop and review rather than overwriting it.

### 4. Phase A — persist a genuine parser rejection

```bat
python -m scripts.day25_quarantine_gate --phase reject --limit 100
```

Enter only your local `flowwatch_ingestor` password when prompted; do not share it. The tool uses one real stored Mongo record containing a financial float. It first verifies that the strict parser fails on that stored representation while the Day-22 source-bytes recovery succeeds. It then commits a `PENDING` quarantine row and generates `reports/day25-quarantine-gate.json`.

### 5. Phase B — restart Python and remediate from Mongo raw evidence

```bat
python -m scripts.day25_replay_quarantine
```

Expected `status: RESOLVED`, nonzero `snapshot_id`. No World Bank API request. The same transaction writes the canonical record and resolves the quarantine event. A failed load rolls both changes back and records the retry failure in a fresh transaction.

Re-run the exact same command to prove no duplicate writes: expect `ALREADY_RESOLVED`.

### 6. Phase C — independent SQL/lineage confirmation

```bat
python -m scripts.day25_quarantine_gate --phase verify
```

Expected `PASS_DAY25_PERSIST_AND_REPLAY`, one resolved event, `retry_count = 1`, zero duplicate temporal keys and matching source key/checksum in the canonical snapshot. Inspect the recorded evidence:

```bat
type reports\day25-quarantine-gate.json
```

## Git work

Commit new `src`, `scripts`, `tests`, `docs`, SQL and generated Alembic migration only after code checks, isolated integration gate, and evidence verification. Ensure migration does not conflict with another pending Alembic head. The source `flowwatch` database must not be modified during this gate.
