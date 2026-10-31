-- Run in isolated flowwatch_day28_gate ONLY. Never mutate production.
SELECT run_id, attempt_no, source_pages, fetched, raw_stored,
       accepted, rejected, inserted, updated, unchanged, ignored, status
FROM public.etl_attempts ORDER BY run_id, attempt_no;

SELECT run_id, attempt_no, count(*) AS decisions,
       count(*) FILTER (WHERE outcome='REJECTED') AS rejected,
       count(*) FILTER (WHERE outcome <> 'REJECTED') AS accepted
FROM public.etl_record_decisions GROUP BY run_id, attempt_no
ORDER BY run_id, attempt_no;

SELECT count(*) AS invalid_attempts FROM public.etl_attempts
WHERE fetched <> raw_stored OR fetched <> accepted + rejected
   OR accepted <> inserted + updated + unchanged + ignored;

SELECT count(*) AS orphan_decisions
FROM public.etl_record_decisions d
LEFT JOIN public.credit_snapshots s ON s.credit_snapshot_id=d.snapshot_id
LEFT JOIN public.source_quarantine q ON q.quarantine_id=d.quarantine_id
WHERE (d.outcome <> 'REJECTED' AND s.credit_snapshot_id IS NULL)
   OR (d.outcome='REJECTED' AND q.quarantine_id IS NULL);

SELECT count(*) AS temporal_duplicate_groups FROM (
    SELECT credit_id, end_of_period FROM public.credit_snapshots
    GROUP BY credit_id, end_of_period HAVING count(*) > 1
) d;
