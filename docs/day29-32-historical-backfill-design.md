# Day 29–32 design: paginated source capture and durable raw-only recovery

**Identity:** API dataset ID/resource ID + explicit run UUID + requested `top/skip`.
Page source checksum is SHA-256 over *exact response bytes*, not JSON
reserialization. A run's source total, page size and page cap are immutable.

**Request contract:** all pages must have identical source-reported total count
and exact expected page cardinality (full pages except the terminal page).
Zero/short interior pages fail closed. The pre-existing WorldBankClient handles
HTTP retry and response validation. Bounded worker fan-out: max 4 workers;
at most 2×workers outstanding futures, always commit in page order.

**Durability sequence:** (1) retrieve source bytes → (2) construct source
lineage envelopes → (3) persist Mongo raw page and all records idempotently →
(4) independently re-read/verify raw data → (5) commit PG checkpoint.
A checkpoint without independently readable Mongo raw causes release failure.
If a page exists in Mongo but not in PG, reconstruct from raw bytes and commit
the missing checkpoint without contacting the World Bank API.

**Crash matrix:** before Mongo page = fetch again; after Mongo page but during
record inserts = reconstruct missing raw records from the stored checksum-
verified page; after Mongo complete but before PG checkpoint = commit PG from
Mongo; after PG checkpoint = verify and skip. Run-wide advisory lock guards
against concurrent writers using the same UUID. PG checkpoint page rows are
insert-only to ingestion role.

**Scientific validity:** source pagination may not be consistent without a
server-side snapshot token. Identical `total_count` is necessary but not
sufficient for identity continuity. Full dataset characterization must include
independent temporal-key duplicate and coverage audits, as well as source
citation, event prevalence and effective sample size.

**Safety:** the production/core database is untouched. This stage does not
claim to have loaded canonical snapshots or created the dbt warehouse.
