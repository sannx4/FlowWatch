"""Day29-32: fail-closed checkpoint ledger for independently fetched source pages.

Revision ID: d29b00000001
Revises: d26e00260001
"""
from __future__ import annotations

from alembic import op

revision = "d29b00000001"
down_revision = "d26e00260001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.historical_backfill_runs (
            run_id uuid PRIMARY KEY,
            dataset_id text NOT NULL,
            resource_id text NOT NULL,
            page_size integer NOT NULL CHECK (page_size BETWEEN 1 AND 1000),
            max_pages integer NOT NULL CHECK (max_pages >= 0),
            observed_total integer CHECK (observed_total > 0),
            status text NOT NULL CHECK (status IN ('RUNNING','FAILED','COMPLETE')),
            started_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            last_error text
        )
    """)
    op.execute("""
        CREATE TABLE public.historical_backfill_pages (
            run_id uuid NOT NULL REFERENCES public.historical_backfill_runs(run_id)
                ON DELETE RESTRICT,
            page_number integer NOT NULL CHECK (page_number > 0),
            page_offset integer NOT NULL CHECK (page_offset >= 0),
            record_count integer NOT NULL CHECK (record_count > 0),
            total_count integer NOT NULL CHECK (total_count > 0),
            source_checksum char(64) NOT NULL CHECK
                (source_checksum ~ '^[0-9a-f]{64}$'),
            raw_bytes_size bigint NOT NULL CHECK (raw_bytes_size > 0),
            completed_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, page_number),
            UNIQUE (run_id, page_offset)
        )
    """)
    op.execute("CREATE INDEX ix_historical_backfill_pages_run_offset ON public.historical_backfill_pages(run_id, page_offset)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON public.historical_backfill_runs TO flowwatch_ingestor")
    op.execute("GRANT SELECT, INSERT ON public.historical_backfill_pages TO flowwatch_ingestor")


def downgrade() -> None:
    op.execute("DROP TABLE public.historical_backfill_pages")
    op.execute("DROP TABLE public.historical_backfill_runs")
