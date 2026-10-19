-- Read-only SQL evidence: execute ONLY against flowwatch_day23_gate.
-- psql -X -v ON_ERROR_STOP=1 -d flowwatch_day23_gate -f sql/day23_entity_evidence.sql
SELECT current_database() AS database_name;
SELECT 'regions' AS entity, count(*) AS total FROM public.regions
UNION ALL SELECT 'countries', count(*) FROM public.countries
UNION ALL SELECT 'projects', count(*) FROM public.projects
UNION ALL SELECT 'credits', count(*) FROM public.credits
UNION ALL SELECT 'credit_snapshots', count(*) FROM public.credit_snapshots;
SELECT c.credit_number, s.end_of_period, count(*) AS duplicate_count
FROM public.credit_snapshots AS s
JOIN public.credits AS c ON c.credit_id = s.credit_id
GROUP BY c.credit_number, s.end_of_period
HAVING count(*) > 1;
SELECT count(*) AS missing_source_lineage
FROM public.credit_snapshots
WHERE source_record_key IS NULL OR source_checksum IS NULL OR ingestion_run_id IS NULL;
