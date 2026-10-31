# FlowWatch — Days 26–28: Integration & Release Guide

**Purpose:** Install the reconciliation ledger (Day 26), validate the migration/integration CI (Day 27), and execute an isolated offline multi-pass ETL gate (Day 28) against genuine stored World Bank source records. This package is not a replacement for existing Days 1–25 code.

## Acceptance and scope

- Day 26: independent identity reconciliation of source-page manifests, MongoDB raw records and committed PostgreSQL processing decisions; checks every source key and per-attempt accounting.
- Day 27: GitHub Actions split into `fast-tests`, `migration-test`, and `live-integration`, with an injected broken revision that must fail without corrupting the migration state.
- Day 28: committed attempt 1 (one deliberate strict-parser quarantine), attempt 2 (recovery, insertion), attempt 3 (fully idempotent replay). A second invocation must verify the existing result without replaying completed attempts.
- All Day-28 database writes are limited by hard-coded connection guards to PostgreSQL database `flowwatch_day28_gate`, PostgreSQL role `flowwatch_ingestor`, and MongoDB database `flowwatch_day28_gate_raw` on local hosts.
- This is an **offline replay** gate: it does not fetch from the World Bank API. `--source-file` creates **logical windows**, not independent upstream pages. For actual saved pages use `--pages-dir ... --require-true-pages`.
- Live database execution and GitHub Actions results must be checked locally; included reports are templates, not proof of successful execution.

## Preparation (Windows CMD, from `E:\flowwatch\FlowWatch`)

1. Confirm you are on a feature branch and the worktree is clean: `git status --short`.
2. Extract the ZIP to the repository root. In PowerShell: `Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\FlowWatch_Days26_27_28_Corrected.zip" -DestinationPath "E:\flowwatch\FlowWatch" -Force`.
3. **Do not overwrite existing Day 22–25 source files.** The package adds Day 26–28 modules, a migration, tests, reports and CI.
4. Verify the package was extracted: `python -m alembic heads` should report `d26e00260001 (head)`.
5. Confirm Docker services are healthy: `docker compose ps`.

### Static and unit verification

```bat
python -m ruff check src tests scripts
python -m mypy src\quality\reconcile.py scripts\day28_etl_gate.py scripts\day27_migration_failure_probe.py
python -m pytest -q tests\unit\test_day26_reconcile.py tests\unit\test_day28_offline_pages.py
python -m pytest -q
```

**Note:** The general regression suite can skip integration tests by design. The live Day-28 gate below is a separate mandatory step.

## Isolated PostgreSQL setup

Use a **new empty database**, not the main `flowwatch` DB or existing Day-25 gate evidence DB. Before running `CREATE DATABASE`, verify it is absent and do not repeat creation if it already exists:

```bat
docker compose exec -T postgres psql -X -U flowwatch_owner -d postgres -At -c "SELECT datname FROM pg_database WHERE datname='flowwatch_day28_gate';"
```

If the query returns nothing:

```bat
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d postgres -c "CREATE DATABASE flowwatch_day28_gate OWNER flowwatch_owner;"
```

`alembic/env.py` reads `POSTGRES_DB`, so override only for a child process. Run migration as owner (the credentials already configured in `.env` remain unchanged):

```bat
cmd /C "set POSTGRES_DB=flowwatch_day28_gate&& python -m alembic upgrade head"
```

Verify the exact resulting revision and tables:

```bat
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d flowwatch_day28_gate -c "SELECT version_num, to_regclass('public.source_quarantine'), to_regclass('public.etl_attempts'), to_regclass('public.etl_record_decisions') FROM alembic_version;"
```

Expected revision: **`d26e00260001`**, with all three tables present.

The ingestion role needs data DML permissions **inside the isolated gate database only**. This is for the test deployment and is not a production grant policy:

```bat
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d flowwatch_day28_gate -c "GRANT CONNECT ON DATABASE flowwatch_day28_gate TO flowwatch_ingestor; GRANT USAGE ON SCHEMA public TO flowwatch_ingestor; GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO flowwatch_ingestor; GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO flowwatch_ingestor; REVOKE UPDATE, DELETE ON public.etl_attempts, public.etl_record_decisions FROM flowwatch_ingestor;"
```

For migration reversibility, perform a `downgrade d25cafe01250` and `upgrade d26e00260001` only in this empty isolated DB, before it contains release-gate evidence. Day 27 CI separately exercises fresh full migration, downgrade, re-upgrade and a broken migration.

## Run the live Day-28 offline ETL gate

Ensure `data\raw\world_bank_sample.json` exists and is the genuine saved World Bank response with a top-level `data` list. If the path differs, substitute your actual source file:

```bat
python -m scripts.day28_etl_gate --source-file data\raw\world_bank_sample.json --windows 10
```

The command may prompt for the existing `flowwatch_ingestor` PostgreSQL password and will connect only to local database services. It uses MongoDB's configured connection unless `FLOWWATCH_GATE_MONGO_URI` is provided for CI. Do not paste credentials into the shell or source files.

Expected for exactly 100 records, including one controlled decimal-parser rejection:

| Attempt | Fetched | Accepted | Rejected | Inserted | Updated | Unchanged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial | 100 | 99 | 1 | 99 | 0 | 0 |
| Remediation | 100 | 100 | 0 | 1 | 0 | 99 |
| Rerun | 100 | 100 | 0 | 0 | 0 | 100 |

For **ten genuine independently saved pages**, supply `--pages-dir PATH --windows 10 --require-true-pages`. Those files must each contain the complete original response body with a top-level `data` list.

The script generates:
- `reports/day28-etl-gate.json` (observed machine-readable run evidence)
- `reports/etl-gate.md` (observed human-readable release report)

The test deliberately simulates the previously identified BSON float incompatibility; it must not be presented as an actual new upstream source defect.

### Confirm immutable evidence and idempotent restart

Run the exact same command a second time. It should detect three completed attempts, avoid new canonical inserts and verify the previously stored evidence.

Then run live integration tests with explicit opt-in for Windows CMD:

```bat
set FLOWWATCH_RUN_INTEGRATION=1
python -m pytest -q tests\integration\test_day28_etl_gate.py
set FLOWWATCH_RUN_INTEGRATION=
```

Review evidence:

```bat
type reports\day28-etl-gate.json
type reports\etl-gate.md
```

The completed gate requires zero temporal duplicates, one resolved quarantine, three committed reconciliation attempts, and identity-level accounting. Do not report a PASS if the command raises an exception.

## Day-27 GitHub CI

The workflow is `.github/workflows/etl-days26-28.yml`. Push the branch and open a pull request. It contains three independent jobs:

1. `fast-tests` — Ruff, mypy, and fast unit suite.
2. `migration-test` — fresh PostgreSQL database, Alembic to head, downgrade/re-upgrade, deliberately broken migration rejected with transactional rollback.
3. `live-integration` — ephemeral PostgreSQL 17 + MongoDB 8, three-pass Day-28 run and re-entrant rerun.

GitHub Actions must execute before CI coverage can be claimed. The deliberately broken migration probe **must never be added to actual Alembic history**; it is generated in a temporary directory.

## Research relevance

Source records silently lost, duplicated, incorrectly converted to floating-point, or inconsistently repaired can bias later financial forecasting labels and conformal residuals. Research tests must retain source identities and raw checksums and must distinguish real World Bank data from controlled fault injection. See `docs/days26-28-research-method.md`.

## Troubleshooting

- **`relation public.etl_attempts does not exist`**: migrate the isolated Day-28 DB to `d26e00260001`; do not manually apply its SQL in place of Alembic.
- **`permission denied`**: check `flowwatch_ingestor` access to the isolated DB only and verify the ledger is deliberately append-only.
- **`MongoDB connection refused`**: check `docker compose ps` and your existing localhost mapping/authentication configuration.
- **`No real BSON-float strict-parser incompatibility found`**: the supplied file may be a different fixture without the original controlled example; use the authentic stored file from previous Day-25 testing or a recorded source page with a demonstrable incompatible value. Do not fabricate source values while claiming genuine input.
- **Existing database**: do not drop or recreate a database that has recorded evidence. Inspect it and resume the interrupted gate.
- **`pytest` skipped live integration**: run with `FLOWWATCH_RUN_INTEGRATION=1` after the gate and clear the variable afterwards.

## Post-gate work

After a verified Days 26–28 release gate, build the enterprise dbt staging, dimensions, facts, finance metrics, research-feasibility audit and Parquet export on `v7-enterprise-data-platform` without replacing the trusted Days 1–25 code.
