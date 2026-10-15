\# MongoDB Raw-Lineage Model



\## Purpose



MongoDB is the searchable recent raw-lineage store for FlowWatch.



It preserves source material before business transformation so later

canonical rows, validation failures and research datasets can eventually

trace back to the exact ingestion run and raw source object.



MongoDB is not the canonical analytical source of truth. PostgreSQL owns

canonical normalized data.



MongoDB is also not yet the permanent archive. The durable historical raw

archive is introduced later in the lake phase.



\## Day-15 scope



Day 15 defines three collections:



```text

ingestion\_runs

raw\_pages

raw\_records

