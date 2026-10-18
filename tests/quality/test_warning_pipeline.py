
"""Integration tests for non-blocking quality warnings."""

from __future__ import annotations

from uuid import UUID, uuid4

from src.quality.rules import QualityRuleId
from src.quality.temporal import TemporalIdentityScanner
from src.quality.validator import QualityValidationService
from src.validation.models import ValidationContext
from src.validation.source_record import WorldBankSourceRecord


def make_context(
    run_id: UUID,
    *,
    offset: int = 0,
) -> ValidationContext:
    return ValidationContext(
        run_id=run_id,
        page_number=(offset // 100) + 1,
        page_offset=offset,
        source_checksum="a" * 64,
    )


def make_record(
    **overrides: object,
) -> dict[str, object]:
    """Build a complete test record accepted by the source schema."""

    record: dict[str, object] = {
        field: None
        for field in WorldBankSourceRecord.model_fields
    }

    record.update(
        {
            "country": "Test Country",
            "country_code": "TST",
            "credit_number": "IDA00060",
            "project_id": "TEST-PROJECT",
            "region": "TEST REGION",
            "end_of_period": "31-Oct-2016",
        }
    )

    record.update(overrides)

    return record


def test_unusual_financial_record_is_accepted_with_warnings() -> None:
    run_id = uuid4()

    record = make_record(
        original_principal_amount_us_="100",
        disbursed_amount_us_="120",
        undisbursed_amount_us_="0",
        cancelled_amount_us_="0",
    )

    result = QualityValidationService().validate_page(
        [record],
        context=make_context(run_id, offset=500),
    )

    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert result.warning_count == 1

    warning_envelope = result.warnings[0]

    assert {
        warning.rule_id
        for warning in warning_envelope.warnings
    } == {
        QualityRuleId.DISBURSEMENT_EXCEEDS_PRINCIPAL,
        QualityRuleId.FINANCIAL_COMPONENT_MISMATCH,
    }

    assert warning_envelope.run_id == run_id
    assert warning_envelope.page_offset == 500
    assert warning_envelope.source_record_offset == 500
    assert warning_envelope.source_checksum == "a" * 64
    assert warning_envelope.raw_record == record

    serialized = warning_envelope.model_dump(
        mode="json",
    )

    assert serialized["warnings"][0]["rule_id"] == (
        "DQ-AMOUNT-002"
    )


def test_clean_record_is_accepted_without_warning() -> None:
    record = make_record(
        original_principal_amount_us_="100",
        disbursed_amount_us_="80",
        undisbursed_amount_us_="15",
        cancelled_amount_us_="5",
    )

    result = QualityValidationService().validate_page(
        [record],
        context=make_context(uuid4()),
    )

    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert result.warning_count == 0
    assert result.total_count == 1


def test_invalid_numeric_record_is_rejected_not_warned() -> None:
    record = make_record(
        disbursed_amount_us_="Infinity",
    )

    result = QualityValidationService().validate_page(
        [record],
        context=make_context(uuid4()),
    )

    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.warning_count == 0

    assert QualityRuleId.INVALID_DECIMAL in (
        result.rejected[0].rule_ids
    )


def test_duplicate_is_not_counted_as_an_accepted_warning() -> None:
    run_id = uuid4()

    service = QualityValidationService(
        temporal_scanner=TemporalIdentityScanner(),
    )

    record = make_record(
        original_principal_amount_us_="100",
        disbursed_amount_us_="120",
        undisbursed_amount_us_="0",
        cancelled_amount_us_="0",
    )

    first = service.validate_page(
        [record],
        context=make_context(run_id, offset=0),
    )

    second = service.validate_page(
        [record],
        context=make_context(run_id, offset=2000),
    )

    assert first.accepted_count == 1
    assert first.warning_count == 1

    assert second.accepted_count == 0
    assert second.rejected_count == 1
    assert second.warning_count == 0

    assert second.rejected[0].rule_ids == (
        QualityRuleId.DUPLICATE_CREDIT_PERIOD,
    )

    assert second.rejected[0].page_offset == 2000
    assert second.rejected[0].raw_record == record


def test_date_warning_does_not_reject_record() -> None:
    record = make_record(
        board_approval_date="31-Dec-2020",
        agreement_signing_date="01-Jan-2020",
    )

    result = QualityValidationService().validate_page(
        [record],
        context=make_context(uuid4()),
    )

    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert result.warning_count == 1

    assert result.warnings[0].warnings[0].rule_id == (
        QualityRuleId.UNEXPECTED_DATE_ORDER
    )
