
"""Day 19: transactional batch-loader unit tests.

These tests use a disposable SQLite database to verify
transaction ownership. PostgreSQL-specific constraints
will be tested separately against an isolated test database.
"""

from collections.abc import Iterator
from typing import cast

import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine

from src.ingestion.raw_envelope import RawRecordEnvelope
from src.loaders import postgres as loader


@pytest.fixture
def test_db() -> Iterator[tuple[Engine, Table]]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    metadata = MetaData()

    records = Table(
        "test_records",
        metadata,
        Column("record_id", Integer, primary_key=True),
        Column("value", String(50), nullable=False),
    )

    metadata.create_all(engine)

    yield engine, records

    engine.dispose()


def test_successful_batch_commits_all_records(
    test_db: tuple[Engine, Table],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, records = test_db

    def fake_load(
        connection: Connection,
        envelope: int,
    ) -> int:
        connection.execute(
            insert(records).values(
                record_id=envelope,
                value="committed",
            )
        )

        return envelope

    monkeypatch.setattr(
        loader,
        "load_curated_record",
        fake_load,
    )

    # The stub deliberately uses integers rather than real
    # envelopes to isolate transaction management.
    envelopes = cast(
        list[RawRecordEnvelope],
        [1, 2, 3],
    )

    results = loader.load_curated_batch(
        engine,
        envelopes,
    )

    assert len(results) == 3

    with engine.connect() as connection:
        saved_ids = connection.execute(
            select(records.c.record_id).order_by(
                records.c.record_id
            )
        ).scalars().all()

    assert saved_ids == [1, 2, 3]


def test_mid_batch_exception_rolls_back_every_insert(
    test_db: tuple[Engine, Table],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, records = test_db

    def fake_load(
        connection: Connection,
        envelope: int,
    ) -> int:
        connection.execute(
            insert(records).values(
                record_id=envelope,
                value="pending",
            )
        )

        if envelope == 3:
            raise RuntimeError(
                "DAY19_INJECTED_BATCH_FAILURE"
            )

        return envelope

    monkeypatch.setattr(
        loader,
        "load_curated_record",
        fake_load,
    )

    envelopes = cast(
        list[RawRecordEnvelope],
        [1, 2, 3, 4, 5],
    )

    with pytest.raises(
        RuntimeError,
        match="DAY19_INJECTED_BATCH_FAILURE",
    ):
        loader.load_curated_batch(
            engine,
            envelopes,
        )

    with engine.connect() as connection:
        saved_ids = connection.execute(
            select(records.c.record_id)
        ).scalars().all()

    assert saved_ids == []


def test_failed_batch_rolls_back_existing_row_updates(
    test_db: tuple[Engine, Table],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, records = test_db

    with engine.begin() as connection:
        connection.execute(
            insert(records).values(
                record_id=1,
                value="original",
            )
        )

    def fake_load(
        connection: Connection,
        envelope: int,
    ) -> int:
        connection.execute(
            update(records)
            .where(records.c.record_id == envelope)
            .values(value="incorrect-update")
        )

        raise RuntimeError(
            "DAY19_INJECTED_UPDATE_FAILURE"
        )

    monkeypatch.setattr(
        loader,
        "load_curated_record",
        fake_load,
    )

    envelopes = cast(
        list[RawRecordEnvelope],
        [1],
    )

    with pytest.raises(
        RuntimeError,
        match="DAY19_INJECTED_UPDATE_FAILURE",
    ):
        loader.load_curated_batch(
            engine,
            envelopes,
        )

    with engine.connect() as connection:
        value = connection.execute(
            select(records.c.value).where(
                records.c.record_id == 1
            )
        ).scalar_one()

    assert value == "original"
