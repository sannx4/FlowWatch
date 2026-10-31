"""Day33: isolated source-observation canonical publication evidence.

Revision ID: d33c00000001
Revises: d29b00000001
"""
from __future__ import annotations

from alembic import op

revision = "d33c00000001"
down_revision = "d29b00000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.historical_canonical_publications (
            run_id uuid PRIMARY KEY REFERENCES public.historical_backfill_runs(run_id)
                ON DELETE RESTRICT,
            source_pages integer NOT NULL CHECK (source_pages > 0),
            source_records integer NOT NULL CHECK (source_records > 0),
            accepted integer NOT NULL CHECK (accepted >= 0),
            rejected integer NOT NULL CHECK (rejected >= 0),
            inserted integer NOT NULL CHECK (inserted >= 0),
            updated integer NOT NULL CHECK (updated >= 0),
            unchanged integer NOT NULL CHECK (unchanged >= 0),
            ignored integer NOT NULL CHECK (ignored >= 0),
            publication_status text NOT NULL CHECK (publication_status = 'PASS'),
            parser_version text NOT NULL,
            completed_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_hist_publication_partition CHECK (
                source_records = accepted + rejected AND
                accepted = inserted + updated + unchanged + ignored
            )
        )
    """)
    op.execute("""
        CREATE TABLE public.historical_canonical_decisions (
            run_id uuid NOT NULL REFERENCES public.historical_canonical_publications(run_id)
                ON DELETE RESTRICT,
            source_record_key text NOT NULL CHECK (btrim(source_record_key) <> ''),
            source_checksum char(64) NOT NULL,
            outcome text NOT NULL CHECK (
                outcome IN ('INSERTED','UPDATED','UNCHANGED','IGNORED','REJECTED')
            ),
            credit_snapshot_id bigint REFERENCES public.credit_snapshots(credit_snapshot_id)
                ON DELETE RESTRICT,
            quarantine_id bigint REFERENCES public.source_quarantine(quarantine_id)
                ON DELETE RESTRICT,
            recorded_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, source_record_key),
            CONSTRAINT ck_hist_decision_target CHECK (
                (outcome = 'REJECTED' AND quarantine_id IS NOT NULL AND credit_snapshot_id IS NULL)
                OR (outcome <> 'REJECTED' AND quarantine_id IS NULL AND credit_snapshot_id IS NOT NULL)
            )
        )
    """)
    op.execute("CREATE INDEX ix_historical_canonical_decisions_outcome ON public.historical_canonical_decisions(run_id, outcome)")
    op.execute("GRANT SELECT, INSERT ON public.historical_canonical_publications TO flowwatch_ingestor")
    op.execute("GRANT SELECT, INSERT ON public.historical_canonical_decisions TO flowwatch_ingestor")
    op.execute("GRANT SELECT, INSERT, UPDATE ON public.regions, public.countries, public.projects, public.credits, public.credit_snapshots, public.source_quarantine TO flowwatch_ingestor")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO flowwatch_ingestor")


def downgrade() -> None:
    op.execute("DROP TABLE public.historical_canonical_decisions")
    op.execute("DROP TABLE public.historical_canonical_publications")
