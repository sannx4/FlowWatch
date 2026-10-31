"""Day28 offline integration drill: real World Bank fixture -> isolated Mongo -> PG.

Two supported source modes:
  --source-file FILE: split a single authentic stored page into 10 *logical*
      windows; NOT a claim of fetching 10 independently issued API pages.
  --pages-dir DIR: consume 10 or more independently stored raw source pages.

All canonical / quarantine / reconciliation writes target flowwatch_day28_gate.
Mongo writes target flowwatch_day28_gate_raw. Never calls the upstream API.
Use --require-true-pages to reject the fixture-window mode for a full-page gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from getpass import getpass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Connection, Engine

from src.loaders.day23_upsert import CanonicalInput, SourceIdentity
from src.loaders.day24_bulk import load_bulk_batch
from src.quality.day25_quarantine import (
    BROKEN_PARSER,
    FIXED_PARSER,
    RULE_EXACT_DECIMAL,
    RawLocator,
    float_financial_field,
    record_rejection,
    resolve_rejection,
)
from src.quality.reconcile import (
    ReconciliationError,
    ReconciliationResult,
    reconcile_attempt,
    record_decision,
    require_partition,
)
from src.transformation.pure import transform_canonical_record
from src.transformation.rehydration import recover_exact_source_record

PG_DB = "flowwatch_day28_gate"
MONGO_DB = "flowwatch_day28_gate_raw"
REPORT = Path("reports/day28-etl-gate.json")
REPORT_MD = Path("reports/etl-gate.md")


@dataclass(frozen=True)
class SourceRecord:
    page_number: int
    page_offset: int
    record_index: int
    raw_bytes: bytes
    checksum: str
    payload: dict[str, Any]
    key: str


@dataclass(frozen=True)
class SourcePage:
    number: int
    offset: int
    checksum: str
    raw_bytes: bytes
    records: tuple[SourceRecord, ...]


def _require_local_postgres(host: str) -> None:
    allowed = {"127.0.0.1", "localhost", "postgres"}
    if host not in allowed:
        raise RuntimeError(f"Refusing PostgreSQL host {host!r}; permitted: {sorted(allowed)}")


def create_gate_engine() -> Engine:
    load_dotenv(override=False)
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    _require_local_postgres(host)
    password = os.getenv("FLOWWATCH_GATE_PG_PASSWORD")
    if password is None:
        password = getpass("Password for PostgreSQL flowwatch_ingestor: ")
    if not password:
        raise ValueError("Empty gate PostgreSQL password")
    return create_engine(URL.create(
        "postgresql+psycopg", username="flowwatch_ingestor", password=password,
        host=host, port=int(os.getenv("POSTGRES_PORT", "5434")), database=PG_DB,
    ), pool_pre_ping=True, connect_args={"connect_timeout": 10})


def verify_gate_database(connection: Connection) -> None:
    identity = tuple(connection.execute(text(
        "SELECT current_database(), session_user, current_user"
    )).one())
    if identity != (PG_DB, "flowwatch_ingestor", "flowwatch_ingestor"):
        raise RuntimeError(f"REFUSING WRITE: wrong DB/role {identity}")
    # The whole gate expects Day25 and Day26 schema, never silently creates it.
    for table in ("public.source_quarantine", "public.etl_attempts", "public.etl_record_decisions"):
        if connection.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar_one() is None:
            raise RuntimeError(f"Missing migrated table {table}")


def _parse_page(raw: bytes) -> list[dict[str, Any]]:
    page = json.loads(raw)
    if not isinstance(page, dict) or not isinstance(page.get("data"), list):
        raise TypeError("Each source page requires JSON object containing data list")
    if not page["data"] or not all(isinstance(r, dict) for r in page["data"]):
        raise ValueError("Page contains zero or non-object records")
    return page["data"]


def load_source_pages(
    *, source_file: Path | None, pages_dir: Path | None, windows: int,
) -> tuple[tuple[SourcePage, ...], str]:
    """Preserve exact raw source bytes; only selection windows are derived."""
    if (source_file is None) == (pages_dir is None):
        raise ValueError("Supply exactly one source-file or pages-dir")
    pages: list[SourcePage] = []
    mode = "independent_stored_pages" if pages_dir else "logical_windows_of_single_stored_page"
    if pages_dir:
        files = sorted(pages_dir.glob("*.json"))
        if len(files) < windows:
            raise ValueError(f"Require >= {windows} raw JSON pages; found {len(files)}")
        offset = 0
        for page_no, path in enumerate(files, 1):
            raw = path.read_bytes()
            payloads = _parse_page(raw)
            digest = hashlib.sha256(raw).hexdigest()
            members = tuple(SourceRecord(
                page_number=page_no, page_offset=offset, record_index=index,
                raw_bytes=raw, checksum=digest, payload=payload,
                key=f"day28:{page_no}:{digest}:{index}",
            ) for index, payload in enumerate(payloads))
            pages.append(SourcePage(page_no, offset, digest, raw, members))
            offset += len(members)
    else:
        assert source_file is not None
        raw = source_file.read_bytes()
        payloads = _parse_page(raw)
        if len(payloads) < windows:
            raise ValueError("Fixture has fewer observations than logical windows")
        digest = hashlib.sha256(raw).hexdigest()
        for page_no in range(1, windows + 1):
            lo, hi = (page_no - 1) * len(payloads) // windows, page_no * len(payloads) // windows
            members = tuple(SourceRecord(
                page_number=page_no, page_offset=lo, record_index=index,
                raw_bytes=raw, checksum=digest, payload=payloads[index],
                key=f"day28:{page_no}:{digest}:{index}",
            ) for index in range(lo, hi))
            pages.append(SourcePage(page_no, lo, digest, raw, members))
    keys = [rec.key for page in pages for rec in page.records]
    if len(keys) != len(set(keys)):
        raise ValueError("Input contains repeated source identities")
    if len(pages) < windows:
        raise ValueError("Insufficient page count")
    return tuple(pages), mode


def manifest_identity(pages: tuple[SourcePage, ...]) -> UUID:
    encoded = "|".join(
        f"{page.number}:{page.offset}:{page.checksum}:{','.join(r.key for r in page.records)}"
        for page in pages
    )
    return uuid5(NAMESPACE_URL, "flowwatch:day28:" + hashlib.sha256(encoded.encode()).hexdigest())


def mongo_for_gate() -> Any:
    """Prefer an explicit URI in CI; otherwise reuse existing authenticated config."""
    uri = os.getenv("FLOWWATCH_GATE_MONGO_URI")
    if uri:
        from urllib.parse import urlsplit

        from pymongo import MongoClient

        parsed = urlsplit(uri)
        if parsed.scheme != "mongodb" or parsed.hostname not in (
            "127.0.0.1", "localhost", "mongodb"
        ):
            raise RuntimeError("REFUSING: explicit gate Mongo URI must use local MongoDB")
        client: Any = MongoClient(uri, serverSelectionTimeoutMS=8000)
    else:
        from src.ingestion.mongodb_connection import (
            create_mongodb_client,
            load_mongodb_config,
        )
        client = create_mongodb_client(load_mongodb_config())
    client.admin.command("ping")
    address = client.address
    if address is None or address[0] not in ("127.0.0.1", "localhost", "mongodb"):
        client.close()
        raise RuntimeError("REFUSING: resolved MongoDB gate host is not local")
    return client


def persist_raw(client: Any, pages: tuple[SourcePage, ...], run_id: UUID) -> None:
    db = client[MONGO_DB]
    pages_col = db["raw_pages"]
    records_col = db["raw_records"]
    pages_col.create_index([("run_id", 1), ("page_number", 1)], unique=True)
    records_col.create_index([("run_id", 1), ("source_record_key", 1)], unique=True)
    for page in pages:
        page_data = {
            "run_id": str(run_id), "page_number": page.number,
            "page_offset": page.offset, "source_checksum": page.checksum,
            "raw_bytes": page.raw_bytes, "source_kind": "offline_source_gate",
            "page_window_size": len(page.records),
        }
        match = {"run_id": str(run_id), "page_number": page.number}
        prior = pages_col.find_one(match)
        if prior is not None:
            for key in ("source_checksum", "raw_bytes", "page_offset", "page_window_size"):
                if prior[key] != page_data[key]:
                    raise ReconciliationError(f"Raw page changed on replay: {page.number}, {key}")
        else:
            pages_col.insert_one(page_data)
        for rec in page.records:
            raw_record = {
                "run_id": str(run_id), "source_record_key": rec.key,
                "source_checksum": rec.checksum, "page_number": rec.page_number,
                "page_offset": rec.page_offset, "record_index": rec.record_index,
                "payload": rec.payload,
            }
            existing = records_col.find_one({"run_id": str(run_id), "source_record_key": rec.key})
            if existing is not None:
                for key in ("payload", "source_checksum", "record_index", "page_number", "page_offset"):
                    if existing[key] != raw_record[key]:
                        raise ReconciliationError(f"Immutable Mongo raw record changed: {rec.key}")
            else:
                records_col.insert_one(raw_record)
    if pages_col.count_documents({"run_id": str(run_id)}) != len(pages):
        raise ReconciliationError("Mongo raw page cardinality mismatch")


def independent_mongo_keys(client: Any, run_id: UUID) -> list[str]:
    return [str(doc["source_record_key"]) for doc in client[MONGO_DB]["raw_records"].find(
        {"run_id": str(run_id)}, {"_id": 0, "source_record_key": 1}
    )]


def recover_record(client: Any, run_id: UUID, rec: SourceRecord) -> dict[str, Any]:
    db = client[MONGO_DB]
    stored = db["raw_records"].find_one({"run_id": str(run_id), "source_record_key": rec.key})
    page = db["raw_pages"].find_one({"run_id": str(run_id), "page_number": rec.page_number})
    if stored is None or page is None:
        raise ReconciliationError("Missing independently persisted Mongo raw locator")
    for name in ("source_checksum", "record_index", "page_number", "page_offset"):
        if stored[name] != getattr(rec, "checksum" if name == "source_checksum" else name):
            raise ReconciliationError(f"Mongo raw locator changed: {name}")
    if page["source_checksum"] != rec.checksum:
        raise ReconciliationError("Mongo raw page checksum mismatch")
    return recover_exact_source_record(
        page["raw_bytes"], source_checksum=rec.checksum,
        record_index=rec.record_index, stored_payload=stored["payload"],
    )


def _snapshot_state(connection: Connection, records: list[CanonicalInput]) -> dict[str, int]:
    """Isolated run uses identical lineage across replays; only relevant keys."""
    keys = [r.lineage.source_record_key for r in records]
    if not keys:
        return {}
    rows = connection.execute(text("""
        SELECT source_record_key, credit_snapshot_id FROM public.credit_snapshots
        WHERE source_record_key = ANY(:keys)
    """), {"keys": keys}).all()
    return {str(r[0]): int(r[1]) for r in rows}


def _quarantine_id(connection: Connection, run_id: UUID, key: str) -> int:
    return int(connection.execute(text("""
        SELECT quarantine_id FROM public.source_quarantine
        WHERE source_run_id=:run_id AND source_record_key=:key
          AND rule_id=:rule AND failed_parser_version=:parser
    """), {"run_id": run_id, "key": key,
           "rule": RULE_EXACT_DECIMAL, "parser": BROKEN_PARSER}).scalar_one())


def process_attempt(
    connection: Connection, client: Any, pages: tuple[SourcePage, ...],
    run_id: UUID, attempt: int, reject_key: str,
) -> ReconciliationResult:
    verify_gate_database(connection)
    if connection.execute(text("""
        SELECT COUNT(*) FROM public.etl_attempts
        WHERE run_id=:run_id AND attempt_no=:attempt
    """), {"run_id": run_id, "attempt": attempt}).scalar_one():
        raise RuntimeError("Refusing to overwrite immutable completed attempt")
    manifest_keys = [r.key for p in pages for r in p.records]
    raw_keys = independent_mongo_keys(client, run_id)
    if set(raw_keys) != set(manifest_keys) or len(raw_keys) != len(manifest_keys):
        raise ReconciliationError("Raw Mongo landing is incomplete before curated publication")
    chosen: list[tuple[SourceRecord, CanonicalInput]] = []
    failed: SourceRecord | None = None
    for page in pages:
        for rec in page.records:
            if attempt == 1 and rec.key == reject_key:
                field, value = float_financial_field(rec.payload)
                # Demonstrate a real, strict-parser-incompatible BSON float.
                try:
                    transform_canonical_record(rec.payload)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Fault-injection prerequisite failed: legacy parser unexpectedly accepts float")
                qid = record_rejection(
                    connection, locator=RawLocator(
                        run_id=run_id, source_record_key=rec.key,
                        source_checksum=rec.checksum, page_number=rec.page_number,
                        page_offset=rec.page_offset, record_index=rec.record_index,
                    ), rule_id=RULE_EXACT_DECIMAL, offending_field=field,
                    offending_value=str(value),
                    detail="Controlled legacy BSON float parser rejection; source remains valid",
                    parser_version=BROKEN_PARSER,
                )
                record_decision(
                    connection, run_id=run_id, attempt=attempt,
                    source_record_key=rec.key, source_checksum=rec.checksum,
                    outcome="REJECTED", quarantine_id=qid,
                )
                failed = rec
            else:
                exact = recover_record(client, run_id, rec)
                transform_canonical_record(exact)
                chosen.append((rec, CanonicalInput(
                    payload=exact, lineage=SourceIdentity(
                        run_id=run_id, source_checksum=rec.checksum,
                        source_record_key=rec.key,
                    ),
                )))
    if attempt == 1 and failed is None:
        raise AssertionError("No controlled rejection created")
    inputs = [item for _, item in chosen]
    before = _snapshot_state(connection, inputs)
    result = load_bulk_batch(connection, inputs, snapshot_policy="reject")
    after = _snapshot_state(connection, inputs)
    inserted = 0
    unchanged = 0
    for rec, _item in chosen:
        if rec.key not in after:
            raise ReconciliationError(f"Accepted source record absent from canonical DB: {rec.key}")
        outcome = "UNCHANGED" if rec.key in before else "INSERTED"
        inserted += outcome == "INSERTED"
        unchanged += outcome == "UNCHANGED"
        record_decision(
            connection, run_id=run_id, attempt=attempt,
            source_record_key=rec.key, source_checksum=rec.checksum,
            outcome=outcome, snapshot_id=after[rec.key],
        )
    if inserted != result.inserted or unchanged != result.unchanged:
        raise ReconciliationError("Independently classified outcomes disagree with COPY result")
    if result.updated or result.ignored:
        raise ReconciliationError("Controlled immutable replay unexpectedly changed canonical observations")
    if attempt == 2:
        qid = _quarantine_id(connection, run_id, reject_key)
        if reject_key not in after:
            raise ReconciliationError("Corrected replay has no target snapshot")
        resolve_rejection(
            connection, quarantine_id=qid,
            snapshot_id=after[reject_key], parser_version=FIXED_PARSER,
        )
    return reconcile_attempt(
        connection, run_id=run_id, attempt=attempt,
        manifest_keys=manifest_keys, raw_keys=raw_keys, page_count=len(pages),
    )


def _fault_probe(connection: Connection, client: Any, pages: tuple[SourcePage, ...], run_id: UUID) -> bool:
    """Inject a missing ledger decision in an independent, read-only projection.

    The ingestion role deliberately has no DELETE permission on immutable ledgers.
    Preserve that privilege boundary: read actual committed decisions, omit one
    in a test-only in-memory view, and require the reconciler to reject it.
    """
    keys = [rec.key for page in pages for rec in page.records]
    raw_keys = independent_mongo_keys(client, run_id)
    decisions = {
        str(row.source_record_key): str(row.outcome)
        for row in connection.execute(text("""
            SELECT source_record_key, outcome
            FROM public.etl_record_decisions
            WHERE run_id=:run_id AND attempt_no=3
        """), {"run_id": run_id})
    }
    if set(decisions) != set(keys):
        raise ReconciliationError("Cannot run fault probe: actual attempt-3 ledger incomplete")
    removed = min(decisions)
    del decisions[removed]
    try:
        require_partition(keys, raw_keys, decisions)
    except ReconciliationError:
        return True
    raise AssertionError("Missing decision not rejected by identity-based reconciliation")


def _read_stats(connection: Connection, run_id: UUID) -> dict[str, Any]:
    rows = connection.execute(text("""
        SELECT attempt_no, source_pages, fetched, raw_stored, accepted, rejected,
               inserted, updated, unchanged, ignored, status
        FROM public.etl_attempts WHERE run_id=:run_id ORDER BY attempt_no
    """), {"run_id": run_id}).mappings().all()
    count = int(connection.execute(text("""
        SELECT COUNT(*) FROM public.credit_snapshots
        WHERE ingestion_run_id=:run_id
    """), {"run_id": run_id}).scalar_one())
    duplicates = int(connection.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT credit_id, end_of_period FROM public.credit_snapshots
            GROUP BY credit_id, end_of_period HAVING COUNT(*) > 1
        ) x
    """)).scalar_one())
    pending = int(connection.execute(text("""
        SELECT COUNT(*) FROM public.source_quarantine
        WHERE source_run_id=:run_id AND status <> 'RESOLVED'
    """), {"run_id": run_id}).scalar_one())
    rejected = connection.execute(text("""
        SELECT status, retry_count, source_record_key, source_checksum,
               resolved_snapshot_id FROM public.source_quarantine
        WHERE source_run_id=:run_id
    """), {"run_id": run_id}).mappings().all()
    return {
        "attempts": [dict(row) for row in rows], "canonical_snapshot_count": count,
        "duplicate_temporal_groups": duplicates, "unresolved_quarantine": pending,
        "quarantine": [dict(row) for row in rejected],
    }


def _reports(report: dict[str, Any]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    rows = report["observed"]["attempts"]
    table = "\n".join(
        f"| {r['attempt_no']} | {r['fetched']} | {r['raw_stored']} | {r['accepted']} | "
        f"{r['rejected']} | {r['inserted']} | {r['updated']} | {r['unchanged']} | "
        f"{r['ignored']} | {r['status']} |" for r in rows
    )
    REPORT_MD.write_text(f"""# FlowWatch — Days 26–28: ETL Release Gate

Status: **{report['status']}** (observed locally when this script was executed).

- Test timestamp (UTC): {report['tested_at_utc']}
- Run ID: `{report['run_id']}`
- PostgreSQL database: `{report['postgres_database']}`
- MongoDB database: `{report['mongo_database']}`
- Source provenance: `{report['source_mode']}`
- Authentic source observations: {report['source_observations']}
- Source pages/windows: {report['source_pages']}
- No World Bank API calls were made by this gate.

| Attempt | Fetched | Raw | Accepted | Rejected | Inserted | Updated | Unchanged | Ignored | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{table}

## Independent controls

- Immutable source SHA-256 verified on each replay: PASS.
- Per-source-record decision identity and canonical/quarantine FKs: PASS.
- Deliberately omitted decision fails reconciliation: {report['fault_injection_detection']}.
- Quarantined parser failure recovered from Mongo without source API: PASS.
- Third-pass duplicate-free replay: PASS.
- Temporal duplicate groups: {report['observed']['duplicate_temporal_groups']}.
- Unresolved quarantines: {report['observed']['unresolved_quarantine']}.

## Research threat and validity note

A missing, double-counted or silently rejected credit snapshot can change the
observed forecasting target distribution and residual calibration evidence.
Reconciliation therefore checks **record identity across independently derived
source manifest, Mongo storage and PostgreSQL decisions**, not just totals.
Test reference: `tests/unit/test_day26_reconcile.py` and
`tests/integration/test_day28_etl_gate.py`.

## Limitations

{chr(10).join('- ' + x for x in report['limitations'])}
""", encoding="utf-8")


def _log(run_id: UUID, phase: str, **details: Any) -> None:
    """Machine-searchable correlation events; never print credentials/raw payload."""
    print(json.dumps({
        "component": "flowwatch.day28_etl_gate", "run_id": str(run_id),
        "phase": phase, "at_utc": datetime.now(UTC).isoformat(),
        **details,
    }, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--source-file", type=Path, default=None)
    group.add_argument("--pages-dir", type=Path, default=None)
    parser.add_argument("--windows", type=int, default=10)
    parser.add_argument("--require-true-pages", action="store_true")
    args = parser.parse_args()
    if args.windows < 2:
        parser.error("--windows must be >= 2")
    source_file = args.source_file
    if args.pages_dir is None and source_file is None:
        source_file = Path("data/raw/world_bank_sample.json")
    if args.require_true_pages and args.pages_dir is None:
        parser.error("--require-true-pages requires --pages-dir")
    pages, mode = load_source_pages(
        source_file=source_file, pages_dir=args.pages_dir, windows=args.windows,
    )
    run_id = manifest_identity(pages)
    source_count = sum(len(page.records) for page in pages)
    if source_count != len({rec.key for page in pages for rec in page.records}):
        raise ReconciliationError("Duplicate source identities")
    _log(run_id, "START", source_mode=mode, records=source_count, pages=len(pages))
    client = mongo_for_gate()
    try:
        engine = create_gate_engine()
    except Exception:
        client.close()
        raise
    try:
        with engine.connect() as con:
            verify_gate_database(con)
            completed = [int(row[0]) for row in con.execute(text("""
                SELECT attempt_no FROM public.etl_attempts
                WHERE run_id=:id ORDER BY attempt_no
            """), {"id": run_id}).all()]
            if completed != list(range(1, len(completed) + 1)) or len(completed) > 3:
                raise ReconciliationError("Noncontiguous or unexpected completed attempt history")
        _log(run_id, "PREVIOUS_ATTEMPTS", completed=completed)
        persist_raw(client, pages, run_id)
        _log(run_id, "RAW_STORED", records=source_count)
        # A deliberate parser failure on an authentic stored float, not fabricated World Bank data.
        reject_key: str | None = None
        for page in pages:
            for rec in page.records:
                try:
                    float_financial_field(rec.payload)
                    transform_canonical_record(rec.payload)
                except ValueError:
                    try:
                        float_financial_field(rec.payload)
                    except ValueError:
                        continue
                    reject_key = rec.key
                    break
            if reject_key:
                break
        if reject_key is None:
            raise RuntimeError("No real BSON-float strict-parser incompatibility found")
        for attempt in (1, 2, 3):
            if attempt in completed:
                _log(run_id, "ATTEMPT_ALREADY_COMMITTED", attempt=attempt)
                continue
            _log(run_id, "ATTEMPT_START", attempt=attempt)
            with engine.begin() as con:
                attempt_result = process_attempt(con, client, pages, run_id, attempt, reject_key)
            _log(run_id, "ATTEMPT_COMMITTED", **{k: v for k, v in attempt_result.to_dict().items() if k != "run_id"})
        with engine.begin() as con:
            verify_gate_database(con)
            negative = _fault_probe(con, client, pages, run_id)
        with engine.connect() as con:
            verify_gate_database(con)
            stats = _read_stats(con, run_id)
        if not negative or stats["duplicate_temporal_groups"] or stats["unresolved_quarantine"]:
            raise ReconciliationError("Final gate failed")
        if len(stats["attempts"]) != 3 or stats["canonical_snapshot_count"] != source_count:
            raise ReconciliationError("Canonical/reconciliation count mismatch")
        if [(x["inserted"], x["rejected"], x["unchanged"]) for x in stats["attempts"]] != [
            (source_count - 1, 1, 0), (1, 0, source_count - 1), (0, 0, source_count)
        ]:
            raise ReconciliationError("Unexpected three-pass transition counts")
        if len(stats["quarantine"]) != 1 or stats["quarantine"][0]["retry_count"] != 1:
            raise ReconciliationError("Quarantine replay did not resolve exactly once")
        report = {
            "status": "PASS_DAY26_27_28_LOCAL_ETL_GATE",
            "tested_at_utc": datetime.now(UTC).isoformat(), "run_id": str(run_id),
            "postgres_database": PG_DB, "mongo_database": MONGO_DB,
            "source_mode": mode, "source_observations": source_count,
            "source_pages": len(pages), "resumed_completed_attempts": completed,
            "source_checksums": [p.checksum for p in pages],
            "observed": stats, "fault_injection_detection": negative,
            "source_api_contacted": False,
            "limitations": [
                "The fixture-window mode is not a true independent 10-API-page source acquisition.",
                "The replay is a single-worker deterministic local gate; concurrent writers untested.",
                "Day25 legacy-parser failure is deliberately selected as a controlled test condition.",
                "This proves no unexplained loss for this tested run, not all future upstream inputs.",
                "CI migration upgrade/downgrade and isolated runners require a separate GitHub Actions run.",
            ],
        }
        _reports(report)
        _log(run_id, "PASS", evidence=str(REPORT), report=str(REPORT_MD))
    except Exception as exc:
        _log(run_id, "FAILED", error_type=type(exc).__name__, error=str(exc)[:500])
        raise
    finally:
        engine.dispose()
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
