\# FlowWatch Schema Decision Log



\## Day 5 — Production DDL and Migration Baseline



\### PostgreSQL runtime



PostgreSQL is run through Docker Compose on a dedicated FlowWatch network with a named persistent volume and health check.



Local host exposure uses `127.0.0.1` rather than all interfaces.



\### Credentials



The database uses a non-default project-specific user.



Real credentials are stored only in `.env`.



`.env.example` documents required variables without containing real secrets.



\### Schema authority



Alembic migrations are the authoritative mechanism for changing the production schema.



SQLAlchemy metadata provides machine-readable schema definitions for migration generation and application code.



`sql/operational/schema.sql` is retained as an inspectable DDL artifact rather than an independent migration mechanism.



\### Primary and natural keys



Internal surrogate keys remain relational primary keys.



World Bank identifiers remain UNIQUE natural/business keys.



\### Temporal identity



A credit snapshot is uniquely identified by:



`(credit\_id, end\_of\_period)`



This preserves historical state and remains compatible with future point-in-time queries.



\### Foreign-key deletion policy



Canonical relationships use `ON DELETE RESTRICT`.



Historical finance records must not disappear silently through cascading entity deletion.



\### Monetary values



Financial amounts use exact PostgreSQL `NUMERIC` types rather than floating-point types.



This avoids binary floating-point representation error in canonical monetary storage.



\### Nullability



Identity fields and required relationships are non-null.



Lifecycle and financial attributes remain nullable where the source may legitimately omit them.



Business assumptions that have not yet been validated against the wider historical dataset are not enforced as hard database constraints.



\### Lineage



`ingestion\_run\_id`, `source\_checksum`, and `source\_record\_key` remain reserved in `credit\_snapshots`.



`ingestion\_run\_id` does not yet have a foreign key because the `ingestion\_runs` model is introduced on Day 10.



\### Integrity checks



Day-5 checks enforce structural invariants such as:



\- nonblank business identifiers;

\- unique snapshot identity;

\- valid SHA-256 checksum shape;

\- nonnegative service-charge rate.



More domain-specific data-quality rules are intentionally deferred until wider source validation.

