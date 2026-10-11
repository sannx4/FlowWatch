from __future__ import annotations

import hashlib
import os

from dotenv import load_dotenv
from pymongo import MongoClient
from sqlalchemy import URL, create_engine, text

from src.transformation.day07 import (
    parse_source_date,
    record_checksum,
)


def build_postgres_engine():
    return create_engine(
        URL.create(
            drivername="postgresql+psycopg",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
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
            database=os.environ["POSTGRES_DB"],
        )
    )


def build_mongo_client() -> MongoClient:
    return MongoClient(
        host=os.getenv(
            "MONGO_HOST",
            "localhost",
        ),
        port=int(
            os.getenv(
                "MONGO_PORT",
                "27018",
            )
        ),
        username=os.environ[
            "MONGO_INITDB_ROOT_USERNAME"
        ],
        password=os.environ[
            "MONGO_INITDB_ROOT_PASSWORD"
        ],
        authSource="admin",
        serverSelectionTimeoutMS=5000,
    )


def main() -> None:
    load_dotenv()

    postgres = build_postgres_engine()
    mongo = build_mongo_client()

    try:
        with postgres.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        c.credit_number,
                        cs.end_of_period,
                        cs.ingestion_run_id::text
                            AS run_id,
                        cs.source_record_key,
                        cs.source_checksum
                    FROM credit_snapshots cs
                    JOIN credits c
                      ON c.credit_id = cs.credit_id
                    WHERE cs.ingestion_run_id IS NOT NULL
                      AND cs.source_record_key IS NOT NULL
                      AND cs.source_checksum IS NOT NULL
                    ORDER BY cs.end_of_period
                    LIMIT 1
                    """
                )
            ).mappings().one()

        database = mongo[
            os.environ["MONGO_INITDB_DATABASE"]
        ]

        raw_record = database[
            "day07_raw_records"
        ].find_one(
            {
                "run_id": row["run_id"],
                "source_record_key": (
                    row["source_record_key"]
                ),
            }
        )

        if raw_record is None:
            raise RuntimeError(
                "Matching Mongo raw record not found."
            )

        payload = raw_record["payload"]

        calculated_checksum = record_checksum(
            payload
        )

        if calculated_checksum != row["source_checksum"]:
            raise RuntimeError(
                "Record checksum mismatch."
            )

        if (
            payload["credit_number"]
            != row["credit_number"]
        ):
            raise RuntimeError(
                "Credit number mismatch."
            )

        if (
            parse_source_date(
                payload["end_of_period"]
            )
            != row["end_of_period"]
        ):
            raise RuntimeError(
                "end_of_period mismatch."
            )

        raw_payload = database[
            "day07_raw_payloads"
        ].find_one(
            {
                "_id": raw_record[
                    "source_file_checksum"
                ]
            }
        )

        if raw_payload is None:
            raise RuntimeError(
                "Exact raw payload not found."
            )

        stored_bytes = bytes(
            raw_payload["raw_bytes"]
        )

        stored_file_checksum = hashlib.sha256(
            stored_bytes
        ).hexdigest()

        if (
            stored_file_checksum
            != raw_record["source_file_checksum"]
        ):
            raise RuntimeError(
                "Raw file checksum mismatch."
            )

        print()
        print("DAY 7 LINEAGE VERIFIED")
        print("----------------------")

        print(
            f"credit_number="
            f"{row['credit_number']}"
        )

        print(
            f"end_of_period="
            f"{row['end_of_period']}"
        )

        print(
            f"run_id="
            f"{row['run_id']}"
        )

        print(
            f"source_record_key="
            f"{row['source_record_key']}"
        )

        print(
            f"postgres_source_checksum="
            f"{row['source_checksum']}"
        )

        print(
            f"mongo_source_checksum="
            f"{raw_record['source_checksum']}"
        )

        print(
            f"raw_file_sha256="
            f"{stored_file_checksum}"
        )

        print()
        print(
            "PostgreSQL -> Mongo raw record: OK"
        )

        print(
            "Mongo raw record checksum: OK"
        )

        print(
            "Exact raw source bytes checksum: OK"
        )

        print()
        print("LINEAGE PROOF: SUCCESS")

    finally:
        postgres.dispose()
        mongo.close()


if __name__ == "__main__":
    main()