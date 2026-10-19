
-- FlowWatch Day 21
-- PostgreSQL least-privilege integration tests.
--
-- Run as the existing database administrator.
-- Tests execute statements under restricted roles.
-- All operations occur inside a rolled-back transaction.
--
-- No canonical records are inserted, updated or deleted.

BEGIN;

-- ============================================
-- TEST 1: Migration role can manage schema
-- ============================================

SET LOCAL ROLE flowwatch_migrator;

CREATE TABLE public.flowwatch_day21_security_probe (
    id INTEGER
);

ALTER TABLE public.flowwatch_day21_security_probe
ADD COLUMN description TEXT;

-- ============================================
-- TEST 2: Ingestion role can access data
-- ============================================

SET LOCAL ROLE flowwatch_ingestor;

SELECT COUNT(*) AS ingestion_can_read
FROM public.credit_snapshots;

-- Zero-row statements test write privileges
-- without changing actual application records.

INSERT INTO public.regions (region_name)
SELECT 'FLOWWATCH_DAY21_PROBE'
WHERE FALSE;

UPDATE public.regions
SET region_name = region_name
WHERE FALSE;

-- ============================================
-- TEST 3: Ingestion role cannot change schema
-- ============================================

DO $$
DECLARE
    denied BOOLEAN := FALSE;
BEGIN
    BEGIN
        EXECUTE
            'CREATE TABLE public.flowwatch_forbidden_table
             (id INTEGER)';
    EXCEPTION
        WHEN insufficient_privilege THEN
            denied := TRUE;
    END;

    IF NOT denied THEN
        RAISE EXCEPTION
            'FAIL: Ingestion role can create tables';
    END IF;

    RAISE NOTICE
        'PASS: Ingestion role cannot create tables';

    denied := FALSE;

    BEGIN
        EXECUTE
            'ALTER TABLE
             public.flowwatch_day21_security_probe
             ADD COLUMN forbidden_column INTEGER';
    EXCEPTION
        WHEN insufficient_privilege THEN
            denied := TRUE;
    END;

    IF NOT denied THEN
        RAISE EXCEPTION
            'FAIL: Ingestion role can alter tables';
    END IF;

    RAISE NOTICE
        'PASS: Ingestion role cannot alter tables';
END;
$$;

-- ============================================
-- TEST 4: API role can read canonical data
-- ============================================

SET LOCAL ROLE flowwatch_api;

SELECT COUNT(*) AS api_can_read
FROM public.credit_snapshots;

-- ============================================
-- TEST 5: API role cannot modify data
-- ============================================

DO $$
DECLARE
    statement TEXT;
    denied BOOLEAN;
BEGIN
    FOREACH statement IN ARRAY ARRAY[
        'INSERT INTO public.regions (region_name)
         SELECT ''FLOWWATCH_FORBIDDEN'' WHERE FALSE',

        'UPDATE public.regions
         SET region_name = region_name WHERE FALSE',

        'DELETE FROM public.regions WHERE FALSE'
    ]
    LOOP
        denied := FALSE;

        BEGIN
            EXECUTE statement;
        EXCEPTION
            WHEN insufficient_privilege THEN
                denied := TRUE;
        END;

        IF NOT denied THEN
            RAISE EXCEPTION
                'FAIL: API modification allowed: %',
                statement;
        END IF;

        RAISE NOTICE
            'PASS: API modification denied';
    END LOOP;
END;
$$;

-- ============================================
-- TEST 6: Roll back test transaction
-- ============================================

ROLLBACK;

-- All tests must pass.
-- No test tables or row modifications persist.
