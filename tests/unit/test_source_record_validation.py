from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from src.ingestion.checksum import (
    sha256_bytes,
)
from src.validation.models import (
    RejectedRecordEnvelope,
    RejectionReasonCode,
    ValidatedSourceRecordEnvelope,
    ValidationContext,
)
from src.validation.service import (
    SourceRecordValidationService,
)

FIXTURE_DIR = (
    Path(__file__).resolve()
    .parents[1]
    / "fixtures"
    / "validation"
)


FIXED_TIME = datetime(
    2026,
    10,
    12,
    14,
    0,
    0,
    tzinfo=UTC,
)


def fixed_clock() -> datetime:
    return FIXED_TIME


def load_fixture(
    filename: str,
) -> dict[str, Any]:
    path = (
        FIXTURE_DIR
        / filename
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(
            handle
        )


def make_context() -> ValidationContext:
    return ValidationContext(
        run_id=UUID(
            "11111111-1111-1111-1111-111111111111"
        ),
        page_number=1,
        page_offset=100,
        source_checksum=(
            sha256_bytes(
                b"day12-test-page"
            )
        ),
    )


def make_service() -> SourceRecordValidationService:
    return SourceRecordValidationService(
        clock=fixed_clock
    )


def test_valid_source_record_is_parsed() -> None:
    raw_record = load_fixture(
        "valid_worldbank_record.json"
    )

    result = (
        make_service()
        .validate_record(
            raw_record,
            context=make_context(),
            record_index=0,
        )
    )

    assert isinstance(
        result,
        ValidatedSourceRecordEnvelope,
    )

    assert (
        result.record.credit_number
        == "IDA00010"
    )

    assert (
        result.record.end_of_period
        == date(
            2022,
            6,
            30,
        )
    )

    assert (
        result.record
        .disbursed_amount_us_
        == Decimal(
            "8427973.97"
        )
    )


def test_observed_numeric_string_is_explicitly_parsed() -> None:
    raw_record = load_fixture(
        "valid_worldbank_record.json"
    )

    result = (
        make_service()
        .validate_record(
            raw_record,
            context=make_context(),
            record_index=0,
        )
    )

    assert isinstance(
        result,
        ValidatedSourceRecordEnvelope,
    )

    assert (
        result.record
        .exchange_adjustment_us_
        == Decimal(
            0
        )
    )


def test_observed_null_date_is_accepted() -> None:
    raw_record = load_fixture(
        "valid_worldbank_record.json"
    )

    result = (
        make_service()
        .validate_record(
            raw_record,
            context=make_context(),
            record_index=0,
        )
    )

    assert isinstance(
        result,
        ValidatedSourceRecordEnvelope,
    )

    assert (
        result.record
        .last_disbursement_date
        is None
    )


def test_malformed_date_is_quarantined() -> None:
    raw_record = load_fixture(
        "invalid_date_worldbank_record.json"
    )

    result = (
        make_service()
        .validate_record(
            raw_record,
            context=make_context(),
            record_index=0,
        )
    )

    assert isinstance(
        result,
        RejectedRecordEnvelope,
    )

    assert any(
        issue.reason_code
        == RejectionReasonCode.INVALID_DATE
        and issue.field_path
        == "end_of_period"
        for issue in result.reasons
    )

    assert (
        result.raw_record[
            "end_of_period"
        ]
        == "31-Feb-2022"
    )


def test_malformed_numeric_is_quarantined() -> None:
    raw_record = load_fixture(
        "invalid_numeric_worldbank_record.json"
    )

    result = (
        make_service()
        .validate_record(
            raw_record,
            context=make_context(),
            record_index=1,
        )
    )

    assert isinstance(
        result,
        RejectedRecordEnvelope,
    )

    assert any(
        issue.reason_code
        == RejectionReasonCode.INVALID_NUMERIC
        and issue.field_path
        == "disbursed_amount_us_"
        for issue in result.reasons
    )

    assert (
        result.raw_record[
            "disbursed_amount_us_"
        ]
        == "eight-million"
    )


def test_page_continues_after_bad_records() -> None:
    valid = load_fixture(
        "valid_worldbank_record.json"
    )

    invalid_date = load_fixture(
        "invalid_date_worldbank_record.json"
    )

    invalid_numeric = load_fixture(
        "invalid_numeric_worldbank_record.json"
    )

    result = (
        make_service()
        .validate_page(
            [
                valid,
                invalid_date,
                invalid_numeric,
            ],
            context=make_context(),
        )
    )

    assert result.total_count == 3
    assert result.accepted_count == 1
    assert result.rejected_count == 2

    assert (
        result.accepted[
            0
        ].record.credit_number
        == "IDA00010"
    )


def test_missing_required_identifier_is_quarantined() -> None:
    raw_record = load_fixture(
        "valid_worldbank_record.json"
    )

    del raw_record[
        "credit_number"
    ]

    result = (
        make_service()
        .validate_record(
            raw_record,
            context=make_context(),
            record_index=2,
        )
    )

    assert isinstance(
        result,
        RejectedRecordEnvelope,
    )

    assert any(
        issue.reason_code
        == (
            RejectionReasonCode
            .MISSING_REQUIRED_FIELD
        )
        and issue.field_path
        == "credit_number"
        for issue in result.reasons
    )


def test_non_object_record_is_quarantined() -> None:
    result = (
        make_service()
        .validate_record(
            "not-a-json-object",
            context=make_context(),
            record_index=3,
        )
    )

    assert isinstance(
        result,
        RejectedRecordEnvelope,
    )

    assert (
        result.reasons[
            0
        ].reason_code
        == (
            RejectionReasonCode
            .INVALID_RECORD_TYPE
        )
    )


def test_source_record_offset_is_traceable() -> None:
    raw_record = load_fixture(
        "invalid_numeric_worldbank_record.json"
    )

    result = (
        make_service()
        .validate_record(
            raw_record,
            context=make_context(),
            record_index=7,
        )
    )

    assert isinstance(
        result,
        RejectedRecordEnvelope,
    )

    assert (
        result.page_offset
        == 100
    )

    assert (
        result.record_index
        == 7
    )

    assert (
        result.source_record_offset
        == 107
    )


def test_unknown_additive_source_field_is_preserved() -> None:
    raw_record = load_fixture(
        "valid_worldbank_record.json"
    )

    raw_record[
        "future_source_field"
    ] = "new-value"

    result = (
        make_service()
        .validate_record(
            raw_record,
            context=make_context(),
            record_index=0,
        )
    )

    assert isinstance(
        result,
        ValidatedSourceRecordEnvelope,
    )

    assert (
        result.record.model_extra
        is not None
    )

    assert (
        result.record.model_extra[
            "future_source_field"
        ]
        == "new-value"
    )