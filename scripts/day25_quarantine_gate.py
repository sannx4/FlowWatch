"""Day25: persist genuine legacy-parser rejection; verify separate-process replay.

Reject phase: selects real MongoDB observation whose BSON has a financial
float, confirms the old path fails but exact recovery works, commits one
quarantine record. Verify phase: checks resolved event and curated lineage.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from scripts.day25_common import DATABASE, engine_for_gate, verify_gate
from scripts.replay_raw import resolve_latest_run_id
from src.ingestion.mongodb_connection import create_mongodb_client, load_mongodb_config
from src.ingestion.raw_replay import select_raw_record_envelopes
from src.quality.day25_quarantine import (
    BROKEN_PARSER,
    RULE_EXACT_DECIMAL,
    RawLocator,
    float_financial_field,
    record_rejection,
)
from src.transformation.pure import transform_canonical_record
from src.transformation.rehydration import recover_exact_source_record

EVIDENCE = Path("reports/day25-quarantine-gate.json")


def select_real_failure(limit: int) -> tuple[Any, str, str]:
    cfg = load_mongodb_config()
    client = create_mongodb_client(cfg)
    try:
        client.admin.command("ping")
        db = client[cfg.database_name]
        run_id = resolve_latest_run_id(db)
        envelopes = select_raw_record_envelopes(db, run_id=run_id, limit=limit)
        for envelope in envelopes:
            if not isinstance(envelope.payload, dict):
                continue
            try:
                field, value = float_financial_field(envelope.payload)
            except ValueError:
                continue
            try:
                transform_canonical_record(envelope.payload)
            except ValueError:
                # A real failure must be eliminated by the corrected source parser.
                page = db["raw_pages"].find_one({
                    "run_id": str(envelope.run_id),
                    "page_number": envelope.page_number,
                    "page_offset": envelope.page_offset,
                    "source_checksum": envelope.source_checksum,
                }, {"raw_bytes": 1})
                if page is None or not isinstance(page.get("raw_bytes"), bytes):
                    raise RuntimeError("Unable to validate exact-source fix")
                exact = recover_exact_source_record(
                    page["raw_bytes"], source_checksum=envelope.source_checksum,
                    record_index=envelope.record_index,
                    stored_payload=envelope.payload,
                )
                transform_canonical_record(exact)
                return envelope, field, str(value)
        raise RuntimeError(
            "No real BSON-decimal parser failure with verified exact-source fix found"
        )
    finally:
        client.close()


def _reject(limit: int) -> None:
    envelope, field, value = select_real_failure(limit)
    locator = RawLocator(
        run_id=envelope.run_id, source_record_key=envelope.source_record_key,
        source_checksum=envelope.source_checksum,
        page_number=envelope.page_number, page_offset=envelope.page_offset,
        record_index=envelope.record_index,
    )
    engine = engine_for_gate()
    try:
        with engine.begin() as connection:
            verify_gate(connection)
            quarantine_id = record_rejection(
                connection, locator=locator, rule_id=RULE_EXACT_DECIMAL,
                offending_field=field, offending_value=value,
                detail="Legacy BSON float violates strict exact-decimal transformation; "
                       "recover original source JSON bytes before loading",
                parser_version=BROKEN_PARSER,
            )
        with engine.connect() as connection:
            verify_gate(connection)
            found = connection.execute(text("""
                SELECT status, occurrences, source_record_key
                FROM public.source_quarantine WHERE quarantine_id=:id
            """), {"id": quarantine_id}).one()
        if found.status != "PENDING":
            raise AssertionError("Expected pending quarantine")
    finally:
        engine.dispose()
    report = {
        "phase": "REJECTED_AND_PERSISTED", "tested_at_utc": datetime.now(UTC).isoformat(),
        "database": DATABASE, "quarantine_id": quarantine_id,
        "source_run_id": str(envelope.run_id),
        "source_record_key": locator.source_record_key,
        "source_checksum": locator.source_checksum,
        "offending_field": field, "offending_stored_float_repr": value,
        "occurrences": int(found.occurrences),
        "source_api_contacted": False, "source_mongodb_mutated": False,
        "research_note": "A parser incompatibility, not an invalid World Bank observation. "
                         "Never silently exclude from training populations.",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Quarantine committed: id={quarantine_id}, field={field}, status=PENDING")
    print(f"Evidence: {EVIDENCE}")
    print("Next: python -m scripts.day25_replay_quarantine --evidence reports/day25-quarantine-gate.json")


def _verify() -> None:
    report = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    if report["database"] != DATABASE:
        raise RuntimeError("Evidence database mismatch")
    engine = engine_for_gate()
    try:
        with engine.connect() as connection:
            verify_gate(connection)
            row = connection.execute(text("""
                SELECT q.status, q.retry_count, q.resolved_parser_version,
                       q.resolved_snapshot_id, q.source_record_key,
                       s.source_record_key AS curated_source_record_key,
                       s.source_checksum AS curated_checksum,
                       q.source_checksum AS quarantined_checksum
                FROM public.source_quarantine q
                LEFT JOIN public.credit_snapshots s
                     ON s.credit_snapshot_id=q.resolved_snapshot_id
                WHERE q.quarantine_id=:id
            """), {"id": report["quarantine_id"]}).mappings().one()
            duplicates = int(connection.execute(text("""
                SELECT count(*) FROM (
                    SELECT credit_id, end_of_period
                    FROM public.credit_snapshots
                    GROUP BY credit_id, end_of_period HAVING count(*)>1
                ) d
            """)).scalar_one())
            if row["status"] != "RESOLVED" or row["retry_count"] != 1:
                raise AssertionError(f"Replay unresolved or incorrect attempts: {row}")
            if row["resolved_parser_version"] != "exact-source-rehydrate-v1":
                raise AssertionError("Corrected parser provenance missing")
            if row["source_record_key"] != row["curated_source_record_key"]:
                raise AssertionError("Curated source key differs from quarantine")
            if row["curated_checksum"] != row["quarantined_checksum"]:
                raise AssertionError("Curated checksum differs from original source")
            if duplicates:
                raise AssertionError("Duplicate snapshot business keys detected")
            snapshot_id = int(row["resolved_snapshot_id"])
    finally:
        engine.dispose()
    report.update({"phase": "PASS_DAY25_PERSIST_AND_REPLAY",
                   "verified_at_utc": datetime.now(UTC).isoformat(),
                   "resolved_snapshot_id": snapshot_id,
                   "retry_count": 1, "temporal_duplicates": 0,
                   "source_api_contacted": False,
                   "stored_raw_records_mutated": False})
    EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Day 25: PASS — quarantined event {report['quarantine_id']} "
          f"replayed to canonical snapshot {snapshot_id}; 0 duplicates")
    print(f"Evidence: {EVIDENCE}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("reject", "verify"), required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.phase == "reject":
        _reject(args.limit)
    else:
        _verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
