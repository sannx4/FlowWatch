"""Day33 canonical publication from verified isolated historical Mongo raw evidence.

No upstream requests. No writes to the primary FlowWatch application database.
No implicit snapshot corrections. A publication is one PostgreSQL transaction.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from src.ingestion.historical_backfill import MONGO_DATABASE, PG_DATABASE
from src.ingestion.raw_envelope import RawPageEnvelope, RawRecordEnvelope
from src.loaders.day23_upsert import (
    CanonicalInput,
    SnapshotCorrectionRequired,
    SourceIdentity,
    ensure_sql_numeric_precision,
    load_exact_record,
)
from src.quality.day25_quarantine import RawLocator, record_rejection
from src.transformation.pure import transform_canonical_record
from src.warehouse.historical_contracts import (
    HistoricalCanonicalIntegrityError,
    SourceObservation,
    assert_identity_partition,
    profile_canonical_keys,
)

PARSER_VERSION = "historical-exact-source-decimal-v1"
QUARANTINE_RULE = "HISTORICAL_CANONICAL_VALIDATION"
MAX_OBSERVATIONS = 10000  # Explicit bounded release; stream for full 1.6M source later.


@dataclass(frozen=True)
class Candidate:
    observation: SourceObservation
    exact_payload: dict[str, Any]
    validation_error: str | None


def _reject_nonfinite(value: str) -> None:
    raise HistoricalCanonicalIntegrityError(f"Nonfinite source JSON constant: {value}")


def _guard_identity(engine: Engine) -> None:
    with engine.connect() as conn:
        identity = tuple(conn.execute(text(
            "SELECT current_database(), session_user, current_user"
        )).one())
        expected = (PG_DATABASE, "flowwatch_ingestor", "flowwatch_ingestor")
        if identity != expected:
            raise HistoricalCanonicalIntegrityError(
                f"REFUSING canonical writes: PostgreSQL identity {identity} != {expected}"
            )
        for table in ("historical_backfill_runs", "historical_backfill_pages",
                      "historical_canonical_publications", "historical_canonical_decisions",
                      "source_quarantine", "credit_snapshots"):
            if conn.execute(text("SELECT to_regclass(:table)"),
                            {"table": f"public.{table}"}).scalar_one() is None:
                raise HistoricalCanonicalIntegrityError(f"Missing migration: public.{table}")


def _load_candidates(engine: Engine, mongo: Any, run_id: UUID) -> tuple[list[Candidate], dict[str, Any]]:
    """Cross-check immutable PG manifests, Mongo envelopes and raw exact-decimal JSON."""
    with engine.connect() as conn:
        run = conn.execute(text("""
            SELECT dataset_id, resource_id, page_size, max_pages, observed_total, status
            FROM public.historical_backfill_runs WHERE run_id=:rid
        """), {"rid": run_id}).mappings().one_or_none()
        if run is None or run["status"] != "COMPLETE":
            raise HistoricalCanonicalIntegrityError("Backfill run must exist and be COMPLETE")
        checkpoint_rows = conn.execute(text("""
            SELECT page_number, page_offset, record_count, total_count,
                   source_checksum, raw_bytes_size
            FROM public.historical_backfill_pages
            WHERE run_id=:rid ORDER BY page_number
        """), {"rid": run_id}).mappings().all()
    if not checkpoint_rows:
        raise HistoricalCanonicalIntegrityError("No committed historical pages")
    checkpoints = [dict(row) for row in checkpoint_rows]
    expected_records = sum(int(row["record_count"]) for row in checkpoints)
    observed_total = int(run["observed_total"])
    page_size = int(run["page_size"])
    pages_in_source = (observed_total + page_size - 1) // page_size
    planned_pages = min(pages_in_source, int(run["max_pages"])) if run["max_pages"] else pages_in_source
    if len(checkpoints) != planned_pages:
        raise HistoricalCanonicalIntegrityError("Completed run has missing page checkpoints")
    for i, row in enumerate(checkpoints):
        offset = i * page_size
        if (row["page_number"] != i + 1 or row["page_offset"] != offset
                or row["record_count"] != min(page_size, observed_total - offset)
                or row["total_count"] != observed_total):
            raise HistoricalCanonicalIntegrityError("Historical page plan is not contiguous")
    if expected_records > MAX_OBSERVATIONS:
        raise HistoricalCanonicalIntegrityError(
            f"Refusing {expected_records} records; current bounded gate limit is {MAX_OBSERVATIONS}"
        )
    db = mongo[MONGO_DATABASE]
    rid = str(run_id)
    if db["raw_pages"].count_documents({"run_id": rid}) != len(checkpoints):
        raise HistoricalCanonicalIntegrityError("Uncheckpointed or missing Mongo raw pages")
    if db["raw_records"].count_documents({"run_id": rid}) != expected_records:
        raise HistoricalCanonicalIntegrityError("Mongo raw-record count does not match checkpoints")
    candidates: list[Candidate] = []
    raw_keys: list[str] = []
    checksums: dict[str, str] = {}
    source_keys: list[str] = []
    parsed_keys: list[tuple[str, Any]] = []
    for row in checkpoints:
        page_no = int(row["page_number"])
        page_doc = db["raw_pages"].find_one({"run_id": rid, "page_number": page_no})
        if page_doc is None:
            raise HistoricalCanonicalIntegrityError(f"Missing Mongo raw page {page_no}")
        envelope = RawPageEnvelope.from_mongo_document(page_doc)
        if (envelope.page_offset != row["page_offset"]
                or envelope.record_count != row["record_count"]
                or envelope.total_count != row["total_count"]
                or envelope.source_checksum != row["source_checksum"]
                or len(envelope.raw_bytes) != row["raw_bytes_size"]
                or envelope.dataset_id != run["dataset_id"]
                or envelope.resource_id != run["resource_id"]):
            raise HistoricalCanonicalIntegrityError(f"Cross-store page {page_no} mismatch")
        if hashlib.sha256(envelope.raw_bytes).hexdigest() != envelope.source_checksum:
            raise HistoricalCanonicalIntegrityError(f"Page {page_no} raw-byte checksum mismatch")
        try:
            normal = json.loads(envelope.raw_bytes, parse_constant=_reject_nonfinite)
            exact = json.loads(envelope.raw_bytes, parse_float=Decimal,
                               parse_constant=_reject_nonfinite)
        except (ValueError, UnicodeError) as exc:
            raise HistoricalCanonicalIntegrityError("Invalid immutable raw JSON") from exc
        if (not isinstance(normal, dict) or not isinstance(exact, dict)
                or not isinstance(normal.get("data"), list)
                or not isinstance(exact.get("data"), list)
                or normal != envelope.payload
                or len(normal["data"]) != envelope.record_count
                or len(exact["data"]) != envelope.record_count):
            raise HistoricalCanonicalIntegrityError("Raw page payload/length mismatch")
        raw_docs = list(db["raw_records"].find({"run_id": rid, "page_number": page_no}))
        by_index: dict[int, RawRecordEnvelope] = {}
        for raw_doc in raw_docs:
            record = RawRecordEnvelope.from_mongo_document(raw_doc)
            if record.record_index in by_index:
                raise HistoricalCanonicalIntegrityError("Duplicate raw record index")
            by_index[record.record_index] = record
            raw_keys.append(record.source_record_key)
        if len(by_index) != envelope.record_count:
            raise HistoricalCanonicalIntegrityError("Page raw-record count mismatch")
        for i, (normal_value, exact_value) in enumerate(zip(
            normal["data"], exact["data"], strict=True
        )):
            stored = by_index.get(i)
            if (stored is None or not isinstance(normal_value, dict)
                    or not isinstance(exact_value, dict)
                    or stored.run_id != run_id
                    or stored.page_offset != envelope.page_offset
                    or stored.source_checksum != envelope.source_checksum
                    or stored.payload != normal_value):
                raise HistoricalCanonicalIntegrityError("Raw-record value/locator mismatch")
            expected = RawRecordEnvelope.from_source_payload(
                run_id=run_id, dataset_id=envelope.dataset_id,
                resource_id=envelope.resource_id, retrieved_at=envelope.retrieved_at,
                page_number=page_no, page_offset=envelope.page_offset,
                record_index=i, source_checksum=envelope.source_checksum,
                payload=normal_value,
            )
            if stored.source_record_key != expected.source_record_key:
                raise HistoricalCanonicalIntegrityError("Deterministic raw source key changed")
            source_keys.append(expected.source_record_key)
            checksums[expected.source_record_key] = expected.source_checksum
            observation = SourceObservation(
                source_record_key=stored.source_record_key,
                source_checksum=stored.source_checksum,
                page_number=page_no, page_offset=envelope.page_offset,
                record_index=i, payload=normal_value,
            )
            error: str | None = None
            try:
                mapped = transform_canonical_record(exact_value)
                ensure_sql_numeric_precision(mapped["snapshot"])
                parsed_keys.append((mapped["credit"]["credit_number"],
                                    mapped["snapshot"]["end_of_period"]))
            except (ValueError, TypeError, OverflowError) as exc:
                error = f"{type(exc).__name__}: {str(exc)[:350]}"
            candidates.append(Candidate(observation, exact_value, error))
    if len(source_keys) != expected_records or len(set(source_keys)) != expected_records:
        raise HistoricalCanonicalIntegrityError("Missing or duplicate source record identities")
    if set(raw_keys) != set(source_keys) or len(raw_keys) != len(source_keys):
        raise HistoricalCanonicalIntegrityError("Cross-store raw identity partition failed")
    profile = profile_canonical_keys(parsed_keys)
    return candidates, {
        "run_id": rid, "pages": len(checkpoints), "raw_records": expected_records,
        "source_total_reported": int(run["observed_total"]),
        "valid_candidates": len(parsed_keys),
        "invalid_candidates": expected_records - len(parsed_keys),
        "temporal_profile": profile,
        "source_keys": source_keys,
        "raw_keys": raw_keys, "checksums": checksums,
    }


def _existing_publication(connection: Connection, run_id: UUID) -> dict[str, Any] | None:
    row = connection.execute(text("""
        SELECT source_pages, source_records, accepted, rejected, inserted,
               updated, unchanged, ignored, publication_status, parser_version
        FROM public.historical_canonical_publications WHERE run_id=:rid
    """), {"rid": run_id}).mappings().one_or_none()
    return dict(row) if row is not None else None


def _verify_existing(connection: Connection, run_id: UUID,
                     profile: Mapping[str, Any]) -> dict[str, Any] | None:
    published = _existing_publication(connection, run_id)
    if published is None:
        return None
    rows = connection.execute(text("""
        SELECT source_record_key, source_checksum, outcome,
               credit_snapshot_id, quarantine_id
        FROM public.historical_canonical_decisions WHERE run_id=:rid
    """), {"rid": run_id}).mappings().all()
    decisions = {str(row["source_record_key"]): str(row["outcome"]) for row in rows}
    if len(rows) != len(decisions):
        raise HistoricalCanonicalIntegrityError("Publication has duplicate ledger keys")
    counts = assert_identity_partition(profile["source_keys"], profile["raw_keys"], decisions)
    if (published["source_pages"] != profile["pages"]
            or published["source_records"] != profile["raw_records"]
            or published["accepted"] != counts["accepted"]
            or published["rejected"] != counts["rejected"]
            or any(published[k] != counts[k] for k in ("inserted", "updated", "unchanged", "ignored"))
            or published["publication_status"] != "PASS"
            or published["parser_version"] != PARSER_VERSION):
        raise HistoricalCanonicalIntegrityError("Stored canonical publication counts changed")
    for row in rows:
        if row["source_checksum"] != profile["checksums"][str(row["source_record_key"])]:
            raise HistoricalCanonicalIntegrityError("Publication decision checksum drift")
        if (row["outcome"] == "REJECTED") != (row["quarantine_id"] is not None):
            raise HistoricalCanonicalIntegrityError("Inconsistent quarantine decision")
        if (row["outcome"] != "REJECTED") != (row["credit_snapshot_id"] is not None):
            raise HistoricalCanonicalIntegrityError("Inconsistent snapshot decision")
    return {"status": "PASS_EXISTING_CANONICAL_PUBLICATION", "reused": True,
            "run_id": str(run_id), **counts, "pages": profile["pages"]}


def publish_historical_canonical(
    engine: Engine, mongo: Any, run_id: UUID, *, apply: bool = False,
    allow_quarantine: bool = False,
) -> dict[str, Any]:
    """Preview by default; --apply commits atomically with immutable decisions."""
    if allow_quarantine and not apply:
        raise ValueError("--allow-quarantine requires --apply")
    _guard_identity(engine)
    candidates, profile = _load_candidates(engine, mongo, run_id)
    preview = {
        "status": "PASS_CANONICAL_PREFLIGHT", "run_id": str(run_id),
        "canonical_loaded": False,
        "source_pages": profile["pages"], "source_records": profile["raw_records"],
        "source_total_reported": profile["source_total_reported"],
        "valid_candidates": profile["valid_candidates"],
        "invalid_candidates": profile["invalid_candidates"],
        "temporal_profile": profile["temporal_profile"],
        "limit": MAX_OBSERVATIONS,
        "note": "A bounded subset; not a representative sample or full backfill.",
    }
    with engine.connect() as conn:
        existing = _verify_existing(conn, run_id, profile)
    if existing is not None:
        return {**preview, **existing, "canonical_loaded": True}
    if not apply:
        return preview
    if profile["invalid_candidates"] and not allow_quarantine:
        raise HistoricalCanonicalIntegrityError(
            f"Preflight found {profile['invalid_candidates']} invalid records. "
            "No rows written; --allow-quarantine explicitly opts into partial publication."
        )
    # A global publication lock avoids racing changes to shared canonical natural keys
    # when *different* historical runs are promoted concurrently.
    with engine.connect() as guard:
        if not guard.execute(text("SELECT pg_try_advisory_lock(hashtext(:id))"),
                             {"id": "hist-canonical:global"}).scalar_one():
            raise HistoricalCanonicalIntegrityError("Another canonical publisher owns this run")
        try:
            outcomes: dict[str, str] = {}
            decisions: list[dict[str, Any]] = []
            with engine.begin() as conn:
                if _existing_publication(conn, run_id) is not None:
                    raise HistoricalCanonicalIntegrityError("Concurrent canonical publication already exists")
                for candidate in candidates:
                    o = candidate.observation
                    error = candidate.validation_error
                    snapshot_id: int | None = None
                    quarantine_id: int | None = None
                    outcome: str
                    if error is None:
                        try:
                            with conn.begin_nested():
                                result = load_exact_record(
                                    conn,
                                    CanonicalInput(
                                        candidate.exact_payload,
                                        SourceIdentity(run_id, o.source_checksum, o.source_record_key),
                                    ),
                                    snapshot_policy="reject",
                                )
                                snapshot_id = result.credit_snapshot_id
                                outcome = result.outcomes["credit_snapshots"].upper()
                        except (SnapshotCorrectionRequired, ValueError, TypeError, OverflowError) as exc:
                            error = f"{type(exc).__name__}: {str(exc)[:350]}"
                    if error is not None:
                        if not allow_quarantine:
                            raise HistoricalCanonicalIntegrityError(
                                f"Canonical publication blocked at page {o.page_number} "
                                f"index {o.record_index}: {error}. Transaction rolled back."
                            )
                        quarantine_id = record_rejection(
                            conn,
                            locator=RawLocator(
                                run_id=run_id, source_record_key=o.source_record_key,
                                source_checksum=o.source_checksum,
                                page_number=o.page_number, page_offset=o.page_offset,
                                record_index=o.record_index,
                            ),
                            rule_id=QUARANTINE_RULE,
                            offending_field="canonical_transform_or_snapshot",
                            offending_value=error,
                            detail=error,
                            parser_version=PARSER_VERSION,
                        )
                        outcome = "REJECTED"
                        snapshot_id = None
                    outcomes[o.source_record_key] = outcome
                    decisions.append({
                        "rid": run_id, "key": o.source_record_key,
                        "checksum": o.source_checksum, "outcome": outcome,
                        "snapshot": snapshot_id, "quarantine": quarantine_id,
                    })
                counts = assert_identity_partition(
                    profile["source_keys"], profile["raw_keys"], outcomes
                )
                if counts["rejected"] and not allow_quarantine:
                    raise HistoricalCanonicalIntegrityError("Refusing unexpected rejected records")
                conn.execute(text("""
                    INSERT INTO public.historical_canonical_publications (
                        run_id, source_pages, source_records, accepted, rejected,
                        inserted, updated, unchanged, ignored, publication_status, parser_version
                    ) VALUES (
                        :rid, :pages, :fetched, :accepted, :rejected,
                        :inserted, :updated, :unchanged, :ignored, 'PASS', :parser
                    )
                """), {"rid": run_id, "pages": profile["pages"],
                       **counts, "parser": PARSER_VERSION})
                conn.execute(text("""
                    INSERT INTO public.historical_canonical_decisions (
                        run_id, source_record_key, source_checksum, outcome,
                        credit_snapshot_id, quarantine_id
                    ) VALUES (:rid, :key, :checksum, :outcome, :snapshot, :quarantine)
                """), decisions)
                verified = _verify_existing(conn, run_id, profile)
                if verified is None:
                    raise HistoricalCanonicalIntegrityError("Missing publication ledger after insert")
            return {**preview, **counts, "status": "PASS_CANONICAL_PUBLICATION",
                    "canonical_loaded": True, "reused": False, "pages": profile["pages"]}
        finally:
            guard.execute(text("SELECT pg_advisory_unlock(hashtext(:id))"),
                          {"id": "hist-canonical:global"})
