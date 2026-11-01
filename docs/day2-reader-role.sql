-- Execute in flowwatch_historical_gate as an authorized DBA, not the primary DB.
-- Separate the role's password creation from this tracked script.
-- If role exists, skip CREATE ROLE after checking privileges.
DO $$
BEGIN
 IF current_database() <> 'flowwatch_historical_gate' THEN
  RAISE EXCEPTION 'Refusing to touch unexpected database';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='flowwatch_api_reader') THEN
  CREATE ROLE flowwatch_api_reader LOGIN;
 END IF;
END $$;
GRANT CONNECT ON DATABASE flowwatch_historical_gate TO flowwatch_api_reader;
GRANT USAGE ON SCHEMA fw_analytics TO flowwatch_api_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA fw_analytics TO flowwatch_api_reader;
-- ALTER ROLE flowwatch_api_reader PASSWORD '<ENTER INTERACTIVELY; DO NOT COMMIT>';
-- With psql: \password flowwatch_api_reader
-- Never grant write privileges; the API also uses SET TRANSACTION READ ONLY.
