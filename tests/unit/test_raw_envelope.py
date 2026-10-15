from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest
from bson import BSON
from bson.codec_options import (
    CodecOptions,
)
from bson.objectid import ObjectId
from pydantic import ValidationError

from src.ingestion.raw_envelope import (
    RawIngestionRunReference,
    RawPageEnvelope,
    RawRecordEnvelope,
)

RUN_ID = UUID(
    "15151515-1515-1515-1515-151515151515"
)

RETRIEVED_AT = datetime(
    2026,
    10,
    15,
    12,
    0,
    0,
    tzinfo=UTC,
)

SOURCE_CHECKSUM = (
    "a" * 64
)

DATASET_ID = "DS00976"
RESOURCE_ID = "RS00906"


BSON_OPTIONS = CodecOptions(
    tz_aware=True,
    tzinfo=UTC,
)


def bson_round_trip(
    document: dict[
        str,
        object,
    ],
) -> dict[
    str,
    object,
]:
    encoded = BSON.encode(
        document
    )

    return BSON(
        encoded
    ).decode(
        codec_options=(
            BSON_OPTIONS
        )
    )


def test_raw_page_envelope_preserves_payload_and_bytes() -> None:
    payload = {
        "count": 1,
        "data": [
            {
                "credit_number": (
                    "IDA00010"
                ),
                "end_of_period": (
                    "2024-06-30"
                ),
            }
        ],
    }

    raw_bytes = (
        b'{"count":1,"data":'
        b'[{"credit_number":"IDA00010",'
        b'"end_of_period":"2024-06-30"}]}'
    )

    original_payload = deepcopy(
        payload
    )

    envelope = RawPageEnvelope(
        run_id=RUN_ID,
        dataset_id=DATASET_ID,
        resource_id=RESOURCE_ID,
        retrieved_at=(
            RETRIEVED_AT
        ),
        page_number=1,
        page_offset=0,
        source_checksum=(
            SOURCE_CHECKSUM
        ),
        record_count=1,
        total_count=1,
        raw_bytes=raw_bytes,
        payload=payload,
    )

    assert payload == (
        original_payload
    )

    assert (
        envelope.reconstruct_payload()
        == original_payload
    )

    assert (
        envelope.reconstruct_raw_bytes()
        == raw_bytes
    )


def test_raw_record_envelope_preserves_source_payload() -> None:
    payload = {
        "credit_number": (
            "IDA00010"
        ),
        "end_of_period": (
            "2024-06-30"
        ),
        "original_principal_amount": (
            "1234.500"
        ),
        "nullable_source_value": None,
        "nested": {
            "source_value": (
                "unchanged"
            ),
        },
    }

    original_payload = deepcopy(
        payload
    )

    envelope = (
        RawRecordEnvelope
        .from_source_payload(
            run_id=RUN_ID,
            dataset_id=DATASET_ID,
            resource_id=RESOURCE_ID,
            retrieved_at=(
                RETRIEVED_AT
            ),
            page_number=1,
            page_offset=0,
            record_index=0,
            source_checksum=(
                SOURCE_CHECKSUM
            ),
            payload=payload,
        )
    )

    assert payload == (
        original_payload
    )

    assert (
        envelope.payload
        == original_payload
    )

    assert (
        envelope.credit_number
        == "IDA00010"
    )

    assert (
        envelope.end_of_period
        == "2024-06-30"
    )

    assert (
        envelope.reconstruct_payload()
        == original_payload
    )


def test_raw_record_preserves_non_object_source_value() -> None:
    payload = (
        "malformed-source-record"
    )

    envelope = (
        RawRecordEnvelope
        .from_source_payload(
            run_id=RUN_ID,
            dataset_id=DATASET_ID,
            resource_id=RESOURCE_ID,
            retrieved_at=(
                RETRIEVED_AT
            ),
            page_number=2,
            page_offset=100,
            record_index=3,
            source_checksum=(
                SOURCE_CHECKSUM
            ),
            payload=payload,
        )
    )

    assert (
        envelope.credit_number
        is None
    )

    assert (
        envelope.end_of_period
        is None
    )

    assert (
        envelope.source_record_offset
        == 103
    )

    assert (
        envelope.reconstruct_payload()
        == payload
    )


def test_raw_record_survives_bson_round_trip() -> None:
    payload = {
        "credit_number": (
            "IDA00010"
        ),
        "end_of_period": (
            "2024-06-30"
        ),
        "value": "001.2300",
        "null_value": None,
        "items": [
            1,
            "2",
            False,
        ],
    }

    envelope = (
        RawRecordEnvelope
        .from_source_payload(
            run_id=RUN_ID,
            dataset_id=DATASET_ID,
            resource_id=RESOURCE_ID,
            retrieved_at=(
                RETRIEVED_AT
            ),
            page_number=1,
            page_offset=0,
            record_index=0,
            source_checksum=(
                SOURCE_CHECKSUM
            ),
            payload=payload,
        )
    )

    mongo_document = (
        envelope.to_mongo_document()
    )

    mongo_document[
        "_id"
    ] = ObjectId()

    decoded = bson_round_trip(
        mongo_document
    )

    restored = (
        RawRecordEnvelope
        .from_mongo_document(
            decoded
        )
    )

    assert restored.run_id == (
        RUN_ID
    )

    assert (
        restored.reconstruct_payload()
        == payload
    )

    assert (
        restored.credit_number
        == "IDA00010"
    )

    assert (
        restored.end_of_period
        == "2024-06-30"
    )


def test_ingestion_run_reference_survives_bson_round_trip() -> None:
    reference = (
        RawIngestionRunReference(
            run_id=RUN_ID,
            dataset_id=(
                DATASET_ID
            ),
            resource_id=(
                RESOURCE_ID
            ),
            started_at=(
                RETRIEVED_AT
            ),
            referenced_at=(
                RETRIEVED_AT
            ),
            status="running",
            code_version=(
                "day15-test"
            ),
        )
    )

    decoded = bson_round_trip(
        reference.to_mongo_document()
    )

    restored = (
        RawIngestionRunReference
        .from_mongo_document(
            decoded
        )
    )

    assert restored == reference


def test_invalid_checksum_is_rejected() -> None:
    with pytest.raises(
        ValidationError
    ):
        RawRecordEnvelope.from_source_payload(
            run_id=RUN_ID,
            dataset_id=DATASET_ID,
            resource_id=RESOURCE_ID,
            retrieved_at=(
                RETRIEVED_AT
            ),
            page_number=1,
            page_offset=0,
            record_index=0,
            source_checksum=(
                "not-a-sha256"
            ),
            payload={},
        )


def test_inconsistent_source_record_offset_is_rejected() -> None:
    with pytest.raises(
        ValidationError
    ):
        RawRecordEnvelope(
            run_id=RUN_ID,
            dataset_id=DATASET_ID,
            resource_id=RESOURCE_ID,
            retrieved_at=(
                RETRIEVED_AT
            ),
            page_number=1,
            page_offset=100,
            record_index=4,
            source_record_offset=999,
            source_checksum=(
                SOURCE_CHECKSUM
            ),
            payload={},
        )