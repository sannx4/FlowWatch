-- FlowWatch Day 24: READ-ONLY diagnostic queries.
-- Connect specifically to flowwatch_day24_gate, NEVER the main flowwatch DB.
-- The benchmark uses rollback; snapshots remain at zero after all trials.
SELECT current_database() AS database_name, current_user AS active_role,
       (SELECT COUNT(*) FROM public.credit_snapshots) AS committed_snapshot_count;

-- Unique temporal identities must be enforced by the canonical index/constraint.
SELECT COUNT(*) AS snapshot_rows,
       COUNT(DISTINCT (credit_id, end_of_period)) AS distinct_credit_periods
FROM public.credit_snapshots;

-- Null/missing lineage in any existing canonical snapshots.
SELECT COUNT(*) AS snapshots_missing_lineage
FROM public.credit_snapshots
WHERE ingestion_run_id IS NULL OR source_checksum IS NULL
   OR source_record_key IS NULL;

-- PostgreSQL confirms the actual uniqueness constraint.
SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.credit_snapshots'::regclass
  AND contype = 'u'
ORDER BY conname;

-- Numeric column precision/scale contract used by Day-22 checks and COPY.
SELECT column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'credit_snapshots'
  AND data_type = 'numeric'
ORDER BY ordinal_position;

-- Active temp stage only exists DURING each transaction and is dropped on commit.
-- The runtime benchmark's JSON report contains actual pre-rollback counts,
-- value/lineage parity results, trial timings and 3-pass replay proof.
