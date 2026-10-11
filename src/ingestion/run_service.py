from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from src.db.ingestion_models import (
    IngestionRun,
    IngestionRunStatus,
)
from src.ingestion.run_repository import (
    IngestionRunRepository,
)
from src.observability.logging import (
    get_logger,
    log_event,
    set_correlation_ids,
)


def utc_now() -> datetime:
    """Return timezone-aware current UTC time."""

    return datetime.now(
        UTC
    )


class IngestionRunStateError(RuntimeError):
    """Raised for an invalid ingestion-run state transition."""


class IngestionRunService:
    """Own ingestion-run lifecycle and resume semantics."""

    def __init__(
        self,
        repository: IngestionRunRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

        self._logger = get_logger(
            "ingestion.run-service"
        )

    def start_run(
        self,
        *,
        source_dataset_id: str,
        source_resource_id: str,
        page_size: int,
        code_version: str,
    ) -> IngestionRun:
        """Create a new root ingestion run."""

        self._validate_identity(
            source_dataset_id=source_dataset_id,
            source_resource_id=source_resource_id,
            page_size=page_size,
            code_version=code_version,
        )

        run = IngestionRun(
            run_id=uuid.uuid4(),
            source_dataset_id=(
                source_dataset_id.strip()
            ),
            source_resource_id=(
                source_resource_id.strip()
            ),
            started_at=self._clock(),
            completed_at=None,
            status=(
                IngestionRunStatus.RUNNING.value
            ),
            pages=0,
            rows=0,
            page_size=page_size,
            code_version=code_version.strip(),
            failure_reason=None,
            resumed_from_run_id=None,
            resume_from_page=None,
            resume_from_offset=None,
        )

        self._persist(
            run
        )

        self._set_run_context(
            run
        )

        log_event(
            self._logger,
            "ingestion_run_started",
            status="running",
            run_id=str(
                run.run_id
            ),
            source_dataset_id=(
                run.source_dataset_id
            ),
            source_resource_id=(
                run.source_resource_id
            ),
            page_size=run.page_size,
            code_version=run.code_version,
        )

        return run

    def record_page(
        self,
        run_id: uuid.UUID,
        *,
        row_count: int,
    ) -> IngestionRun:
        """Record one successfully completed source page."""

        if row_count <= 0:
            raise ValueError(
                "row_count must be greater than zero."
            )

        run = (
            self._repository.get_required(
                run_id
            )
        )

        self._require_running(
            run
        )

        run.pages += 1
        run.rows += row_count

        self._persist(
            run
        )

        self._set_run_context(
            run
        )

        log_event(
            self._logger,
            "ingestion_run_page_recorded",
            status="running",
            run_id=str(
                run.run_id
            ),
            pages=run.pages,
            rows=run.rows,
            latest_page_rows=row_count,
        )

        return run

    def fail_run(
        self,
        run_id: uuid.UUID,
        *,
        reason: str,
    ) -> IngestionRun:
        """Mark a running ingestion execution as failed."""

        clean_reason = reason.strip()

        if not clean_reason:
            raise ValueError(
                "Failure reason cannot be empty."
            )

        run = (
            self._repository.get_required(
                run_id
            )
        )

        self._require_running(
            run
        )

        run.status = (
            IngestionRunStatus.FAILED.value
        )

        run.completed_at = (
            self._clock()
        )

        run.failure_reason = (
            clean_reason
        )

        self._persist(
            run
        )

        self._set_run_context(
            run
        )

        log_event(
            self._logger,
            "ingestion_run_failed",
            status="failed",
            run_id=str(
                run.run_id
            ),
            pages=run.pages,
            rows=run.rows,
            failure_reason=(
                run.failure_reason
            ),
        )

        return run

    def succeed_run(
        self,
        run_id: uuid.UUID,
    ) -> IngestionRun:
        """Mark a running ingestion execution as successful."""

        run = (
            self._repository.get_required(
                run_id
            )
        )

        self._require_running(
            run
        )

        run.status = (
            IngestionRunStatus.SUCCEEDED.value
        )

        run.completed_at = (
            self._clock()
        )

        run.failure_reason = None

        self._persist(
            run
        )

        self._set_run_context(
            run
        )

        log_event(
            self._logger,
            "ingestion_run_succeeded",
            status="success",
            run_id=str(
                run.run_id
            ),
            pages=run.pages,
            rows=run.rows,
        )

        return run

    def resume_failed_run(
        self,
        failed_run_id: uuid.UUID,
        *,
        code_version: str,
    ) -> IngestionRun:
        """Create a new run linked to a failed run's page boundary."""

        failed_run = (
            self._repository.get_required(
                failed_run_id
            )
        )

        if (
            failed_run.status
            != IngestionRunStatus.FAILED.value
        ):
            raise IngestionRunStateError(
                "Only failed ingestion runs "
                "can be resumed."
            )

        clean_code_version = (
            code_version.strip()
        )

        if not clean_code_version:
            raise ValueError(
                "code_version cannot be empty."
            )

        resume_from_page = (
            failed_run.pages + 1
        )

        resume_from_offset = (
            failed_run.pages
            * failed_run.page_size
        )

        resumed_run = IngestionRun(
            run_id=uuid.uuid4(),
            source_dataset_id=(
                failed_run.source_dataset_id
            ),
            source_resource_id=(
                failed_run.source_resource_id
            ),
            started_at=self._clock(),
            completed_at=None,
            status=(
                IngestionRunStatus.RUNNING.value
            ),
            pages=0,
            rows=0,
            page_size=(
                failed_run.page_size
            ),
            code_version=(
                clean_code_version
            ),
            failure_reason=None,
            resumed_from_run_id=(
                failed_run.run_id
            ),
            resume_from_page=(
                resume_from_page
            ),
            resume_from_offset=(
                resume_from_offset
            ),
        )

        self._persist(
            resumed_run
        )

        self._set_run_context(
            resumed_run
        )

        log_event(
            self._logger,
            "ingestion_run_resumed",
            status="running",
            run_id=str(
                resumed_run.run_id
            ),
            resumed_from_run_id=str(
                failed_run.run_id
            ),
            resume_from_page=(
                resumed_run.resume_from_page
            ),
            resume_from_offset=(
                resumed_run.resume_from_offset
            ),
            prior_pages=(
                failed_run.pages
            ),
            prior_rows=(
                failed_run.rows
            ),
        )

        return resumed_run

    def get_run(
        self,
        run_id: uuid.UUID,
    ) -> IngestionRun:
        """Return persisted metadata for a run."""

        return (
            self._repository.get_required(
                run_id
            )
        )

    def _persist(
        self,
        run: IngestionRun,
    ) -> None:
        try:
            self._repository.add(
                run
            )

            self._repository.commit()

            self._repository.refresh(
                run
            )

        except Exception:
            self._repository.rollback()
            raise

    @staticmethod
    def _validate_identity(
        *,
        source_dataset_id: str,
        source_resource_id: str,
        page_size: int,
        code_version: str,
    ) -> None:
        if not source_dataset_id.strip():
            raise ValueError(
                "source_dataset_id cannot be empty."
            )

        if not source_resource_id.strip():
            raise ValueError(
                "source_resource_id cannot be empty."
            )

        if page_size <= 0:
            raise ValueError(
                "page_size must be greater than zero."
            )

        if not code_version.strip():
            raise ValueError(
                "code_version cannot be empty."
            )

    @staticmethod
    def _require_running(
        run: IngestionRun,
    ) -> None:
        if (
            run.status
            != IngestionRunStatus.RUNNING.value
        ):
            raise IngestionRunStateError(
                "Ingestion run is terminal and "
                "cannot be modified: "
                f"run_id={run.run_id}, "
                f"status={run.status}"
            )

    @staticmethod
    def _set_run_context(
        run: IngestionRun,
    ) -> None:
        set_correlation_ids(
            run_id=str(
                run.run_id
            )
        )