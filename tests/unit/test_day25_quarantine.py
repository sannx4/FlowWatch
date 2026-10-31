"""Day25 immutable locator, rule-selection and SQL metadata tests."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from src.quality.day25_quarantine import (
    BROKEN_PARSER,
    FIXED_PARSER,
    RULE_EXACT_DECIMAL,
    RawLocator,
    float_financial_field,
)


def _locator(**overrides: object) -> RawLocator:
    values = {
        "run_id": uuid4(), "source_record_key": "run:page:0",
        "source_checksum": "a" * 64, "page_number": 0,
        "page_offset": 0, "record_index": 0,
    }
    values.update(overrides)
    return RawLocator(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["service_charge_rate", "original_principal_amount_us_"])
def test_financial_float_selected(field: str) -> None:
    assert float_financial_field({field: 1.25}) == (field, 1.25)


def test_int_and_decimal_not_detected_as_unsafe_float() -> None:
    with pytest.raises(ValueError, match="No financial float"):
        float_financial_field({"service_charge_rate": Decimal("1.25"),
                               "original_principal_amount_us_": 1})


def test_nonnumeric_float_ignored() -> None:
    with pytest.raises(ValueError):
        float_financial_field({"non_financial_field": 1.5})


def test_float_sort_is_deterministic() -> None:
    assert float_financial_field({"z_us_": 2.1, "a_us_": 1.2}) == ("a_us_", 1.2)


def test_valid_locator() -> None:
    assert _locator().source_checksum == "a" * 64


@pytest.mark.parametrize("invalid", ["", "ab", "G" * 64])
def test_invalid_hash_rejected(invalid: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        _locator(source_checksum=invalid)


def test_empty_source_key_rejected() -> None:
    with pytest.raises(ValueError, match="source_record_key"):
        _locator(source_record_key="")


def test_negative_offset_rejected() -> None:
    with pytest.raises(ValueError):
        _locator(record_index=-1)


def test_source_locator_types_checked() -> None:
    with pytest.raises(TypeError):
        _locator(run_id="not-uuid")


def test_migration_sql_contains_safety_constraints() -> None:
    ddl = Path("sql/operational/day25_quarantine.sql").read_text(encoding="utf-8")
    for marker in ("UNIQUE", "resolved_snapshot_id", "source_checksum", "record_index",
                   "CHECK", "GRANT", "source_record_key", "retry_count"):
        assert marker in ddl


def test_parser_and_rule_ids_are_versioned() -> None:
    assert BROKEN_PARSER != FIXED_PARSER
    assert RULE_EXACT_DECIMAL.startswith("EXACT_")
