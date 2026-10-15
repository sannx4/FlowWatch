from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, select

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

TEST_MONGO_DATABASE = (
    "flowwatch_day16_lineage_test"
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


def _require_integration() -> None:
    if (
        os.getenv(
            "FLOWWATCH_RUN_LINEAGE_INTEGRATION"
        )
        != "1"
    ):
        pytest.skip(
            "Day-16 lineage integration test is opt-in."
        )


def _build_postgres_engine():
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


def test_real_sample_traces_postgres_to_exact_mongo_record() -> None:
    """
    Prove the Day-16 lineage chain:

    real source bytes
        -> RawPageEnvelope
        -> RawRecordEnvelope
        -> MongoDB raw landing
        -> PostgreSQL curated snapshot
        -> exact Mongo raw record

    PostgreSQL writes are rolled back at the end.
    MongoDB uses a disposable test database.
    """

    _require_integration()

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

    assert (
        len(
            records
        )
        == 100
    )

    source_checksum = (
        hashlib.sha256(
            raw_bytes
        ).hexdigest()
    )

    run_id = uuid4()

    from datetime import (
        UTC,
        datetime,
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
            len(
                records
            )
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
        _build_postgres_engine()
    )

    try:
        mongo_client.admin.command(
            "ping"
        )

        mongo_client.drop_database(
            TEST_MONGO_DATABASE
        )

        mongo_database = mongo_client[
            TEST_MONGO_DATABASE
        ]

        ensure_raw_indexes(
            mongo_database
        )

        raw_loader = MongoRawLoader(
            mongo_database
        )

        mongo_result = (
            raw_loader.persist_page(
                page=page,
                records=(
                    envelopes
                ),
            )
        )

        assert (
            mongo_result.page_inserted
            is True
        )

        assert (
            mongo_result.records_inserted
            == 100
        )

        with postgres.connect() as connection:
            transaction = (
                connection.begin()
            )

            try:
                last_result = None
                last_envelope = None

                for envelope in envelopes:
                    last_result = (
                        load_curated_record(
                            connection,
                            envelope,
                        )
                    )

                    last_envelope = (
                        envelope
                    )

                assert (
                    last_result
                    is not None
                )

                assert (
                    last_envelope
                    is not None
                )

                snapshot_row = (
                    connection.execute(
                        select(
                            CreditSnapshot
                            .__table__
                            .c
                            .ingestion_run_id,
                            CreditSnapshot
                            .__table__
                            .c
                            .source_checksum,
                            CreditSnapshot
                            .__table__
                            .c
                            .source_record_key,
                            CreditSnapshot
                            .__table__
                            .c
                            .end_of_period,
                            Credit
                            .__table__
                            .c
                            .credit_number,
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
                            CreditSnapshot
                            .__table__
                            .c
                            .credit_snapshot_id
                            == last_result
                            .credit_snapshot_id
                        )
                    ).one()
                )

                assert (
                    snapshot_row.ingestion_run_id
                    == run_id
                )

                assert (
                    snapshot_row.source_checksum
                    == last_envelope.source_checksum
                )

                assert (
                    snapshot_row.source_record_key
                    == last_envelope.source_record_key
                )

                mongo_record = mongo_database[
                    RAW_RECORDS_COLLECTION
                ].find_one(
                    {
                        "run_id": str(
                            snapshot_row.ingestion_run_id
                        ),
                        "source_record_key": (
                            snapshot_row
                            .source_record_key
                        ),
                    }
                )

                assert (
                    mongo_record
                    is not None
                )

                assert (
                    mongo_record[
                        "run_id"
                    ]
                    == str(
                        run_id
                    )
                )

                assert (
                    mongo_record[
                        "source_checksum"
                    ]
                    == snapshot_row.source_checksum
                )

                assert (
                    mongo_record[
                        "source_record_key"
                    ]
                    == snapshot_row.source_record_key
                )

                assert (
                    mongo_record[
                        "payload"
                    ]
                    == last_envelope.payload
                )

                assert (
                    snapshot_row.credit_number
                    == last_envelope.payload[
                        "credit_number"
                    ]
                )

            finally:
                transaction.rollback()

    finally:
        mongo_client.drop_database(
            TEST_MONGO_DATABASE
        )

        mongo_client.close()

        postgres.dispose()