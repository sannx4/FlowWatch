"""Day-21 committed core gate, restricted to flowwatch_day21_gate.

Precondition: ONLY the isolated gate database has zero credit_snapshots.
No World Bank API calls; reads stored raw MongoDB envelopes.

Usage:
    python -m scripts.verify_day21_committed_gate --limit 5
"""

from __future__ import annotations

import argparse
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
from scripts.verify_day21_core_gate import (
    _snapshot_count,
    _validate_raw_records,
    _verify_loader_lineage,
)
from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.raw_replay import (
    replay_envelopes,
    select_raw_record_envelopes,
)

GATE_DATABASE = "flowwatch_day21_gate"
REPORT_PATH = Path("reports/day21-core-gate-committed.json")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args()


def _verify_identity(connection: Connection) -> None:
    database, login_role, effective_role = connection.execute(
        text("SELECT current_database(), session_user, current_user")
    ).one()
    if database != GATE_DATABASE:
        raise RuntimeError(
            f"REFUSING TO WRITE: expected {GATE_DATABASE}, connected to {database}"
        )
    if (login_role, effective_role) != (
        "flowwatch_ingestor",
        "flowwatch_ingestor",
    ):
        raise RuntimeError("REFUSING TO WRITE: not the restricted ingestor role")


def _distinct_snapshot_count(connection: Connection) -> int:
    return int(
        connection.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "SELECT DISTINCT credit_id, end_of_period "
                "FROM public.credit_snapshots"
                ") AS distinct_identities"
            )
        ).scalar_one()
    )


def main() -> int:
    args = _parse_args()
    if args.limit <= 0:
        raise SystemExit("--limit must be greater than zero")
    if args.run_id is not None:
        try:
            UUID(args.run_id)
        except ValueError as exc:
            raise SystemExit("--run-id must be a valid UUID") from exc

    load_dotenv()
    mongo_config = load_mongodb_config()
    client = create_mongodb_client(mongo_config)
    try:
        client.admin.command("ping")
        mongo_database = client[mongo_config.database_name]
        run_id = (
            args.run_id
            if args.run_id is not None
            else resolve_latest_run_id(mongo_database)
        )
        envelopes = select_raw_record_envelopes(
            mongo_database, run_id=run_id, limit=args.limit
        )
        if not envelopes:
            raise LookupError("No stored raw MongoDB records match the request")
        accepted, rejections, warnings = _validate_raw_records(envelopes)
    finally:
        client.close()

    if len(envelopes) != len(accepted) + len(rejections):
        raise AssertionError("Source-accounting invariant failed")
    if not accepted:
        raise RuntimeError("No accepted raw records; cannot test committed inserts")
    if rejections:
        raise RuntimeError(
            "Gate cannot pass with in-memory-only rejections; "
            "durable quarantine verification is required"
        )

    print(f"Source run: {run_id}")
    print(
        f"Selected: {len(envelopes)}; accepted: {len(accepted)}; "
        f"rejected: {len(rejections)}"
    )
    print(f"Warning conditions: {sum(warnings.values())}")
    print(f"Target: {GATE_DATABASE} (isolated database only)")

    password = getpass("PostgreSQL flowwatch_ingestor password: ")
    if not password:
        raise SystemExit("A role password is required")
    url = URL.create(
        drivername="postgresql+psycopg",
        username="flowwatch_ingestor",
        password=password,
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5434")),
        database=GATE_DATABASE,
    )
    del password
    engine = create_engine(url, pool_pre_ping=True)
    try:
        # The preflight query precedes all writes. A nonempty gate database
        # aborts rather than silently upserting existing snapshots.
        with engine.connect() as connection:
            _verify_identity(connection)
            before = _snapshot_count(connection)
            if before != 0:
                raise RuntimeError(
                    f"Expected zero snapshots in {GATE_DATABASE}; found {before}. "
                    "Do not clear or modify the main flowwatch database."
                )

        # First pass must INSERT AND COMMIT real source snapshots.
        with engine.begin() as connection:
            _verify_identity(connection)
            first = replay_envelopes(connection, accepted)
            _verify_loader_lineage(
                connection, accepted, first.credit_snapshot_ids
            )
            within_first = _snapshot_count(connection)
            if within_first != len(accepted):
                raise AssertionError("First committed batch row count mismatch")

        # Confirm first-pass records survived the commit.
        with engine.connect() as connection:
            _verify_identity(connection)
            committed_first = _snapshot_count(connection)
            if committed_first != len(accepted):
                raise AssertionError("Inserted snapshots did not survive commit")
            _verify_loader_lineage(
                connection, accepted, first.credit_snapshot_ids
            )

        # Repeat the identical accepted set and COMMIT again.
        with engine.begin() as connection:
            _verify_identity(connection)
            second = replay_envelopes(connection, accepted)
            _verify_loader_lineage(
                connection, accepted, second.credit_snapshot_ids
            )
            within_second = _snapshot_count(connection)
            if first.credit_snapshot_ids != second.credit_snapshot_ids:
                raise AssertionError("Rerun changed canonical snapshot identities")
            if within_second != committed_first:
                raise AssertionError("Rerun created duplicate canonical rows")

        with engine.connect() as connection:
            _verify_identity(connection)
            committed_second = _snapshot_count(connection)
            distinct_second = _distinct_snapshot_count(connection)
            _verify_loader_lineage(
                connection, accepted, second.credit_snapshot_ids
            )
            if committed_second != committed_first:
                raise AssertionError("Canonical count increased after second commit")
            if distinct_second != committed_second:
                raise AssertionError("Duplicate canonical temporal identities found")
    finally:
        engine.dispose()

    report: dict[str, Any] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "gate_database": GATE_DATABASE,
        "mode": "committed_isolated_database",
        "postgres_role": "flowwatch_ingestor",
        "mongo_run_id": str(run_id),
        "raw_records_selected": len(envelopes),
        "accepted_records": len(accepted),
        "rejected_records": len(rejections),
        "quarantined_records_persisted": 0,
        "warning_rule_counts": dict(sorted(warnings.items())),
        "snapshot_count_before": before,
        "snapshot_count_after_first_commit": committed_first,
        "snapshot_count_after_second_commit": committed_second,
        "distinct_temporal_identities": distinct_second,
        "duplicate_rows_added_on_rerun": committed_second - committed_first,
        "all_selected_input_accounted_for": True,
        "lineage_verified_on_both_commits": True,
        "source_api_contacted": False,
        "limitations": [
            "This gate verifies stored MongoDB sample replay, not new API retrieval.",
            "The sample has no rejections; durable quarantine is unverified.",
            "The production FlowWatch database is not modified by this script.",
            (
                "Replaying identical source data can upsert rows, "
                "even when counts stay stable."
            ),
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Snapshots before first commit: {before}")
    print(f"Snapshots after first commit: {committed_first}")
    print(f"Snapshots after second commit: {committed_second}")
    print(f"Duplicates added on rerun: {committed_second - committed_first}")
    print(f"Distinct temporal identities: {distinct_second}")
    print("Committed gate: PASS (isolated database)")
    print(f"Evidence: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
