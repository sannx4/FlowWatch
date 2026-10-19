"""Day-23 three-commit integration gate: checksum-verified Mongo -> PostgreSQL.

This script WRITES ONLY flowwatch_day23_gate as flowwatch_ingestor.
Precondition: isolated database exists and has zero credit_snapshots.
No source API calls; a synthetic correction is tested in a rolled-back transaction.

Run: python -m scripts.day23_idempotency_gate --limit 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from getpass import getpass
from pathlib import Path
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Connection

from scripts.replay_raw import resolve_latest_run_id
from src.ingestion.mongodb_connection import create_mongodb_client, load_mongodb_config
from src.ingestion.raw_replay import select_raw_record_envelopes
from src.loaders.day23_upsert import (
    CanonicalInput,
    SnapshotCorrectionRequired,
    SourceIdentity,
    load_exact_batch,
    load_exact_record,
)
from src.transformation.rehydration import recover_exact_source_record

GATE_DATABASE = "flowwatch_day23_gate"
EVIDENCE = Path("reports/day23-entity-upsert-evidence.json")
TABLES = ("regions", "countries", "projects", "credits", "credit_snapshots")


def _snapshot_details(connection: Connection, pk: int) -> dict[str, Any]:
    row = connection.execute(
        text(
            "SELECT credit_snapshot_id, credit_status, source_checksum, "
            "source_record_key, ingestion_run_id::text AS ingestion_run_id "
            "FROM public.credit_snapshots WHERE credit_snapshot_id = :pk"
        ),
        {"pk": pk},
    ).mappings().one()
    return dict(row)


def _counts(connection: Connection) -> dict[str, int]:
    # All identifiers are constants, not user-supplied values.
    return {
        name: int(connection.execute(text(f"SELECT count(*) FROM public.{name}")).scalar_one())
        for name in TABLES
    }


def _verify_database(connection: Connection) -> None:
    db, session_role, active_role = connection.execute(
        text("SELECT current_database(), session_user, current_user")
    ).one()
    if db != GATE_DATABASE or session_role != "flowwatch_ingestor" or active_role != "flowwatch_ingestor":
        raise RuntimeError("REFUSING TO WRITE: isolated DB / restricted role mismatch")


def _recover(limit: int, run_id: str | None) -> tuple[str, tuple[CanonicalInput, ...]]:
    config = load_mongodb_config()
    client = create_mongodb_client(config)
    try:
        client.admin.command("ping")
        db = client[config.database_name]
        selected_run = run_id or resolve_latest_run_id(db)
        envelopes = select_raw_record_envelopes(db, run_id=selected_run, limit=limit)
        if not envelopes:
            raise LookupError(f"No stored source records for {selected_run}")
        cached: dict[tuple[int, int, str], bytes] = {}
        records: list[CanonicalInput] = []
        for envelope in envelopes:
            key = (
                envelope.page_number, envelope.page_offset, envelope.source_checksum
            )
            if key not in cached:
                page = db["raw_pages"].find_one(
                    {
                        "run_id": str(envelope.run_id),
                        "page_number": envelope.page_number,
                        "page_offset": envelope.page_offset,
                        "source_checksum": envelope.source_checksum,
                    },
                    {"raw_bytes": 1},
                )
                if page is None:
                    raise LookupError(f"Original raw page is missing: {key}")
                original_bytes = page.get("raw_bytes")
                if not isinstance(original_bytes, bytes):
                    raise TypeError(f"Original raw page is not bytes: {key}")
                cached[key] = original_bytes
            exact = recover_exact_source_record(
                cached[key],
                source_checksum=envelope.source_checksum,
                record_index=envelope.record_index,
                stored_payload=envelope.payload,
            )
            records.append(
                CanonicalInput(
                    payload=exact,
                    lineage=SourceIdentity(
                        run_id=envelope.run_id,
                        source_checksum=envelope.source_checksum,
                        source_record_key=envelope.source_record_key,
                    ),
                )
            )
        identities = {(str(item.payload["credit_number"]), str(item.payload["end_of_period"])) for item in records}
        if len(identities) != len(records):
            raise RuntimeError("Selected input has duplicate snapshot business identities")
        return str(selected_run), tuple(records)
    finally:
        client.close()


def _correction_probe(connection: Connection, original: CanonicalInput, pk: int) -> dict[str, Any]:
    """Exercise reject/ignore/update while unconditionally rolling everything back."""
    baseline = _snapshot_details(connection, pk)
    corrected = dict(original.payload)
    corrected["credit_status"] = f"{corrected.get('credit_status') or 'UNKNOWN'} [DAY23 CONTROLLED TEST]"
    # This temporary identifier is NEVER persisted: the outer tx rolls back.
    test_key = original.lineage.source_record_key + ":day23-controlled-test"
    simulated = CanonicalInput(
        payload=corrected,
        lineage=SourceIdentity(
            run_id=original.lineage.run_id,
            source_checksum=hashlib.sha256(
                json.dumps(corrected, default=str, sort_keys=True).encode()
            ).hexdigest(),
            source_record_key=test_key,
        ),
    )
    rejected = False
    try:
        load_exact_record(connection, simulated, snapshot_policy="reject")
    except SnapshotCorrectionRequired:
        rejected = True
    if not rejected:
        raise AssertionError("Default correction guard accepted changed snapshot")

    ignored = load_exact_record(connection, simulated, snapshot_policy="ignore")
    if ignored.outcomes["credit_snapshots"] != "ignored":
        raise AssertionError("Explicit ignore did not ignore changed snapshot")
    if _snapshot_details(connection, pk) != baseline:
        raise AssertionError("Ignore unexpectedly mutated financial snapshot")

    applied = load_exact_record(connection, simulated, snapshot_policy="update")
    revised = _snapshot_details(connection, pk)
    if applied.outcomes["credit_snapshots"] != "updated":
        raise AssertionError("Correction was not classified as updated")
    if revised["source_record_key"] != test_key:
        raise AssertionError("Correction did not update provenance")
    if revised["credit_status"] != corrected["credit_status"]:
        raise AssertionError("Correction was not applied")
    return {
        "reject_changed_snapshot": rejected,
        "ignore_changed_snapshot": ignored.outcomes["credit_snapshots"] == "ignored",
        "explicit_update_applied": applied.outcomes["credit_snapshots"] == "updated",
        "probe_rolled_back": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--run-id", type=str)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.run_id:
        try:
            UUID(args.run_id)
        except ValueError as exc:
            parser.error(f"Invalid run ID: {exc}")

    load_dotenv()
    source_run, records = _recover(args.limit, args.run_id)
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost"):
        raise RuntimeError("REFUSING: gate permits local PostgreSQL only")
    password = getpass("Password for PostgreSQL flowwatch_ingestor: ")
    if not password:
        raise RuntimeError("Empty password")
    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="flowwatch_ingestor", password=password,
            host=host, port=int(os.getenv("POSTGRES_PORT", "5434")),
            database=GATE_DATABASE,
        ),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    del password
    try:
        with engine.connect() as connection:
            _verify_database(connection)
            baseline = _counts(connection)
        if baseline["credit_snapshots"] != 0:
            raise RuntimeError(
                "REFUSING: isolated day23 database must start with zero snapshots. "
                "See README_DAY23.md; never truncate the main database."
            )
        counts_per_pass: list[dict[str, int]] = []
        actions: list[dict[str, int]] = []
        key_sets: list[tuple[int, ...]] = []
        for attempt in range(1, 4):
            with engine.begin() as connection:
                _verify_database(connection)
                loaded, operation_counts = load_exact_batch(connection, records)
                counts = _counts(connection)
                key_set = tuple(item.credit_snapshot_id for item in loaded)
            counts_per_pass.append(counts)
            actions.append(operation_counts)
            key_sets.append(key_set)
            print(f"Committed pass {attempt}: {counts}; operations={operation_counts}")
        if not (counts_per_pass[0] == counts_per_pass[1] == counts_per_pass[2]):
            raise AssertionError("Entity counts changed across identical source replays")
        if not (key_sets[0] == key_sets[1] == key_sets[2]):
            raise AssertionError("Source replay created different snapshot primary keys")
        if counts_per_pass[0]["credit_snapshots"] != len(records):
            raise AssertionError("First pass did not create each distinct source snapshot")
        if any(
            actions[repeat].get("credit_snapshots.updated", 0)
            or actions[repeat].get("credit_snapshots.inserted", 0)
            for repeat in (1, 2)
        ):
            raise AssertionError("Repeated identical snapshots were rewritten")

        # Synthetic correction changes only the in-memory input and is rolled
        # back even if the probe fails. It is NOT source World Bank evidence.
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                _verify_database(connection)
                correction_result = _correction_probe(
                    connection, records[0], key_sets[0][0]
                )
            finally:
                transaction.rollback()
        with engine.connect() as connection:
            _verify_database(connection)
            final = _counts(connection)
            persisted = _snapshot_details(connection, key_sets[0][0])
        if persisted["source_record_key"] == records[0].lineage.source_record_key + ":day23-controlled-test":
            raise AssertionError("Synthetic correction probe was not rolled back")
        if final != counts_per_pass[-1]:
            raise AssertionError("The correction probe altered committed counts")
    finally:
        engine.dispose()

    report = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "source_run_id": source_run,
        "source_records": len(records),
        "database": GATE_DATABASE,
        "database_role": "flowwatch_ingestor",
        "counts_before": baseline,
        "counts_per_committed_pass": counts_per_pass,
        "operations_per_pass": actions,
        "snapshot_primary_keys_same_across_replays": True,
        "snapshot_business_keys_unique": True,
        "simulated_correction_rollback": correction_result,
        "counts_after_rollback": final,
        "source_api_contacted": False,
        "stored_raw_records_mutated": False,
        "status": "PASS_DAY23_ISOLATED_GATE",
        "limitations": [
            "Tested a bounded batch, not the full historical source.",
            "Correction exercise uses a synthetic modification rolled back afterward.",
            "Real upstream corrections require explicit source-version precedence review.",
            "Row status counts assume single-writer gate execution.",
            "Legacy replay entrypoints remain unchanged pending deployment cutover.",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Day 23: PASS — 3 committed identical batches, zero new snapshots on retries")
    print(f"Evidence: {EVIDENCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
