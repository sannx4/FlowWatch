from __future__ import annotations

import argparse
import json
import os
from datetime import date
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import (
    URL,
    create_engine,
    select,
)

from src.db.models import (
    Credit,
    CreditSnapshot,
)
from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.mongodb_indexes import (
    RAW_RECORDS_COLLECTION,
)


def build_postgres_engine():
    """
    Create the PostgreSQL engine using the existing
    FlowWatch environment configuration.
    """

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


def _json_safe_document(
    document: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:
    """
    Convert Mongo-specific values such as ObjectId into
    printable values without modifying the stored document.
    """

    result = dict(
        document
    )

    if "_id" in result:
        result[
            "_id"
        ] = str(
            result[
                "_id"
            ]
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Trace one PostgreSQL credit snapshot "
            "back to its exact MongoDB raw source record."
        )
    )

    parser.add_argument(
        "--credit-number",
        required=True,
        help=(
            "Credit number stored in PostgreSQL."
        ),
    )

    parser.add_argument(
        "--end-of-period",
        required=True,
        help=(
            "Reporting period in YYYY-MM-DD format."
        ),
    )

    args = parser.parse_args()

    try:
        period = date.fromisoformat(
            args.end_of_period
        )
    except ValueError:
        print(
            "ERROR: --end-of-period must "
            "use YYYY-MM-DD format."
        )
        return 2

    postgres = (
        build_postgres_engine()
    )

    mongo_config = (
        load_mongodb_config()
    )

    mongo_client = (
        create_mongodb_client(
            mongo_config
        )
    )

    try:
        with postgres.connect() as connection:
            row = (
                connection.execute(
                    select(
                        CreditSnapshot
                        .__table__
                        .c
                        .credit_snapshot_id
                        .label(
                            "credit_snapshot_id"
                        ),
                        Credit
                        .__table__
                        .c
                        .credit_number
                        .label(
                            "credit_number"
                        ),
                        CreditSnapshot
                        .__table__
                        .c
                        .end_of_period
                        .label(
                            "end_of_period"
                        ),
                        CreditSnapshot
                        .__table__
                        .c
                        .ingestion_run_id
                        .label(
                            "ingestion_run_id"
                        ),
                        CreditSnapshot
                        .__table__
                        .c
                        .source_checksum
                        .label(
                            "source_checksum"
                        ),
                        CreditSnapshot
                        .__table__
                        .c
                        .source_record_key
                        .label(
                            "source_record_key"
                        ),
                    )
                    .join(
                        Credit.__table__,
                        (
                            CreditSnapshot
                            .__table__
                            .c
                            .credit_id
                            == Credit
                            .__table__
                            .c
                            .credit_id
                        ),
                    )
                    .where(
                        Credit
                        .__table__
                        .c
                        .credit_number
                        == args.credit_number,
                        CreditSnapshot
                        .__table__
                        .c
                        .end_of_period
                        == period,
                    )
                ).one_or_none()
            )

        if row is None:
            print(
                "LINEAGE STATUS: NOT FOUND"
            )

            print(
                "No PostgreSQL snapshot matched "
                f"{args.credit_number} / "
                f"{period.isoformat()}."
            )

            return 3

        if (
            row.ingestion_run_id
            is None
            or row.source_checksum
            is None
            or row.source_record_key
            is None
        ):
            print(
                "LINEAGE STATUS: INCOMPLETE"
            )

            print(
                "The PostgreSQL snapshot exists "
                "but its Day-16 lineage fields "
                "are incomplete."
            )

            return 4

        mongo_database = mongo_client[
            mongo_config.database_name
        ]

        raw_document = mongo_database[
            RAW_RECORDS_COLLECTION
        ].find_one(
            {
                "run_id": str(
                    row.ingestion_run_id
                ),
                "source_record_key": (
                    row.source_record_key
                ),
            }
        )

        if raw_document is None:
            print(
                "LINEAGE STATUS: BROKEN"
            )

            print(
                "PostgreSQL lineage exists, but "
                "the corresponding Mongo raw "
                "record was not found."
            )

            return 5

        run_matches = (
            raw_document.get(
                "run_id"
            )
            == str(
                row.ingestion_run_id
            )
        )

        checksum_matches = (
            raw_document.get(
                "source_checksum"
            )
            == row.source_checksum
        )

        key_matches = (
            raw_document.get(
                "source_record_key"
            )
            == row.source_record_key
        )

        lineage_matches = (
            run_matches
            and checksum_matches
            and key_matches
        )

        result = {
            "lineage_status": (
                "MATCH"
                if lineage_matches
                else "MISMATCH"
            ),
            "postgres_snapshot": {
                "credit_snapshot_id": (
                    row.credit_snapshot_id
                ),
                "credit_number": (
                    row.credit_number
                ),
                "end_of_period": (
                    row
                    .end_of_period
                    .isoformat()
                ),
                "ingestion_run_id": str(
                    row.ingestion_run_id
                ),
                "source_checksum": (
                    row.source_checksum
                ),
                "source_record_key": (
                    row.source_record_key
                ),
            },
            "checks": {
                "run_id_match": (
                    run_matches
                ),
                "source_checksum_match": (
                    checksum_matches
                ),
                "source_record_key_match": (
                    key_matches
                ),
            },
            "mongo_raw_record": (
                _json_safe_document(
                    raw_document
                )
            ),
        }

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )

        if not lineage_matches:
            return 6

        return 0

    finally:
        mongo_client.close()

        postgres.dispose()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )