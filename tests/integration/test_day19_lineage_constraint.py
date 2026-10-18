
"""Day 19: verify PostgreSQL source-lineage integrity."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from src.db.models import (
    Country,
    Credit,
    CreditSnapshot,
    Project,
    Region,
)

TEST_DATABASE = "flowwatch_day19_test"


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    """Connect only to the dedicated Day-19 test database."""

    if os.getenv("FLOWWATCH_RUN_DAY19_INTEGRATION") != "1":
        pytest.skip("Day-19 integration tests are opt-in.")

    load_dotenv()

    if os.getenv("POSTGRES_DB") != TEST_DATABASE:
        pytest.fail(
            "Refusing test outside flowwatch_day19_test."
        )

    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5434")),
        database=TEST_DATABASE,
    )

    engine = create_engine(
        url,
        connect_args={
            "connect_timeout": 5,
            "options": (
                "-c statement_timeout=10000 "
                "-c lock_timeout=3000"
            ),
        },
    )

    try:
        with engine.connect() as connection:
            actual_database = connection.exec_driver_sql(
                "SELECT current_database()"
            ).scalar_one()

        assert actual_database == TEST_DATABASE
        yield engine
    finally:
        engine.dispose()


def _create_test_credit(connection: Connection) -> int:
    """Create a temporary Region->Country->Project->Credit."""

    suffix = uuid4().hex[:10]

    region_id = connection.execute(
        insert(Region.__table__)
        .values(region_name=f"D19 Region {suffix}")
        .returning(Region.__table__.c.region_id)
    ).scalar_one()

    country_id = connection.execute(
        insert(Country.__table__)
        .values(
            country_code=f"T{suffix}",
            country_name=f"D19 Country {suffix}",
            region_id=region_id,
        )
        .returning(Country.__table__.c.country_id)
    ).scalar_one()

    project_pk = connection.execute(
        insert(Project.__table__)
        .values(
            project_id=f"D19P{suffix}",
            project_name="Day19 Lineage Test",
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

    return int(credit_id)


@pytest.mark.parametrize(
    "invalid_case",
    [
        "missing_checksum",
        "missing_run_id",
        "blank_source_key",
    ],
)
def test_incomplete_lineage_rejected(
    pg_engine: Engine,
    invalid_case: str,
) -> None:
    """The Day-19 CHECK constraint must reject bad lineage."""

    lineage = {
        "ingestion_run_id": uuid4(),
        "source_checksum": "a" * 64,
        "source_record_key": "record:day19-test",
    }

    if invalid_case == "missing_checksum":
        lineage["source_checksum"] = None
    elif invalid_case == "missing_run_id":
        lineage["ingestion_run_id"] = None
    else:
        lineage["source_record_key"] = "   "

    with pg_engine.connect() as connection:
        credit_id = _create_test_credit(connection)

        with pytest.raises(IntegrityError) as error:
            connection.execute(
                insert(CreditSnapshot.__table__).values(
                    credit_id=credit_id,
                    end_of_period=date(2022, 6, 30),
                    **lineage,
                )
            )

        assert error.value.orig.sqlstate == "23514"

    # Closing the connection rolls back the test changes.


def test_complete_lineage_accepted(
    pg_engine: Engine,
) -> None:
    """A snapshot with all three lineage fields is valid."""

    with pg_engine.connect() as connection:
        credit_id = _create_test_credit(connection)

        snapshot_id = connection.execute(
            insert(CreditSnapshot.__table__)
            .values(
                credit_id=credit_id,
                end_of_period=date(2022, 6, 30),
                ingestion_run_id=uuid4(),
                source_checksum="b" * 64,
                source_record_key="record:complete-day19",
            )
            .returning(
                CreditSnapshot.__table__.c.credit_snapshot_id
            )
        ).scalar_one()

        assert snapshot_id is not None


def test_legacy_snapshot_without_lineage_accepted(
    pg_engine: Engine,
) -> None:
    """All-null lineage remains valid for legacy records."""

    with pg_engine.connect() as connection:
        credit_id = _create_test_credit(connection)

        snapshot_id = connection.execute(
            insert(CreditSnapshot.__table__)
            .values(
                credit_id=credit_id,
                end_of_period=date(2022, 6, 30),
            )
            .returning(
                CreditSnapshot.__table__.c.credit_snapshot_id
            )
        ).scalar_one()

        assert snapshot_id is not None
