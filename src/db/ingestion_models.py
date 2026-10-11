from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class IngestionRunStatus(StrEnum):
    """Allowed ingestion-run lifecycle states."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IngestionRun(Base):
    """Persistent metadata for one logical ingestion execution."""

    __tablename__ = "ingestion_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="status_valid",
        ),
        CheckConstraint(
            "pages >= 0",
            name="pages_nonnegative",
        ),
        CheckConstraint(
            "rows >= 0",
            name="rows_nonnegative",
        ),
        CheckConstraint(
            "page_size > 0",
            name="page_size_positive",
        ),
        CheckConstraint(
            (
                "(status = 'running' AND completed_at IS NULL) "
                "OR "
                "(status IN ('succeeded', 'failed') "
                "AND completed_at IS NOT NULL)"
            ),
            name="terminal_completion_consistent",
        ),
        CheckConstraint(
            (
                "status <> 'failed' "
                "OR failure_reason IS NOT NULL"
            ),
            name="failed_run_has_reason",
        ),
        CheckConstraint(
            (
                "(resumed_from_run_id IS NULL "
                "AND resume_from_page IS NULL "
                "AND resume_from_offset IS NULL) "
                "OR "
                "(resumed_from_run_id IS NOT NULL "
                "AND resume_from_page IS NOT NULL "
                "AND resume_from_offset IS NOT NULL)"
            ),
            name="resume_metadata_consistent",
        ),
        CheckConstraint(
            (
                "resume_from_page IS NULL "
                "OR resume_from_page > 0"
            ),
            name="resume_page_positive",
        ),
        CheckConstraint(
            (
                "resume_from_offset IS NULL "
                "OR resume_from_offset >= 0"
            ),
            name="resume_offset_nonnegative",
        ),
        Index(
            "ix_ingestion_runs_status_started_at",
            "status",
            "started_at",
        ),
        Index(
            "ix_ingestion_runs_resumed_from_run_id",
            "resumed_from_run_id",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    source_dataset_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    source_resource_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=IngestionRunStatus.RUNNING.value,
        server_default=IngestionRunStatus.RUNNING.value,
    )

    pages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    page_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    code_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    resumed_from_run_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "ingestion_runs.run_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    resume_from_page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    resume_from_offset: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )