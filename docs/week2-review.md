\# Week 2 Review — Production-Grade Source Ingestion



\## Scope



Week 2 hardened the FlowWatch World Bank ingestion boundary.



The week covered:



\- HTTP reliability;

\- explicit pagination;

\- ingestion-run state;

\- page manifests and SHA-256 checksums;

\- source validation;

\- quarantine semantics;

\- deterministic failure injection;

\- CI enforcement.



\## Day 8 — Hardened HTTP client



FlowWatch introduced a reusable World Bank HTTP client with:



\- connect/read timeouts;

\- bounded retries;

\- exponential backoff;

\- structured request metadata;

\- response validation;

\- structured failures.



Transient failures retry only inside the configured retry budget.



Retry exhaustion fails closed.



\## Day 9 — Pagination contract



World Bank `top` / `skip` pagination became an explicit iterator contract.



Each page carries:



\- page number;

\- offset;

\- record count;

\- total source count;

\- request metadata;

\- exact response bytes.



Page metadata is checked against request metadata.



\## Day 10 — Ingestion run model



Ingestion runs now preserve:



\- run ID;

\- source identifiers;

\- start/completion timestamps;

\- status;

\- page/row progress;

\- code version;

\- failure reason;

\- resume lineage.



Failed runs remain queryable.



\## Day 11 — Page manifests and checksums



Every source page can be identified by a SHA-256 checksum calculated from its

exact raw response bytes.



The page manifest preserves source-page provenance before transformation.



\## Day 12 — Validation and quarantine



Pydantic source models validate World Bank source records before business

transformation.



Malformed values are represented as rejected-record envelopes with

machine-readable reason codes.



Invalid records are quarantined rather than silently coerced.



\## Day 13 — Failure injection



Fault injection covers:



\- connection reset;

\- malformed JSON;

\- missing required fields;

\- duplicate pages;

\- partial write failures.



The failure policy is:



```text

transient transport fault

&#x20;   -> bounded retry

&#x20;   -> fail closed on exhaustion



record-level schema fault

&#x20;   -> quarantine



malformed response

&#x20;   -> fail closed



duplicate page

&#x20;   -> reject



persistence failure

&#x20;   -> rollback

&#x20;   -> fail closed

