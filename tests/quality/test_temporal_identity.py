
"""Day-20 temporal identity tests using controlled test fixtures."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from src.quality.rules import QualityRuleId
from src.quality.temporal import TemporalIdentityScanner
from src.quality.validator import QualityPageValidationResult
from src.validation.models import ValidatedSourceRecordEnvelope
from src.validation.source_record import WorldBankSourceRecord


def make_record(
    *,
    run_id: UUID,
    credit: str = "IDA00210",
    period: date = date(2024, 6, 30),
    status: str = "Repaying",
    page_offset: int = 0,
    record_index: int = 0,
) -> tuple[ValidatedSourceRecordEnvelope, dict[str, str]]:
    """Build a minimal validated-envelope fixture."""

    raw_record = {
        "credit_number": credit,
        "end_of_period": period.strftime("%d-%b-%Y"),
        "credit_status": status,
    }

    parsed_record = WorldBankSourceRecord.model_construct(
        credit_number=credit,
        end_of_period=period,
        credit_status=status,
    )

    envelope = ValidatedSourceRecordEnvelope(
        run_id=run_id,
        page_number=(page_offset // 100) + 1,
        page_offset=page_offset,
        record_index=record_index,
        source_record_offset=page_offset + record_index,
        source_checksum="a" * 64,
        record=parsed_record,
    )

    return envelope, raw_record


def make_page(
    *envelopes: ValidatedSourceRecordEnvelope,
) -> QualityPageValidationResult:
    return QualityPageValidationResult(
        accepted=envelopes,
        rejected=(),
    )


def test_first_identity_is_accepted() -> None:
    run_id = uuid4()
    scanner = TemporalIdentityScanner()

    record, raw = make_record(run_id=run_id)

    result = scanner.check_page(
        make_page(record),
        raw_records=[raw],
    )

    assert result.accepted_count == 1
    assert result.rejected_count == 0


def test_identical_duplicate_across_distant_pages() -> None:
    run_id = uuid4()
    scanner = TemporalIdentityScanner()

    first, first_raw = make_record(
        run_id=run_id,
        page_offset=0,
    )

    second, second_raw = make_record(
        run_id=run_id,
        page_offset=2000,
    )

    scanner.check_page(
        make_page(first),
        raw_records=[first_raw],
    )

    result = scanner.check_page(
        make_page(second),
        raw_records=[second_raw],
    )

    assert result.accepted_count == 0
    assert result.rejected_count == 1

    rejection = result.rejected[0]

    assert rejection.rule_ids == (
        QualityRuleId.DUPLICATE_CREDIT_PERIOD,
    )
    assert rejection.page_offset == 2000
    assert rejection.source_record_offset == 2000
    assert rejection.run_id == run_id
    assert rejection.raw_record == second_raw

    first_lineage = (
        rejection.reasons[0]
        .offending_value["first_observation"]
    )

    assert first_lineage["page_offset"] == 0
    assert first_lineage["run_id"] == str(run_id)


def test_conflicting_duplicate_is_rejected() -> None:
    run_id = uuid4()
    scanner = TemporalIdentityScanner()

    first, first_raw = make_record(
        run_id=run_id,
        status="Repaying",
    )

    second, second_raw = make_record(
        run_id=run_id,
        status="Fully Repaid",
        page_offset=5000,
    )

    scanner.check_page(
        make_page(first),
        raw_records=[first_raw],
    )

    result = scanner.check_page(
        make_page(second),
        raw_records=[second_raw],
    )

    assert result.rejected_count == 1
    assert result.accepted_count == 0
    assert result.rejected[0].rule_ids == (
        QualityRuleId.CONFLICTING_CREDIT_PERIOD,
    )
    assert result.rejected[0].raw_record == second_raw


def test_same_credit_different_periods_are_accepted() -> None:
    run_id = uuid4()
    scanner = TemporalIdentityScanner()

    first, first_raw = make_record(run_id=run_id)

    second, second_raw = make_record(
        run_id=run_id,
        period=date(2024, 9, 30),
        page_offset=2000,
    )

    result_one = scanner.check_page(
        make_page(first),
        raw_records=[first_raw],
    )

    result_two = scanner.check_page(
        make_page(second),
        raw_records=[second_raw],
    )

    assert result_one.accepted_count == 1
    assert result_two.accepted_count == 1
    assert result_two.rejected_count == 0


def test_different_credits_same_period_are_accepted() -> None:
    run_id = uuid4()
    scanner = TemporalIdentityScanner()

    first, first_raw = make_record(run_id=run_id)

    second, second_raw = make_record(
        run_id=run_id,
        credit="IDA00010",
        page_offset=500,
    )

    scanner.check_page(
        make_page(first),
        raw_records=[first_raw],
    )

    result = scanner.check_page(
        make_page(second),
        raw_records=[second_raw],
    )

    assert result.accepted_count == 1


def test_duplicate_inside_single_page() -> None:
    run_id = uuid4()
    scanner = TemporalIdentityScanner()

    first, first_raw = make_record(
        run_id=run_id,
        record_index=0,
    )

    second, second_raw = make_record(
        run_id=run_id,
        record_index=1,
    )

    result = scanner.check_page(
        make_page(first, second),
        raw_records=[first_raw, second_raw],
    )

    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert result.rejected[0].record_index == 1


def test_different_run_requires_new_scanner() -> None:
    scanner = TemporalIdentityScanner()

    first, first_raw = make_record(run_id=uuid4())
    second, second_raw = make_record(run_id=uuid4())

    scanner.check_page(
        make_page(first),
        raw_records=[first_raw],
    )

    with pytest.raises(ValueError, match="new TemporalIdentityScanner"):
        scanner.check_page(
            make_page(second),
            raw_records=[second_raw],
        )
