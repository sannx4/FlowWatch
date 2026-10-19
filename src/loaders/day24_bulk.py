"""Atomic COPY-to-staging snapshot loader matching the Day-23 row-loader contract.

The caller owns the PostgreSQL transaction. Source bytes are never changed.
The Day-23 entity _upsert is retained as the correctness reference; only the
snapshot-write path is optimized with psycopg3 COPY + set-based INSERT.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.sql.schema import Table

from src.db.models import Country, Credit, CreditSnapshot, Project, Region
from src.loaders.day23_upsert import (
    CanonicalInput,
    SnapshotCorrectionRequired,
    SnapshotPolicy,
    _upsert,
    ensure_sql_numeric_precision,
)
from src.transformation.pure import transform_canonical_record
from src.transformation.types import CanonicalValues

# Schema-controlled column names; no user-generated SQL identifiers are accepted.
_BUSINESS_COLUMNS = tuple(
    col.name for col in CreditSnapshot.__table__.columns
    if col.name not in (
        "credit_snapshot_id", "ingestion_run_id", "source_checksum",
        "source_record_key", "created_at",
    )
)
_AUDIT_COLUMNS = ("ingestion_run_id", "source_checksum", "source_record_key")
_COPY_COLUMNS = (*_BUSINESS_COLUMNS, *_AUDIT_COLUMNS)
_STAGE = "flowwatch_d24_stage"
_KEYS = ("credit_id", "end_of_period")
_NON_KEY_BUSINESS = tuple(col for col in _BUSINESS_COLUMNS if col not in _KEYS)


class DuplicateSnapshotIdentity(ValueError):
    """A batch contained conflicting or repeated temporal identities."""


@dataclass(frozen=True)
class BulkLoadResult:
    input_records: int
    inserted: int
    updated: int
    unchanged: int
    ignored: int
    copy_seconds: float
    merge_seconds: float
    entity_seconds: float
    snapshot_ids: tuple[int, ...]


def _stage_sql() -> str:
    columns = ", ".join(_COPY_COLUMNS)
    return (
        f"CREATE TEMP TABLE {_STAGE} ON COMMIT DROP AS "
        f"SELECT {columns} FROM public.credit_snapshots WITH NO DATA"
    )


def _difference_sql(left: str, right: str) -> str:
    return " OR ".join(
        f"{left}.{name} IS DISTINCT FROM {right}.{name}"
        for name in _NON_KEY_BUSINESS
    )


def _copy_rows(connection: Connection, rows: Sequence[Mapping[str, Any]]) -> None:
    """psycopg3 COPY uses SQLAlchemy's *same* checked-out transaction."""
    if not rows:
        return
    statement = f"COPY {_STAGE} ({', '.join(_COPY_COLUMNS)}) FROM STDIN"
    # SQLAlchemy Connection.connection is a PoolProxiedConnection;
    # driver_connection is psycopg.Connection for the postgresql+psycopg dialect.
    driver: Any = connection.connection.driver_connection
    if driver is None or not hasattr(driver, "cursor"):
        raise TypeError("Day 24 requires a psycopg3 PostgreSQL driver")
    with driver.cursor() as cursor, cursor.copy(statement) as copy:
        for row in rows:
            copy.write_row(tuple(row[name] for name in _COPY_COLUMNS))


def _resolve_entities(
    connection: Connection, canonical: CanonicalValues,
) -> int:
    region_id, _ = _upsert(
        connection, cast(Table, Region.__table__),
        pk="region_id", keys=("region_name",), values=dict(canonical["region"]),
    )
    country_id, _ = _upsert(
        connection, cast(Table, Country.__table__), pk="country_id",
        keys=("country_code",),
        values={**canonical["country"], "region_id": region_id},
    )
    project_pk, _ = _upsert(
        connection, cast(Table, Project.__table__), pk="project_pk",
        keys=("project_id",),
        values={**canonical["project"], "country_id": country_id},
    )
    credit_id, _ = _upsert(
        connection, cast(Table, Credit.__table__), pk="credit_id",
        keys=("credit_number",),
        values={**canonical["credit"], "project_pk": project_pk},
    )
    return credit_id


def _validate_input(
    records: Sequence[CanonicalInput], snapshot_policy: SnapshotPolicy,
) -> tuple[CanonicalValues, ...]:
    if snapshot_policy not in ("reject", "ignore", "update"):
        raise ValueError(f"Unknown snapshot policy: {snapshot_policy}")
    parsed: list[CanonicalValues] = []
    seen: set[tuple[str, Any]] = set()
    for item in records:
        canonical = transform_canonical_record(item.payload)
        ensure_sql_numeric_precision(canonical["snapshot"])
        identity = (
            canonical["credit"]["credit_number"],
            canonical["snapshot"]["end_of_period"],
        )
        if identity in seen:
            raise DuplicateSnapshotIdentity(f"Repeated (credit_number, period): {identity}")
        seen.add(identity)
        parsed.append(canonical)
    return tuple(parsed)


def load_bulk_batch(
    connection: Connection,
    records: Sequence[CanonicalInput],
    *,
    snapshot_policy: SnapshotPolicy = "reject",
) -> BulkLoadResult:
    """Set-based idempotent snapshot load; never commit or rollback itself.

    Preconditions: single-writer controlled load, SQLAlchemy transaction active,
    PostgreSQL + psycopg3, input passes upstream quality gate. On failure, caller
    MUST roll back the entire transaction, including entity UPSERTs.
    """
    parsed = _validate_input(records, snapshot_policy)
    if not connection.in_transaction():
        raise RuntimeError("Caller must supply an active database transaction")
    if not records:
        return BulkLoadResult(0, 0, 0, 0, 0, 0.0, 0.0, 0.0, ())

    # Entity UPSERT behavior matches Day 23 exactly, including mutable attributes.
    before_entities = perf_counter()
    staged: list[dict[str, Any]] = []
    for item, canonical in zip(records, parsed, strict=True):
        credit_id = _resolve_entities(connection, canonical)
        staged.append({
            **canonical["snapshot"],
            "credit_id": credit_id,
            "ingestion_run_id": item.lineage.run_id,
            "source_checksum": item.lineage.source_checksum,
            "source_record_key": item.lineage.source_record_key,
        })
    entity_seconds = perf_counter() - before_entities

    connection.execute(text(f"DROP TABLE IF EXISTS pg_temp.{_STAGE}"))
    connection.execute(text(_stage_sql()))
    copied_at = perf_counter()
    _copy_rows(connection, staged)
    copy_seconds = perf_counter() - copied_at

    # A separate check is intentional: Day 23 rejects corrections using the SAME
    # source_record_key even when policy='ignore'. A changed source version must
    # also be explicitly reviewed and opted into ('update' or 'ignore').
    merged_at = perf_counter()
    difference = _difference_sql("live", "stage")
    matched = connection.execute(text(f"""
        SELECT live.credit_id, live.end_of_period,
               live.source_record_key AS existing_source_record_key,
               stage.source_record_key AS incoming_source_record_key,
               ({difference}) AS business_differs
        FROM public.credit_snapshots AS live
        JOIN {_STAGE} AS stage USING (credit_id, end_of_period)
    """)).mappings().all()
    changed = [row for row in matched if row["business_differs"]]
    for row in changed:
        if row["existing_source_record_key"] == row["incoming_source_record_key"]:
            raise SnapshotCorrectionRequired(
                "Same source_record_key produced different canonical values"
            )
    if changed and snapshot_policy == "reject":
        raise SnapshotCorrectionRequired(
            f"{len(changed)} existing temporal snapshots differ; explicit "
            "reviewed 'update' or 'ignore' policy required"
        )

    # The initial benchmark is single-writer. A production
    # correction-precedence/serialization policy remains future work.
    columns = ", ".join(_COPY_COLUMNS)
    select_columns = ", ".join(f"stage.{col}" for col in _COPY_COLUMNS)
    insert_sql = (
        f"INSERT INTO public.credit_snapshots ({columns}) "
        f"SELECT {select_columns} FROM {_STAGE} AS stage WHERE TRUE "
    )
    if snapshot_policy == "update":
        setters = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in (*_NON_KEY_BUSINESS, *_AUDIT_COLUMNS)
        )
        predicate = _difference_sql("credit_snapshots", "EXCLUDED")
        insert_sql += (
            "ON CONFLICT (credit_id, end_of_period) DO UPDATE "
            f"SET {setters} WHERE ({predicate})"
        )
    else:
        insert_sql += "ON CONFLICT (credit_id, end_of_period) DO NOTHING"
    connection.execute(text(insert_sql))

    # Query only selected staging identities, not unrelated rows in this DB.
    ids = connection.execute(text(f"""
        SELECT stage.credit_id, stage.end_of_period, live.credit_snapshot_id
        FROM {_STAGE} AS stage
        JOIN public.credit_snapshots AS live USING (credit_id, end_of_period)
    """)).all()
    if len(ids) != len(records):
        raise AssertionError("Bulk merge lost source observations")
    pk_by_key = {(r[0], r[1]): int(r[2]) for r in ids}
    result_ids = tuple(
        pk_by_key[(row["credit_id"], row["end_of_period"])] for row in staged
    )
    updated = len(changed) if snapshot_policy == "update" else 0
    ignored = len(changed) if snapshot_policy == "ignore" else 0
    inserted = len(records) - len(matched)
    unchanged = len(matched) - len(changed)
    return BulkLoadResult(
        input_records=len(records), inserted=inserted, updated=updated,
        unchanged=unchanged, ignored=ignored,
        copy_seconds=copy_seconds,
        merge_seconds=perf_counter() - merged_at,
        entity_seconds=entity_seconds,
        snapshot_ids=result_ids,
    )
