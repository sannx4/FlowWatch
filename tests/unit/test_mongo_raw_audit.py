from __future__ import annotations

import pytest

from src.ingestion.mongo_raw_audit import (
    compare_raw_runs,
    profile_raw_run,
)


def record(
    run: str,
    credit: str,
    *,
    rate: str = "1",
    extra: bool = False,
):
    payload = {
        "credit_number": credit,
        "end_of_period": "2022-06-30",
        "service_charge_rate": rate,
    }

    if extra:
        payload[
            "new_source_attribute"
        ] = True

    return {
        "run_id": run,
        "dataset_id": (
            "world_bank_ida_statement_of_credits"
        ),
        "resource_id": (
            "world_bank_sample_day16"
        ),
        "source_record_key": (
            f"record:{run}-{credit}"
        ),
        "payload": payload,
    }


def test_schema_profile_reports_missing_fields() -> None:
    rows = [
        record(
            "a",
            "IDA00001",
        ),
        record(
            "a",
            "IDA00002",
            extra=True,
        ),
    ]

    profile = profile_raw_run(
        rows
    )

    assert profile[
        "record_count_examined"
    ] == 2

    assert profile[
        "field_profile"
    ]["new_source_attribute"]["missing"] == 1

    assert profile[
        "duplicate_business_identity_count"
    ] == 0


def test_run_comparison_detects_payload_and_schema_change() -> None:
    before = [
        record(
            "a",
            "IDA00001",
        ),
        record(
            "a",
            "IDA00002",
        ),
    ]

    after = [
        record(
            "b",
            "IDA00001",
            rate="2",
            extra=True,
        ),
        record(
            "b",
            "IDA00003",
        ),
    ]

    result = compare_raw_runs(
        before,
        after,
    )

    assert result[
        "status"
    ] == "COMPARED_STORED_RUNS"

    assert result[
        "matched_business_identities"
    ] == 1

    assert result[
        "changed_payloads_among_matched"
    ] == 1

    assert result[
        "new_business_identities"
    ] == 1

    assert result[
        "missing_business_identities"
    ] == 1

    assert result[
        "fields_added"
    ] == [
        "new_source_attribute"
    ]


def test_incomparable_sources_are_rejected() -> None:
    original = record(
        "a",
        "IDA00001",
    )

    incompatible = record(
        "b",
        "IDA00001",
    )

    incompatible[
        "resource_id"
    ] = "different"

    with pytest.raises(
        ValueError,
        match="different resource_id",
    ):
        compare_raw_runs(
            [original],
            [incompatible],
        )


def test_comparison_rejects_same_run() -> None:
    with pytest.raises(
        ValueError,
        match="two different",
    ):
        compare_raw_runs(
            [
                record(
                    "a",
                    "IDA00001",
                )
            ],
            [
                record(
                    "a",
                    "IDA00001",
                )
            ],
        )


def test_inconsistent_metadata_fails_closed() -> None:
    with pytest.raises(
        ValueError,
        match="Inconsistent",
    ):
        profile_raw_run(
            [
                record(
                    "a",
                    "IDA00001",
                ),
                record(
                    "b",
                    "IDA00002",
                ),
            ]
        )