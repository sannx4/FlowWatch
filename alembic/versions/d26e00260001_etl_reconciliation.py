"""Day 26 immutable per-attempt ETL decision and reconciliation ledgers.

Revision ID: d26e00260001
Revises: d25cafe01250
"""
from __future__ import annotations

from alembic import op

revision = "d26e00260001"
down_revision = "d25cafe01250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.etl_attempts (
            run_id uuid NOT NULL,
            attempt_no integer NOT NULL CHECK (attempt_no > 0),
            source_pages integer NOT NULL CHECK (source_pages > 0),
            fetched integer NOT NULL CHECK (fetched > 0),
            raw_stored integer NOT NULL CHECK (raw_stored >= 0),
            accepted integer NOT NULL CHECK (accepted >= 0),
            rejected integer NOT NULL CHECK (rejected >= 0),
            inserted integer NOT NULL CHECK (inserted >= 0),
            updated integer NOT NULL CHECK (updated >= 0),
            unchanged integer NOT NULL CHECK (unchanged >= 0),
            ignored integer NOT NULL CHECK (ignored >= 0),
            status text NOT NULL CHECK (status = 'PASS'),
            completed_at timestamptz NOT NULL,
            PRIMARY KEY (run_id, attempt_no),
            CONSTRAINT ck_etl_source_balance CHECK (
                fetched = raw_stored AND fetched = accepted + rejected
            ),
            CONSTRAINT ck_etl_outcome_balance CHECK (
                accepted = inserted + updated + unchanged + ignored
            )
        )
    """)
    op.execute("""
        CREATE TABLE public.etl_record_decisions (
            run_id uuid NOT NULL,
            attempt_no integer NOT NULL CHECK (attempt_no > 0),
            source_record_key text NOT NULL CHECK (btrim(source_record_key) <> ''),
            source_checksum char(64) NOT NULL,
            outcome text NOT NULL CHECK
              (outcome IN ('INSERTED','UPDATED','UNCHANGED','IGNORED','REJECTED')),
            snapshot_id bigint REFERENCES public.credit_snapshots(credit_snapshot_id)
                ON DELETE RESTRICT,
            quarantine_id bigint REFERENCES public.source_quarantine(quarantine_id)
                ON DELETE RESTRICT,
            recorded_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, attempt_no, source_record_key),
            CONSTRAINT ck_etl_decision_target CHECK (
                (outcome = 'REJECTED' AND snapshot_id IS NULL AND quarantine_id IS NOT NULL)
                OR (outcome <> 'REJECTED' AND snapshot_id IS NOT NULL AND quarantine_id IS NULL)
            )
        )
    """)
    op.execute("CREATE INDEX ix_etl_decisions_outcome ON public.etl_record_decisions(run_id, attempt_no, outcome)")
    op.execute("GRANT SELECT, INSERT ON public.etl_attempts TO flowwatch_ingestor")
    op.execute("GRANT SELECT, INSERT ON public.etl_record_decisions TO flowwatch_ingestor")


def downgrade() -> None:
    op.execute("DROP TABLE public.etl_record_decisions")
    op.execute("DROP TABLE public.etl_attempts")
