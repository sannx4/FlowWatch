"""Dependency-ordered and correction-policy-aware canonical PostgreSQL upserts.

Caller supplies exact-source-decoded payloads and immutable lineage. This module
never calls MongoDB, the World Bank, or commits its own transactions.

Conflict strategy:
- Region: natural key region_name; insert or unchanged.
- Country/Project/Credit: natural keys; update genuinely changed mutable fields.
- Snapshot: (credit_id, end_of_period); equal business values -> unchanged.
  Changed values -> reject (default), ignore, or update with explicit opt-in.
No update is issued for a byte-equivalent canonical replay.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.sql.schema import Table

from src.db.models import Country, Credit, CreditSnapshot, Project, Region
from src.transformation.pure import transform_canonical_record

SnapshotPolicy = Literal["reject", "ignore", "update"]
Outcome = Literal["inserted", "updated", "unchanged", "ignored"]


class SnapshotCorrectionRequired(ValueError):
    """A changed snapshot needs an explicit, reviewed correction policy."""


@dataclass(frozen=True)
class SourceIdentity:
    run_id: UUID
    source_checksum: str
    source_record_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be UUID")
        if len(self.source_checksum) != 64 or any(
            char not in "0123456789abcdef" for char in self.source_checksum
        ):
            raise ValueError("source_checksum must be lowercase SHA-256 hex")
        if not self.source_record_key:
            raise ValueError("source_record_key cannot be empty")


@dataclass(frozen=True)
class CanonicalInput:
    payload: Mapping[str, Any]
    lineage: SourceIdentity


@dataclass(frozen=True)
class LoadedRecord:
    region_id: int
    country_id: int
    project_pk: int
    credit_id: int
    credit_snapshot_id: int
    outcomes: dict[str, Outcome]


def ensure_sql_numeric_precision(values: Mapping[str, Any]) -> None:
    """Fail before DML if the canonical NUMERIC column would silently round."""
    table = CreditSnapshot.__table__
    for name, value in values.items():
        if not isinstance(value, Decimal):
            continue
        scale = getattr(table.c[name].type, "scale", None)
        precision = getattr(table.c[name].type, "precision", None)
        if scale is None or precision is None:
            continue
        quantum = Decimal(1).scaleb(-scale)
        try:
            quantized = value.quantize(quantum)
        except InvalidOperation as exc:
            raise ValueError(f"{name}: cannot fit NUMERIC({precision},{scale})") from exc
        if quantized != value:
            raise ValueError(
                f"{name}: {value} would round in NUMERIC({precision},{scale}); "
                "investigate source and schema precision"
            )
        if len(quantized.as_tuple().digits) > precision:
            raise ValueError(f"{name}: exceeds NUMERIC({precision},{scale})")


def _compare_fields(
    row: RowMapping, values: Mapping[str, Any], fields: Sequence[str]
) -> bool:
    """True if any business field differs (not source audit fields)."""
    return any(row[field] != values[field] for field in fields)


def _upsert(
    connection: Connection,
    table: Table,
    *,
    pk: str,
    keys: tuple[str, ...],
    values: dict[str, Any],
    mode: Literal["update", "ignore"] = "update",
) -> tuple[int, Outcome]:
    assert keys and all(key in values for key in keys)
    where = and_(*(table.c[key] == values[key] for key in keys))
    previous = connection.execute(select(table).where(where)).mappings().one_or_none()
    changes = tuple(name for name in values if name not in keys)
    different = previous is not None and _compare_fields(previous, values, changes)

    statement = insert(table).values(**values)
    if mode == "update" and changes:
        excluded = statement.excluded
        # WHERE prevents PostgreSQL from rewriting unchanged tuples on retries.
        condition = or_(
            *(table.c[name].is_distinct_from(excluded[name]) for name in changes)
        )
        statement = statement.on_conflict_do_update(
            index_elements=list(keys),
            set_={name: excluded[name] for name in changes},
            where=condition,
        )
    else:
        statement = statement.on_conflict_do_nothing(index_elements=list(keys))

    found = connection.execute(statement.returning(table.c[pk])).scalar_one_or_none()
    if found is None:
        found = connection.execute(select(table.c[pk]).where(where)).scalar_one()
    if previous is None:
        # Single-writer batch evidence; concurrent writers may race this classification.
        outcome: Outcome = "inserted"
    elif not different:
        outcome = "unchanged"
    elif mode == "ignore":
        outcome = "ignored"
    else:
        outcome = "updated"
    return int(found), outcome


def load_exact_record(
    connection: Connection,
    item: CanonicalInput,
    *,
    snapshot_policy: SnapshotPolicy = "reject",
) -> LoadedRecord:
    """Write one validated, exact-decimal record; transaction owned by caller."""
    if snapshot_policy not in ("reject", "ignore", "update"):
        raise ValueError(f"Unknown snapshot policy: {snapshot_policy}")
    canonical = transform_canonical_record(item.payload)
    ensure_sql_numeric_precision(canonical["snapshot"])

    region_id, region_action = _upsert(
        connection,
        cast(Table, Region.__table__),
        pk="region_id", keys=("region_name",), values=dict(canonical["region"]),
    )
    country_id, country_action = _upsert(
        connection,
        cast(Table, Country.__table__),
        pk="country_id", keys=("country_code",),
        values={**canonical["country"], "region_id": region_id},
    )
    project_pk, project_action = _upsert(
        connection,
        cast(Table, Project.__table__),
        pk="project_pk", keys=("project_id",),
        values={**canonical["project"], "country_id": country_id},
    )
    credit_id, credit_action = _upsert(
        connection,
        cast(Table, Credit.__table__),
        pk="credit_id", keys=("credit_number",),
        values={**canonical["credit"], "project_pk": project_pk},
    )

    business = {**canonical["snapshot"], "credit_id": credit_id}
    snap_table = cast(Table, CreditSnapshot.__table__)
    snap_keys = ("credit_id", "end_of_period")
    predicate = and_(
        snap_table.c.credit_id == credit_id,
        snap_table.c.end_of_period == canonical["snapshot"]["end_of_period"],
    )
    previous = connection.execute(select(snap_table).where(predicate)).mappings().one_or_none()
    business_differs = previous is not None and _compare_fields(
        previous, business, tuple(business.keys())
    )
    if business_differs and snapshot_policy == "reject":
        raise SnapshotCorrectionRequired(
            "Existing temporal snapshot differs. Review source precedence "
            "and rerun with snapshot_policy='update' or 'ignore' explicitly."
        )
    if business_differs and previous is not None and (
        previous["source_record_key"] == item.lineage.source_record_key
    ):
        # A changed observation with an unchanged raw source identity indicates
        # a transform/storage inconsistency, not an independently sourced fix.
        raise SnapshotCorrectionRequired(
            "Same source_record_key produced different canonical values"
        )
    values = {
        **business,
        "ingestion_run_id": item.lineage.run_id,
        "source_checksum": item.lineage.source_checksum,
        "source_record_key": item.lineage.source_record_key,
    }
    # Identical financial observations keep the first accepted lineage; a
    # changed record switches lineage only under an explicit update decision.
    if previous is not None and not business_differs:
        snap_id = int(previous["credit_snapshot_id"])
        snapshot_action: Outcome = "unchanged"
    else:
        snap_id, snapshot_action = _upsert(
            connection,
            snap_table, pk="credit_snapshot_id", keys=snap_keys,
            values=values,
            mode="ignore" if snapshot_policy == "ignore" else "update",
        )
    return LoadedRecord(
        region_id, country_id, project_pk, credit_id, snap_id,
        {
            "regions": region_action,
            "countries": country_action,
            "projects": project_action,
            "credits": credit_action,
            "credit_snapshots": snapshot_action,
        },
    )


def load_exact_batch(
    connection: Connection,
    records: Sequence[CanonicalInput],
    *,
    snapshot_policy: SnapshotPolicy = "reject",
) -> tuple[tuple[LoadedRecord, ...], dict[str, int]]:
    """Batch loading is atomic when caller passes a transactional connection."""
    results = tuple(
        load_exact_record(connection, record, snapshot_policy=snapshot_policy)
        for record in records
    )
    counts: Counter[str] = Counter()
    for result in results:
        for entity, outcome in result.outcomes.items():
            counts[f"{entity}.{outcome}"] += 1
    return results, dict(sorted(counts.items()))
