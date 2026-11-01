"""Serialization and SQL parity static tests, without a DB connection."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from scripts.day39_42_research_export import (
    BASE_COLUMNS,
    _source_query,
    _warehouse_mismatch_query,
    canonical_digest,
)
from src.warehouse.research_contracts import FINANCIAL_COLUMNS, ResearchContractError


def test_complete_source_numeric_field_coverage() -> None:
    query = _warehouse_mismatch_query()
    selection = _source_query()
    assert len(FINANCIAL_COLUMNS) == 13
    for field in FINANCIAL_COLUMNS:
        assert f"f.{field} IS DISTINCT FROM s.{field}" in query
        assert f"s.{field}" in selection
    assert "s.source_checksum" in query
    assert "f.source_record_key" in query


def _row() -> dict[str, object]:
    example = dict.fromkeys(BASE_COLUMNS)
    example.update({
        "publication_run_id": "run-1",
        "credit_snapshot_id": 1,
        "credit_id": 2,
        "credit_number": "C1",
        "end_of_period": date(2024, 1, 31),
        "disbursed_amount_usd": Decimal("123.40"),
    })
    return example


def test_logical_hash_is_stable_and_sensitive() -> None:
    row = _row()
    digest = canonical_digest([row])
    assert digest == canonical_digest([dict(row)])
    changed = _row()
    changed["disbursed_amount_usd"] = Decimal("123.41")
    assert canonical_digest([changed]) != digest


def test_logical_hash_disambiguates_numeric_vs_string() -> None:
    row = _row()
    other = _row()
    other["disbursed_amount_usd"] = "123.40"
    assert canonical_digest([row]) != canonical_digest([other])


def test_logical_hash_rejects_float() -> None:
    row = _row()
    row["disbursed_amount_usd"] = 123.4
    with pytest.raises(ResearchContractError, match="Unserializable"):
        canonical_digest([row])
