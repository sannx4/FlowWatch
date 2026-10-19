
"""Day-21 safe core-store gate: MongoDB replay, quality and restricted PostgreSQL.

Runs BOTH replays inside ONE PostgreSQL transaction and rolls it back.
This validates restricted-role loading without changing the existing database.
Durable ingestion/quarantine acceptance requires separate follow-up verification.

Usage (from the repository root):
    python -m scripts.verify_day21_core_gate --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import UTC, datetime
from getpass import getpass
from pathlib import Path
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Connection

from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.raw_envelope import RawRecordEnvelope
from src.ingestion.raw_replay import (
    replay_envelopes,
    select_raw_record_envelopes,
)
from src.quality.temporal import TemporalIdentityScanner
from src.quality.validator import QualityValidationService
from src.validation.models import ValidationContext

REPORT_PATH = Path("reports/day21-core-gate-dry-run.json")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--run-id", type=str, default=None)
    return parser.parse_args()


def _validate_raw_records(
    envelopes: tuple[RawRecordEnvelope, ...],
) -> tuple[
    tuple[RawRecordEnvelope, ...],
    list[dict[str, Any]],
    Counter[str],
]:
    """Validate original page prefixes to preserve source lineage."""

    page_groups: dict[
        tuple[int, int, str],
        list[RawRecordEnvelope],
    ] = {}

    for envelope in envelopes:
        key = (
            envelope.page_number,
            envelope.page_offset,
            envelope.source_checksum,
        )
        page_groups.setdefault(key, []).append(envelope)

    scanner = TemporalIdentityScanner()
    service = QualityValidationService(
        temporal_scanner=scanner,
    )

    accepted: list[RawRecordEnvelope] = []
    rejections: list[dict[str, Any]] = []
    warning_rule_counts: Counter[str] = Counter()

    for (
        page_number,
        page_offset,
        page_checksum,
    ), group in page_groups.items():

        group.sort(key=lambda item: item.record_index)

        observed_indices = [
            item.record_index for item in group
        ]

        if observed_indices != list(range(len(group))):
            raise ValueError(
                "Selected MongoDB documents do not form a page prefix "
                f"starting at record_index=0 for page_offset={page_offset}. "
                "Use a different --run-id or --limit; do not reindex lineage."
            )

        run_ids = {item.run_id for item in group}

        if len(run_ids) != 1:
            raise ValueError(
                "Source page group contains multiple ingestion run IDs"
            )

        context = ValidationContext(
            run_id=next(iter(run_ids)),
            page_number=page_number,
            page_offset=page_offset,
            source_checksum=page_checksum,
        )

        result = service.validate_page(
            [item.payload for item in group],
            context=context,
        )

        if result.total_count != len(group):
            raise AssertionError(
                "Source accounting failed for one raw page"
            )

        accepted.extend(
            group[item.record_index]
            for item in result.accepted
        )

        rejections.extend(
            item.model_dump(mode="json")
            for item in result.rejected
        )

        for item in result.warnings:
            for warning in item.warnings:
                warning_rule_counts[
                    warning.rule_id.value
                ] += 1

    if len(envelopes) != len(accepted) + len(rejections):
        raise AssertionError(
            "Raw input count does not match accepted plus rejected"
        )

    return (
        tuple(accepted),
        rejections,
        warning_rule_counts,
    )


def _snapshot_count(connection: Connection) -> int:
    result = connection.execute(
        text("SELECT COUNT(*) FROM public.credit_snapshots")
    ).scalar_one()

    return int(result)


def _verify_loader_lineage(
    connection: Connection,
    envelopes: tuple[RawRecordEnvelope, ...],
    snapshot_ids: tuple[int, ...],
) -> None:

    if len(envelopes) != len(snapshot_ids):
        raise AssertionError(
            "Loader returned a different number of snapshot IDs"
        )

    if len(set(snapshot_ids)) != len(snapshot_ids):
        raise AssertionError(
            "Accepted records mapped to duplicate snapshot IDs"
        )

    statement = text(
        "SELECT ingestion_run_id::text, "
        "source_checksum, source_record_key "
        "FROM public.credit_snapshots "
        "WHERE credit_snapshot_id = :snapshot_id"
    )

    for envelope, snapshot_id in zip(
        envelopes,
        snapshot_ids,
        strict=True,
    ):
        record = connection.execute(
            statement,
            {"snapshot_id": snapshot_id},
        ).one()

        if record[0] != str(envelope.run_id):
            raise AssertionError(
                "Stored snapshot ingestion-run lineage differs"
            )

        if record[1] != envelope.source_checksum:
            raise AssertionError(
                "Stored snapshot source checksum differs"
            )

        if record[2] != envelope.source_record_key:
            raise AssertionError(
                "Stored snapshot source record key differs"
            )


def main() -> int:
    args = _arguments()

    if args.limit <= 0:
        raise SystemExit("--limit must be positive")

    if args.run_id is not None:
        try:
            UUID(args.run_id)
        except ValueError as exc:
            raise SystemExit(
                "--run-id must be a valid UUID"
            ) from exc

    load_dotenv()

    mongo_config = load_mongodb_config()
    mongo_client = create_mongodb_client(mongo_config)

    try:
        mongo_client.admin.command("ping")

        mongo_db = mongo_client[
            mongo_config.database_name
        ]

        if args.run_id is None:
            from scripts.replay_raw import resolve_latest_run_id

            run_id = resolve_latest_run_id(mongo_db)
        else:
            run_id = args.run_id

        envelopes = select_raw_record_envelopes(
            mongo_db,
            run_id=run_id,
            limit=args.limit,
        )

        if not envelopes:
            raise LookupError(
                f"No MongoDB raw records found for run {run_id}"
            )

        print(
            f"Stored Mongo records selected: {len(envelopes)}"
        )
        print(f"Existing ingestion run: {run_id}")

        accepted, rejections, warnings = (
            _validate_raw_records(envelopes)
        )

        print(
            f"Accepted: {len(accepted)}; "
            f"rejected: {len(rejections)}"
        )

        print(
            "Financial/date warning conditions: "
            f"{sum(warnings.values())}"
        )

    finally:
        mongo_client.close()

    if not accepted:
        raise RuntimeError(
            "No accepted records available for PostgreSQL replay test"
        )

    if rejections:
        print(
            "NOTE: rejected records are accounted for IN MEMORY ONLY, "
            "not quarantined"
        )

    password = getpass(
        "PostgreSQL flowwatch_ingestor password: "
    )

    if not password:
        raise SystemExit(
            "An ingestion-role password is required"
        )

    url = URL.create(
        drivername="postgresql+psycopg",
        username="flowwatch_ingestor",
        password=password,
        host=os.getenv(
            "POSTGRES_HOST",
            "127.0.0.1",
        ),
        port=int(
            os.getenv(
                "POSTGRES_PORT",
                "5434",
            )
        ),
        database=os.getenv(
            "POSTGRES_DB",
            "flowwatch",
        ),
    )

    del password

    engine = create_engine(
        url,
        pool_pre_ping=True,
    )

    try:
        with engine.connect() as connection:
            transaction = connection.begin()

            try:
                role = str(
                    connection.execute(
                        text("SELECT session_user")
                    ).scalar_one()
                )

                current_role = str(
                    connection.execute(
                        text("SELECT current_user")
                    ).scalar_one()
                )

                if (role, current_role) != (
                    "flowwatch_ingestor",
                    "flowwatch_ingestor",
                ):
                    raise AssertionError(
                        "Replay did not authenticate as restricted ingestor"
                    )

                before = _snapshot_count(connection)

                first = replay_envelopes(
                    connection,
                    accepted,
                )

                after_first = _snapshot_count(connection)

                _verify_loader_lineage(
                    connection,
                    accepted,
                    first.credit_snapshot_ids,
                )

                second = replay_envelopes(
                    connection,
                    accepted,
                )

                after_second = _snapshot_count(connection)

                _verify_loader_lineage(
                    connection,
                    accepted,
                    second.credit_snapshot_ids,
                )

                if (
                    first.credit_snapshot_ids
                    != second.credit_snapshot_ids
                ):
                    raise AssertionError(
                        "Same source records mapped to new snapshot IDs"
                    )

                if after_first != after_second:
                    raise AssertionError(
                        "Second replay created additional canonical rows"
                    )

                if after_first < before:
                    raise AssertionError(
                        "Replay unexpectedly reduced canonical row count"
                    )

                inserted_first = after_first - before

                duplicate_rows_second = (
                    after_second - after_first
                )

            finally:
                transaction.rollback()

        with engine.connect() as connection:
            after_rollback = _snapshot_count(connection)

        if after_rollback != before:
            raise AssertionError(
                "Snapshot count changed despite test rollback"
            )

    finally:
        engine.dispose()

    report: dict[str, Any] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "mode": "transactional_dry_run_rolled_back",
        "database_user": "flowwatch_ingestor",
        "mongo_run_id": run_id,
        "raw_records_selected": len(envelopes),
        "accepted": len(accepted),
        "rejected_accounted_in_memory": len(rejections),
        "durable_quarantine_records_written": 0,
        "rejection_rule_counts": dict(
            sorted(
                Counter(
                    rule
                    for item in rejections
                    for rule in item["rule_ids"]
                ).items()
            )
        ),
        "warning_rule_counts": dict(
            sorted(warnings.items())
        ),
        "canonical_rows_before": before,
        "canonical_rows_after_first_replay_inside_transaction": (
            after_first
        ),
        "canonical_rows_after_second_replay_inside_transaction": (
            after_second
        ),
        "logical_rows_added_on_first_replay": inserted_first,
        "duplicate_rows_added_on_second_replay": (
            duplicate_rows_second
        ),
        "canonical_rows_after_rollback": after_rollback,
        "source_api_contacted": False,
        "gate_status": (
            "DRY_RUN_PASS_NOT_DURABLE_END_TO_END_GATE"
        ),
        "limitations": [
            (
                "Both replay passes are deliberately rolled back to protect "
                "existing canonical data."
            ),
            (
                "No durable quarantine or warning-event persistence is "
                "implemented by this check."
            ),
            (
                "This test does not establish a committed multi-store ingestion "
                "or atomic Mongo/PostgreSQL write."
            ),
            (
                "Selected records must form contiguous prefixes of each "
                "sampled source page."
            ),
            (
                "A separate committed isolated-database test is required "
                "before tagging v0.1-core."
            ),
        ],
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Canonical rows before: {before}")

    print(
        "Canonical rows after first replay (uncommitted): "
        f"{after_first}"
    )

    print(
        "Canonical rows after second replay (uncommitted): "
        f"{after_second}"
    )

    print(f"Duplicate rows on rerun: {duplicate_rows_second}")
    print(f"Canonical rows after rollback: {after_rollback}")
    print("Role verified: flowwatch_ingestor")
    print(f"Evidence: {REPORT_PATH}")

    print(
        "Status: SAFE DRY-RUN PASS "
        "(durable core-store gate remains pending)"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
