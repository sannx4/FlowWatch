"""Determinism, precision, failure-mode and Day-7 compatibility tests."""

from __future__ import annotations

import ast
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.transformation.pure import (
    MONEY_FIELDS,
    canonical_fingerprint,
    transform_canonical_record,
    transform_country,
    transform_credit,
    transform_project,
    transform_region,
    transform_snapshot,
)
from src.transformation.types import (
    TransformationError,
    optional_date,
    optional_decimal,
    optional_text,
    required_date,
    required_text,
)


@pytest.fixture
def raw_record() -> dict[str, object]:
    return {
        "region": "South Asia",
        "country_code": "IN",
        "country": "India",
        "project_id": "P123456",
        "project_name": "Irrigation",
        "credit_number": "IDA-1234",
        "borrower": "Government",
        "currency_of_commitment": "USD",
        "end_of_period": "30-Jun-2025",
        "credit_status": "Active",
        "board_approval_date": "01-Jan-2020",
        "agreement_signing_date": None,
        "effective_date_most_recent": "01-Mar-2020",
        "first_repayment_date": "01-Jan-2025",
        "last_repayment_date": "01-Jan-2050",
        "closed_date_most_recent": None,
        "last_disbursement_date": None,
        "original_principal_amount_us_": "999999999999.1234567890123456789012",
        "disbursed_amount_us_": "2.00000000000000000009",
        "service_charge_rate": "0.75000",
    }


def test_entities_and_snapshot_are_separate_pure_mappings(raw_record: dict[str, object]) -> None:
    assert transform_region(raw_record) == {"region_name": "South Asia"}
    assert transform_country(raw_record) == {
        "country_code": "IN", "country_name": "India"
    }
    assert transform_project(raw_record)["project_id"] == "P123456"
    assert transform_credit(raw_record)["credit_number"] == "IDA-1234"
    assert transform_snapshot(raw_record)["end_of_period"] == date(2025, 6, 30)


def test_canonical_repeatedly_equal_without_source_mutation(
    raw_record: dict[str, object],
) -> None:
    original = deepcopy(raw_record)
    a = transform_canonical_record(raw_record)
    b = transform_canonical_record(raw_record)
    assert a == b
    assert a is not b
    assert raw_record == original
    assert canonical_fingerprint(raw_record) == canonical_fingerprint(deepcopy(raw_record))
    assert len(canonical_fingerprint(raw_record)) == 64


def test_fingerprint_unaffected_by_input_order(raw_record: dict[str, object]) -> None:
    reordered = dict(reversed(list(raw_record.items())))
    assert canonical_fingerprint(raw_record) == canonical_fingerprint(reordered)


def test_fingerprint_changes_if_amount_changes(raw_record: dict[str, object]) -> None:
    other = {**raw_record, "disbursed_amount_us_": "3.00000000000000000009"}
    assert canonical_fingerprint(raw_record) != canonical_fingerprint(other)


def test_exact_decimal_precision_and_scale(raw_record: dict[str, object]) -> None:
    snapshot = transform_snapshot(raw_record)
    assert snapshot["original_principal_amount_usd"] == Decimal(
        "999999999999.1234567890123456789012"
    )
    assert str(snapshot["disbursed_amount_usd"]) == "2.00000000000000000009"
    assert snapshot["service_charge_rate"] == Decimal("0.75000")
    assert str(snapshot["service_charge_rate"]) == "0.75000"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_optional_null_date(value: object) -> None:
    assert optional_date(value, field="x") is None


@pytest.mark.parametrize("value", [None, "", "  "])
def test_optional_null_decimal(value: object) -> None:
    assert optional_decimal(value, field="x") is None


@pytest.mark.parametrize("value", [None, "", "  "])
def test_optional_null_text(value: object) -> None:
    assert optional_text(value, field="x") is None


def test_required_fields_reject_empty(raw_record: dict[str, object]) -> None:
    for field in ("region", "country_code", "country", "project_id", "credit_number", "end_of_period"):
        broken = {**raw_record, field: ""}
        with pytest.raises(TransformationError):
            transform_canonical_record(broken)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-02-29", date(2024, 2, 29)),
        ("30-Jun-2022", date(2022, 6, 30)),
        ("1-Jan-2023", date(2023, 1, 1)),
        ("2025-06-30T00:00:00.000", date(2025, 6, 30)),
        ("2025-06-30T00:00:00Z", date(2025, 6, 30)),
        ("2025-06-30T00:00:00+00:00", date(2025, 6, 30)),
        (date(2025, 6, 30), date(2025, 6, 30)),
    ],
)
def test_supported_calendar_dates(value: object, expected: date) -> None:
    assert optional_date(value, field="test") == expected


@pytest.mark.parametrize(
    "value",
    ["2025-02-30", "31-Feb-2025", "30-Not-2025", "2025/06/30", "30-06-2025", "2025-06-30T12:30:00Z", "2025-06-30T00:00:00+05:30", 20250630],
)
def test_malformed_or_ambiguous_dates_fail(value: object) -> None:
    with pytest.raises(TransformationError):
        optional_date(value, field="test")


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), 1.1, True, "NaN", "Infinity", "12,345.67", "1_000", "money", object()],
)
def test_lossy_or_invalid_numeric_values_fail(value: object) -> None:
    with pytest.raises(TransformationError):
        optional_decimal(value, field="amount")


@pytest.mark.parametrize(
    "value, expected",
    [("0", Decimal(0)), ("1.23e-10", Decimal("1.23e-10")), (42, Decimal(42)), ("-0.0001", Decimal("-0.0001"))],
)
def test_exact_supported_decimal_inputs(value: object, expected: Decimal) -> None:
    assert optional_decimal(value, field="amount") == expected


def test_missing_optional_money_fields_are_null(raw_record: dict[str, object]) -> None:
    result = transform_snapshot(raw_record)
    for target, source in MONEY_FIELDS.items():
        if source not in raw_record:
            assert result[target] is None


def test_no_hidden_read_or_write_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]
    banned = {"sqlalchemy", "pymongo", "requests", "httpx", "socket", "subprocess"}
    for path in (root / "src/transformation/types.py", root / "src/transformation/pure.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert all(name.split(".")[0] not in banned for name in names)


def test_parity_with_day07_on_valid_reference_fixture(
    raw_record: dict[str, object],
) -> None:
    legacy = pytest.importorskip("src.transformation.day07")
    original = legacy.transform_record(raw_record)
    improved = transform_canonical_record(raw_record)
    assert original == improved


def test_required_helpers_are_strict() -> None:
    with pytest.raises(TransformationError):
        required_text(" ", field="id")
    with pytest.raises(TransformationError):
        required_date(None, field="period")
    assert optional_text(" India ", field="country") == "India"
