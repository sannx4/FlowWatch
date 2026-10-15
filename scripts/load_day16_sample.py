from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine

from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.mongodb_indexes import (
    ensure_raw_indexes,
)
from src.ingestion.mongodb_raw_loader import (
    MongoRawLoader,
)
from src.ingestion.postgres_curated_loader import (
    load_curated_record,
)
from src.ingestion.raw_envelope import (
    RawPageEnvelope,
    RawRecordEnvelope,
)
from src.transformation.day07 import (
    transform_record,
)

SAMPLE_PATH = Path(
    "data/raw/world_bank_sample.json"
)

DATASET_ID = (
    "world_bank_ida_statement_of_credits"
)

RESOURCE_ID = (
    "world_bank_sample_day16"
)


def build_postgres_engine():
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


def main() -> int:
    raw_bytes = (
        SAMPLE_PATH.read_bytes()
    )

    source_payload = json.loads(
        raw_bytes.decode(
            "utf-8"
        )
    )

    records = source_payload[
        "data"
    ]

    if len(records) != 100:
        raise RuntimeError(
            "Expected exactly 100 records "
            "in the Day-16 sample."
        )

    source_checksum = (
        hashlib.sha256(
            raw_bytes
        ).hexdigest()
    )

    # Deterministic run identity for the persisted
    # Day-16 sample proof.
    #
    # Re-running the same source bytes with the same
    # selected record count exercises same-run
    # idempotency.
    run_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        (
            "flowwatch:day16:"
            f"{source_checksum}:"
            f"{len(records)}"
        ),
    )

    retrieved_at = datetime.now(
        UTC
    )

    page = RawPageEnvelope(
        run_id=run_id,
        dataset_id=(
            DATASET_ID
        ),
        resource_id=(
            RESOURCE_ID
        ),
        retrieved_at=(
            retrieved_at
        ),
        page_number=1,
        page_offset=0,
        source_checksum=(
            source_checksum
        ),
        record_count=(
            len(records)
        ),
        total_count=int(
            source_payload[
                "count"
            ]
        ),
        raw_bytes=(
            raw_bytes
        ),
        payload=(
            source_payload
        ),
    )

    envelopes = [
        RawRecordEnvelope.from_source_payload(
            run_id=run_id,
            dataset_id=(
                DATASET_ID
            ),
            resource_id=(
                RESOURCE_ID
            ),
            retrieved_at=(
                retrieved_at
            ),
            page_number=1,
            page_offset=0,
            record_index=index,
            source_checksum=(
                source_checksum
            ),
            payload=record,
        )
        for index, record
        in enumerate(
            records
        )
    ]

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

        ensure_raw_indexes(
            mongo_database
        )

        mongo_loader = MongoRawLoader(
            mongo_database
        )

        mongo_result = (
            mongo_loader.persist_page(
                page=page,
                records=envelopes,
            )
        )

        with postgres.begin() as connection:
            for envelope in envelopes:
                load_curated_record(
                    connection,
                    envelope,
                )

        first_payload = (
            envelopes[
                0
            ].payload
        )

        if not isinstance(
            first_payload,
            dict,
        ):
            raise TypeError(
                "Expected first source payload "
                "to be a mapping."
            )

        first_transformed = (
            transform_record(
                first_payload
            )
        )

        first_end_of_period = (
            first_transformed[
                "snapshot"
            ][
                "end_of_period"
            ]
        )

        if first_end_of_period is None:
            raise RuntimeError(
                "First transformed record has "
                "no end_of_period."
            )

        print()
        print(
            "DAY 16 SAMPLE LOAD COMPLETE"
        )
        print(
            "---------------------------"
        )
        print(
            f"run_id={run_id}"
        )
        print(
            "source_checksum="
            f"{source_checksum}"
        )
        print(
            "page_source_key="
            f"{page.page_source_key}"
        )
        print(
            "mongo_page_inserted="
            f"{mongo_result.page_inserted}"
        )
        print(
            "mongo_records_inserted="
            f"{mongo_result.records_inserted}"
        )
        print(
            "mongo_records_existing="
            f"{mongo_result.records_existing}"
        )
        print(
            "postgres_records_loaded="
            f"{len(envelopes)}"
        )

        print()
        print(
            "TRACE COMMAND"
        )
        print(
            "-------------"
        )

        print(
            "python -m scripts.trace_lineage "
            "--credit-number "
            f"\"{first_payload['credit_number']}\" "
            "--end-of-period "
            f"\"{first_end_of_period.isoformat()}\""
        )

        return 0

    finally:
        mongo_client.close()

        postgres.dispose()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )