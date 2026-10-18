from __future__ import annotations

import os
from typing import Any

import pytest
from dotenv import load_dotenv
from pymongo.database import Database
from sqlalchemy import URL, create_engine, delete, select
from sqlalchemy.engine import Connection, Engine

from src.db.models import Credit, CreditSnapshot
from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.raw_envelope import RawRecordEnvelope
from src.ingestion.raw_replay import (
    RAW_RECORDS_COLLECTION,
    replay_envelopes,
    select_raw_record_envelopes,
)
from src.transformation.day07 import transform_record

RUN_DAY17_INTEGRATION = (
    os.getenv("FLOWWATCH_RUN_DAY17_INTEGRATION") == "1"
)

if not RUN_DAY17_INTEGRATION:
    pytest.skip(
        (
            "Set FLOWWATCH_RUN_DAY17_INTEGRATION=1 "
            "to run the Day-17 raw replay proof."
        ),
        allow_module_level=True,
    )


def build_postgres_engine() -> Engine:
    load_dotenv()

    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv(
            "POSTGRES_HOST",
            "localhost",
        ),
        port=int(
            os.getenv(
                "POSTGRES_PORT",
                "5434",
            )
        ),
        database=os.environ["POSTGRES_DB"],
    )

    return create_engine(url)


def business_identity(
    envelope: RawRecordEnvelope,
) -> tuple[str, Any]:
    if not isinstance(
        envelope.payload,
        dict,
    ):
        raise TypeError(
            "Expected raw payload to be a mapping."
        )

    transformed = transform_record(
        envelope.payload
    )

    credit_number = transformed[
        "credit"
    ][
        "credit_number"
    ]

    end_of_period = transformed[
        "snapshot"
    ][
        "end_of_period"
    ]

    if end_of_period is None:
        raise RuntimeError(
            "Replay proof record has no end_of_period."
        )

    return (
        str(credit_number),
        end_of_period,
    )


def select_unique_records(
    candidates: tuple[
        RawRecordEnvelope,
        ...,
    ],
    *,
    count: int,
) -> tuple[
    RawRecordEnvelope,
    ...,
]:
    selected: list[RawRecordEnvelope] = []
    seen: set[tuple[str, Any]] = set()

    for envelope in candidates:
        identity = business_identity(
            envelope
        )

        if identity in seen:
            continue

        seen.add(identity)
        selected.append(envelope)

        if len(selected) == count:
            break

    if len(selected) != count:
        raise AssertionError(
            "Not enough unique raw records "
            "for Day-17 replay proof."
        )

    return tuple(selected)


def find_snapshot(
    connection: Connection,
    envelope: RawRecordEnvelope,
) -> dict[str, Any] | None:
    credit_number, end_of_period = (
        business_identity(envelope)
    )

    credit_table = Credit.__table__
    snapshot_table = CreditSnapshot.__table__

    statement = (
        select(
            snapshot_table.c.credit_snapshot_id,
            snapshot_table.c.ingestion_run_id,
            snapshot_table.c.source_checksum,
            snapshot_table.c.source_record_key,
        )
        .select_from(
            snapshot_table.join(
                credit_table,
                snapshot_table.c.credit_id
                == credit_table.c.credit_id,
            )
        )
        .where(
            credit_table.c.credit_number
            == credit_number,
            snapshot_table.c.end_of_period
            == end_of_period,
        )
    )

    row = (
        connection.execute(statement)
        .mappings()
        .one_or_none()
    )

    if row is None:
        return None

    return dict(row)


def test_delete_and_rebuild_curated_sample_from_mongo_raw() -> None:
    mongo_config = load_mongodb_config()

    mongo_client = create_mongodb_client(
        mongo_config
    )

    postgres = build_postgres_engine()

    connection: Connection | None = None
    transaction = None

    try:
        mongo_client.admin.command("ping")

        mongo_database: Database[
            dict[str, Any]
        ] = mongo_client[
            mongo_config.database_name
        ]

        latest_document = mongo_database[
            RAW_RECORDS_COLLECTION
        ].find_one(
            sort=[
                ("retrieved_at", -1),
                ("_id", -1),
            ]
        )

        assert latest_document is not None

        run_id = latest_document.get("run_id")

        assert run_id is not None

        candidates = select_raw_record_envelopes(
            mongo_database,
            run_id=str(run_id),
            limit=100,
        )

        selected = select_unique_records(
            candidates,
            count=5,
        )

        connection = postgres.connect()
        transaction = connection.begin()

        # Ensure the selected curated rows exist before
        # performing the destructive replay proof.
        initial_result = replay_envelopes(
            connection,
            selected,
        )

        assert initial_result.replayed_records == 5

        before_rows = [
            find_snapshot(
                connection,
                envelope,
            )
            for envelope in selected
        ]

        assert all(
            row is not None
            for row in before_rows
        )

        snapshot_ids = [
            int(
                row["credit_snapshot_id"]
            )
            for row in before_rows
            if row is not None
        ]

        snapshot_table = CreditSnapshot.__table__

        delete_result = connection.execute(
            delete(snapshot_table).where(
                snapshot_table.c.credit_snapshot_id.in_(
                    snapshot_ids
                )
            )
        )

        assert delete_result.rowcount == 5

        # Prove that the curated sample is genuinely gone.
        missing_rows = [
            find_snapshot(
                connection,
                envelope,
            )
            for envelope in selected
        ]

        assert all(
            row is None
            for row in missing_rows
        )

        # Rebuild only from retained MongoDB raw records.
        first_replay = replay_envelopes(
            connection,
            selected,
        )

        assert first_replay.replayed_records == 5

        rebuilt_rows = [
            find_snapshot(
                connection,
                envelope,
            )
            for envelope in selected
        ]

        assert all(
            row is not None
            for row in rebuilt_rows
        )

        # Verify original Day-16 lineage survived replay.
        for envelope, row in zip(
            selected,
            rebuilt_rows,
            strict=True,
        ):
            assert row is not None

            assert str(
                row["ingestion_run_id"]
            ) == str(envelope.run_id)

            assert (
                row["source_checksum"]
                == envelope.source_checksum
            )

            assert (
                row["source_record_key"]
                == envelope.source_record_key
            )

        rebuilt_ids = tuple(
            int(row["credit_snapshot_id"])
            for row in rebuilt_rows
            if row is not None
        )

        # Replay the identical Mongo records again.
        # IDs must remain stable, proving curated
        # idempotency.
        second_replay = replay_envelopes(
            connection,
            selected,
        )

        assert second_replay.replayed_records == 5

        second_rows = [
            find_snapshot(
                connection,
                envelope,
            )
            for envelope in selected
        ]

        second_ids = tuple(
            int(row["credit_snapshot_id"])
            for row in second_rows
            if row is not None
        )

        assert second_ids == rebuilt_ids

    finally:
        # The proof performs real DELETE + REBUILD work,
        # but rollback prevents permanent modification
        # of the development database.
        if (
            transaction is not None
            and transaction.is_active
        ):
            transaction.rollback()

        if connection is not None:
            connection.close()

        mongo_client.close()
        postgres.dispose()