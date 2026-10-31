"""Restricted, isolated Day25 PostgreSQL connection factory."""
from __future__ import annotations

import os
from getpass import getpass

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Connection, Engine

DATABASE = "flowwatch_day25_gate"
USER = "flowwatch_ingestor"


def engine_for_gate() -> Engine:
    load_dotenv()
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    if host not in ("localhost", "127.0.0.1"):
        raise RuntimeError("Refusing remote database: local gate only")
    password = getpass(f"Password for PostgreSQL {USER}: ")
    if not password:
        raise RuntimeError("Password is required")
    return create_engine(URL.create(
        "postgresql+psycopg", username=USER, password=password, host=host,
        port=int(os.getenv("POSTGRES_PORT", "5434")), database=DATABASE,
    ), pool_pre_ping=True, connect_args={"connect_timeout": 10})


def verify_gate(connection: Connection) -> None:
    identity = connection.execute(text(
        "SELECT current_database(),session_user,current_user"
    )).one()
    if identity != (DATABASE, USER, USER):
        raise RuntimeError("REFUSING WRITE: wrong database or PostgreSQL role")
