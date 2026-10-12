from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.ingestion_models import (
    IngestionRun,
)
from src.db.raw_manifest_models import (
    RawPageManifest,
)
from src.ingestion.manifest_repository import (
    RawPageManifestRepository,
)
from src.ingestion.manifest_service import (
    RawPageManifestConflictError,
    RawPageManifestService,
    RawPageManifestStateError,
)
from src.ingestion.paginator import (
    PageRequestMetadata,
    WorldBankPage,
)
from src.ingestion.run_repository import (
    IngestionRunRepository,
)
from src.ingestion.run_service import (
    IngestionRunService,
)

TEST_TIME = datetime(
    2026,
    10,
    11,
    12,
    0,
    0,
    tzinfo=UTC,
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

    RawPageManifest.__table__.create(
        engine
    )

    with Session(
        engine
    ) as session:
        yield session

    engine.dispose()


@pytest.fixture
def run_repository(
    db_session: Session,
) -> IngestionRunRepository:
    return IngestionRunRepository(
        db_session
    )


@pytest.fixture
def manifest_repository(
    db_session: Session,
) -> RawPageManifestRepository:
    return RawPageManifestRepository(
        db_session
    )


@pytest.fixture
def run_service(
    run_repository: IngestionRunRepository,
) -> IngestionRunService:
    return IngestionRunService(
        run_repository,
        clock=fixed_clock,
    )


@pytest.fixture
def manifest_service(
    manifest_repository: RawPageManifestRepository,
    run_repository: IngestionRunRepository,
) -> RawPageManifestService:
    return RawPageManifestService(
        manifest_repository,
        run_repository,
        clock=fixed_clock,
    )


def make_page(
    *,
    raw_bytes: bytes = (
        b'{"count":2,"data":[{"id":1},{"id":2}]}'
    ),
    page_number: int = 1,
    offset: int = 0,
) -> WorldBankPage:
    records = (
        {
            "id": 1,
        },
        {
            "id": 2,
        },
    )

    request = PageRequestMetadata(
        request_id=(
            f"request-{page_number}-{offset}"
        ),
        status_code=200,
        attempts=1,
        duration_ms=12.5,
        url=(
            "https://example.test/"
            f"?top=2&skip={offset}"
        ),
        requested_top=2,
        requested_skip=offset,
    )

    return WorldBankPage(
        page_number=page_number,
        offset=offset,
        record_count=2,
        total_count=2,
        records=records,
        raw_bytes=raw_bytes,
        request=request,
    )


def start_run(
    run_service: IngestionRunService,
):
    return run_service.start_run(
        source_dataset_id="DS00976",
        source_resource_id="RS00906",
        page_size=2,
        code_version="abc123",
    )


def test_record_page_persists_manifest_metadata(
    run_service: IngestionRunService,
    manifest_service: RawPageManifestService,
) -> None:
    run = start_run(
        run_service
    )

    page = make_page()

    manifest = (
        manifest_service.record_page(
            run.run_id,
            page,
        )
    )

    assert manifest.manifest_id is not None

    assert (
        manifest.run_id
        == run.run_id
    )

    assert manifest.page_number == 1
    assert manifest.offset == 0

    assert (
        manifest.requested_page_size
        == 2
    )

    assert manifest.record_count == 2
    assert manifest.total_count == 2

    assert (
        manifest.payload_size_bytes
        == len(
            page.raw_bytes
        )
    )

    assert len(
        manifest.sha256
    ) == 64

    assert (
        manifest.request_id
        == page.request.request_id
    )

    assert manifest.status_code == 200
    assert manifest.attempts == 1


def test_identical_payload_across_runs_has_same_checksum(
    run_service: IngestionRunService,
    manifest_service: RawPageManifestService,
) -> None:
    payload = (
        b'{"count":2,"data":[{"id":1},{"id":2}]}'
    )

    first_run = start_run(
        run_service
    )

    first_manifest = (
        manifest_service.record_page(
            first_run.run_id,
            make_page(
                raw_bytes=payload
            ),
        )
    )

    second_run = start_run(
        run_service
    )

    second_manifest = (
        manifest_service.record_page(
            second_run.run_id,
            make_page(
                raw_bytes=payload
            ),
        )
    )

    assert (
        first_manifest.sha256
        == second_manifest.sha256
    )


def test_changed_payload_is_detected(
    run_service: IngestionRunService,
    manifest_service: RawPageManifestService,
) -> None:
    run = start_run(
        run_service
    )

    page = make_page()

    manifest = (
        manifest_service.record_page(
            run.run_id,
            page,
        )
    )

    assert manifest_service.payload_matches(
        manifest.manifest_id,
        page.raw_bytes,
    )

    assert not manifest_service.payload_matches(
        manifest.manifest_id,
        page.raw_bytes + b"!",
    )


def test_duplicate_page_in_same_run_is_rejected(
    run_service: IngestionRunService,
    manifest_service: RawPageManifestService,
) -> None:
    run = start_run(
        run_service
    )

    page = make_page()

    manifest_service.record_page(
        run.run_id,
        page,
    )

    with pytest.raises(
        RawPageManifestConflictError,
        match="manifest already exists",
    ):
        manifest_service.record_page(
            run.run_id,
            page,
        )


def test_terminal_run_cannot_accept_new_manifest(
    run_service: IngestionRunService,
    manifest_service: RawPageManifestService,
) -> None:
    run = start_run(
        run_service
    )

    run_service.fail_run(
        run.run_id,
        reason="simulated failure",
    )

    with pytest.raises(
        RawPageManifestStateError,
        match="only be manifested",
    ):
        manifest_service.record_page(
            run.run_id,
            make_page(),
        )


def test_manifest_pages_persists_before_yield(
    run_service: IngestionRunService,
    manifest_service: RawPageManifestService,
    manifest_repository: RawPageManifestRepository,
) -> None:
    run = start_run(
        run_service
    )

    page = make_page()

    stream = (
        manifest_service.manifest_pages(
            run.run_id,
            [
                page,
            ],
        )
    )

    manifested_page = next(
        stream
    )

    stored = (
        manifest_repository
        .get_by_run_page(
            run.run_id,
            page.page_number,
        )
    )

    assert stored is not None

    assert (
        stored.manifest_id
        == manifested_page.manifest.manifest_id
    )

    assert (
        manifested_page.page
        is page
    )