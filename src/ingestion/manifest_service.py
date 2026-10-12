from __future__ import annotations

from collections.abc import (
    Callable,
    Iterable,
    Iterator,
)
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from src.db.ingestion_models import (
    IngestionRunStatus,
)
from src.db.raw_manifest_models import (
    RawPageManifest,
)
from src.ingestion.checksum import (
    checksum_matches,
    sha256_bytes,
)
from src.ingestion.manifest_repository import (
    RawPageManifestRepository,
)
from src.ingestion.paginator import (
    WorldBankPage,
)
from src.ingestion.run_repository import (
    IngestionRunRepository,
)
from src.observability.logging import (
    get_logger,
    log_event,
    set_correlation_ids,
)

logger = get_logger(
    "ingestion.page-manifest"
)


def utc_now() -> datetime:
    return datetime.now(
        UTC
    )


class RawPageManifestStateError(
    RuntimeError
):
    """Raised when a page cannot be manifested in the current run state."""


class RawPageManifestConflictError(
    RuntimeError
):
    """Raised when the same run/page boundary is manifested twice."""


@dataclass(
    frozen=True,
    slots=True,
)
class ManifestedPage:
    page: WorldBankPage
    manifest: RawPageManifest


class RawPageManifestService:
    def __init__(
        self,
        manifest_repository: RawPageManifestRepository,
        run_repository: IngestionRunRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._manifest_repository = (
            manifest_repository
        )

        self._run_repository = (
            run_repository
        )

        self._clock = clock

    def record_page(
        self,
        run_id: UUID,
        page: WorldBankPage,
    ) -> RawPageManifest:
        run = (
            self._run_repository
            .get_required(
                run_id
            )
        )

        if (
            run.status
            != IngestionRunStatus.RUNNING.value
        ):
            raise RawPageManifestStateError(
                "Raw pages may only be manifested "
                "while the ingestion run is running"
            )

        self._validate_page(
            page
        )

        existing_page = (
            self._manifest_repository
            .get_by_run_page(
                run_id,
                page.page_number,
            )
        )

        if existing_page is not None:
            raise RawPageManifestConflictError(
                "A manifest already exists for "
                f"run {run_id}, "
                f"page {page.page_number}"
            )

        existing_offset = (
            self._manifest_repository
            .get_by_run_offset(
                run_id,
                page.offset,
            )
        )

        if existing_offset is not None:
            raise RawPageManifestConflictError(
                "A manifest already exists for "
                f"run {run_id}, "
                f"offset {page.offset}"
            )

        checksum = sha256_bytes(
            page.raw_bytes
        )

        manifest = RawPageManifest(
            run_id=run_id,
            page_number=page.page_number,
            offset=page.offset,
            requested_page_size=(
                page.request.requested_top
            ),
            record_count=page.record_count,
            total_count=page.total_count,
            payload_size_bytes=len(
                page.raw_bytes
            ),
            sha256=checksum,
            request_id=page.request.request_id,
            source_url=page.request.url,
            status_code=(
                page.request.status_code
            ),
            attempts=page.request.attempts,
            manifested_at=self._clock(),
        )

        persisted = self._persist(
            manifest
        )

        set_correlation_ids(
            run_id=str(
                run_id
            ),
            request_id=(
                page.request.request_id
            ),
        )

        log_event(
            logger,
            "raw_page_manifest_recorded",
            component=(
                "ingestion.page-manifest"
            ),
            status="recorded",
            manifest_id=str(
                persisted.manifest_id
            ),
            page_number=(
                persisted.page_number
            ),
            offset=persisted.offset,
            record_count=(
                persisted.record_count
            ),
            payload_size_bytes=(
                persisted.payload_size_bytes
            ),
            sha256=persisted.sha256,
        )

        return persisted

    def manifest_pages(
        self,
        run_id: UUID,
        pages: Iterable[
            WorldBankPage
        ],
    ) -> Iterator[
        ManifestedPage
    ]:
        """Persist each manifest before releasing the page downstream."""

        for page in pages:
            manifest = self.record_page(
                run_id,
                page,
            )

            yield ManifestedPage(
                page=page,
                manifest=manifest,
            )

    def get_manifest(
        self,
        manifest_id: UUID,
    ) -> RawPageManifest:
        return (
            self._manifest_repository
            .get_required(
                manifest_id
            )
        )

    def payload_matches(
        self,
        manifest_id: UUID,
        payload: bytes,
    ) -> bool:
        manifest = self.get_manifest(
            manifest_id
        )

        return checksum_matches(
            payload,
            manifest.sha256,
        )

    def _persist(
        self,
        manifest: RawPageManifest,
    ) -> RawPageManifest:
        try:
            self._manifest_repository.add(
                manifest
            )

            self._manifest_repository.commit()

            self._manifest_repository.refresh(
                manifest
            )

            return manifest

        except Exception:
            self._manifest_repository.rollback()
            raise

    @staticmethod
    def _validate_page(
        page: WorldBankPage,
    ) -> None:
        if page.page_number <= 0:
            raise ValueError(
                "page_number must be positive"
            )

        if page.offset < 0:
            raise ValueError(
                "page offset cannot be negative"
            )

        if (
            page.record_count
            != len(
                page.records
            )
        ):
            raise ValueError(
                "page record_count does not match "
                "the number of records"
            )

        if (
            page.request.requested_skip
            != page.offset
        ):
            raise ValueError(
                "page offset does not match "
                "request metadata"
            )

        if (
            page.request.requested_top
            <= 0
        ):
            raise ValueError(
                "requested page size must be positive"
            )

        if (
            page.record_count
            > page.request.requested_top
        ):
            raise ValueError(
                "record_count cannot exceed "
                "requested page size"
            )

        if page.total_count < 0:
            raise ValueError(
                "total_count cannot be negative"
            )

        if (
            page.total_count
            < page.record_count
        ):
            raise ValueError(
                "total_count cannot be smaller "
                "than record_count"
            )

        if not isinstance(
            page.raw_bytes,
            bytes,
        ):
            raise TypeError(
                "WorldBankPage.raw_bytes "
                "must contain exact bytes"
            )