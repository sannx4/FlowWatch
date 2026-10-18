
"""Day 19 PostgreSQL integrity and transaction tests.

These tests are opt-in and require a dedicated database named
flowwatch_day19_test. They must never run against the primary
FlowWatch database.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import (
    URL,
    create_engine,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from src.db.models import (
    Country,
    Credit,
    CreditSnapshot,
    Project,
    Region,
)
from src.ingestion.postgres_curated_loader import (
    CuratedLoadResult,
)
from src.ingestion.raw_envelope import RawRecordEnvelope
from src.loaders import postgres as loader

TEST_DATABASE = "flowwatch_day19_test"

SAMPLE_PATH = Path("data/raw/world_bank_sample.json")

DATASET_ID = "world_bank_ida_statement_of_credits"
RESOURCE_ID = "world_bank_sample_day16"

CORE_TABLES = (
    Region.__table__,
    Country.__table__,
    Project.__table__,
    Credit.__table__,
    CreditSnapshot.__table__,
)


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    """Connect only to the explicitly authorized test DB."""

    if os.getenv("FLOWWATCH_RUN_DAY19_INTEGRATION") != "1":
        pytest.skip("Day-19 PostgreSQL tests are opt-in.")

    load_dotenv()

    database_name = os.environ.get("POSTGRES_DB")

    if database_name != TEST_DATABASE:
        pytest.fail(
            "Refusing integration test: POSTGRES_DB must be "
            f"{TEST_DATABASE!r}, received {database_name!r}."
        )

    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5434")),
        database=database_name,
    )

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "options": (
                "-c statement_timeout=10000 "
                "-c lock_timeout=3000"
            )
        },
    )

    try:
        with engine.connect() as connection:
            actual_database = connection.exec_driver_sql(
                "SELECT current_database()"
            ).scalar_one()

        if actual_database != TEST_DATABASE:
            pytest.fail(
                f"Unexpected database: {actual_database}"
            )

        yield engine

    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("table", "values"),
    [
        (
            Project.__table__,
            {
                "project_id": "D19_ORPHAN_PROJECT",
                "country_id": -9_000_000_001,
            },
        ),
        (
            Credit.__table__,
            {
                "credit_number": "D19_ORPHAN_CREDIT",
                "project_pk": -9_000_000_001,
            },
        ),
        (
            CreditSnapshot.__table__,
            {
                "credit_id": -9_000_000_001,
                "end_of_period": date(2022, 6, 30),
            },
        ),
    ],
)
def test_orphan_rows_are_rejected(
    pg_engine: Engine,
    table: object,
    values: dict[str, object],
) -> None:
    """An orphan project, credit, or snapshot must fail."""

    with pytest.raises(IntegrityError) as error, pg_engine.begin() as connection:
        connection.execute(
            insert(table).values(**values)  # type: ignore[arg-type]
        )

    assert error.value.orig.sqlstate == "23503"


def test_duplicate_snapshot_identity_rejected(
    pg_engine: Engine,
) -> None:
    """A credit cannot have duplicate snapshot periods."""

    suffix = uuid4().hex[:10]

    with pytest.raises(IntegrityError) as error, pg_engine.begin() as connection:
        region_id = connection.execute(
            insert(Region.__table__)
            .values(
                region_name=f"Day19 Test Region {suffix}"
            )
            .returning(Region.__table__.c.region_id)
        ).scalar_one()

        country_id = connection.execute(
            insert(Country.__table__)
            .values(
                country_code=f"T{suffix}",
                country_name="Day19 Test Country",
                region_id=region_id,
            )
            .returning(Country.__table__.c.country_id)
        ).scalar_one()

        project_pk = connection.execute(
            insert(Project.__table__)
            .values(
                project_id=f"D19P{suffix}",
                project_name="Day19 Test Project",
                country_id=country_id,
            )
            .returning(Project.__table__.c.project_pk)
        ).scalar_one()

        credit_id = connection.execute(
            insert(Credit.__table__)
            .values(
                credit_number=f"D19C{suffix}",
                project_pk=project_pk,
            )
            .returning(Credit.__table__.c.credit_id)
        ).scalar_one()

        snapshot_values = {
            "credit_id": credit_id,
            "end_of_period": date(2022, 6, 30),
        }

        connection.execute(
            insert(CreditSnapshot.__table__).values(
                **snapshot_values
            )
        )

        # Same credit + reporting period: must fail.
        connection.execute(
            insert(CreditSnapshot.__table__).values(
                **snapshot_values
            )
        )

    assert error.value.orig.sqlstate == "23505"


def _core_counts(
    connection: Connection,
) -> tuple[int, ...]:
    """Count canonical rows across all five core tables."""

    return tuple(
        int(
            connection.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
        )
        for table in CORE_TABLES
    )


def _real_sample_envelopes(
    run_id: object,
) -> list[RawRecordEnvelope]:
    """Build two envelopes from the actual source sample."""

    raw_bytes = SAMPLE_PATH.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8"))

    records = payload["data"][:2]

    assert len(records) == 2

    checksum = hashlib.sha256(raw_bytes).hexdigest()
    retrieved_at = datetime.now(UTC)

    return [
        RawRecordEnvelope.from_source_payload(
            run_id=run_id,
            dataset_id=DATASET_ID,
            resource_id=RESOURCE_ID,
            retrieved_at=retrieved_at,
            page_number=1,
            page_offset=0,
            record_index=index,
            source_checksum=checksum,
            payload=record,
        )
        for index, record in enumerate(records)
    ]


def test_real_batch_failure_rolls_back_all_core_tables(
    pg_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inject a failure after actual PostgreSQL writes."""

    run_id = uuid4()
    envelopes = _real_sample_envelopes(run_id)

    with pg_engine.connect() as connection:
        counts_before = _core_counts(connection)

    original_loader = loader.load_curated_record
    records_processed = 0

    def fail_after_second_insert(
        connection: Connection,
        envelope: RawRecordEnvelope,
    ) -> CuratedLoadResult:
        nonlocal records_processed

        result = original_loader(connection, envelope)
        records_processed += 1

        if records_processed == 2:
            raise RuntimeError(
                "DAY19_INJECTED_POSTGRES_FAILURE"
            )

        return result

    monkeypatch.setattr(
        loader,
        "load_curated_record",
        fail_after_second_insert,
    )

    with pytest.raises(
        RuntimeError,
        match="DAY19_INJECTED_POSTGRES_FAILURE",
    ):
        loader.load_curated_batch(
            pg_engine,
            envelopes,
        )

    assert records_processed == 2

    with pg_engine.connect() as connection:
        counts_after = _core_counts(connection)

        remaining_snapshots = connection.execute(
            select(func.count())
            .select_from(CreditSnapshot.__table__)
            .where(
                CreditSnapshot.__table__.c.ingestion_run_id
                == run_id
            )
        ).scalar_one()

    assert counts_after == counts_before
    assert remaining_snapshots == 0
