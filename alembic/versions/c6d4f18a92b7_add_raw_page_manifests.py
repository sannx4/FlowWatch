"""Add raw page manifests.

Revision ID: c6d4f18a92b7
Revises: b8f3d91c7a42
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c6d4f18a92b7"
down_revision: str | None = (
    "b8f3d91c7a42"
)

branch_labels: (
    str | Sequence[str] | None
) = None

depends_on: (
    str | Sequence[str] | None
) = None


def upgrade() -> None:
    op.create_table(
        "raw_page_manifests",
        sa.Column(
            "manifest_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "page_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "offset",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "requested_page_size",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "record_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "total_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "payload_size_bytes",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "sha256",
            sa.String(
                length=64
            ),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            sa.String(
                length=64
            ),
            nullable=False,
        ),
        sa.Column(
            "source_url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "status_code",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "manifested_at",
            sa.DateTime(
                timezone=True
            ),
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            "page_number > 0",
            name="page_number_positive",
        ),
        sa.CheckConstraint(
           '"offset" >= 0',
           name="offset_nonnegative",
        ),
        sa.CheckConstraint(
            "requested_page_size > 0",
            name=(
                "requested_page_size_positive"
            ),
        ),
        sa.CheckConstraint(
            "record_count >= 0",
            name="record_count_nonnegative",
        ),
        sa.CheckConstraint(
            (
                "record_count "
                "<= requested_page_size"
            ),
            name=(
                "record_count_within_page_size"
            ),
        ),
        sa.CheckConstraint(
            "total_count >= 0",
            name="total_count_nonnegative",
        ),
        sa.CheckConstraint(
            "total_count >= record_count",
            name="total_count_covers_page",
        ),
        sa.CheckConstraint(
            "payload_size_bytes >= 0",
            name="payload_size_nonnegative",
        ),
        sa.CheckConstraint(
            "length(sha256) = 64",
            name="sha256_length",
        ),
        sa.CheckConstraint(
            (
                "status_code >= 100 "
                "AND status_code <= 599"
            ),
            name="status_code_valid",
        ),
        sa.CheckConstraint(
            "attempts > 0",
            name="attempts_positive",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ingestion_runs.run_id"],
            name=(
                "fk_raw_page_manifests_"
                "run_id_ingestion_runs"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "manifest_id",
            name=(
                "pk_raw_page_manifests"
            ),
        ),
        sa.UniqueConstraint(
            "run_id",
            "page_number",
            name=(
                "uq_raw_page_manifests_"
                "run_page"
            ),
        ),
        sa.UniqueConstraint(
            "run_id",
            "offset",
            name=(
                "uq_raw_page_manifests_"
                "run_offset"
            ),
        ),
    )

    op.create_index(
        "ix_raw_page_manifests_sha256",
        "raw_page_manifests",
        [
            "sha256",
        ],
        unique=False,
    )

    op.create_index(
        (
            "ix_raw_page_manifests_"
            "run_manifested_at"
        ),
        "raw_page_manifests",
        [
            "run_id",
            "manifested_at",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        (
            "ix_raw_page_manifests_"
            "run_manifested_at"
        ),
        table_name=(
            "raw_page_manifests"
        ),
    )

    op.drop_index(
        "ix_raw_page_manifests_sha256",
        table_name=(
            "raw_page_manifests"
        ),
    )

    op.drop_table(
        "raw_page_manifests"
    )