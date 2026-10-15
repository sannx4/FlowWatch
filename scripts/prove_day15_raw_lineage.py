from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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


def find_index_plan(
    value: Any,
    index_name: str,
) -> dict[str, Any] | None:
    """
    Recursively search a MongoDB explain document
    for the requested index.
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
            return value

        for child in (
            value.values()
        ):
            match = find_index_plan(
                child,
                index_name,
            )

            if match is not None:
                return match

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            match = find_index_plan(
                child,
                index_name,
            )

            if match is not None:
                return match

    return None


def main() -> None:
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--keep",
        action="store_true",
        help=(
            "Keep proof documents "
            "after the run."
        ),
    )

    args = parser.parse_args()

    mongo_config = (
        load_mongodb_config()
    )

    database_name = (
        mongo_config.database_name
    )

    run_id = uuid4()

    retrieved_at = datetime.now(
        UTC
    )

    source_record = {
        "credit_number": (
            "IDA00010"
        ),
        "end_of_period": (
            "2024-06-30"
        ),
        "credit_status": (
            "Disbursing"
        ),
        "original_principal_amount": (
            "1000.00"
        ),
        "test_nested_payload": {
            "value": (
                "preserve-me"
            ),
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

    source_checksum = (
        hashlib.sha256(
            raw_bytes
        ).hexdigest()
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
            started_at=(
                retrieved_at
            ),
            referenced_at=(
                retrieved_at
            ),
            status="running",
            code_version=(
                "day15-proof"
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
            retrieved_at=(
                retrieved_at
            ),
            page_number=1,
            page_offset=0,
            source_checksum=(
                source_checksum
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
            retrieved_at=(
                retrieved_at
            ),
            page_number=1,
            page_offset=0,
            record_index=0,
            source_checksum=(
                source_checksum
            ),
            payload=(
                source_record
            ),
        )
    )

    client = (
        create_mongodb_client(
            mongo_config
        )
    )

    database = client[
        database_name
    ]

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

        index_plan = (
            find_index_plan(
                explain,
                RAW_RECORD_SOURCE_IDENTITY_INDEX,
            )
        )

        if index_plan is None:
            raise AssertionError(
                "MongoDB explain did not "
                "show the expected source "
                "identity index."
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

        if len(
            documents
        ) != 1:
            raise AssertionError(
                "Expected exactly one "
                "raw source record."
            )

        restored = (
            RawRecordEnvelope
            .from_mongo_document(
                documents[0]
            )
        )

        reconstructed_payload = (
            restored
            .reconstruct_payload()
        )

        if (
            reconstructed_payload
            != source_record
        ):
            raise AssertionError(
                "Raw source payload changed "
                "during MongoDB storage."
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

        if page_document is None:
            raise AssertionError(
                "Raw page could not be "
                "reconstructed."
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

        if (
            reconstructed_raw_bytes
            != raw_bytes
        ):
            raise AssertionError(
                "Raw HTTP bytes changed "
                "during MongoDB storage."
            )

        reconstructed_checksum = (
            hashlib.sha256(
                reconstructed_raw_bytes
            ).hexdigest()
        )

        if (
            reconstructed_checksum
            != source_checksum
        ):
            raise AssertionError(
                "Reconstructed raw bytes "
                "do not match the stored "
                "SHA-256 checksum."
            )

        proof = {
            "status": (
                "PASS"
            ),
            "database": (
                database_name
            ),
            "run_id": str(
                run_id
            ),
            "collection": (
                RAW_RECORDS_COLLECTION
            ),
            "index": (
                RAW_RECORD_SOURCE_IDENTITY_INDEX
            ),
            "explain_stage": (
                index_plan.get(
                    "stage",
                    "index-plan",
                )
            ),
            "payload_equal": (
                True
            ),
            "raw_bytes_equal": (
                True
            ),
            "checksum_equal": (
                True
            ),
            "checksum": (
                source_checksum
            ),
        }

        print(
            json.dumps(
                proof,
                indent=2,
                default=str,
            )
        )

    finally:
        if not args.keep:
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


if __name__ == "__main__":
    main()