"""Persistent, idempotent source-quarantine decisions for FlowWatch Day 25.

All writes are transactional and caller-owned. Original MongoDB source bytes are
never altered. Stored offending values are JSON-safe diagnostics, not a repaired
source payload. No network operations occur here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

RULE_EXACT_DECIMAL = "EXACT_DECIMAL_FROM_SOURCE_REQUIRED"
BROKEN_PARSER = "legacy-bson-float-v1"
FIXED_PARSER = "exact-source-rehydrate-v1"


@dataclass(frozen=True)
class RawLocator:
    run_id: UUID
    source_record_key: str
    source_checksum: str
    page_number: int
    page_offset: int
    record_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be UUID")
        if not self.source_record_key:
            raise ValueError("source_record_key required")
        if len(self.source_checksum) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.source_checksum
        ):
            raise ValueError("source_checksum must be lowercase SHA-256")
        if min(self.page_number, self.page_offset, self.record_index) < 0:
            raise ValueError("Source offsets cannot be negative")


def float_financial_field(record: dict[str, Any]) -> tuple[str, float]:
    """Find an actual BSON float that the strict decimal mapper must reject."""
    for field, value in sorted(record.items()):
        if isinstance(value, float) and (
            field.endswith("_us_") or field == "service_charge_rate"
        ):
            return field, value
    raise ValueError("No financial float found: cannot exercise this failure gate")


def record_rejection(
    connection: Connection,
    *,
    locator: RawLocator,
    rule_id: str,
    offending_field: str,
    offending_value: str,
    detail: str,
    parser_version: str,
) -> int:
    """Durably record a failure on commit; same event deduplicates on replay."""
    if not rule_id or not offending_field or not parser_version:
        raise ValueError("Rule, offending field and parser version are required")
    # Stringifies the diagnostic to avoid JSON float precision and sensitive payload copies.
    stmt = text("""
        INSERT INTO public.source_quarantine
            (source_run_id, source_record_key, source_checksum,
             page_number, page_offset, record_index, rule_id,
             offending_field, offending_value, failure_detail, failed_parser_version)
        VALUES (:source_run_id, :source_record_key, :source_checksum,
                :page_number, :page_offset, :record_index, :rule_id,
                :offending_field, jsonb_build_object('source_repr', CAST(:offending_value AS text)),
                :failure_detail, :failed_parser_version)
        ON CONFLICT (source_run_id, source_record_key, rule_id, failed_parser_version)
        DO UPDATE SET occurrences = source_quarantine.occurrences + 1,
                      last_seen_at = now(),
                      failure_detail = EXCLUDED.failure_detail
        RETURNING quarantine_id
    """)
    return int(connection.execute(stmt, {
        "source_run_id": locator.run_id,
        "source_record_key": locator.source_record_key,
        "source_checksum": locator.source_checksum,
        "page_number": locator.page_number,
        "page_offset": locator.page_offset,
        "record_index": locator.record_index,
        "rule_id": rule_id,
        "offending_field": offending_field,
        "offending_value": offending_value,
        "failure_detail": detail,
        "failed_parser_version": parser_version,
    }).scalar_one())


def fetch_locked(connection: Connection, quarantine_id: int) -> dict[str, Any]:
    row = connection.execute(
        text("SELECT * FROM public.source_quarantine WHERE quarantine_id=:id FOR UPDATE"),
        {"id": quarantine_id},
    ).mappings().one_or_none()
    if row is None:
        raise LookupError(f"Quarantine ID {quarantine_id} not found")
    return dict(row)


def resolve_rejection(
    connection: Connection, *, quarantine_id: int, snapshot_id: int,
    parser_version: str,
) -> None:
    if not parser_version or snapshot_id <= 0:
        raise ValueError("Successful replay requires parser version and snapshot ID")
    result = connection.execute(text("""
        UPDATE public.source_quarantine
        SET status='RESOLVED', retry_count=retry_count+1,
            resolved_at=now(), last_retry_at=now(), last_error=NULL,
            resolved_parser_version=:parser_version,
            resolved_snapshot_id=:snapshot_id
        WHERE quarantine_id=:id AND status IN ('PENDING','BLOCKED')
        RETURNING quarantine_id
    """), {"id": quarantine_id, "parser_version": parser_version,
           "snapshot_id": snapshot_id}).scalar_one_or_none()
    if result is None:
        raise RuntimeError("Cannot resolve this quarantine row in its current state")


def record_retry_failure(connection: Connection, *, quarantine_id: int, error: str) -> None:
    connection.execute(text("""
        UPDATE public.source_quarantine
        SET status='BLOCKED', retry_count=retry_count+1,
            last_retry_at=now(), last_error=:error
        WHERE quarantine_id=:id AND status <> 'RESOLVED'
    """), {"id": quarantine_id, "error": error[:1000]})
