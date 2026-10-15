from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.mongodb_indexes import (
    INGESTION_RUNS_COLLECTION,
    RAW_PAGES_COLLECTION,
    RAW_RECORD_SOURCE_IDENTITY_INDEX,
    RAW_RECORDS_COLLECTION,
    ensure_raw_indexes,
)
from src.ingestion.raw_envelope import (
    RawIngestionRunReference,
    RawPageEnvelope,
    RawRecordEnvelope,
)
from src.ingestion.worldbank_client import (
    DEFAULT_DATASET_ID,
    DEFAULT_RESOURCE_ID,
)

pytestmark = pytest.mark.skipif(
    os.getenv(
        "FLOWWATCH_RUN_MONGODB_INTEGRATION"
    )
    != "1",
    reason=(
        "MongoDB integration test "
        "requires explicit opt-in"
    ),
)


TEST_DATABASE = (
    "flowwatch_day15_test"
)


def explain_uses_index(
    value: Any,
    index_name: str,
) -> bool:
    """
    Search a MongoDB explain document for
    the expected index name.
    """

    if isinstance(
        value,
        dict,
    ):
        if (
            value.get(
                "indexName"
            )
            == index_name
        ):
            return True

        return any(
            explain_uses_index(
                child,
                index_name,
            )
            for child in value.values()
        )

    if isinstance(
        value,
        list,
    ):
        return any(
            explain_uses_index(
                child,
                index_name,
            )
            for child in value
        )

    return False


def test_source_identity_index_and_payload_reconstruction() -> None:
    mongo_config = (
        load_mongodb_config()
    )

    client = (
        create_mongodb_client(
            mongo_config
        )
    )

    database = client[
        TEST_DATABASE
    ]

    run_id = uuid4()

    now = datetime.now(
        UTC
    )

    source_record = {
        "credit_number": (
            "IDA00010"
        ),
        "end_of_period": (
            "2024-06-30"
        ),
        "amount": (
            "1000.00"
        ),
        "nested": {
            "unchanged": True,
        },
    }

    page_payload = {
        "count": 1,
        "data": [
            source_record
        ],
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

    checksum = (
        hashlib.sha256(
            raw_bytes
        ).hexdigest()
    )

    run_inserted = False
    page_inserted = False
    record_inserted = False

    try:
        client.admin.command(
            "ping"
        )

        ensure_raw_indexes(
            database
        )

        run_reference = (
            RawIngestionRunReference(
                run_id=run_id,
                dataset_id=(
                    DEFAULT_DATASET_ID
                ),
                resource_id=(
                    DEFAULT_RESOURCE_ID
                ),
                started_at=now,
                referenced_at=now,
                status="running",
                code_version=(
                    "day15-integration-test"
                ),
            )
        )

        page_envelope = (
            RawPageEnvelope(
                run_id=run_id,
                dataset_id=(
                    DEFAULT_DATASET_ID
                ),
                resource_id=(
                    DEFAULT_RESOURCE_ID
                ),
                retrieved_at=now,
                page_number=1,
                page_offset=0,
                source_checksum=(
                    checksum
                ),
                record_count=1,
                total_count=1,
                raw_bytes=raw_bytes,
                payload=(
                    page_payload
                ),
            )
        )

        record_envelope = (
            RawRecordEnvelope
            .from_source_payload(
                run_id=run_id,
                dataset_id=(
                    DEFAULT_DATASET_ID
                ),
                resource_id=(
                    DEFAULT_RESOURCE_ID
                ),
                retrieved_at=now,
                page_number=1,
                page_offset=0,
                record_index=0,
                source_checksum=(
                    checksum
                ),
                payload=(
                    source_record
                ),
            )
        )

        database[
            INGESTION_RUNS_COLLECTION
        ].insert_one(
            run_reference
            .to_mongo_document()
        )

        run_inserted = True

        database[
            RAW_PAGES_COLLECTION
        ].insert_one(
            page_envelope
            .to_mongo_document()
        )

        page_inserted = True

        database[
            RAW_RECORDS_COLLECTION
        ].insert_one(
            record_envelope
            .to_mongo_document()
        )

        record_inserted = True

        query = {
            "dataset_id": (
                DEFAULT_DATASET_ID
            ),
            "resource_id": (
                DEFAULT_RESOURCE_ID
            ),
            "credit_number": (
                "IDA00010"
            ),
            "end_of_period": (
                "2024-06-30"
            ),
        }

        cursor = (
            database[
                RAW_RECORDS_COLLECTION
            ]
            .find(
                query
            )
            .hint(
                RAW_RECORD_SOURCE_IDENTITY_INDEX
            )
            .limit(
                1
            )
        )

        explain = (
            cursor.explain()
        )

        assert explain_uses_index(
            explain,
            RAW_RECORD_SOURCE_IDENTITY_INDEX,
        )

        documents = list(
            database[
                RAW_RECORDS_COLLECTION
            ]
            .find(
                query
            )
            .hint(
                RAW_RECORD_SOURCE_IDENTITY_INDEX
            )
            .limit(
                1
            )
        )

        assert len(
            documents
        ) == 1

        restored_record = (
            RawRecordEnvelope
            .from_mongo_document(
                documents[0]
            )
        )

        assert (
            restored_record
            .reconstruct_payload()
            == source_record
        )

        page_document = (
            database[
                RAW_PAGES_COLLECTION
            ].find_one(
                {
                    "run_id": str(
                        run_id
                    ),
                    "page_number": 1,
                }
            )
        )

        assert (
            page_document
            is not None
        )

        restored_page = (
            RawPageEnvelope
            .from_mongo_document(
                page_document
            )
        )

        reconstructed_raw_bytes = (
            restored_page
            .reconstruct_raw_bytes()
        )

        assert (
            reconstructed_raw_bytes
            == raw_bytes
        )

        reconstructed_checksum = (
            hashlib.sha256(
                reconstructed_raw_bytes
            ).hexdigest()
        )

        assert (
            reconstructed_checksum
            == checksum
        )

    finally:
        if record_inserted:
            database[
                RAW_RECORDS_COLLECTION
            ].delete_many(
                {
                    "run_id": str(
                        run_id
                    )
                }
            )

        if page_inserted:
            database[
                RAW_PAGES_COLLECTION
            ].delete_many(
                {
                    "run_id": str(
                        run_id
                    )
                }
            )

        if run_inserted:
            database[
                INGESTION_RUNS_COLLECTION
            ].delete_many(
                {
                    "run_id": str(
                        run_id
                    )
                }
            )

        client.close()