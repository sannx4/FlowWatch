# FlowWatch — Day 23: Dependency-Safe Entity UPSERTs

Implementation adds a new **exact-source loader** without replacing existing `src/ingestion/postgres_curated_loader.py`. The Day-21 replay script continues to work as before; Day-23 gate uses `src/loaders/day23_upsert.py`. The standard entrypoint cutover is a separate reviewed step.

## Local setup (Windows CMD, in `.venv`)

1. Merge Day-22 PR before branching. Run `git switch main`, `git pull --ff-only origin main`, `git switch -c day23-entity-upsert-idempotency`.
2. Place these files into the same repo-relative paths shown in the archive.
3. Verify: `python -m ruff check src tests scripts`; `python -m mypy src\loaders\day23_upsert.py`; `python -m pytest -q tests\unit\test_day23_upsert_contract.py`.
4. Prepare a **new isolated database** (never truncate `flowwatch`):

   `docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d postgres -c "CREATE DATABASE flowwatch_day23_gate WITH TEMPLATE flowwatch OWNER flowwatch_owner;"`

   This step requires no other sessions connected to the source template database. If the database already exists, STOP and inspect it; do not overwrite it automatically.

   `docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U flowwatch_owner -d flowwatch_day23_gate -c "TRUNCATE TABLE public.credit_snapshots RESTART IDENTITY;"`

   `docker compose exec -T postgres psql -U flowwatch_owner -d flowwatch_day23_gate -At -c "SELECT count(*) FROM public.credit_snapshots;"`

   Expected **0** in *only* `flowwatch_day23_gate`.

5. Run: `python -m scripts.day23_idempotency_gate --limit 5` and supply only the `flowwatch_ingestor` password interactively.
6. Check saved evidence: `type reports\day23-entity-upsert-evidence.json`.
7. Reconcile SQL: `docker compose exec -T postgres psql -U flowwatch_owner -d flowwatch_day23_gate -At -c "SELECT COUNT(*) FROM public.credit_snapshots;"`; expected five. Source `flowwatch` remains unchanged.
8. Full suite: `python -m pytest -q`; `git status --short`.

**Security:** New loader cannot migrate schemas, never calls remote APIs, and no credentials are committed. Script accepts only a local host and the hardcoded `flowwatch_day23_gate` database, with explicit session-user checks. Source records remain immutable.

**Scope:** The three commits insert and replay real World Bank data. The correction demonstration is synthetic and rolled back. Mutable entity fields use last-in-batch Type-1 semantics; future historical modelling must not mistake this for historical attribute correctness.
