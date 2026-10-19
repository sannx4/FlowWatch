"""Day 24 SQL and source mapping unit contracts; no database writes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from src.loaders.day23_upsert import CanonicalInput, SourceIdentity
from src.loaders.day24_bulk import (
    _BUSINESS_COLUMNS,
    _COPY_COLUMNS,
    _NON_KEY_BUSINESS,
    DuplicateSnapshotIdentity,
    _difference_sql,
    _stage_sql,
    _validate_input,
    load_bulk_batch,
)


def _record(*, period: str = "30-Jun-2022", money: str = "125.50") -> CanonicalInput:
    return CanonicalInput(
        payload={
            "region": "South Asia",
            "country_code": "IN", "country": "India",
            "project_id": "P100001", "credit_number": "IDA100001",
            "end_of_period": period, "original_principal_amount_us_": money,
        },
        lineage=SourceIdentity(
            UUID("00000000-0000-4000-8000-000000000003"),
            "a" * 64, "day24:known-source:0",
        ),
    )


def test_copy_has_every_snapshot_business_field_and_provenance() -> None:
    assert {"credit_id", "end_of_period", "credit_status"} <= set(_BUSINESS_COLUMNS)
    assert {
        "service_charge_rate", "disbursed_amount_usd", "credits_held_usd"
    } <= set(_BUSINESS_COLUMNS)
    assert set(_COPY_COLUMNS) - set(_BUSINESS_COLUMNS) == {
        "ingestion_run_id", "source_checksum", "source_record_key"
    }
    assert "credit_snapshot_id" not in _COPY_COLUMNS
    assert "created_at" not in _COPY_COLUMNS


def test_stage_is_temporary_constraint_free_ctas() -> None:
    stmt = _stage_sql()
    assert "CREATE TEMP TABLE" in stmt
    assert "ON COMMIT DROP" in stmt
    assert "WITH NO DATA" in stmt
    assert "FROM public.credit_snapshots" in stmt


def test_correction_comparison_includes_temporal_business_values() -> None:
    predicate = _difference_sql("credit_snapshots", "EXCLUDED")
    assert "IS DISTINCT FROM" in predicate
    assert "credit_status" in predicate
    assert "original_principal_amount_usd" in predicate
    assert "source_checksum" not in predicate
    assert "credit_id" not in _NON_KEY_BUSINESS
    assert "end_of_period" not in _NON_KEY_BUSINESS


def test_real_precision_preserved_before_copy() -> None:
    parsed = _validate_input([_record(money="125.50")], "reject")
    assert parsed[0]["snapshot"]["original_principal_amount_usd"] == Decimal("125.50")
    assert parsed[0]["snapshot"]["end_of_period"] == date(2022, 6, 30)


def test_bad_precision_rejected_before_any_db_write() -> None:
    with pytest.raises(ValueError, match="would round"):
        _validate_input([_record(money="1.001")], "reject")


def test_duplicate_temporal_snapshot_rejected_before_write() -> None:
    with pytest.raises(DuplicateSnapshotIdentity, match="Repeated"):
        _validate_input([_record(), _record()], "reject")


def test_invalid_correction_policy_rejected_before_any_db_write() -> None:
    with pytest.raises(ValueError, match="Unknown snapshot policy"):
        load_bulk_batch(None, [_record()], snapshot_policy="unreviewed")  # type: ignore[arg-type]


def test_float_input_not_silently_accepted() -> None:
    item = _record()
    payload = {**item.payload, "original_principal_amount_us_": 1.123}
    with pytest.raises(ValueError, match="binary floats"):
        _validate_input([CanonicalInput(payload, item.lineage)], "reject")


def test_zero_record_batch_returns_no_writes() -> None:
    class FakeConnection:
        def in_transaction(self) -> bool:
            return True

    output = load_bulk_batch(FakeConnection(), [])  # type: ignore[arg-type]
    assert output.input_records == 0
    assert output.inserted == 0
    assert output.snapshot_ids == ()


def test_fixture_source_sha_and_exact_decimal(tmp_path: Path) -> None:
    import hashlib

    from scripts.day24_bulk_benchmark import _load_source

    path = tmp_path / "source.json"
    raw = (
        '{"data":[{"region":"South Asia","country_code":"IN",'
        '"country":"India","project_id":"P100001",'
        '"credit_number":"IDA100001","end_of_period":"30-Jun-2022",'
        '"original_principal_amount_us_":125.50}]}'
    )
    path.write_text(raw, encoding="utf-8")
    items, digest, count = _load_source(path, 1)
    assert count == 1
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert items[0].payload["original_principal_amount_us_"] == Decimal("125.50")
    assert items[0].lineage.source_record_key.endswith(":0")
