from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from src.db.ingestion_models import (
    IngestionRunStatus,
)

TEST_RUN_ID = UUID(
    "13131313-1313-1313-1313-131313131313"
)


FIXED_TIME = datetime(
    2026,
    10,
    13,
    12,
    0,
    0,
    tzinfo=UTC,
)


def fixed_clock() -> datetime:
    return FIXED_TIME


def make_page(
    *,
    page_number: int = 1,
    offset: int = 0,
    requested_top: int = 100,
    payload: bytes = (
        b'{"count":1,"data":'
        b'[{"credit_number":"IDA00010"}]}'
    ),
) -> SimpleNamespace:
    """
    Build a source-page test double matching the metadata contract
    consumed by RawPageManifestService.

    `requested_top` and `requested_skip` deliberately mirror the
    real World Bank request metadata names.
    """

    request = SimpleNamespace(
        request_id=(
            f"day13-request-{page_number}"
        ),
        url=(
            "https://datacatalogapi.worldbank.org/"
            "dexapps/fone/api/apiservice"
        ),
        status_code=200,
        attempts=1,
        duration_ms=10.0,
        requested_top=requested_top,
        requested_skip=offset,
        # Compatibility aliases are retained only for fault-test
        # readability. Production manifest code consumes the
        # requested_* fields above.
        top=requested_top,
        skip=offset,
    )

    return SimpleNamespace(
        page_number=page_number,
        offset=offset,
        record_count=1,
        total_count=100,
        records=(
            {
                "credit_number": "IDA00010",
            },
        ),
        raw_bytes=payload,
        request=request,
    )


class FakeRunRepository:
    def __init__(
        self,
        *,
        run_id: UUID = TEST_RUN_ID,
    ) -> None:
        self._run = SimpleNamespace(
            run_id=run_id,
            status=(
                IngestionRunStatus.RUNNING
            ),
        )

    def get_required(
        self,
        run_id: UUID,
    ) -> SimpleNamespace:
        if (
            run_id
            != self._run.run_id
        ):
            raise LookupError(
                f"unknown run_id: {run_id}"
            )

        return self._run


class FaultInjectingManifestRepository:
    """
    Repository test double for manifest persistence fault injection.

    Objects added before commit are held in `pending`.

    A successful commit moves them to `committed`.

    An injected commit failure raises SQLAlchemyError. The production
    manifest service must then invoke rollback and propagate the
    failure instead of treating the write as successful.
    """

    def __init__(
        self,
        *,
        fail_on_commit: bool = False,
    ) -> None:
        self.fail_on_commit = (
            fail_on_commit
        )

        self.pending: list[Any] = []
        self.committed: list[Any] = []

        self.commit_calls = 0
        self.rollback_calls = 0
        self.refresh_calls = 0

    def add(
        self,
        manifest: Any,
    ) -> Any:
        self.pending.append(
            manifest
        )

        return manifest

    def get(
        self,
        manifest_id: UUID,
    ) -> Any | None:
        for manifest in (
            self.committed
            + self.pending
        ):
            if (
                manifest.manifest_id
                == manifest_id
            ):
                return manifest

        return None

    def get_required(
        self,
        manifest_id: UUID,
    ) -> Any:
        manifest = self.get(
            manifest_id
        )

        if manifest is None:
            raise LookupError(
                "unknown manifest_id: "
                f"{manifest_id}"
            )

        return manifest

    def get_by_run_page(
        self,
        run_id: UUID,
        page_number: int,
    ) -> Any | None:
        for manifest in (
            self.committed
            + self.pending
        ):
            if (
                manifest.run_id
                == run_id
                and manifest.page_number
                == page_number
            ):
                return manifest

        return None

    def get_by_run_offset(
        self,
        run_id: UUID,
        offset: int,
    ) -> Any | None:
        for manifest in (
            self.committed
            + self.pending
        ):
            if (
                manifest.run_id
                == run_id
                and manifest.offset
                == offset
            ):
                return manifest

        return None

    def list_for_run(
        self,
        run_id: UUID,
    ) -> list[Any]:
        return [
            manifest
            for manifest
            in self.committed
            if manifest.run_id
            == run_id
        ]

    def commit(
        self,
    ) -> None:
        self.commit_calls += 1

        if self.fail_on_commit:
            raise SQLAlchemyError(
                "injected partial write failure"
            )

        self.committed.extend(
            self.pending
        )

        self.pending.clear()

    def rollback(
        self,
    ) -> None:
        self.rollback_calls += 1

        self.pending.clear()

    def refresh(
        self,
        manifest: Any,
    ) -> None:
        del manifest

        self.refresh_calls += 1