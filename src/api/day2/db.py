"""SQLAlchemy connection pooling with explicit read-only transactions."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from src.api.day2.config import ISOLATED_DB, WAREHOUSE_SCHEMA, Settings


def make_engine(settings: Settings) -> Engine:
    return create_engine(settings.database_url(), pool_size=5, max_overflow=5,
                         pool_pre_ping=True, pool_timeout=5, connect_args={"connect_timeout": 5})


@contextmanager
def read_connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as conn, conn.begin():
        conn.execute(text("SET TRANSACTION READ ONLY"))
        ident = conn.execute(text("SELECT current_database(), current_user")).one()
        if tuple(ident) != (ISOLATED_DB, "flowwatch_api_reader"):
            raise RuntimeError("Refusing unexpected DB identity")
        yield conn


def check_warehouse(conn: Connection) -> dict[str, Any]:
    tables = ["dim_country", "dim_project", "dim_credit", "fct_credit_period", "mart_credit_period_metrics"]
    missing = [t for t in tables if conn.execute(text("SELECT to_regclass(:name)"),
                 {"name": f"{WAREHOUSE_SCHEMA}.{t}"}).scalar() is None]
    if missing:
        raise RuntimeError("dbt warehouse not built: " + ", ".join(missing))
    return {"database": ISOLATED_DB, "schema": WAREHOUSE_SCHEMA, "tables_verified": len(tables)}
