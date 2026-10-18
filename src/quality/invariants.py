
"""Non-blocking financial and date-quality diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.quality.rules import (
    RULE_CATALOG,
    QualityRuleId,
)
from src.validation.models import ValidatedSourceRecordEnvelope
from src.validation.source_record import WorldBankSourceRecord

AMOUNT_TOLERANCE = Decimal("0.01")

DATE_RELATIONSHIPS = (
    ("board_approval_date", "agreement_signing_date"),
    ("first_repayment_date", "last_repayment_date"),
    ("effective_date_most_recent", "closed_date_most_recent"),
)


class QualityWarning(BaseModel):
    """A diagnostic that does not reject a source record."""

    model_config = ConfigDict(frozen=True)

    rule_id: QualityRuleId
    field_path: str
    message: str
    observed_values: dict[str, str]


class QualityWarningEnvelope(BaseModel):
    """Warnings with the original source record and lineage."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    page_number: int
    page_offset: int
    record_index: int
    source_record_offset: int
    source_checksum: str

    credit_number: str
    end_of_period: str

    raw_record: dict[str, Any]

    warnings: tuple[QualityWarning, ...] = Field(
        min_length=1,
    )


def _make_warning(
    rule_id: QualityRuleId,
    *,
    field_path: str,
    observed_values: dict[str, str],
) -> QualityWarning:
    return QualityWarning(
        rule_id=rule_id,
        field_path=field_path,
        message=RULE_CATALOG[rule_id],
        observed_values=observed_values,
    )


def evaluate_invariants(
    record: WorldBankSourceRecord,
) -> tuple[QualityWarning, ...]:
    """Check financial and date relationships without rejecting data."""

    warnings: list[QualityWarning] = []

    original = record.original_principal_amount_us_
    disbursed = record.disbursed_amount_us_
    undisbursed = record.undisbursed_amount_us_
    cancelled = record.cancelled_amount_us_

    if (
        original is not None
        and disbursed is not None
        and disbursed > original
    ):
        warnings.append(
            _make_warning(
                QualityRuleId.DISBURSEMENT_EXCEEDS_PRINCIPAL,
                field_path=(
                    "disbursed_amount_us_,"
                    "original_principal_amount_us_"
                ),
                observed_values={
                    "original_principal_amount_us_": str(original),
                    "disbursed_amount_us_": str(disbursed),
                },
            )
        )

    if all(
        value is not None
        for value in (
            original,
            disbursed,
            undisbursed,
            cancelled,
        )
    ):
        assert original is not None
        assert disbursed is not None
        assert undisbursed is not None
        assert cancelled is not None

        component_sum = disbursed + undisbursed + cancelled
        difference = component_sum - original

        if abs(difference) > AMOUNT_TOLERANCE:
            warnings.append(
                _make_warning(
                    QualityRuleId.FINANCIAL_COMPONENT_MISMATCH,
                    field_path=(
                        "disbursed_amount_us_,"
                        "undisbursed_amount_us_,"
                        "cancelled_amount_us_,"
                        "original_principal_amount_us_"
                    ),
                    observed_values={
                        "original_principal_amount_us_": str(original),
                        "component_sum_usd": str(component_sum),
                        "difference_usd": str(difference),
                    },
                )
            )

    for earlier_field, later_field in DATE_RELATIONSHIPS:
        earlier = getattr(record, earlier_field)
        later = getattr(record, later_field)

        if (
            earlier is not None
            and later is not None
            and earlier > later
        ):
            warnings.append(
                _make_warning(
                    QualityRuleId.UNEXPECTED_DATE_ORDER,
                    field_path=f"{earlier_field},{later_field}",
                    observed_values={
                        earlier_field: earlier.isoformat(),
                        later_field: later.isoformat(),
                    },
                )
            )

    return tuple(warnings)


def build_warning_envelope(
    envelope: ValidatedSourceRecordEnvelope,
    *,
    raw_record: Mapping[str, Any],
) -> QualityWarningEnvelope | None:
    """Attach complete source lineage to detected warning conditions."""

    warnings = evaluate_invariants(envelope.record)

    if not warnings:
        return None

    return QualityWarningEnvelope(
        run_id=envelope.run_id,
        page_number=envelope.page_number,
        page_offset=envelope.page_offset,
        record_index=envelope.record_index,
        source_record_offset=envelope.source_record_offset,
        source_checksum=envelope.source_checksum,
        credit_number=envelope.record.credit_number,
        end_of_period=envelope.record.end_of_period.isoformat(),
        raw_record=dict(raw_record),
        warnings=warnings,
    )
