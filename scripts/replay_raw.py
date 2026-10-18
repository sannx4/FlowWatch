from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from typing import Any

from dotenv import load_dotenv
from pymongo import DESCENDING
from pymongo.database import Database
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.raw_replay import (
    RAW_RECORDS_COLLECTION,
    replay_raw_records,
)


def build_postgres_engine() -> Engine:
    load_dotenv()

    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ[
            "POSTGRES_USER"
        ],
        password=os.environ[
            "POSTGRES_PASSWORD"
        ],
        host=os.getenv(
            "POSTGRES_HOST",
            "localhost",
        ),
        port=int(
            os.getenv(
                "POSTGRES_PORT",
                "5434",
            )
        ),
        database=os.environ[
            "POSTGRES_DB"
        ],
    )

    return create_engine(
        url
    )


def resolve_latest_run_id(
    mongo_database: Database[
        dict[str, Any]
    ],
) -> str:
    collection = mongo_database[
        RAW_RECORDS_COLLECTION
    ]

    document = collection.find_one(
        {},
        {
            "run_id": 1,
        },
        sort=[
            (
                "retrieved_at",
                DESCENDING,
            ),
            (
                "_id",
                DESCENDING,
            ),
        ],
    )

    if document is None:
        raise LookupError(
            "MongoDB raw_records is empty."
        )

    run_id = document.get(
        "run_id"
    )

    if not run_id:
        raise RuntimeError(
            "Latest Mongo raw record has "
            "no run_id."
        )

    return str(
        run_id
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay stored MongoDB raw records "
            "into the PostgreSQL canonical store "
            "without contacting the World Bank API."
        )
    )

    run_group = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    run_group.add_argument(
        "--run-id",
        help=(
            "Replay raw records belonging to "
            "this ingestion run."
        ),
    )

    run_group.add_argument(
        "--latest-run",
        action="store_true",
        help=(
            "Replay the most recently retrieved "
            "MongoDB raw-record run."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Optional maximum number of raw "
            "records to replay."
        ),
    )

    parser.add_argument(
        "--source-record-key",
        action="append",
        dest="source_record_keys",
        default=None,
        help=(
            "Replay a specific source_record_key. "
            "May be supplied multiple times."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if (
        args.limit is not None
        and args.limit <= 0
    ):
        raise SystemExit(
            "--limit must be greater than zero."
        )

    mongo_config = (
        load_mongodb_config()
    )

    mongo_client = (
        create_mongodb_client(
            mongo_config
        )
    )

    postgres = (
        build_postgres_engine()
    )

    try:
        mongo_client.admin.command(
            "ping"
        )

        mongo_database = mongo_client[
            mongo_config.database_name
        ]

        if args.latest_run:
            run_id = (
                resolve_latest_run_id(
                    mongo_database
                )
            )
        else:
            run_id = str(
                args.run_id
            )

        with postgres.begin() as connection:
            result = replay_raw_records(
                mongo_database,
                connection,
                run_id=run_id,
                limit=args.limit,
                source_record_keys=(
                    args.source_record_keys
                ),
            )

        print()
        print(
            "DAY 17 RAW REPLAY COMPLETE"
        )
        print(
            "--------------------------"
        )

        print(
            json.dumps(
                asdict(result),
                indent=2,
            )
        )

        print()
        print(
            "source_api_contacted=false"
        )

        return 0

    finally:
        mongo_client.close()
        postgres.dispose()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )