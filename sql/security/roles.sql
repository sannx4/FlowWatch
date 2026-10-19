
-- FlowWatch Day 21: PostgreSQL least-privilege roles.
--
-- Execute as the existing database administrator.
-- Does not delete rows or recreate application tables.
--
-- Passwords are intentionally excluded from this file.
-- Service credentials must be provisioned separately.
--
-- Target database: flowwatch
-- Target schema: public

BEGIN;

-- =====================================================
-- 1. Create dedicated roles
-- =====================================================

DO $roles$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'flowwatch_schema_owner'
    ) THEN
        CREATE ROLE flowwatch_schema_owner
            NOLOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'flowwatch_migrator'
    ) THEN
        CREATE ROLE flowwatch_migrator
            LOGIN
            INHERIT
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'flowwatch_ingestor'
    ) THEN
        CREATE ROLE flowwatch_ingestor
            LOGIN
            INHERIT
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'flowwatch_api'
    ) THEN
        CREATE ROLE flowwatch_api
            LOGIN
            INHERIT
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION;
    END IF;
END;
$roles$;

-- =====================================================
-- 2. Assign migration ownership privileges
-- =====================================================

GRANT flowwatch_schema_owner
TO flowwatch_migrator;

-- The migration role receives object-owner privileges
-- through membership in flowwatch_schema_owner.
--
-- Neither application role receives this membership.

-- =====================================================
-- 3. Schema access
-- =====================================================

REVOKE CREATE ON SCHEMA public FROM PUBLIC;

REVOKE ALL ON SCHEMA public
FROM flowwatch_ingestor, flowwatch_api;

GRANT USAGE, CREATE ON SCHEMA public
TO flowwatch_schema_owner;

GRANT USAGE ON SCHEMA public
TO flowwatch_migrator,
   flowwatch_ingestor,
   flowwatch_api;

-- =====================================================
-- 4. Transfer application object ownership
-- =====================================================

ALTER TABLE public.alembic_version
OWNER TO flowwatch_schema_owner;

ALTER TABLE public.regions
OWNER TO flowwatch_schema_owner;

ALTER TABLE public.countries
OWNER TO flowwatch_schema_owner;

ALTER TABLE public.projects
OWNER TO flowwatch_schema_owner;

ALTER TABLE public.credits
OWNER TO flowwatch_schema_owner;

ALTER TABLE public.credit_snapshots
OWNER TO flowwatch_schema_owner;

ALTER TABLE public.ingestion_runs
OWNER TO flowwatch_schema_owner;

ALTER TABLE public.raw_page_manifests
OWNER TO flowwatch_schema_owner;

-- PostgreSQL also transfers ownership of sequences
-- owned by columns when the owning table's owner
-- changes.

-- =====================================================
-- 5. Remove unintended application privileges
-- =====================================================

REVOKE ALL ON ALL TABLES IN SCHEMA public
FROM PUBLIC;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA public
FROM PUBLIC;

REVOKE ALL ON ALL TABLES IN SCHEMA public
FROM flowwatch_ingestor, flowwatch_api;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA public
FROM flowwatch_ingestor, flowwatch_api;

-- =====================================================
-- 6. Ingestion privileges
-- =====================================================

-- The current canonical loader uses:
-- INSERT ... ON CONFLICT DO UPDATE ... RETURNING
--
-- Therefore it needs SELECT, INSERT, and UPDATE.

GRANT SELECT, INSERT, UPDATE ON TABLE
    public.regions,
    public.countries,
    public.projects,
    public.credits,
    public.credit_snapshots
TO flowwatch_ingestor;

-- Run tracking and page-manifest maintenance.

GRANT SELECT, INSERT, UPDATE ON TABLE
    public.ingestion_runs,
    public.raw_page_manifests
TO flowwatch_ingestor;

-- Required by SERIAL/sequence-backed primary keys.

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA public
TO flowwatch_ingestor;

-- No DELETE, TRUNCATE, REFERENCES, TRIGGER,
-- object ownership, or schema CREATE grants.

-- =====================================================
-- 7. Read-only API privileges
-- =====================================================

GRANT SELECT ON TABLE
    public.regions,
    public.countries,
    public.projects,
    public.credits,
    public.credit_snapshots
TO flowwatch_api;

-- The API cannot write canonical tables.
-- It cannot read Alembic migration metadata.
-- Additional read access must be granted explicitly.

-- =====================================================
-- 8. Complete
-- =====================================================

COMMIT;

-- Future migrations must explicitly grant privileges
-- on new objects. Do not grant blanket privileges
-- on all future tables.
--
-- Future Alembic sessions should create objects as
-- flowwatch_schema_owner through an authorized
-- SET ROLE configuration.
