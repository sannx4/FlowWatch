"""Day34-38: isolated historical dbt warehouse preflight/build/reconciliation.

Build requires --build. NEVER connects to the original flowwatch database.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import date
from decimal import Decimal
from getpass import getpass
from pathlib import Path
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Connection, Engine

DB_NAME = "flowwatch_historical_gate"
WAREHOUSE_SCHEMA = "fw_analytics"
OWNER = "flowwatch_owner"
EXPECTED_ALEMBIC = "d33c00000001"
ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "warehouse_dbt"
DEFAULT_REPORT = ROOT / "reports" / "day34-38-warehouse-gate.json"


class WarehouseGateError(RuntimeError):
    """Reject unsafe database identity, incomplete source, or warehouse differences."""


def _connection_settings() -> tuple[str, int, str]:
    load_dotenv(override=False)
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    if host not in {"localhost", "127.0.0.1"}:
        raise WarehouseGateError("REFUSING: warehouse PostgreSQL host must be local")
    port = int(os.getenv("POSTGRES_PORT", "5434"))
    if not 1 <= port <= 65535:
        raise WarehouseGateError("Invalid PostgreSQL port")
    password = os.getenv("FLOWWATCH_DBT_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    if not password:
        password = getpass("Password for isolated PostgreSQL flowwatch_owner: ")
    if not password:
        raise WarehouseGateError("Empty database password")
    return host, port, password


def connect_isolated(host: str, port: int, password: str) -> Engine:
    return create_engine(
        URL.create("postgresql+psycopg", username=OWNER, password=password,
                   host=host, port=port, database=DB_NAME),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def validate_source(connection: Connection, run_id: UUID) -> dict[str, Any]:
    identity = connection.execute(text(
        "SELECT current_database(), session_user, current_user"
    )).one()
    if tuple(identity) != (DB_NAME, OWNER, OWNER):
        raise WarehouseGateError(f"REFUSING wrong PG identity: {tuple(identity)}")
    version = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()
    if version != EXPECTED_ALEMBIC:
        raise WarehouseGateError(f"Expected Alembic {EXPECTED_ALEMBIC}, found {version}")
    published = connection.execute(text("""
        SELECT p.run_id, p.source_pages, p.source_records, p.accepted,
               p.rejected, p.inserted, p.updated, p.unchanged,
               p.ignored, p.publication_status, r.status as ingestion_status
        FROM public.historical_canonical_publications p
        JOIN public.historical_backfill_runs r ON r.run_id = p.run_id
        WHERE p.run_id = :rid
    """), {"rid": run_id}).mappings().one_or_none()
    if published is None:
        raise WarehouseGateError("No committed Day33 canonical publication for requested run")
    info = dict(published)
    if info["ingestion_status"] != "COMPLETE" or info["publication_status"] != "PASS":
        raise WarehouseGateError("Historical source is not COMPLETE and PASS")
    if int(info["source_records"]) != int(info["accepted"]) + int(info["rejected"]):
        raise WarehouseGateError("Historical publication source balance failed")
    if int(info["accepted"]) != sum(int(info[k]) for k in
       ("inserted", "updated", "unchanged", "ignored")):
        raise WarehouseGateError("Historical publication outcome balance failed")
    decisions = connection.execute(text("""
        SELECT count(*) as total,
               count(*) FILTER (WHERE outcome = 'REJECTED') as rejected,
               count(*) FILTER (WHERE outcome != 'REJECTED') as accepted
        FROM public.historical_canonical_decisions WHERE run_id=:rid
    """), {"rid": run_id}).mappings().one()
    if (decisions["total"] != info["source_records"]
            or decisions["accepted"] != info["accepted"]
            or decisions["rejected"] != info["rejected"]):
        raise WarehouseGateError("Historical publication ledger count mismatch")
    canonical = connection.execute(text("""
        SELECT count(*) as rows, count(distinct credit_id) as credits,
               min(end_of_period) as first_period, max(end_of_period) as last_period
        FROM public.credit_snapshots
    """)).mappings().one()
    if int(canonical["rows"]) == 0:
        raise WarehouseGateError("No historical canonical snapshots in isolated database")
    return {
        "run_id": str(run_id), "published_observations": int(info["source_records"]),
        "published_accepted": int(info["accepted"]),
        "published_rejected": int(info["rejected"]),
        "canonical_snapshot_rows": int(canonical["rows"]),
        "canonical_credits": int(canonical["credits"]),
        "first_period": canonical["first_period"], "last_period": canonical["last_period"],
    }


def validate_warehouse(connection: Connection, source: dict[str, Any]) -> dict[str, Any]:
    # Fixed identifiers only; NEVER interpolate input into SQL relation names.
    expected_tables = (
        "fw_analytics.dim_country", "fw_analytics.dim_project",
        "fw_analytics.dim_credit", "fw_analytics.fct_credit_period",
        "fw_analytics.mart_credit_period_metrics",
    )
    for table in expected_tables:
        if connection.execute(text("SELECT to_regclass(:name)"),
                              {"name": table}).scalar_one() is None:
            raise WarehouseGateError(f"Missing warehouse object: {table}")
    result = connection.execute(text("""
        SELECT (SELECT count(*) FROM public.credit_snapshots) as source_count,
               (SELECT count(*) FROM fw_analytics.fct_credit_period) as fact_count,
               (SELECT count(*) FROM fw_analytics.mart_credit_period_metrics) as metric_count,
               (SELECT count(*) FROM public.credits) as source_credit_count,
               (SELECT count(*) FROM fw_analytics.dim_credit) as dim_credit_count,
               (SELECT count(*) FROM public.projects) as source_project_count,
               (SELECT count(*) FROM fw_analytics.dim_project) as dim_project_count,
               (SELECT count(*) FROM public.countries) as source_country_count,
               (SELECT count(*) FROM fw_analytics.dim_country) as dim_country_count,
               (SELECT count(*) FROM fw_analytics.mart_credit_period_metrics
                WHERE is_consecutive_month) as adjacent_observations,
               (SELECT count(*) FROM fw_analytics.mart_credit_period_metrics
                WHERE not is_consecutive_month) as nonadjacent_observations
    """)).mappings().one()
    for a, b in (("source_count", "fact_count"),
                 ("fact_count", "metric_count"),
                 ("source_credit_count", "dim_credit_count"),
                 ("source_project_count", "dim_project_count"),
                 ("source_country_count", "dim_country_count")):
        if result[a] != result[b]:
            raise WarehouseGateError(f"Warehouse cardinality mismatch: {a} != {b}")
    if int(result["fact_count"]) != source["canonical_snapshot_rows"]:
        raise WarehouseGateError("Canonical source changed during dbt materialization")
    # Independent two-way equality by natural source ID and *exact* source values.
    # These checks are also encoded as singular dbt tests.
    diff = connection.execute(text("""
        SELECT count(*)
        FROM public.credit_snapshots s
        FULL OUTER JOIN fw_analytics.fct_credit_period f
          ON s.credit_snapshot_id=f.credit_snapshot_id
        WHERE s.credit_snapshot_id IS NULL OR f.credit_snapshot_id IS NULL
          OR s.credit_id IS DISTINCT FROM f.credit_id
          OR s.end_of_period IS DISTINCT FROM f.end_of_period
          OR s.disbursed_amount_usd IS DISTINCT FROM f.disbursed_amount_usd
          OR s.undisbursed_amount_usd IS DISTINCT FROM f.undisbursed_amount_usd
          OR s.repaid_to_ida_usd IS DISTINCT FROM f.repaid_to_ida_usd
          OR s.borrowers_obligation_usd IS DISTINCT FROM f.borrowers_obligation_usd
          OR s.source_record_key IS DISTINCT FROM f.source_record_key
          OR s.source_checksum IS DISTINCT FROM f.source_checksum
    """)).scalar_one()
    if diff:
        raise WarehouseGateError(f"Warehouse differs from operational source: {diff} rows")
    return {key: int(value) for key, value in result.items()}


def _json_default(value: object) -> str:
    if isinstance(value, (date, Decimal, UUID)):
        return str(value)
    raise TypeError(f"Unsupported report value: {type(value).__name__}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, required=True)
    parser.add_argument("--build", action="store_true", help="Explicitly execute dbt build and tests")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    host, port, password = _connection_settings()
    engine = connect_isolated(host, port, password)
    try:
        with engine.connect() as connection:
            source = validate_source(connection, args.run_id)
        if not args.build:
            result: dict[str, Any] = {"status": "PASS_DBT_WAREHOUSE_PREFLIGHT",
                                      "warehouse_built": False, "source": source}
        else:
            environment = os.environ.copy()
            environment.update({
                "FLOWWATCH_DBT_PASSWORD": password,
                "POSTGRES_HOST": host,
                "POSTGRES_PORT": str(port),
            })
            try:
                subprocess.run([
                    "dbt", "build", "--project-dir", str(PROJECT),
                    "--profiles-dir", str(PROJECT), "--target", "isolated",
                ], env=environment, cwd=ROOT, check=True)
            except FileNotFoundError as exc:
                raise WarehouseGateError(
                    "dbt executable missing: install requirements-dbt.txt"
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise WarehouseGateError(f"dbt build/tests failed ({exc.returncode})") from exc
            with engine.connect() as connection:
                second = validate_source(connection, args.run_id)
                if second != source:
                    raise WarehouseGateError("Canonical source changed during warehouse build")
                warehouse = validate_warehouse(connection, source)
            result = {"status": "PASS_DBT_FINANCIAL_WAREHOUSE",
                      "warehouse_built": True,
                      "database": DB_NAME, "schema": WAREHOUSE_SCHEMA,
                      "source": source, "warehouse": warehouse,
                      "research_limitation": (
                          "Bounded source capture; not independent samples or complete history. "
                          "Period-end stock changes are not verified cash flows."
                      )}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, default=_json_default) + "\n",
                               encoding="utf-8")
        print(json.dumps(result, indent=2, default=_json_default))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
