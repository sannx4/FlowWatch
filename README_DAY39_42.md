# FlowWatch V7 Day 1 — Final research audit + immutable Parquet release (Days 39–42)

## What you are getting

**Read-only research audit** (default): validates the existing Day33 publication and
Day34–38 warehouse in one **REPEATABLE READ, READ ONLY** transaction. Reconciles
all 13 financial NUMERIC fields and lineage against the dbt fact table. Profiles
per-credit reporting continuity, missingness, negative values requiring review,
non-month-end reporting dates, and structural 3/6/12-month horizon windows.

**Explicit `--export`**: publishes the 3,000 accepted observations as one
versioned `credit_period.parquet` preserving exact Arrow decimal types. Writes
`audit.json` and `manifest.json` containing source run, counts, logical digest,
file SHA-256 and format information. Parquet round-trip is checked field-by-field,
including exact decimal values. A second invocation verifies the existing
artifacts rather than replacing them.

**CI gate:** a separate GitHub Actions workflow recreates the Day34 tiny
synthetic Postgres fixture, builds dbt, runs the research audit, writes exact-
decimal Parquet, and checks immutable replay. CI synthetic data is not the
actual historical research dataset.

**No forecasting readiness assertion**. Horizon windows are *structural* and
not labels, independent samples, leakage-free features, or model-evaluation
results. The upstream API did not promise point-in-time consistent pagination.

## Safety boundaries

- Reads only PostgreSQL `flowwatch_historical_gate` as `flowwatch_owner`.
- The primary `flowwatch` database is never accessed by this module.
- No SQL migrations, new database tables, inserts, updates or deletes.
- No HTTP requests, no new source downloads, no MongoDB mutations.
- `--export` writes files **only** under ignored `artifacts/flowwatch_day1/`.
- First checks source/backfill ledger, source/fact/mart equality and exact
  financial values, then exports one bounded source publication.
- Bounded release refuses more than 10,000 accepted observations.
- Source rows are `SELECT`ed through the immutable Day33 **decision ledger**.
  The run's accepted observations must map one-to-one to canonical snapshots.
- This release uses the Day34 PostgreSQL owner connection environment; no
  passwords are stored in the exported manifest.
- A named data version depends on a cryptographic **logical record hash**;
  the Parquet byte SHA-256 can vary across writer versions. Both are recorded.

## Windows CMD commands (from `E:\flowwatch\FlowWatch`)

Keep the branch `v7-day1-dbt-warehouse` until its PR is merged. If it is already
merged, start from updated `main` on a new branch (`v7-day1-research-parquet`).

1. Extract ZIP (after downloading into Downloads):

```bat
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%USERPROFILE%\Downloads\FlowWatch_V7_Day39_42_Research_Parquet.zip' -DestinationPath 'E:\flowwatch\FlowWatch' -Force"
```

2. Install Parquet library **in the main FlowWatch `.venv`**. The separate dbt
   environment can remain untouched:

```bat
python -m pip install --prefer-binary --retries 10 --timeout 90 -r requirements-research.txt
python -m pip check
python -m ruff check src tests scripts
python -m mypy src\warehouse\research_contracts.py scripts\day39_42_research_export.py
python -m pytest -q
```

3. Run the safe **read-only** research audit:

```bat
python -m scripts.day39_42_research_export --run-id 241490b7-5d6e-4392-b351-f6308118cf98
```

Expected: `PASS_RESEARCH_AUDIT_PREFLIGHT` (this creates a **report file**, but
no DB write and no Parquet export). Inspect `reports\day39-42-research-gate.json`.

4. Publish the bounded dataset if audit passes:

```bat
python -m scripts.day39_42_research_export --run-id 241490b7-5d6e-4392-b351-f6308118cf98 --export
```

Expected: `PASS_DAY1_BOUNDED_RESEARCH_EXPORT` and
`PASS_NEW_IMMUTABLE_PARQUET` within the `artifact` output. It will print an
`artifacts/flowwatch_day1/<run-id>/<logical-sha256>/` path.

5. Repeat the **same** `--export` command. Expected nested status:
`PASS_EXISTING_IMMUTABLE_PARQUET` and `reused: true`. The file hashes must match.

6. Check and commit only code, tests, contracts, and the report. **Never add the
   Parquet export** to Git. Generated artifacts are ignored using
   `artifacts/.gitignore`:

```bat
git status --short
python -m ruff check src tests scripts
python -m pytest -q
git add README_DAY39_42.md requirements-research.txt artifacts/.gitignore
git add src/warehouse/research_contracts.py scripts/day39_42_research_export.py
git add tests/unit/test_day39_42_research_contracts.py tests/unit/test_day39_42_export_contracts.py
git add scripts/day39_42_ci_assert.py .github/workflows/day39-42-research-parquet.yml
git add docs/day39-42-research-contract.md reports/day39-42-research-gate.json
git diff --cached --check
git diff --cached --stat
```

Commit, push and open a PR only after the above checks pass.

## Evidence boundaries

The current run contains 3,000 observations across 19 credits from a
reported 1,612,290-row source. We deliberately **do not** call this full
historical coverage, a statistically representative sample, a complete
production data lake, a label-validated machine learning dataset, or a
reproducible cross-horizon model evaluation. Full-source ingestion and proper
out-of-time research splits remain separate future milestones.
