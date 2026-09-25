# ADR-001: Operational Data Model

## Status

Accepted for initial implementation.

## Context

The World Bank historical credit dataset contains repeated observations of the same credit across different reporting periods.

FlowWatch needs an operational data model that can:

* preserve historical credit states;
* support relational integrity;
* support idempotent ingestion;
* retain World Bank source identifiers;
* support source lineage;
* support future point-in-time and as-of queries;
* avoid overwriting historical values that may later be required for forecasting or research.

A single wide table shaped exactly like the source JSON would be simpler to ingest, but it would mix stable entity information with time-varying observations.

This would make temporal reasoning, deduplication, lineage, and later ML feature construction more difficult.

## Decision

FlowWatch will use a normalized operational model consisting of:

```text
regions
  -> countries
      -> projects
          -> credits
              -> credit_snapshots
```

`regions`, `countries`, `projects`, and `credits` represent business entities.

`credit_snapshots` represents the observed state of a credit at a particular reporting period.

The preliminary temporal identity of a source observation is:

```text
(credit_number, end_of_period)
```

Inside the relational database this becomes:

```text
(credit_id, end_of_period)
```

and will be protected with a UNIQUE constraint.

## Key Strategy

World Bank identifiers will be retained as natural/business keys.

Examples:

```text
country_code
project_id
credit_number
```

Internal surrogate keys will be used as relational primary keys.

Examples:

```text
country_id
project_pk
credit_id
credit_snapshot_id
```

The natural identifiers will still receive UNIQUE constraints where appropriate.

This allows FlowWatch to preserve source identity while using stable internal keys for relationships.

## Temporal Attribute Policy

Attributes that can change between reporting periods must not automatically be stored as static entity attributes.

Examples include:

* `credit_status`;
* disbursed amount;
* undisbursed amount;
* cancelled amount;
* repayment balances.

These values belong in `credit_snapshots`.

Some attributes currently placed in `credits`, especially date fields that appear to describe the latest known state, remain provisional.

Their temporal stability must be verified against a larger historical sample before the schema is treated as final.

## Lineage Decision

Each canonical snapshot reserves the following audit fields:

```text
ingestion_run_id
source_checksum
source_record_key
```

These fields will later connect the canonical PostgreSQL record to the ingestion run and exact raw source object.

The detailed ingestion-run and raw-lineage implementation is deferred to later project phases.

## Operational vs Analytical Responsibility

The operational PostgreSQL schema is optimized for:

* correctness;
* integrity;
* temporal history;
* idempotent loading;
* traceability.

It is not intended to be the primary analytical model.

Later warehouse models may deliberately denormalize the operational data for:

* dashboard queries;
* aggregations;
* forecasting;
* feature engineering;
* reporting.

This keeps operational correctness separate from analytical convenience.

## Alternatives Considered

### Alternative 1 — Single wide source-shaped table

Store every World Bank row directly in one table.

Advantages:

* simple initial ingestion;
* minimal transformation;
* fewer joins.

Disadvantages:

* duplicates entity information across reporting periods;
* mixes persistent entities with temporal state;
* makes entity-level constraints harder to enforce;
* makes later schema evolution and lineage less clear.

Decision: rejected as the canonical operational model.

### Alternative 2 — Natural keys as primary keys everywhere

Use identifiers such as `credit_number` and `project_id` directly as primary and foreign keys.

Advantages:

* source identity is immediately visible;
* fewer internal identifiers.

Disadvantages:

* tightly couples relational structure to external identifier formats;
* produces wider foreign keys;
* makes future source-key changes harder to isolate.

Decision: retain natural keys as UNIQUE business identifiers but use surrogate internal primary keys.

### Alternative 3 — Store current credit state only

Keep one row per credit and update it when a new reporting period arrives.

Advantages:

* very simple current-state queries;
* small table size.

Disadvantages:

* destroys historical state;
* prevents reliable as-of queries;
* creates severe risk for future point-in-time ML evaluation;
* makes historical reproduction impossible.

Decision: rejected.

## Consequences

### Positive consequences

* Historical credit states are preserved.
* Point-in-time queries become possible.
* Source business identifiers remain available.
* Relational integrity can be enforced.
* Repeated ingestion can be made idempotent.
* Future feature generation can respect historical information boundaries.
* Canonical records can later be traced to raw source records.

### Negative consequences

* The schema requires more joins than a single flat table.
* Transformation and loading logic becomes more complex.
* Entity-versus-temporal attribute classification must be tested carefully.
* Analytical workloads will eventually require a separate warehouse layer.

## Validation Required

The initial sample is not sufficient to prove that every apparently static source attribute is actually stable over the entire historical dataset.

Before the operational schema is considered final, wider historical profiling must verify:

* whether `credit_status` varies across snapshots;
* whether date fields such as effective or closed dates change retrospectively;
* whether project/country relationships remain stable;
* whether `(credit_number, end_of_period)` is unique across broader non-adjacent source pages;
* whether fields currently classified as entity attributes actually need temporal history.

These checks will be performed during later source-validation work before the production schema is frozen.
