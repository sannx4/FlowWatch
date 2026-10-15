\# Day 16 — Idempotent Raw Landing and Lineage Identifiers



\## Objective



Build deterministic raw-source identities, make MongoDB raw landing

idempotent, propagate authoritative lineage identifiers into PostgreSQL,

and prove that a curated snapshot can be traced back to the exact raw

MongoDB record from the same ingestion run.



\---



\## Implementation



Day 16 introduced deterministic source identity at two levels.



\### Page identity



A deterministic `page\_source\_key` is derived from:



\- dataset identifier

\- resource identifier

\- page offset

\- exact source-page SHA-256 checksum



The ingestion run identifier is intentionally excluded from the

deterministic source key.



\### Record identity



A deterministic `source\_record\_key` is derived from:



\- dataset identifier

\- resource identifier

\- deterministic page source key

\- record index

\- canonical record checksum



The canonical record checksum uses deterministic JSON serialization.



\---



\## MongoDB Idempotency Policy



MongoDB uniqueness is enforced by:



```text

(run\_id, page\_source\_key)

(run\_id, source\_record\_key)

