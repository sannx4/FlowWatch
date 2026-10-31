# Day 33 — Historical canonical publication: safety and research contract

## Scope

Reads verified, independently fetched MongoDB pages for a **completed** Day29–32
historical run. Writes only to PostgreSQL `flowwatch_historical_gate`, as
`flowwatch_ingestor`, using the pre-existing Day23 exact-decimal canonical
entity loader and Day25 quarantine helper. No upstream HTTP requests.

## Data and publication boundaries

- The primary application database `flowwatch` is **never a permitted target**.
- The MongoDB source database `flowwatch_historical_gate_raw` is **read-only**.
- Every raw MongoDB page is checked against a PostgreSQL Day29 checkpoint.
- SHA-256, page size, source keys, record positions and JSON payloads are checked.
- Raw JSON is parsed once into normal values and once into `Decimal` values,
  preserving original base-10 numeric literals without repeated page parsing.
- Day23 canonical upserts use `snapshot_policy='reject'` (no unreviewed changes).
- A single DB transaction covers entity writes, quarantine events, immutable
  observation decisions, and publication summary; failures roll back all.
- A per-record savepoint prevents a partially inserted entity graph from being
  retained after a rejected source record.
- Repeated `(credit_number, end_of_period)` observations are counted separately
  from distinct temporal snapshots; source observations are never falsely
  claimed to be statistically independent.
- `--apply` is mandatory for any canonical write. `--allow-quarantine` must be
  additionally supplied to permit partial accepted-data publication.
- Replaying a committed source-run publication validates its immutable decision
  ledger and returns `PASS_EXISTING_CANONICAL_PUBLICATION`, not new writes.
- This bounded batch loader intentionally refuses more than 10,000 raw records;
  full-source streaming and temporal research readiness are a later milestone.

## Known limitations

1. The upstream source cannot guarantee a point-in-time snapshot across pages.
2. Credit-level mutable descriptions may reflect the final observation processed
   during a run; no separate SCD Type 2 implementation is claimed here.
3. A historical source with mixed or conflicting canonical values may require
   manual correction review and explicit quarantine authorization.
4. No forecasting, survival labels, row-wise independence, dbt models or Parquet
   artifacts are produced by this Day33 release.
5. This release uses the existing Day23 per-record loader, not the Day24 bulk
   loader. Performance of a complete 1.6M-row backfill is unverified.
6. `credit_snapshots` is a canonical latest-value table keyed by credit+period;
   source-level observations are preserved in immutable publication decisions.
