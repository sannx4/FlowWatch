# Day 25 — Durable quarantine / replay research contract

## System boundary

MongoDB `raw_pages`/`raw_records` remain immutable. PostgreSQL `source_quarantine` is the durable decision ledger. A quarantine row preserves source run UUID, record key, checksum, page number, page offset and record index, the specific rule, JSON-safe offending diagnostic, failed parser version and immutable first-seen timestamp. A corrected replay fetches the matching raw record/page, verifies SHA-256 and index identity, rehydrates financial decimals, and inserts canonical data with the Day-23 dependency-safe loader. No upstream HTTP fetch is permitted.

## Reproduction

1. Create an isolated database named `flowwatch_day25_gate` from `flowwatch` and clear its snapshots only.
2. Apply `sql/operational/day25_quarantine.sql` to the isolated database as `flowwatch_owner`.
3. Run `python -m scripts.day25_quarantine_gate --phase reject --limit 100`; inspect the committed `PENDING` row.
4. Start a distinct Python process: `python -m scripts.day25_replay_quarantine` and inspect `RESOLVED` output.
5. Start the replay command again to prove `ALREADY_RESOLVED` is no-op.
6. Run `python -m scripts.day25_quarantine_gate --phase verify`, compare quarantine and curated checksum/source key and assert zero duplicate `(credit_id, end_of_period)`.
7. Run `python -m pytest -q tests/unit/test_day25_quarantine.py` and the full test suite.

## Scientific validity threat and decision

**Threat:** rejecting valid source records because financial JSON numbers were decoded to BSON/Python binary floats would disproportionately exclude particular credit periods or amount categories. Financial forecasting targets, reporting gaps, effective sample size, and 3-/6-/12-month maturity availability could change as a function of a parser defect. Treating such rejections as genuinely missing data biases missingness characterisation, residual dependence, calibration support and tail coverage.

**Policy:** fail closed, record the exact rejection and immutable source identity, do not coerce float to Decimal, and restore from checksum-verified original page bytes. Mark a row `RESOLVED` only in the same transaction that commits the curated snapshot. Keep failed attempts, parser versions, and human-readable remediation error. Never mutate MongoDB evidence to make a parser pass.

**Scope of proof:** the gate deliberately selects a real stored World Bank source observation that suffers a *legacy storage-format parsing incompatibility*. The source observation is not invalid. This is a controlled parser-fix experiment; it must never be presented as evidence that the World Bank published malformed finance data. `PENDING` is a processing status, not a quality label. Once an issue is resolved, use the recovered canonical observation in future science with provenance rather than permanently dropping it.

**Reproducible test references:** `tests/unit/test_day25_quarantine.py`, `scripts/day25_quarantine_gate.py`, `scripts/day25_replay_quarantine.py`, `reports/day25-quarantine-gate.json` (generated at run time).

## Engineering limitations

- This is an isolated five-table core demonstration; automated routing from every ingestion entrypoint to quarantine is future pipeline-integration work. Reconciliation semantics are Day 26.
- PostgreSQL stores a compact offending diagnostic, not a duplicated source payload. MongoDB raw retention depends on Day-18 archival policy; absence of a retained raw page blocks replay.
- No repair occurs by editing MongoDB or inventing revised World Bank observations.
- Replay defaults to `snapshot_policy='reject'`, so real upstream financial corrections still require reviewed source precedence (Day 23 open item).
- The workflow assumes a single test writer and persists one selection from the latest run. Production scheduler will require concurrency/retry scheduling and operator approval policies.
- `source_quarantine` uses one row per run/source-key/rule/parser version, not one row per retry; `occurrences` and `retry_count` distinguish the two.
- The isolated database gate creates and later resolves a real source-derived canonical row. It does not roll back the demonstration; never point it to `flowwatch`.
