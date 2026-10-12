from __future__ import annotations

import pytest

from src.ingestion.manifest_service import (
    RawPageManifestConflictError,
    RawPageManifestService,
)
from tests.faults.helpers import (
    TEST_RUN_ID,
    FakeRunRepository,
    FaultInjectingManifestRepository,
    fixed_clock,
    make_page,
)


def test_duplicate_page_is_rejected_without_second_manifest() -> None:
    manifest_repository = (
        FaultInjectingManifestRepository()
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

    first_manifest = (
        service.record_page(
            TEST_RUN_ID,
            page,
        )
    )

    with pytest.raises(
        RawPageManifestConflictError
    ):
        service.record_page(
            TEST_RUN_ID,
            page,
        )

    assert (
        first_manifest.page_number
        == 1
    )

    assert (
        len(
            manifest_repository
            .committed
        )
        == 1
    )

    assert (
        manifest_repository
        .commit_calls
        == 1
    )