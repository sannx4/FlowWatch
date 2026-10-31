"""Day 26: fail-closed, independently observed run-level reconciliation.

Expected keys are derived from verified source-page manifests, raw keys from
MongoDB, and decisions from committed PostgreSQL rows. None is inferred from
another count. Caller controls the SQL transaction and publication boundary.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

OUTCOMES = frozenset({"INSERTED", "UPDATED", "UNCHANGED", "IGNORED", "REJECTED"})
ACCEPTED = OUTCOMES - {"REJECTED"}


class ReconciliationError(RuntimeError):
    """No successful ingestion can contain an unexplained or duplicated record."""


@dataclass(frozen=True)
class ReconciliationResult:
    run_id: str
    attempt: int
    fetched: int
    raw_stored: int
    accepted: int
    rejected: int
    inserted: int
    updated: int
    unchanged: int
    ignored: int
    pages: int
    status: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def unique_keys(items: Iterable[str], label: str) -> set[str]:
    values = list(items)
    if not values:
        raise ReconciliationError(f"{label}: zero source records; refusing empty PASS")
    if any(not isinstance(value, str) or not value for value in values):
        raise ReconciliationError(f"{label}: invalid source_record_key")
    if len(values) != len(set(values)):
        repeats = [key for key, n in Counter(values).items() if n > 1]
        raise ReconciliationError(f"{label}: duplicate source keys {repeats[:5]}")
    return set(values)


def require_partition(expected: Iterable[str], raw: Iterable[str], decisions: Mapping[str, str]) -> dict[str, int]:
    """Exact identity partition—not merely equality of aggregate row counts."""
    expected_set = unique_keys(expected, "source manifests")
    raw_set = unique_keys(raw, "Mongo raw_records")
    if raw_set != expected_set:
        raise ReconciliationError(
            f"raw/source mismatch: missing_raw={sorted(expected_set - raw_set)[:5]} "
            f"unexpected_raw={sorted(raw_set - expected_set)[:5]}"
        )
    decision_set = set(decisions)
    if decision_set != expected_set:
        raise ReconciliationError(
            f"unexplained loss/extra decisions: missing={sorted(expected_set - decision_set)[:5]} "
            f"unexpected={sorted(decision_set - expected_set)[:5]}"
        )
    invalid = {key: value for key, value in decisions.items() if value not in OUTCOMES}
    if invalid:
        raise ReconciliationError(f"unsupported outcomes: {invalid}")
    counts = Counter(decisions.values())
    accepted = sum(counts[value] for value in ACCEPTED)
    rejected = counts["REJECTED"]
    if accepted + rejected != len(expected_set):
        raise ReconciliationError("accepted + rejected != fetched")
    return {
        "fetched": len(expected_set), "raw_stored": len(raw_set),
        "accepted": accepted, "rejected": rejected,
        "inserted": counts["INSERTED"], "updated": counts["UPDATED"],
        "unchanged": counts["UNCHANGED"], "ignored": counts["IGNORED"],
    }


def record_decision(
    connection: Connection, *, run_id: UUID, attempt: int, source_record_key: str,
    outcome: str, source_checksum: str, snapshot_id: int | None = None,
    quarantine_id: int | None = None,
) -> None:
    """One immutable decision per (run, attempt, source record)."""
    if outcome not in OUTCOMES or attempt < 1:
        raise ValueError("Invalid reconciliation outcome/attempt")
    if (outcome == "REJECTED") != (quarantine_id is not None):
        raise ValueError("Rejected decisions require quarantine ID only")
    if (outcome in ACCEPTED) != (snapshot_id is not None):
        raise ValueError("Accepted decisions require canonical snapshot ID only")
    connection.execute(text("""
        INSERT INTO public.etl_record_decisions
        (run_id, attempt_no, source_record_key, source_checksum, outcome,
         snapshot_id, quarantine_id)
        VALUES (:run_id, :attempt, :key, :checksum, :outcome, :snapshot, :quarantine)
    """), {
        "run_id": run_id, "attempt": attempt, "key": source_record_key,
        "checksum": source_checksum, "outcome": outcome,
        "snapshot": snapshot_id, "quarantine": quarantine_id,
    })


def reconcile_attempt(
    connection: Connection, *, run_id: UUID, attempt: int,
    manifest_keys: Iterable[str], raw_keys: Iterable[str], page_count: int,
) -> ReconciliationResult:
    """Reconcile DB decisions against independent source and Mongo observations.

    Invoke inside the same transaction as the decisions/canonical writes.
    An exception causes the caller to roll back the complete attempt.
    """
    if page_count < 1:
        raise ReconciliationError("At least one verified page is required")
    rows = connection.execute(text("""
        SELECT d.source_record_key, d.source_checksum, d.outcome,
               d.snapshot_id, d.quarantine_id,
               s.source_record_key AS snapshot_source_key,
               s.source_checksum AS snapshot_checksum,
               q.source_record_key AS quarantine_source_key,
               q.source_checksum AS quarantine_checksum
        FROM public.etl_record_decisions d
        LEFT JOIN public.credit_snapshots s ON s.credit_snapshot_id=d.snapshot_id
        LEFT JOIN public.source_quarantine q ON q.quarantine_id=d.quarantine_id
        WHERE d.run_id=:run_id AND d.attempt_no=:attempt
    """), {"run_id": run_id, "attempt": attempt}).mappings().all()
    decisions = {str(row["source_record_key"]): str(row["outcome"]) for row in rows}
    if len(decisions) != len(rows):
        raise ReconciliationError("Duplicate decisions in SQL ledger")
    for row in rows:
        outcome = str(row["outcome"])
        if outcome in ACCEPTED:
            if row["snapshot_id"] is None:
                raise ReconciliationError("Accepted decision has no canonical snapshot")
            # UNCHANGED may preserve older lineage from an earlier valid source
            # version; in this isolated test the source identity never changes.
            if row["snapshot_source_key"] != row["source_record_key"] or (
                str(row["snapshot_checksum"]) != str(row["source_checksum"])
            ):
                raise ReconciliationError("Canonical source lineage differs from decision")
        elif outcome == "REJECTED":
            if row["quarantine_id"] is None or (
                row["quarantine_source_key"] != row["source_record_key"]
                or str(row["quarantine_checksum"]) != str(row["source_checksum"])
            ):
                raise ReconciliationError("Rejected decision has no matching quarantine lineage")
    counts = require_partition(manifest_keys, raw_keys, decisions)
    summary = ReconciliationResult(
        run_id=str(run_id),
        attempt=attempt,
        pages=page_count,
        fetched=counts["fetched"],
        raw_stored=counts["raw_stored"],
        accepted=counts["accepted"],
        rejected=counts["rejected"],
        inserted=counts["inserted"],
        updated=counts["updated"],
        unchanged=counts["unchanged"],
        ignored=counts["ignored"],
    )
    # An insert only occurs after full reconciliation. No successful row can be
    # fabricated by trusting a caller-provided count.
    connection.execute(text("""
        INSERT INTO public.etl_attempts
        (run_id, attempt_no, source_pages, fetched, raw_stored, accepted,
         rejected, inserted, updated, unchanged, ignored, status, completed_at)
        VALUES (:run_id, :attempt, :pages, :fetched, :raw_stored, :accepted,
                :rejected, :inserted, :updated, :unchanged, :ignored,
                'PASS', now())
    """), {"run_id": run_id, "attempt": attempt, **{
        key: value for key, value in summary.to_dict().items()
        if key not in {"run_id", "attempt", "status"}
    }})
    return summary
