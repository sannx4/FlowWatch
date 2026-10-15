from __future__ import annotations

from src.ingestion.raw_checksum import (
    checksum_record,
)
from src.ingestion.source_keys import (
    build_page_source_key,
    build_record_source_key,
)


def test_same_page_identity_produces_same_key() -> None:
    checksum = (
        "a" * 64
    )

    first = build_page_source_key(
        dataset_id="DS00976",
        resource_id="RS00906",
        page_offset=0,
        source_checksum=checksum,
    )

    second = build_page_source_key(
        dataset_id="DS00976",
        resource_id="RS00906",
        page_offset=0,
        source_checksum=checksum,
    )

    assert first == second


def test_changed_page_checksum_changes_key() -> None:
    first = build_page_source_key(
        dataset_id="DS00976",
        resource_id="RS00906",
        page_offset=0,
        source_checksum=(
            "a" * 64
        ),
    )

    second = build_page_source_key(
        dataset_id="DS00976",
        resource_id="RS00906",
        page_offset=0,
        source_checksum=(
            "b" * 64
        ),
    )

    assert first != second


def test_same_record_produces_same_checksum() -> None:
    payload = {
        "credit_number": (
            "IDA00010"
        ),
        "end_of_period": (
            "2024-06-30"
        ),
        "amount": (
            "1000.00"
        ),
    }

    assert (
        checksum_record(
            payload
        )
        == checksum_record(
            payload
        )
    )


def test_mapping_order_does_not_change_record_checksum() -> None:
    first = {
        "credit_number": (
            "IDA00010"
        ),
        "end_of_period": (
            "2024-06-30"
        ),
    }

    second = {
        "end_of_period": (
            "2024-06-30"
        ),
        "credit_number": (
            "IDA00010"
        ),
    }

    assert (
        checksum_record(
            first
        )
        == checksum_record(
            second
        )
    )


def test_same_record_identity_produces_same_key() -> None:
    record_checksum = (
        "c" * 64
    )

    first = build_record_source_key(
        dataset_id="DS00976",
        resource_id="RS00906",
        page_source_key=(
            "page:test"
        ),
        record_index=0,
        record_checksum=(
            record_checksum
        ),
    )

    second = build_record_source_key(
        dataset_id="DS00976",
        resource_id="RS00906",
        page_source_key=(
            "page:test"
        ),
        record_index=0,
        record_checksum=(
            record_checksum
        ),
    )

    assert first == second


def test_record_position_changes_source_key() -> None:
    first = build_record_source_key(
        dataset_id="DS00976",
        resource_id="RS00906",
        page_source_key=(
            "page:test"
        ),
        record_index=0,
        record_checksum=(
            "d" * 64
        ),
    )

    second = build_record_source_key(
        dataset_id="DS00976",
        resource_id="RS00906",
        page_source_key=(
            "page:test"
        ),
        record_index=1,
        record_checksum=(
            "d" * 64
        ),
    )

    assert first != second