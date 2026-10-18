
"""Day-20 financial and date-quality warning tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.quality.invariants import (
    build_warning_envelope,
    evaluate_invariants,
)
from src.quality.rules import QualityRuleId
from src.validation.models import ValidatedSourceRecordEnvelope
from src.validation.source_record import WorldBankSourceRecord


def make_record(
    **overrides: object,
) -> WorldBankSourceRecord:
    data: dict[str, object] = {
        field: None
        for field in WorldBankSourceRecord.model_fields
    }

    data.update(
        {
            "country": "Test Country",
            "country_code": "TST",
            "credit_number": "IDA00060",
            "project_id": "PROJECT001",
            "region": "TEST REGION",
            "end_of_period": "31-Oct-2016",
        }
    )

    data.update(overrides)

    return WorldBankSourceRecord.model_validate(data)


def test_excess_disbursement_produces_warning() -> None:
    record = make_record(
        original_principal_amount_us_="100",
        disbursed_amount_us_="120",
    )

    warnings = evaluate_invariants(record)

    assert len(warnings) == 1
    assert warnings[0].rule_id == (
        QualityRuleId.DISBURSEMENT_EXCEEDS_PRINCIPAL
    )


def test_financial_component_mismatch_produces_warning() -> None:
    record = make_record(
        original_principal_amount_us_="100",
        disbursed_amount_us_="80",
        undisbursed_amount_us_="10",
        cancelled_amount_us_="0",
    )

    warnings = evaluate_invariants(record)

    assert len(warnings) == 1
    assert warnings[0].rule_id == (
        QualityRuleId.FINANCIAL_COMPONENT_MISMATCH
    )


def test_one_record_can_have_two_financial_warnings() -> None:
    record = make_record(
        original_principal_amount_us_="100",
        disbursed_amount_us_="120",
        undisbursed_amount_us_="0",
        cancelled_amount_us_="0",
    )

    warnings = evaluate_invariants(record)

    assert {warning.rule_id for warning in warnings} == {
        QualityRuleId.DISBURSEMENT_EXCEEDS_PRINCIPAL,
        QualityRuleId.FINANCIAL_COMPONENT_MISMATCH,
    }


@pytest.mark.parametrize(
    ("earlier_field", "later_field"),
    [
        ("board_approval_date", "agreement_signing_date"),
        ("first_repayment_date", "last_repayment_date"),
        ("effective_date_most_recent", "closed_date_most_recent"),
    ],
)
def test_reversed_dates_produce_warning(
    earlier_field: str,
    later_field: str,
) -> None:
    record = make_record(
        **{
            earlier_field: "31-Dec-2020",
            later_field: "01-Jan-2020",
        }
    )

    warnings = evaluate_invariants(record)

    assert len(warnings) == 1
    assert warnings[0].rule_id == QualityRuleId.UNEXPECTED_DATE_ORDER


def test_balanced_financial_record_has_no_warnings() -> None:
    record = make_record(
        original_principal_amount_us_="100",
        disbursed_amount_us_="80",
        undisbursed_amount_us_="15",
        cancelled_amount_us_="5",
    )

    assert evaluate_invariants(record) == ()


def test_negative_exchange_adjustment_is_not_rejected() -> None:
    record = make_record(
        exchange_adjustment_us_="-10.25",
    )

    assert evaluate_invariants(record) == ()


def test_warning_envelope_preserves_original_lineage() -> None:
    run_id = uuid4()

    record = make_record(
        original_principal_amount_us_="100",
        disbursed_amount_us_="120",
    )

    envelope = ValidatedSourceRecordEnvelope(
        run_id=run_id,
        page_number=6,
        page_offset=500,
        record_index=7,
        source_record_offset=507,
        source_checksum="a" * 64,
        record=record,
    )

    raw_record = {
        "credit_number": "IDA00060",
        "end_of_period": "31-Oct-2016",
        "original_principal_amount_us_": "100",
        "disbursed_amount_us_": "120",
    }

    warning_envelope = build_warning_envelope(
        envelope,
        raw_record=raw_record,
    )

    assert warning_envelope is not None
    assert warning_envelope.run_id == run_id
    assert warning_envelope.page_offset == 500
    assert warning_envelope.record_index == 7
    assert warning_envelope.source_record_offset == 507
    assert warning_envelope.source_checksum == "a" * 64
    assert warning_envelope.raw_record == raw_record

    serialized = warning_envelope.model_dump(mode="json")

    assert serialized["warnings"][0]["rule_id"] == "DQ-AMOUNT-002"
    assert serialized["source_record_offset"] == 507
