
"""Enforce complete source lineage on canonical snapshots.

Revision ID: f7b19a2c4d63
Revises: c6d4f18a92b7

Day 19 — Canonical constraints and transactional loaders.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f7b19a2c4d63"
down_revision: str | Sequence[str] | None = "c6d4f18a92b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LINEAGE_COMPLETENESS_CHECK = """
(
    (
        ingestion_run_id IS NULL
        AND source_checksum IS NULL
        AND source_record_key IS NULL
    )
    OR
    (
        ingestion_run_id IS NOT NULL
        AND source_checksum IS NOT NULL
        AND source_record_key IS NOT NULL
        AND btrim(source_record_key) <> ''
    )
)
"""


def upgrade() -> None:
    """Reject snapshots with incomplete source lineage."""

    op.create_check_constraint(
        op.f("ck_credit_snapshots_lineage_complete"),
        "credit_snapshots",
        LINEAGE_COMPLETENESS_CHECK,
    )


def downgrade() -> None:
    """Remove the Day-19 lineage completeness constraint."""

    op.drop_constraint(
        op.f("ck_credit_snapshots_lineage_complete"),
        "credit_snapshots",
        type_="check",
    )
