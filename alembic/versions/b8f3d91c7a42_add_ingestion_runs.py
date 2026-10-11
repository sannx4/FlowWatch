"""Add ingestion runs.

Revision ID: b8f3d91c7a42
Revises: ea49ab300f50
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8f3d91c7a42"
down_revision: str | None = "ea49ab300f50"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column(
            "run_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "source_dataset_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "source_resource_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text(
                "'running'"
            ),
            nullable=False,
        ),
        sa.Column(
            "pages",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "rows",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "page_size",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "code_version",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "failure_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "resumed_from_run_id",
            sa.Uuid(),
            nullable=True,
        ),
        sa.Column(
            "resume_from_page",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "resume_from_offset",
            sa.Integer(),
            nullable=True,
        ),
        sa.CheckConstraint(
            (
                "status IN "
                "('running', 'succeeded', 'failed')"
            ),
            name="status_valid",
        ),
        sa.CheckConstraint(
            "pages >= 0",
            name="pages_nonnegative",
        ),
        sa.CheckConstraint(
            "rows >= 0",
            name="rows_nonnegative",
        ),
        sa.CheckConstraint(
            "page_size > 0",
            name="page_size_positive",
        ),
        sa.CheckConstraint(
            (
                "(status = 'running' "
                "AND completed_at IS NULL) "
                "OR "
                "(status IN ('succeeded', 'failed') "
                "AND completed_at IS NOT NULL)"
            ),
            name="terminal_completion_consistent",
        ),
        sa.CheckConstraint(
            (
                "status <> 'failed' "
                "OR failure_reason IS NOT NULL"
            ),
            name="failed_run_has_reason",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            (
                "resume_from_page IS NULL "
                "OR resume_from_page > 0"
            ),
            name="resume_page_positive",
        ),
        sa.CheckConstraint(
            (
                "resume_from_offset IS NULL "
                "OR resume_from_offset >= 0"
            ),
            name="resume_offset_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["resumed_from_run_id"],
            ["ingestion_runs.run_id"],
            name=(
                "fk_ingestion_runs_"
                "resumed_from_run_id_"
                "ingestion_runs"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "run_id",
            name="pk_ingestion_runs",
        ),
    )

    op.create_index(
        "ix_ingestion_runs_status_started_at",
        "ingestion_runs",
        [
            "status",
            "started_at",
        ],
        unique=False,
    )

    op.create_index(
        "ix_ingestion_runs_resumed_from_run_id",
        "ingestion_runs",
        [
            "resumed_from_run_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingestion_runs_resumed_from_run_id",
        table_name="ingestion_runs",
    )

    op.drop_index(
        "ix_ingestion_runs_status_started_at",
        table_name="ingestion_runs",
    )

    op.drop_table(
        "ingestion_runs"
    )