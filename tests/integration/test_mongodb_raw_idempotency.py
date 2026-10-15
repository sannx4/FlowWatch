from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.mongodb_indexes import (
    RAW_PAGES_COLLECTION,
    RAW_RECORDS_COLLECTION,
    ensure_raw_indexes,
)
from src.ingestion.mongodb_raw_loader import (
    MongoRawLoader,
)
from src.ingestion.raw_envelope import (
    RawPageEnvelope,
    RawRecordEnvelope,
)

TEST_DATABASE = "flowwatch_day16_test"

DATASET_ID = "DAY16_TEST_DATASET"

RESOURCE_ID = "DAY16_TEST_RESOURCE"


def _require_mongodb_integration() -> None:
    if (
        os.getenv(
            "FLOWWATCH_RUN_MONGODB_INTEGRATION"
        )
        != "1"
    ):
        pytest.skip(
            "MongoDB integration test is opt-in."
        )


def _build_page_and_records(
    *,
    run_id: UUID,
) -> tuple[
    RawPageEnvelope,
    list[RawRecordEnvelope],
]:
    """
    Build the same deterministic 100-record source page
    for any supplied ingestion run.

    Source keys remain stable across runs because run_id
    is intentionally excluded from deterministic source
    identity.
    """

    retrieved_at = datetime(
        2026,
        10,
        15,
        12,
        0,
        0,
        tzinfo=UTC,
    )

    records_payload = [
        {
            "credit_number": (
                f"IDA{index:05d}"
            ),
            "end_of_period": (
                "2024-06-30"
            ),
            "amount": str(
                index * 100
            ),
        }
        for index in range(
            1,
            101,
        )
    ]

    page_payload = {
        "records": (
            records_payload
        ),
        "total": 100,
    }

    raw_bytes = json.dumps(
        page_payload,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    source_checksum = (
        hashlib.sha256(
            raw_bytes
        ).hexdigest()
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
        record_count=100,
        total_count=100,
        raw_bytes=(
            raw_bytes
        ),
        payload=(
            page_payload
        ),
    )

    records = [
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
            record_index=(
                index
            ),
            source_checksum=(
                source_checksum
            ),
            payload=(
                payload
            ),
        )
        for index, payload in enumerate(
            records_payload
        )
    ]

    return (
        page,
        records,
    )


def test_replaying_same_100_records_is_idempotent() -> None:
    """
    Same run + same deterministic source identities must
    create only one logical raw version.
    """

    _require_mongodb_integration()

    mongo_config = (
        load_mongodb_config()
    )

    client = create_mongodb_client(
        mongo_config
    )

    try:
        client.admin.command(
            "ping"
        )

        client.drop_database(
            TEST_DATABASE
        )

        database = client[
            TEST_DATABASE
        ]

        ensure_raw_indexes(
            database
        )

        run_id = uuid4()

        page, records = (
            _build_page_and_records(
                run_id=run_id
            )
        )

        loader = MongoRawLoader(
            database
        )

        first_write = (
            loader.persist_page(
                page=page,
                records=records,
            )
        )

        assert (
            first_write.page_inserted
            is True
        )

        assert (
            first_write.records_inserted
            == 100
        )

        assert (
            first_write.records_existing
            == 0
        )

        second_write = (
            loader.persist_page(
                page=page,
                records=records,
            )
        )

        assert (
            second_write.page_inserted
            is False
        )

        assert (
            second_write.records_inserted
            == 0
        )

        assert (
            second_write.records_existing
            == 100
        )

        raw_page_count = database[
            RAW_PAGES_COLLECTION
        ].count_documents(
            {
                "run_id": str(
                    run_id
                ),
                "page_source_key": (
                    page.page_source_key
                ),
            }
        )

        assert (
            raw_page_count
            == 1
        )

        raw_record_count = database[
            RAW_RECORDS_COLLECTION
        ].count_documents(
            {
                "run_id": str(
                    run_id
                ),
                "source_record_key": {
                    "$in": [
                        record.source_record_key
                        for record
                        in records
                    ]
                },
            }
        )

        assert (
            raw_record_count
            == 100
        )

        stored_record = database[
            RAW_RECORDS_COLLECTION
        ].find_one(
            {
                "run_id": str(
                    run_id
                ),
                "source_record_key": (
                    records[
                        0
                    ].source_record_key
                ),
            }
        )

        assert (
            stored_record
            is not None
        )

        assert (
            stored_record[
                "payload"
            ]
            == records[
                0
            ].payload
        )

        assert (
            stored_record[
                "run_id"
            ]
            == str(
                run_id
            )
        )

    finally:
        client.drop_database(
            TEST_DATABASE
        )

        client.close()


def test_same_source_can_exist_in_different_runs() -> None:
    """
    The deterministic source identity remains stable across
    runs, while MongoDB preserves a separate observation for
    each ingestion run.

    This is required so PostgreSQL can trace using:

        ingestion_run_id + source_record_key
    """

    _require_mongodb_integration()

    mongo_config = (
        load_mongodb_config()
    )

    client = create_mongodb_client(
        mongo_config
    )

    try:
        client.admin.command(
            "ping"
        )

        client.drop_database(
            TEST_DATABASE
        )

        database = client[
            TEST_DATABASE
        ]

        ensure_raw_indexes(
            database
        )

        first_run_id = uuid4()
        second_run_id = uuid4()

        first_page, first_records = (
            _build_page_and_records(
                run_id=(
                    first_run_id
                )
            )
        )

        second_page, second_records = (
            _build_page_and_records(
                run_id=(
                    second_run_id
                )
            )
        )

        assert (
            first_page.page_source_key
            == second_page.page_source_key
        )

        assert (
            [
                record.source_record_key
                for record
                in first_records
            ]
            == [
                record.source_record_key
                for record
                in second_records
            ]
        )

        loader = MongoRawLoader(
            database
        )

        first_write = (
            loader.persist_page(
                page=first_page,
                records=first_records,
            )
        )

        second_write = (
            loader.persist_page(
                page=second_page,
                records=second_records,
            )
        )

        assert (
            first_write.page_inserted
            is True
        )

        assert (
            first_write.records_inserted
            == 100
        )

        assert (
            second_write.page_inserted
            is True
        )

        assert (
            second_write.records_inserted
            == 100
        )

        page_count = database[
            RAW_PAGES_COLLECTION
        ].count_documents(
            {
                "page_source_key": (
                    first_page.page_source_key
                )
            }
        )

        assert (
            page_count
            == 2
        )

        first_record_key = (
            first_records[
                0
            ].source_record_key
        )

        record_count = database[
            RAW_RECORDS_COLLECTION
        ].count_documents(
            {
                "source_record_key": (
                    first_record_key
                )
            }
        )

        assert (
            record_count
            == 2
        )

        first_run_record = database[
            RAW_RECORDS_COLLECTION
        ].find_one(
            {
                "run_id": str(
                    first_run_id
                ),
                "source_record_key": (
                    first_record_key
                ),
            }
        )

        second_run_record = database[
            RAW_RECORDS_COLLECTION
        ].find_one(
            {
                "run_id": str(
                    second_run_id
                ),
                "source_record_key": (
                    first_record_key
                ),
            }
        )

        assert (
            first_run_record
            is not None
        )

        assert (
            second_run_record
            is not None
        )

        assert (
            first_run_record[
                "run_id"
            ]
            != second_run_record[
                "run_id"
            ]
        )

        assert (
            first_run_record[
                "source_record_key"
            ]
            == second_run_record[
                "source_record_key"
            ]
        )

        assert (
            first_run_record[
                "payload"
            ]
            == second_run_record[
                "payload"
            ]
        )

    finally:
        client.drop_database(
            TEST_DATABASE
        )

        client.close()