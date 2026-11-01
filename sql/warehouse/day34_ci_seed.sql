-- Synthetic fixture ONLY; execute against ephemeral flowwatch_historical_gate.
-- These values are deliberately small and not copied from World Bank observations.
DO $$ BEGIN
 IF current_database() <> 'flowwatch_historical_gate' THEN
   RAISE EXCEPTION 'Refusing seed in non-isolated database %', current_database();
 END IF;
END $$;
INSERT INTO public.regions (region_name) VALUES ('CI TEST REGION');
INSERT INTO public.countries (country_code, country_name, region_id)
SELECT 'CI', 'CI TEST COUNTRY', region_id FROM public.regions WHERE region_name='CI TEST REGION';
INSERT INTO public.projects (project_id, project_name, country_id)
SELECT 'CI-PROJ-001', 'CI TEST PROJECT', country_id FROM public.countries WHERE country_code='CI';
INSERT INTO public.credits (credit_number, project_pk, borrower, currency_of_commitment)
SELECT 'CI-CREDIT-001', project_pk, 'CI TEST', 'USD' FROM public.projects
WHERE project_id='CI-PROJ-001';
INSERT INTO public.historical_backfill_runs
(run_id, dataset_id, resource_id, page_size, max_pages, observed_total, status)
VALUES ('00000000-0000-4000-8000-000000000034', 'ci_test_dataset', 'ci_test_resource',
        3, 1, 3, 'COMPLETE');
INSERT INTO public.credit_snapshots
(credit_id, end_of_period, credit_status, original_principal_amount_usd,
 disbursed_amount_usd, undisbursed_amount_usd, repaid_to_ida_usd,
 borrowers_obligation_usd, source_checksum, source_record_key, ingestion_run_id)
SELECT credit_id, v.period, 'Disbursing', 1000.00,
       v.disbursed, v.undisbursed, v.repaid, 1000.00 - v.repaid,
       repeat('a', 64), v.record_key, '00000000-0000-4000-8000-000000000034'::uuid
FROM public.credits,
(VALUES
 ('2024-04-30'::date, 100.00::numeric, 900.00::numeric, 10.00::numeric, 'ci-record-1'),
 ('2024-05-31'::date, 250.00::numeric, 750.00::numeric, 30.00::numeric, 'ci-record-2'),
 ('2024-07-31'::date, 300.00::numeric, 700.00::numeric, 40.00::numeric, 'ci-record-3')
) AS v(period, disbursed, undisbursed, repaid, record_key)
WHERE credit_number='CI-CREDIT-001';
INSERT INTO public.historical_canonical_publications
(run_id, source_pages, source_records, accepted, rejected, inserted, updated,
 unchanged, ignored, publication_status, parser_version)
VALUES ('00000000-0000-4000-8000-000000000034', 1, 3, 3, 0, 3, 0, 0, 0, 'PASS', 'ci-test-v1');
INSERT INTO public.historical_canonical_decisions
(run_id, source_record_key, source_checksum, outcome, credit_snapshot_id)
SELECT '00000000-0000-4000-8000-000000000034'::uuid, source_record_key,
       source_checksum, 'INSERTED', credit_snapshot_id
FROM public.credit_snapshots;
