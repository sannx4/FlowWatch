# FlowWatch V7 Day-1 — Days 34–38: dbt Financial Warehouse

## Scope and evidence

- Exactly one row per `(credit_id, end_of_period)` in `fct_credit_period`.
- Exact source PostgreSQL `NUMERIC` fields and NULL values are preserved; no float conversions.
- `dim_country`, `dim_project`, `dim_credit` + staging views and period-end fact table.
- `mart_credit_period_metrics` provides **month-adjacent changes in reported STOCKS**. They are **not** independently verified disbursement or repayment cash flows. No forward-filling.
- Generic dbt key/relationship tests and four singular source/metric parity tests.
- Python verifier checks the Day33 PostgreSQL publication ledger, exact counts, canonical source lineage, and built warehouse.
- Hard-coded target: Postgres `flowwatch_historical_gate` with schema `fw_analytics` and role `flowwatch_owner`. Does **not** touch original `flowwatch` database.
- The bounded 3,000-observation dataset is **not a representative sample** nor a full 1.61M historical backfill.

## Installation on Windows CMD (from E:\flowwatch\FlowWatch)

Download the package ZIP into `%USERPROFILE%\Downloads` and extract:

```bat
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%USERPROFILE%\Downloads\FlowWatch_V7_Day34_38_dbt_Warehouse.zip' -DestinationPath 'E:\flowwatch\FlowWatch' -Force"
```

Check existing code first:

```bat
python -m ruff check src tests scripts
python -m mypy scripts\day34_38_dbt_gate.py
python -m pytest -q
```

Install the **dbt Core v1 PostgreSQL adapter** into the active project venv:

```bat
python -m pip install -r requirements-dbt.txt
dbt --version
```

The runner loads `.env` (where `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` already reside). It does not print passwords and never commits them. If your existing `.env` doesn't contain the owner password, the runner prompts for it. Do not set `POSTGRES_DB` manually: this module intentionally hard-codes the isolated DB.

## Run read-only gate

```bat
python -m scripts.day34_38_dbt_gate --run-id 241490b7-5d6e-4392-b351-f6308118cf98
```

Expected: `PASS_DBT_WAREHOUSE_PREFLIGHT` and 3,000 canonical snapshots.

## Run dbt build and 100% reconciliation

```bat
python -m scripts.day34_38_dbt_gate --run-id 241490b7-5d6e-4392-b351-f6308118cf98 --build
```

Expected: dbt builds all models and passes tests, then report `PASS_DBT_FINANCIAL_WAREHOUSE` with source/fact/mart counts all 3,000 and dimensions representing 19 credits. This performs writes **only** in `flowwatch_historical_gate.fw_analytics`.

## Replay and query

Run the same `--build` command a second time; this rebuilds tables deterministically and checks equality. Inspect:

```bat
docker compose exec -T postgres psql -X -U flowwatch_owner -d flowwatch_historical_gate -c "SELECT COUNT(*) AS snapshots, COUNT(DISTINCT credit_id) AS credits FROM fw_analytics.fct_credit_period;"
docker compose exec -T postgres psql -X -U flowwatch_owner -d flowwatch_historical_gate -c "SELECT COUNT(*) FILTER (WHERE is_consecutive_month) AS adjacent, COUNT(*) FILTER (WHERE NOT is_consecutive_month) AS gaps FROM fw_analytics.mart_credit_period_metrics;"
type reports\day34-38-warehouse-gate.json
```


## Limitations and safety

1. This warehouse reflects the *current canonical state*; mutable descriptive attributes are not SCD2 and do not represent a historical as-of database.
2. No upstream snapshot consistency guarantee across pages. No statistically independent observation claim.
3. Date gaps invalidate period-delta outputs; gaps are not imputed.
4. No arbitrary accounting equalities are imposed. Some numeric balances may be negative; investigate with research-quality checks rather than blanket rules.
5. CI includes a three-record **synthetic** fixture for database execution, not a substitute for your 3,000-record local integration.
6. Full-source 1.61M scale, feature maturity, Parquet publication, and model evaluation remain future gates.
7. If Git shows temporary `warehouse_dbt/target` or `warehouse_dbt/logs`, they are excluded via `.gitignore`.
