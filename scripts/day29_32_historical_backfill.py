"""CLI for isolated, real API paginated World Bank raw historical extraction."""
from __future__ import annotations

import argparse
import json
import os
from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from dotenv import load_dotenv
from pymongo import MongoClient
from sqlalchemy import URL, create_engine, text

from src.ingestion.historical_backfill import (
    PG_DATABASE,
    BackfillOptions,
    run_backfill,
)
from src.ingestion.mongodb_connection import create_mongodb_client, load_mongodb_config
from src.ingestion.worldbank_client import WorldBankClientConfig


def _pg_engine():
    load_dotenv(override=False)
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    if host not in ("localhost", "127.0.0.1", "postgres"):
        raise RuntimeError("Postgres host must be local or the compose service")
    password = os.getenv("FLOWWATCH_HISTORICAL_PG_PASSWORD")
    if password is None:
        password = getpass("Password for PostgreSQL flowwatch_ingestor: ")
    if not password:
        raise RuntimeError("Password cannot be empty")
    url = URL.create(
        "postgresql+psycopg", username="flowwatch_ingestor", password=password,
        host=host, port=int(os.getenv("POSTGRES_PORT", "5434")),
        database=PG_DATABASE,
    )
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})


def _mongo_client():
    explicit = os.getenv("FLOWWATCH_HISTORICAL_MONGO_URI")
    if explicit:
        parsed = urlsplit(explicit)
        if parsed.scheme not in ("mongodb", "mongodb+srv") or parsed.hostname not in (
            "localhost", "127.0.0.1", "mongodb", "mongo"
        ):
            raise RuntimeError("Mongo URI must refer to local development MongoDB")
        client = MongoClient(explicit, serverSelectionTimeoutMS=8000)
    else:
        client = create_mongodb_client(load_mongodb_config())
    client.admin.command("ping")
    host = client.address
    if host is None or host[0] not in ("localhost", "127.0.0.1", "mongo", "mongodb"):
        client.close()
        raise RuntimeError("Resolved Mongo host is not local")
    return client


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="Explicitly allow live World Bank API requests")
    p.add_argument("--run-id", type=UUID, help="Resume an existing run by its UUID")
    p.add_argument("--list-runs", action="store_true", help="List recent checkpoint runs without API access")
    p.add_argument("--page-size", type=int, default=1000)
    p.add_argument("--max-pages", type=int, default=3, help="0 = full history (requires --full-history)")
    p.add_argument("--full-history", action="store_true", help="Confirm an uncapped dataset extraction")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--fail-after-pages", type=int, default=0, help="Controlled crash probe; page checkpoints remain durable")
    p.add_argument("--report", type=Path, default=Path("reports/historical-backfill-gate.json"))
    return p


def main() -> int:
    args = _parser().parse_args()
    if not args.list_runs and not args.live:
        raise SystemExit("Refusing live API extraction without --live")
    if args.max_pages == 0 and not args.full_history and not args.list_runs:
        raise SystemExit("Uncapped extraction requires --max-pages 0 --full-history")
    engine = _pg_engine()
    try:
        if args.list_runs:
            with engine.connect() as con:
                rows = con.execute(text("""
                    SELECT run_id, page_size, max_pages, observed_total, status,
                           started_at, last_error
                    FROM public.historical_backfill_runs ORDER BY started_at DESC LIMIT 20
                """)).mappings().all()
                for row in rows:
                    print(json.dumps(dict(row), default=str))
            return 0
        run_id = args.run_id or uuid4()
        print(f"BACKFILL RUN ID: {run_id}", flush=True)
        print("Retain this UUID to resume after interruption.", flush=True)
        options = BackfillOptions(
            run_id=run_id, page_size=args.page_size, max_pages=args.max_pages,
            workers=args.workers, fail_after_pages=args.fail_after_pages,
        )
        mongo = _mongo_client()
        try:
            result = run_backfill(engine, mongo, options, WorldBankClientConfig())
        finally:
            mongo.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"VERIFIED REPORT: {args.report}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
