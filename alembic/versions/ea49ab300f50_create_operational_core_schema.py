"""create operational core schema

Revision ID: ea49ab300f50
Revises:
Create Date: 2026-10-10 23:31:14.250055
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ea49ab300f50"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the FlowWatch operational core schema."""

    op.create_table(
        "regions",
        sa.Column(
            "region_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "region_name",
            sa.Text(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(region_name) <> ''",
            name=op.f("ck_regions_region_name_not_blank"),
        ),
        sa.PrimaryKeyConstraint(
            "region_id",
            name=op.f("pk_regions"),
        ),
        sa.UniqueConstraint(
            "region_name",
            name=op.f("uq_regions_region_name"),
        ),
    )

    op.create_table(
        "countries",
        sa.Column(
            "country_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "country_code",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "country_name",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "region_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(country_code) <> ''",
            name=op.f("ck_countries_country_code_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(country_name) <> ''",
            name=op.f("ck_countries_country_name_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["regions.region_id"],
            name=op.f("fk_countries_region_id_regions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "country_id",
            name=op.f("pk_countries"),
        ),
        sa.UniqueConstraint(
            "country_code",
            name=op.f("uq_countries_country_code"),
        ),
    )

    op.create_index(
        "ix_countries_region_id",
        "countries",
        ["region_id"],
        unique=False,
    )

    op.create_table(
        "projects",
        sa.Column(
            "project_pk",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "project_name",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "country_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(project_id) <> ''",
            name=op.f("ck_projects_project_id_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["countries.country_id"],
            name=op.f("fk_projects_country_id_countries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "project_pk",
            name=op.f("pk_projects"),
        ),
        sa.UniqueConstraint(
            "project_id",
            name=op.f("uq_projects_project_id"),
        ),
    )

    op.create_index(
        "ix_projects_country_id",
        "projects",
        ["country_id"],
        unique=False,
    )

    op.create_table(
        "credits",
        sa.Column(
            "credit_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "credit_number",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "project_pk",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "borrower",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "currency_of_commitment",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "board_approval_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "agreement_signing_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "effective_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "first_repayment_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "last_repayment_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "closed_date",
            sa.Date(),
            nullable=True,
        ),
        sa.CheckConstraint(
            "btrim(credit_number) <> ''",
            name=op.f("ck_credits_credit_number_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["project_pk"],
            ["projects.project_pk"],
            name=op.f("fk_credits_project_pk_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "credit_id",
            name=op.f("pk_credits"),
        ),
        sa.UniqueConstraint(
            "credit_number",
            name=op.f("uq_credits_credit_number"),
        ),
    )

    op.create_index(
        "ix_credits_project_pk",
        "credits",
        ["project_pk"],
        unique=False,
    )

    op.create_table(
        "credit_snapshots",
        sa.Column(
            "credit_snapshot_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "credit_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "end_of_period",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "credit_status",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "service_charge_rate",
            sa.Numeric(precision=12, scale=6),
            nullable=True,
        ),
        sa.Column(
            "original_principal_amount_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "cancelled_amount_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "undisbursed_amount_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "disbursed_amount_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "repaid_to_ida_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "due_to_ida_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "exchange_adjustment_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "borrowers_obligation_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "sold_third_party_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "repaid_third_party_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "due_third_party_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "credits_held_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "last_disbursement_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "ingestion_run_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "source_checksum",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "source_record_key",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_checksum IS NULL "
            "OR source_checksum ~ '^[0-9A-Fa-f]{64}$'",
            name=op.f(
                "ck_credit_snapshots_source_checksum_sha256"
            ),
        ),
        sa.CheckConstraint(
            "service_charge_rate IS NULL "
            "OR service_charge_rate >= 0",
            name=op.f(
                "ck_credit_snapshots_service_charge_rate_nonnegative"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["credit_id"],
            ["credits.credit_id"],
            name=op.f(
                "fk_credit_snapshots_credit_id_credits"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "credit_snapshot_id",
            name=op.f("pk_credit_snapshots"),
        ),
        sa.UniqueConstraint(
            "credit_id",
            "end_of_period",
            name="uq_credit_snapshots_credit_period",
        ),
    )


def downgrade() -> None:
    """Remove the FlowWatch operational core schema."""

    op.drop_table("credit_snapshots")

    op.drop_index(
        "ix_credits_project_pk",
        table_name="credits",
    )
    op.drop_table("credits")

    op.drop_index(
        "ix_projects_country_id",
        table_name="projects",
    )
    op.drop_table("projects")

    op.drop_index(
        "ix_countries_region_id",
        table_name="countries",
    )
    op.drop_table("countries")

    op.drop_table("regions")