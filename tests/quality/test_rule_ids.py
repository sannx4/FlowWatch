
"""Tests for Day-20 machine-readable quality rules and lineage."""

from __future__ import annotations

from uuid import uuid4

from src.quality.rules import (
    RULE_CATALOG,
    QualityRuleId,
)
from src.quality.validator import QualityValidationService
from src.validation.models import ValidationContext


def test_invalid_record_type_preserves_lineage() -> None:
    context = ValidationContext(
        run_id=uuid4(),
        page_number=6,
        page_offset=500,
        source_checksum="a" * 64,
    )

    result = QualityValidationService().validate_page(
        [42],
        context=context,
    )

    assert result.accepted_count == 0
    assert result.rejected_count == 1

    rejected = result.rejected[0]

    assert rejected.rule_ids == (
        QualityRuleId.INVALID_RECORD_TYPE,
    )

    assert rejected.run_id == context.run_id
    assert rejected.page_number == 6
    assert rejected.page_offset == 500
    assert rejected.record_index == 0
    assert rejected.source_record_offset == 500
    assert rejected.source_checksum == "a" * 64
    assert rejected.raw_record == 42


def test_invalid_required_fields_have_rule_ids() -> None:
    context = ValidationContext(
        run_id=uuid4(),
        page_number=1,
        page_offset=0,
        source_checksum="b" * 64,
    )

    record = {
        "credit_number": "",
        "project_id": "",
        "end_of_period": "invalid-date",
    }

    result = QualityValidationService().validate_page(
        [record],
        context=context,
    )

    assert result.rejected_count == 1

    rejected = result.rejected[0]

    assert QualityRuleId.INVALID_CREDIT_NUMBER in rejected.rule_ids
    assert QualityRuleId.INVALID_PROJECT_ID in rejected.rule_ids
    assert QualityRuleId.INVALID_REPORTING_DATE in rejected.rule_ids

    assert rejected.raw_record == record
    assert rejected.source_checksum == context.source_checksum


def test_rule_catalog_covers_all_declared_rules() -> None:
    assert set(QualityRuleId) == set(RULE_CATALOG)


def test_rule_ids_survive_json_serialization() -> None:
    context = ValidationContext(
        run_id=uuid4(),
        page_number=3,
        page_offset=200,
        source_checksum="c" * 64,
    )

    result = QualityValidationService().validate_page(
        [None],
        context=context,
    )

    serialized = result.rejected[0].model_dump(mode="json")

    assert serialized["rule_ids"] == ["DQ-SRC-001"]
    assert serialized["page_offset"] == 200
    assert serialized["source_record_offset"] == 200
    assert serialized["raw_record"] is None
