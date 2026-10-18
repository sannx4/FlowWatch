
"""Tests for the combined source-quality and temporal-validation workflow."""

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
    offset: int,
) -> ValidationContext:
    return ValidationContext(
        run_id=run_id,
        page_number=(offset // 100) + 1,
        page_offset=offset,
        source_checksum="a" * 64,
    )


def make_record(
    *,
    credit: str = "IDA00210",
    period: str = "30-Jun-2024",
    status: str = "Repaying",
) -> dict[str, object]:
    """Build a complete source-schema fixture without external data."""

    record: dict[str, object] = {
        name: None
        for name in WorldBankSourceRecord.model_fields
    }

    record.update(
        {
            "country": "Test Country",
            "country_code": "TST",
            "credit_number": credit,
            "project_id": "TEST-PROJECT",
            "region": "TEST REGION",
            "end_of_period": period,
            "credit_status": status,
        }
    )

    return record


def test_integrated_exact_duplicate_across_pages() -> None:
    run_id = uuid4()

    service = QualityValidationService(
        temporal_scanner=TemporalIdentityScanner(),
    )

    record = make_record()

    first = service.validate_page(
        [record],
        context=make_context(run_id, offset=0),
    )

    second = service.validate_page(
        [record],
        context=make_context(run_id, offset=2000),
    )

    assert first.accepted_count == 1
    assert second.accepted_count == 0
    assert second.rejected_count == 1

    rejected = second.rejected[0]

    assert rejected.rule_ids == (
        QualityRuleId.DUPLICATE_CREDIT_PERIOD,
    )

    assert rejected.run_id == run_id
    assert rejected.page_offset == 2000
    assert rejected.source_record_offset == 2000
    assert rejected.raw_record == record

    first_observation = (
        rejected.reasons[0]
        .offending_value["first_observation"]
    )

    assert first_observation["page_offset"] == 0


def test_integrated_conflicting_duplicate_across_pages() -> None:
    run_id = uuid4()

    service = QualityValidationService(
        temporal_scanner=TemporalIdentityScanner(),
    )

    first_record = make_record(status="Repaying")

    conflicting_record = make_record(
        status="Fully Repaid",
    )

    first = service.validate_page(
        [first_record],
        context=make_context(run_id, offset=0),
    )

    second = service.validate_page(
        [conflicting_record],
        context=make_context(run_id, offset=5000),
    )

    assert first.accepted_count == 1
    assert second.rejected_count == 1

    rejection = second.rejected[0]

    assert rejection.rule_ids == (
        QualityRuleId.CONFLICTING_CREDIT_PERIOD,
    )

    assert rejection.raw_record == conflicting_record
    assert rejection.page_offset == 5000
    assert rejection.source_checksum == "a" * 64


def test_different_reporting_periods_are_valid() -> None:
    run_id = uuid4()

    service = QualityValidationService(
        temporal_scanner=TemporalIdentityScanner(),
    )

    first = service.validate_page(
        [make_record(period="30-Jun-2024")],
        context=make_context(run_id, offset=0),
    )

    second = service.validate_page(
        [make_record(period="30-Sep-2024")],
        context=make_context(run_id, offset=2000),
    )

    assert first.accepted_count == 1
    assert second.accepted_count == 1
    assert second.rejected_count == 0


def test_source_rejection_keeps_rule_id_and_lineage() -> None:
    run_id = uuid4()

    service = QualityValidationService(
        temporal_scanner=TemporalIdentityScanner(),
    )

    invalid_record = make_record(credit="")

    result = service.validate_page(
        [invalid_record],
        context=make_context(run_id, offset=700),
    )

    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.total_count == 1

    rejection = result.rejected[0]

    assert QualityRuleId.INVALID_CREDIT_NUMBER in rejection.rule_ids
    assert rejection.run_id == run_id
    assert rejection.page_offset == 700
    assert rejection.source_record_offset == 700
    assert rejection.raw_record == invalid_record
