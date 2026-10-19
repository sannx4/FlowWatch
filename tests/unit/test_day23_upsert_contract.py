"""Day-23 security, key, precision and conflict-policy unit contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import UniqueConstraint

from src.db.models import Country, Credit, CreditSnapshot, Project, Region
from src.loaders.day23_upsert import (
    CanonicalInput,
    SourceIdentity,
    _compare_fields,
    ensure_sql_numeric_precision,
    load_exact_record,
)


@pytest.mark.parametrize(
    ("model", "keys"),
    [
        (Region, ("region_name",)),
        (Country, ("country_code",)),
        (Project, ("project_id",)),
        (Credit, ("credit_number",)),
        (CreditSnapshot, ("credit_id", "end_of_period")),
    ],
)
def test_real_schema_enforces_natural_key(model: type, keys: tuple[str, ...]) -> None:
    found = {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert keys in found


def test_lineage_accepts_real_sha256() -> None:
    identity = SourceIdentity(
        UUID("00000000-0000-4000-8000-000000000001"),
        "a" * 64,
        "stored-raw-source-key",
    )
    assert identity.source_checksum == "a" * 64


@pytest.mark.parametrize("invalid", ["", "ab", "X" * 64, "g" * 64])
def test_bad_lineage_digest_rejected(invalid: str) -> None:
    with pytest.raises(ValueError):
        SourceIdentity(UUID(int=1), invalid, "source-key")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("original_principal_amount_usd", Decimal("1.001")),
        ("service_charge_rate", Decimal("0.0000009")),
    ],
)
def test_precision_loss_is_rejected(field: str, value: Decimal) -> None:
    with pytest.raises(ValueError, match="would round"):
        ensure_sql_numeric_precision({field: value})


def test_exact_decimal_cents_accepted() -> None:
    ensure_sql_numeric_precision(
        {
            "original_principal_amount_usd": Decimal("123456789.01"),
            "service_charge_rate": Decimal("0.123456"),
        }
    )


def test_snapshot_date_is_real_column() -> None:
    assert "end_of_period" in CreditSnapshot.__table__.c
    assert date(2025, 1, 1).isoformat() == "2025-01-01"


def test_value_comparison_is_exact() -> None:
    assert not _compare_fields(
        {"amount": Decimal("1.00")}, {"amount": Decimal("1.0")}, ["amount"]
    )
    assert _compare_fields({"amount": Decimal("1.00")}, {"amount": None}, ["amount"])


def test_bad_policy_rejected_before_network_or_database_calls() -> None:
    item = CanonicalInput(
        payload={},
        lineage=SourceIdentity(UUID(int=1), "a" * 64, "key"),
    )
    with pytest.raises(ValueError, match="Unknown snapshot policy"):
        load_exact_record(None, item, snapshot_policy="made_up")  # type: ignore[arg-type]


def test_entity_dependency_order_with_exact_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.loaders import day23_upsert

    calls: list[str] = []

    def fake_upsert(
        connection: object,
        table: object,
        *,
        pk: str,
        keys: tuple[str, ...],
        values: dict[str, object],
        mode: str = "update",
    ) -> tuple[int, str]:
        del connection, pk, keys, mode
        name = table.name  # type: ignore[attr-defined]
        calls.append(name)
        return len(calls), "inserted"

    class FakeResult:
        def mappings(self) -> FakeResult:
            return self

        def one_or_none(self) -> None:
            return None

    class FakeConnection:
        def execute(self, statement: object) -> FakeResult:
            del statement
            return FakeResult()

    monkeypatch.setattr(day23_upsert, "_upsert", fake_upsert)
    item = CanonicalInput(
        payload={
            "region": "South Asia",
            "country_code": "IN",
            "country": "India",
            "project_id": "P12345",
            "credit_number": "IDA12345",
            "end_of_period": "01-Jan-2025",
            "disbursed_amount_us_": "200.00",
        },
        lineage=SourceIdentity(UUID(int=1), "b" * 64, "test-run-record"),
    )
    loaded = day23_upsert.load_exact_record(FakeConnection(), item)  # type: ignore[arg-type]
    assert calls == ["regions", "countries", "projects", "credits", "credit_snapshots"]
    assert loaded.credit_snapshot_id == 5
    assert loaded.outcomes["credit_snapshots"] == "inserted"


def test_postgres_upsert_is_guarded_against_noop_updates() -> None:
    from sqlalchemy.dialects import postgresql

    from src.loaders.day23_upsert import _upsert

    statements: list[str] = []

    class FakeResult:
        def __init__(self, operation: str) -> None:
            self.operation = operation

        def mappings(self) -> FakeResult:
            return self

        def one_or_none(self) -> dict[str, object]:
            return {
                "country_id": 7,
                "country_code": "IN",
                "country_name": "India",
                "region_id": 1,
            }

        def scalar_one_or_none(self) -> None:
            return None

        def scalar_one(self) -> int:
            return 7

    class FakeConnection:
        def execute(self, statement: object) -> FakeResult:
            sql = str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]
            statements.append(sql)
            return FakeResult("insert" if sql.startswith("INSERT") else "select")

    pk, outcome = _upsert(
        FakeConnection(),  # type: ignore[arg-type]
        Country.__table__,
        pk="country_id",
        keys=("country_code",),
        values={
            "country_code": "IN",
            "country_name": "India",
            "region_id": 1,
        },
    )
    assert (pk, outcome) == (7, "unchanged")
    assert any("ON CONFLICT" in sql and "IS DISTINCT FROM" in sql for sql in statements)
