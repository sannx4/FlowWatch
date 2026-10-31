"""Replay one persisted quarantine event from immutable MongoDB bytes. No API.

Run: python -m scripts.day25_replay_quarantine --evidence reports/day25-quarantine-gate.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from scripts.day25_common import DATABASE, engine_for_gate, verify_gate
from src.ingestion.mongodb_connection import create_mongodb_client, load_mongodb_config
from src.loaders.day23_upsert import CanonicalInput, SourceIdentity, load_exact_record
from src.quality.day25_quarantine import (
    FIXED_PARSER,
    fetch_locked,
    record_retry_failure,
    resolve_rejection,
)
from src.transformation.rehydration import recover_exact_source_record


def recover_from_mongo(event: dict[str, Any]) -> dict[str, Any]:
    """Read exactly the referenced Mongo raw observation; fail closed on drift."""
    cfg = load_mongodb_config()
    client = create_mongodb_client(cfg)
    try:
        client.admin.command("ping")
        db = client[cfg.database_name]
        run_id = str(event["source_run_id"])
        raw = db["raw_records"].find_one({
            "run_id": run_id, "source_record_key": event["source_record_key"]
        })
        if raw is None:
            raise LookupError("Quarantined raw record no longer exists in MongoDB")
        for field in ("page_number", "page_offset", "record_index", "source_checksum"):
            if raw.get(field) != event[field]:
                raise RuntimeError(f"Raw record locator mismatch: {field}")
        page = db["raw_pages"].find_one({
            "run_id": run_id, "page_number": event["page_number"],
            "page_offset": event["page_offset"],
            "source_checksum": event["source_checksum"],
        }, {"raw_bytes": 1})
        if page is None or not isinstance(page.get("raw_bytes"), bytes):
            raise LookupError("Checksum-addressed raw page unavailable")
        return recover_exact_source_record(
            page["raw_bytes"], source_checksum=event["source_checksum"],
            record_index=event["record_index"], stored_payload=raw["payload"],
        )
    finally:
        client.close()


def replay_one(engine: Any, quarantine_id: int) -> dict[str, Any]:
    try:
        with engine.begin() as connection:
            verify_gate(connection)
            event = fetch_locked(connection, quarantine_id)
            if event["status"] == "RESOLVED":
                return {"status": "ALREADY_RESOLVED", "quarantine_id": quarantine_id,
                        "snapshot_id": int(event["resolved_snapshot_id"])}
            payload = recover_from_mongo(event)
            item = CanonicalInput(payload=payload, lineage=SourceIdentity(
                run_id=UUID(str(event["source_run_id"])),
                source_checksum=str(event["source_checksum"]),
                source_record_key=str(event["source_record_key"]),
            ))
            result = load_exact_record(connection, item, snapshot_policy="reject")
            resolve_rejection(connection, quarantine_id=quarantine_id,
                              snapshot_id=result.credit_snapshot_id,
                              parser_version=FIXED_PARSER)
            return {"status": "RESOLVED", "quarantine_id": quarantine_id,
                    "snapshot_id": result.credit_snapshot_id,
                    "snapshot_outcome": result.outcomes["credit_snapshots"]}
    except Exception as exc:
        # Failure is recorded in a separate transaction; no half-written
        # canonical record is left behind by the failed transaction.
        with engine.begin() as connection:
            verify_gate(connection)
            record_retry_failure(connection, quarantine_id=quarantine_id,
                                 error=f"{type(exc).__name__}: {exc}")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path,
                        default=Path("reports/day25-quarantine-gate.json"))
    args = parser.parse_args()
    report = json.loads(args.evidence.read_text(encoding="utf-8"))
    if report.get("database") != DATABASE:
        raise RuntimeError("Evidence does not target the isolated Day25 database")
    quarantine_id = int(report["quarantine_id"])
    engine = engine_for_gate()
    try:
        outcome = replay_one(engine, quarantine_id)
    finally:
        engine.dispose()
    print(json.dumps(outcome, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
