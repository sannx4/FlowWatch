"""Explicit configuration with no fallback to the primary FlowWatch database."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv()
load_dotenv("day2_local/.env", override=True)

ISOLATED_DB = "flowwatch_historical_gate"
WAREHOUSE_SCHEMA = "fw_analytics"


@dataclass(frozen=True)
class Settings:
    database: str
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    jwt_secret: str
    users_file: Path
    ui_origin: str

    def database_url(self) -> URL:
        if self.database != ISOLATED_DB:
            raise ValueError("Day 2 must not connect to the primary FlowWatch database")
        if self.db_user != "flowwatch_api_reader":
            raise ValueError("Day 2 requires the dedicated flowwatch_api_reader role")
        return URL.create(
            "postgresql+psycopg", username=self.db_user,
            password=self.db_password, host=self.db_host,
            port=self.db_port, database=self.database,
        )


def get_settings() -> Settings:
    secret = os.getenv("FLOWWATCH_TOKEN_SECRET", "")
    if len(secret) < 32:
        raise ValueError("FLOWWATCH_TOKEN_SECRET must contain >=32 characters")
    password = os.getenv("FLOWWATCH_API_DB_PASSWORD", "")
    if not password:
        raise ValueError("FLOWWATCH_API_DB_PASSWORD is required")
    db_name = os.getenv("FLOWWATCH_API_DB_NAME", ISOLATED_DB)
    db_user = os.getenv("FLOWWATCH_API_DB_USER", "flowwatch_api_reader")
    if db_name != ISOLATED_DB or db_user != "flowwatch_api_reader":
        raise ValueError("Only isolated DB + dedicated read-only role are permitted")
    users_path = Path(os.getenv("FLOWWATCH_AUTH_USERS_FILE", "day2_local/users.json"))
    return Settings(
        database=db_name, db_user=db_user, db_password=password,
        db_host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        db_port=int(os.getenv("POSTGRES_PORT", "5434")),
        jwt_secret=secret, users_file=users_path,
        ui_origin=os.getenv("FLOWWATCH_UI_ORIGIN", "http://localhost:5173"),
    )
