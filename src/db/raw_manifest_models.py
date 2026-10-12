from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class RawPageManifest(Base):
    """Integrity and request metadata for one fetched raw source page."""

    __tablename__ = "raw_page_manifests"

    manifest_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "ingestion_runs.run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    offset: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    requested_page_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    record_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    total_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    payload_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    request_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    source_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status_code: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    manifested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "page_number",
            name="uq_raw_page_manifests_run_page",
        ),
        UniqueConstraint(
            "run_id",
            "offset",
            name="uq_raw_page_manifests_run_offset",
        ),
        CheckConstraint(
            "page_number > 0",
            name="page_number_positive",
        ),
        CheckConstraint(
           '"offset" >= 0',
           name="offset_nonnegative",
        ),
        CheckConstraint(
            "requested_page_size > 0",
            name="requested_page_size_positive",
        ),
        CheckConstraint(
            "record_count >= 0",
            name="record_count_nonnegative",
        ),
        CheckConstraint(
            "record_count <= requested_page_size",
            name="record_count_within_page_size",
        ),
        CheckConstraint(
            "total_count >= 0",
            name="total_count_nonnegative",
        ),
        CheckConstraint(
            "total_count >= record_count",
            name="total_count_covers_page",
        ),
        CheckConstraint(
            "payload_size_bytes >= 0",
            name="payload_size_nonnegative",
        ),
        CheckConstraint(
            "length(sha256) = 64",
            name="sha256_length",
        ),
        CheckConstraint(
            "status_code >= 100 AND status_code <= 599",
            name="status_code_valid",
        ),
        CheckConstraint(
            "attempts > 0",
            name="attempts_positive",
        ),
        Index(
            "ix_raw_page_manifests_sha256",
            "sha256",
        ),
        Index(
            "ix_raw_page_manifests_run_manifested_at",
            "run_id",
            "manifested_at",
        ),
    )