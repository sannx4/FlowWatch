
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db import ingestion_models as _ingestion_models  # noqa: F401
from src.db import raw_manifest_models as _raw_manifest_models  # noqa: F401
from src.db.base import Base


class Region(Base):
    __tablename__ = "regions"

    region_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    region_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("region_name"),
        CheckConstraint(
            "btrim(region_name) <> ''",
            name="region_name_not_blank",
        ),
    )


class Country(Base):
    __tablename__ = "countries"

    country_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    country_code: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    country_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    region_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "regions.region_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("country_code"),
        CheckConstraint(
            "btrim(country_code) <> ''",
            name="country_code_not_blank",
        ),
        CheckConstraint(
            "btrim(country_name) <> ''",
            name="country_name_not_blank",
        ),
        Index(
            "ix_countries_region_id",
            "region_id",
        ),
    )


class Project(Base):
    __tablename__ = "projects"

    project_pk: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    project_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    project_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    country_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "countries.country_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("project_id"),
        CheckConstraint(
            "btrim(project_id) <> ''",
            name="project_id_not_blank",
        ),
        Index(
            "ix_projects_country_id",
            "country_id",
        ),
    )


class Credit(Base):
    __tablename__ = "credits"

    credit_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    credit_number: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    project_pk: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "projects.project_pk",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    borrower: Mapped[str | None] = mapped_column(
        Text,
    )

    currency_of_commitment: Mapped[str | None] = mapped_column(
        String(16),
    )

    board_approval_date: Mapped[date | None] = mapped_column(
        Date,
    )

    agreement_signing_date: Mapped[date | None] = mapped_column(
        Date,
    )

    effective_date: Mapped[date | None] = mapped_column(
        Date,
    )

    first_repayment_date: Mapped[date | None] = mapped_column(
        Date,
    )

    last_repayment_date: Mapped[date | None] = mapped_column(
        Date,
    )

    closed_date: Mapped[date | None] = mapped_column(
        Date,
    )

    __table_args__ = (
        UniqueConstraint("credit_number"),
        CheckConstraint(
            "btrim(credit_number) <> ''",
            name="credit_number_not_blank",
        ),
        Index(
            "ix_credits_project_pk",
            "project_pk",
        ),
    )


class CreditSnapshot(Base):
    __tablename__ = "credit_snapshots"

    credit_snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    credit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "credits.credit_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    end_of_period: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    credit_status: Mapped[str | None] = mapped_column(
        Text,
    )

    service_charge_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
    )

    original_principal_amount_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    cancelled_amount_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    undisbursed_amount_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    disbursed_amount_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    repaid_to_ida_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    due_to_ida_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    exchange_adjustment_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    borrowers_obligation_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    sold_third_party_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    repaid_third_party_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    due_third_party_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    credits_held_usd: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(24, 2),
    )

    last_disbursement_date: Mapped[
        date | None
    ] = mapped_column(
        Date,
    )

    # Source lineage fields.
    # These identify the raw acquisition responsible
    # for the canonical snapshot.

    ingestion_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
    )

    source_checksum: Mapped[str | None] = mapped_column(
        String(64),
    )

    source_record_key: Mapped[str | None] = mapped_column(
        Text,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # One snapshot per credit and reporting period.
        UniqueConstraint(
            "credit_id",
            "end_of_period",
            name="uq_credit_snapshots_credit_period",
        ),

        # Service charge cannot be negative.
        CheckConstraint(
            "service_charge_rate IS NULL "
            "OR service_charge_rate >= 0",
            name="service_charge_rate_nonnegative",
        ),

        # Source checksum must be a valid SHA-256 hex digest.
        CheckConstraint(
            "source_checksum IS NULL "
            "OR source_checksum ~ '^[0-9A-Fa-f]{64}$'",
            name="source_checksum_sha256",
        ),

        # Day 19: enforce complete source lineage.
        #
        # Valid:
        #   All three lineage fields are NULL (legacy).
        #   All three fields are populated.
        #
        # Invalid:
        #   Only some lineage fields are populated.
        #   Source record key is blank.
        CheckConstraint(
            """
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
            """,
            name="lineage_complete",
        ),
    )
