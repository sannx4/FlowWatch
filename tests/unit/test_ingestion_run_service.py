from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.ingestion_models import (
    IngestionRun,
    IngestionRunStatus,
)
from src.ingestion.run_repository import (
    IngestionRunRepository,
)
from src.ingestion.run_service import (
    IngestionRunService,
    IngestionRunStateError,
)

TEST_TIME = datetime(
    2026,
    10,
    11,
    9,
    0,
    0,
    tzinfo=UTC,
)


def normalize_utc(
    value: datetime,
) -> datetime:
    """Normalize SQLite/PostgreSQL timestamps to aware UTC."""

    if value.tzinfo is None:
        return value.replace(
            tzinfo=UTC
        )

    return value.astimezone(
        UTC
    )


def fixed_clock() -> datetime:
    return TEST_TIME


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    IngestionRun.__table__.create(
        engine
    )

    with Session(
        engine
    ) as session:
        yield session

    engine.dispose()


@pytest.fixture
def service(
    db_session: Session,
) -> IngestionRunService:
    repository = IngestionRunRepository(
        db_session
    )

    return IngestionRunService(
        repository,
        clock=fixed_clock,
    )


def test_start_run_persists_required_metadata(
    service: IngestionRunService,
) -> None:
    run = service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=100,
        code_version="abc123",
    )

    assert run.run_id is not None

    assert (
        run.source_dataset_id
        == "DS00976"
    )

    assert (
        run.source_resource_id
        == "RS00906"
    )

    assert (
        run.status
        == IngestionRunStatus.RUNNING.value
    )

    assert normalize_utc(
        run.started_at
    ) == TEST_TIME

    assert run.completed_at is None

    assert run.pages == 0
    assert run.rows == 0

    assert run.page_size == 100
    assert run.code_version == "abc123"

    assert run.failure_reason is None

    assert run.resumed_from_run_id is None
    assert run.resume_from_page is None
    assert run.resume_from_offset is None


def test_page_progress_updates_pages_and_rows(
    service: IngestionRunService,
) -> None:
    run = service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=100,
        code_version="abc123",
    )

    service.record_page(
        run.run_id,
        row_count=100,
    )

    updated = service.record_page(
        run.run_id,
        row_count=75,
    )

    assert updated.pages == 2
    assert updated.rows == 175


def test_failed_run_remains_queryable(
    service: IngestionRunService,
    db_session: Session,
) -> None:
    run = service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=100,
        code_version="abc123",
    )

    service.record_page(
        run.run_id,
        row_count=100,
    )

    failed = service.fail_run(
        run.run_id,
        reason="simulated upstream failure",
    )

    failed_run_id = failed.run_id

    db_session.expire_all()

    queried = service.get_run(
        failed_run_id
    )

    assert queried.run_id == failed_run_id

    assert (
        queried.status
        == IngestionRunStatus.FAILED.value
    )

    assert queried.pages == 1
    assert queried.rows == 100

    assert (
        queried.failure_reason
        == "simulated upstream failure"
    )

    assert queried.completed_at is not None

    assert normalize_utc(
        queried.completed_at
    ) == TEST_TIME


def test_resume_references_correct_prior_checkpoint(
    service: IngestionRunService,
) -> None:
    run = service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=100,
        code_version="abc123",
    )

    service.record_page(
        run.run_id,
        row_count=100,
    )

    service.record_page(
        run.run_id,
        row_count=100,
    )

    failed = service.fail_run(
        run.run_id,
        reason="simulated process crash",
    )

    resumed = service.resume_failed_run(
        failed.run_id,
        code_version="def456",
    )

    assert (
        resumed.resumed_from_run_id
        == failed.run_id
    )

    assert (
        resumed.resume_from_page
        == 3
    )

    assert (
        resumed.resume_from_offset
        == 200
    )

    assert resumed.pages == 0
    assert resumed.rows == 0

    assert (
        resumed.source_dataset_id
        == failed.source_dataset_id
    )

    assert (
        resumed.source_resource_id
        == failed.source_resource_id
    )

    assert (
        resumed.page_size
        == failed.page_size
    )

    assert (
        resumed.status
        == IngestionRunStatus.RUNNING.value
    )


def test_successful_run_becomes_terminal(
    service: IngestionRunService,
) -> None:
    run = service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=100,
        code_version="abc123",
    )

    service.record_page(
        run.run_id,
        row_count=100,
    )

    completed = service.succeed_run(
        run.run_id
    )

    assert (
        completed.status
        == IngestionRunStatus.SUCCEEDED.value
    )

    assert completed.completed_at is not None

    assert normalize_utc(
        completed.completed_at
    ) == TEST_TIME

    assert completed.failure_reason is None


def test_terminal_run_cannot_record_more_pages(
    service: IngestionRunService,
) -> None:
    run = service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=100,
        code_version="abc123",
    )

    service.fail_run(
        run.run_id,
        reason="simulated failure",
    )

    with pytest.raises(
        IngestionRunStateError,
        match="terminal",
    ):
        service.record_page(
            run.run_id,
            row_count=100,
        )


def test_only_failed_run_can_be_resumed(
    service: IngestionRunService,
) -> None:
    run = service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=100,
        code_version="abc123",
    )

    with pytest.raises(
        IngestionRunStateError,
        match="Only failed",
    ):
        service.resume_failed_run(
            run.run_id,
            code_version="def456",
        )


@pytest.mark.parametrize(
    "row_count",
    [
        0,
        -1,
    ],
)
def test_invalid_completed_page_count_is_rejected(
    service: IngestionRunService,
    row_count: int,
) -> None:
    run = service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=100,
        code_version="abc123",
    )

    with pytest.raises(
        ValueError,
        match="row_count",
    ):
        service.record_page(
            run.run_id,
            row_count=row_count,
        )