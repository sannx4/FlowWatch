"""Real World Bank top/skip extraction with durable PG checkpoints and Mongo raw landing.

The checkpoint is written only AFTER a complete, checksum-verified Mongo page and
all its raw records exist. A crash between Mongo persistence and PG commit is
recovered from Mongo without a second upstream request. This module never writes
canonical credit tables and is deliberately limited to an isolated gate DB.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.ingestion.historical_plan import (
    PageSpec,
    assert_page_contract,
    is_full_capture,
    plan_pages,
)
from src.ingestion.mongodb_indexes import ensure_raw_indexes
from src.ingestion.mongodb_raw_loader import MongoRawLoader
from src.ingestion.raw_envelope import RawPageEnvelope, RawRecordEnvelope
from src.ingestion.worldbank_client import (
    DEFAULT_DATASET_ID,
    DEFAULT_RESOURCE_ID,
    WorldBankClient,
    WorldBankClientConfig,
    WorldBankResponse,
)

PG_DATABASE = "flowwatch_historical_gate"
MONGO_DATABASE = "flowwatch_historical_gate_raw"


class BackfillIntegrityError(RuntimeError):
    """Fail closed when source, Mongo, or checkpoint evidence disagrees."""


@dataclass(frozen=True)
class BackfillOptions:
    run_id: UUID
    page_size: int = 1000
    max_pages: int = 3
    workers: int = 2
    fail_after_pages: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 1000:
            raise ValueError("page_size must be 1..1000")
        if self.max_pages < 0 or not 1 <= self.workers <= 4:
            raise ValueError("max_pages >= 0 and workers must be 1..4")
        if self.fail_after_pages < 0:
            raise ValueError("fail_after_pages cannot be negative")


def emit(event: str, **fields: Any) -> None:
    print(json.dumps({
        "at_utc": datetime.now(UTC).isoformat(), "component": "flowwatch.historical_backfill",
        "event": event, **fields,
    }, sort_keys=True, default=str), flush=True)


def _required_engine_identity(engine: Engine) -> None:
    with engine.connect() as con:
        actual = tuple(con.execute(text(
            "SELECT current_database(), session_user, current_user"
        )).one())
        expected = (PG_DATABASE, "flowwatch_ingestor", "flowwatch_ingestor")
        if actual != expected:
            raise BackfillIntegrityError(f"REFUSING PostgreSQL writes: {actual} != {expected}")
        for name in ("historical_backfill_runs", "historical_backfill_pages"):
            if con.execute(text("SELECT to_regclass(:name)"),
                           {"name": f"public.{name}"}).scalar_one() is None:
                raise BackfillIntegrityError(f"Migration missing public.{name}")


def _run_row(engine: Engine, rid: UUID) -> dict[str, Any] | None:
    with engine.connect() as con:
        row = con.execute(text("""
            SELECT dataset_id, resource_id, page_size, max_pages, observed_total,
                   status, last_error FROM public.historical_backfill_runs WHERE run_id=:rid
        """), {"rid": rid}).mappings().first()
        return dict(row) if row else None


def _create_or_resume(engine: Engine, opts: BackfillOptions) -> dict[str, Any]:
    with engine.begin() as con:
        row = con.execute(text("""
            SELECT dataset_id, resource_id, page_size, max_pages, observed_total,
                   status, last_error FROM public.historical_backfill_runs
            WHERE run_id=:rid FOR UPDATE
        """), {"rid": opts.run_id}).mappings().first()
        if row:
            if (row["dataset_id"], row["resource_id"], row["page_size"], row["max_pages"]) != (
                DEFAULT_DATASET_ID, DEFAULT_RESOURCE_ID, opts.page_size, opts.max_pages
            ):
                raise BackfillIntegrityError("Resume configuration differs from original run")
            if row["status"] != "COMPLETE":
                con.execute(text("""
                    UPDATE public.historical_backfill_runs
                       SET status='RUNNING', updated_at=now(), last_error=NULL
                     WHERE run_id=:rid
                """), {"rid": opts.run_id})
            return dict(row)
        con.execute(text("""
            INSERT INTO public.historical_backfill_runs
                (run_id, dataset_id, resource_id, page_size, max_pages, status)
            VALUES (:rid, :dataset, :resource, :size, :max_pages, 'RUNNING')
        """), {"rid": opts.run_id, "dataset": DEFAULT_DATASET_ID,
               "resource": DEFAULT_RESOURCE_ID, "size": opts.page_size,
               "max_pages": opts.max_pages})
    return {"observed_total": None, "status": "RUNNING"}


def _committed(engine: Engine, rid: UUID) -> dict[int, dict[str, Any]]:
    with engine.connect() as con:
        rows = con.execute(text("""
            SELECT page_number, page_offset, record_count, total_count,
                   source_checksum, raw_bytes_size
            FROM public.historical_backfill_pages WHERE run_id=:rid
        """), {"rid": rid}).mappings().all()
    return {int(r["page_number"]): dict(r) for r in rows}


def _stored_mongo_page(db: Any, rid: UUID, spec: PageSpec) -> Any | None:
    return db["raw_pages"].find_one({"run_id": str(rid), "page_offset": spec.offset})


def _verify_raw_page(db: Any, rid: UUID, spec: PageSpec, expected_total: int) -> dict[str, Any] | None:
    document = _stored_mongo_page(db, rid, spec)
    if document is None:
        return None
    envelope = RawPageEnvelope.from_mongo_document(document)
    if envelope.page_number != spec.number or envelope.page_offset != spec.offset:
        raise BackfillIntegrityError("Mongo raw page boundary mismatch")
    if envelope.record_count != spec.expected_count or envelope.total_count != expected_total:
        raise BackfillIntegrityError("Mongo raw page count or source-total drift")
    digest = hashlib.sha256(envelope.raw_bytes).hexdigest()
    if digest != envelope.source_checksum:
        raise BackfillIntegrityError("Mongo raw page checksum corrupted")
    # A process may die after the page document was stored but before all raw
    # records completed. Recover records from checksum-verified Mongo raw bytes,
    # never by refetching a potentially changed upstream page.
    payload = json.loads(envelope.raw_bytes)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise BackfillIntegrityError("Persisted raw bytes do not contain a data list")
    if len(payload["data"]) != spec.expected_count or payload != envelope.payload:
        raise BackfillIntegrityError("Persisted raw payload differs from exact source bytes")
    items = [RawRecordEnvelope.from_source_payload(
        run_id=rid, dataset_id=envelope.dataset_id, resource_id=envelope.resource_id,
        retrieved_at=envelope.retrieved_at, page_number=spec.number,
        page_offset=spec.offset, record_index=index, source_checksum=digest, payload=value,
    ) for index, value in enumerate(payload["data"])]
    existing = list(db["raw_records"].find({
        "run_id": str(rid), "page_number": spec.number,
    }))
    if len(existing) != spec.expected_count:
        MongoRawLoader(db).persist_page(page=envelope, records=items)
        existing = list(db["raw_records"].find({
            "run_id": str(rid), "page_number": spec.number,
        }))
        emit("RECOVERED_PARTIAL_MONGO_RECORDS", page=spec.number)
    by_key = {str(x.get("source_record_key")): x for x in existing}
    if len(by_key) != spec.expected_count:
        raise BackfillIntegrityError("Raw record cardinality or unique identity mismatch")
    for item in items:
        stored = by_key.get(item.source_record_key)
        if stored is None or stored.get("payload") != item.payload or (
            stored.get("source_checksum") != digest or
            stored.get("record_index") != item.record_index or
            stored.get("page_offset") != spec.offset
        ):
            raise BackfillIntegrityError("Raw record source identity/payload mismatch")
    return {"page_number": spec.number, "page_offset": spec.offset,
            "record_count": envelope.record_count, "total_count": envelope.total_count,
            "source_checksum": digest, "raw_bytes_size": len(envelope.raw_bytes)}


def _checkpoint(engine: Engine, rid: UUID, page: dict[str, Any]) -> None:
    """Only called after independently verified complete raw Mongo landing."""
    params = {"rid": rid, **page}
    with engine.begin() as con:
        existing_total = con.execute(text("""
            SELECT observed_total FROM public.historical_backfill_runs
            WHERE run_id=:rid FOR UPDATE
        """), {"rid": rid}).scalar_one()
        if existing_total is not None and existing_total != page["total_count"]:
            raise BackfillIntegrityError("Postgres upstream total count drift")
        con.execute(text("""
            UPDATE public.historical_backfill_runs SET observed_total=:total_count,
                updated_at=now() WHERE run_id=:rid
        """), params)
        con.execute(text("""
            INSERT INTO public.historical_backfill_pages
               (run_id, page_number, page_offset, record_count, total_count,
                source_checksum, raw_bytes_size)
            VALUES (:rid, :page_number, :page_offset, :record_count, :total_count,
                    :source_checksum, :raw_bytes_size)
            ON CONFLICT (run_id, page_number) DO NOTHING
        """), params)
        row = con.execute(text("""
            SELECT page_offset, record_count, total_count, source_checksum, raw_bytes_size
            FROM public.historical_backfill_pages
            WHERE run_id=:rid AND page_number=:page_number
        """), params).mappings().one()
        for key in ("page_offset", "record_count", "total_count", "source_checksum", "raw_bytes_size"):
            if row[key] != page[key]:
                raise BackfillIntegrityError(f"Immutable checkpoint changed: {key}")


def _fetch_one(spec: PageSpec, page_size: int, config: WorldBankClientConfig) -> WorldBankResponse:
    # A separate Session per worker avoids concurrent use of requests.Session.
    with WorldBankClient(config) as client:
        return client.fetch(top=page_size, skip=spec.offset)


def _persist_fetched_page(
    db: Any, rid: UUID, spec: PageSpec, response: WorldBankResponse,
    expected_total: int, page_size: int,
) -> dict[str, Any]:
    assert_page_contract(
        spec=spec, reported_total=response.total_count,
        expected_total=expected_total, returned_count=response.record_count,
        top=response.top, skip=response.skip, page_size=page_size,
    )
    if not isinstance(response.payload.get("data"), list):
        raise BackfillIntegrityError("Source payload is missing a data list")
    checksum = hashlib.sha256(response.raw_bytes).hexdigest()
    retrieved_at = datetime.now(UTC)
    page = RawPageEnvelope(
        run_id=rid, dataset_id=DEFAULT_DATASET_ID, resource_id=DEFAULT_RESOURCE_ID,
        retrieved_at=retrieved_at, page_number=spec.number,
        page_offset=spec.offset, source_checksum=checksum,
        record_count=response.record_count, total_count=response.total_count,
        raw_bytes=response.raw_bytes, payload=response.payload,
    )
    records = [RawRecordEnvelope.from_source_payload(
        run_id=rid, dataset_id=DEFAULT_DATASET_ID, resource_id=DEFAULT_RESOURCE_ID,
        retrieved_at=retrieved_at, page_number=spec.number, page_offset=spec.offset,
        record_index=i, source_checksum=checksum, payload=value,
    ) for i, value in enumerate(response.payload["data"])]
    MongoRawLoader(db).persist_page(page=page, records=records)
    verified = _verify_raw_page(db, rid, spec, expected_total)
    if verified is None or verified["source_checksum"] != checksum:
        raise BackfillIntegrityError("Persisted raw page changed or disappeared")
    return verified


def _preflight_existing(
    engine: Engine, db: Any, opts: BackfillOptions,
    specs: tuple[PageSpec, ...], total: int,
) -> list[PageSpec]:
    committed = _committed(engine, opts.run_id)
    if len(committed) > len(specs):
        raise BackfillIntegrityError("More committed pages than declared source plan")
    pending: list[PageSpec] = []
    for spec in specs:
        raw = _verify_raw_page(db, opts.run_id, spec, total)
        checkpoint = committed.get(spec.number)
        if checkpoint is not None:
            if raw is None:
                raise BackfillIntegrityError("PostgreSQL checkpoint exists without Mongo raw page")
            for key in ("page_offset", "record_count", "total_count", "source_checksum", "raw_bytes_size"):
                if checkpoint[key] != raw[key]:
                    raise BackfillIntegrityError(f"Cross-store checkpoint mismatch: {key}")
            emit("REUSED_COMMITTED_PAGE", page=spec.number, offset=spec.offset)
        elif raw is not None:
            # Crash recovery: raw persistence was complete but checkpoint not committed.
            _checkpoint(engine, opts.run_id, raw)
            emit("RECOVERED_MONGO_PAGE_WITHOUT_HTTP", page=spec.number, offset=spec.offset)
        else:
            pending.append(spec)
    if any(n not in {p.number for p in specs} for n in committed):
        raise BackfillIntegrityError("Committed page is outside declared plan")
    return pending


def _run_with_advisory_lock(
    engine: Engine, db: Any, opts: BackfillOptions,
    fetch: Callable[[PageSpec], WorldBankResponse],
) -> dict[str, Any]:
    run = _create_or_resume(engine, opts)
    existing_first = _stored_mongo_page(db, opts.run_id, PageSpec(1, 0, 1))
    first_response: WorldBankResponse | None = None
    total = run["observed_total"]
    if total is None and existing_first is not None:
        first_env = RawPageEnvelope.from_mongo_document(existing_first)
        total = first_env.total_count
    if total is None:
        first_response = fetch(PageSpec(1, 0, opts.page_size))
        total = first_response.total_count
    specs = plan_pages(total, opts.page_size, opts.max_pages)
    pending = _preflight_existing(engine, db, opts, specs, total)
    committed_this_execution = 0
    # Fetch concurrency is bounded at workers; jobs are consumed/committed in order.
    # At most 2*workers HTTP responses are outstanding (memory backpressure).
    with ThreadPoolExecutor(max_workers=opts.workers) as pool:
        future: dict[int, Future[WorldBankResponse]] = {}
        i = 0
        while i < len(pending):
            while len(future) < 2 * opts.workers and i + len(future) < len(pending):
                spec = pending[i + len(future)]
                if spec.number == 1 and first_response is not None:
                    done: Future[WorldBankResponse] = Future()
                    done.set_result(first_response)
                    future[spec.number] = done
                else:
                    future[spec.number] = pool.submit(fetch, spec)
            spec = pending[i]
            response = future.pop(spec.number).result()
            verified = _persist_fetched_page(db, opts.run_id, spec, response, total, opts.page_size)
            _checkpoint(engine, opts.run_id, verified)
            i += 1
            committed_this_execution += 1
            emit("RAW_PAGE_COMMITTED", page=spec.number,
                 offset=spec.offset, records=spec.expected_count,
                 checksum=verified["source_checksum"])
            if opts.fail_after_pages and committed_this_execution == opts.fail_after_pages:
                raise RuntimeError("INJECTED_FAILURE_AFTER_COMMITTED_PAGE")
    # Re-audit independently from PostgreSQL and Mongo before publication.
    remaining = _preflight_existing(engine, db, opts, specs, total)
    if remaining:
        raise BackfillIntegrityError(f"Incomplete ingestion: {len(remaining)} pending pages")
    with engine.begin() as con:
        con.execute(text("""
            UPDATE public.historical_backfill_runs
            SET status='COMPLETE', last_error=NULL, updated_at=now()
            WHERE run_id=:rid
        """), {"rid": opts.run_id})
    result = {
        "status": "PASS_FULL_RAW_CAPTURE" if is_full_capture(total, specs) else "PASS_BOUNDED_RAW_CAPTURE",
        "run_id": str(opts.run_id), "source_total_reported": total,
        "pages_committed": len(specs), "raw_records_committed": sum(p.expected_count for p in specs),
        "pages_fetched_this_execution": committed_this_execution,
        "remaining_pages": 0, "canonical_loaded": False,
        "source_mode": "independently_fetched_world_bank_top_skip_pages",
        "snapshot_consistency_guaranteed_by_upstream": False,
        "postgres_database": PG_DATABASE, "mongo_db": MONGO_DATABASE,
        "limitation": "Source can reorder across requests despite constant total_count; no point-in-time API snapshot is guaranteed.",
    }
    emit("BACKFILL_COMPLETE", **result)
    return result


def run_backfill(
    engine: Engine, mongo: Any, opts: BackfillOptions,
    client_config: WorldBankClientConfig | None = None,
    fetch_override: Callable[[PageSpec], WorldBankResponse] | None = None,
) -> dict[str, Any]:
    """Use an advisory lock to prevent simultaneous writers for one run UUID."""
    _required_engine_identity(engine)
    db = mongo[MONGO_DATABASE]
    ensure_raw_indexes(db)
    db["raw_pages"].create_index(
        [("run_id", 1), ("page_offset", 1)], unique=True,
        name="ux_historical_run_offset",
    )
    config = client_config or WorldBankClientConfig()
    fetch = fetch_override or (lambda spec: _fetch_one(spec, opts.page_size, config))
    with engine.connect() as guard:
        locked = guard.execute(text("SELECT pg_try_advisory_lock(hashtext(:rid))"),
                               {"rid": str(opts.run_id)}).scalar_one()
        if not locked:
            raise BackfillIntegrityError("Another worker is already using this backfill run_id")
        try:
            try:
                return _run_with_advisory_lock(engine, db, opts, fetch)
            except Exception as exc:
                if _run_row(engine, opts.run_id):
                    with engine.begin() as con:
                        con.execute(text("""
                            UPDATE public.historical_backfill_runs
                            SET status='FAILED', last_error=:err, updated_at=now()
                            WHERE run_id=:rid
                        """), {"rid": opts.run_id, "err": str(exc)[:3000]})
                emit("BACKFILL_FAILED", run_id=str(opts.run_id), error=str(exc))
                raise
        finally:
            guard.execute(text("SELECT pg_advisory_unlock(hashtext(:rid))"),
                          {"rid": str(opts.run_id)})
