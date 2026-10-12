from __future__ import annotations

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.ingestion.manifest_service import (
    RawPageManifestService,
)
from tests.faults.helpers import (
    TEST_RUN_ID,
    FakeRunRepository,
    FaultInjectingManifestRepository,
    fixed_clock,
    make_page,
)


def test_partial_manifest_write_rolls_back_and_fails_closed() -> None:
    manifest_repository = (
        FaultInjectingManifestRepository(
            fail_on_commit=True,
        )
    )

    run_repository = (
        FakeRunRepository()
    )

    service = RawPageManifestService(
        manifest_repository,
        run_repository,
        clock=fixed_clock,
    )

    page = make_page(
        page_number=1,
        offset=0,
    )

    with pytest.raises(
        SQLAlchemyError,
        match=(
            "injected partial write failure"
        ),
    ):
        service.record_page(
            TEST_RUN_ID,
            page,
        )

    assert (
        manifest_repository
        .commit_calls
        == 1
    )

    assert (
        manifest_repository
        .rollback_calls
        == 1
    )

    assert (
        manifest_repository.pending
        == []
    )

    assert (
        manifest_repository.committed
        == []
    )