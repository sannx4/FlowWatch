FlowWatch

Development-finance observability and temporal analytics over World Bank IDA financing data.
A data engineering project focused on reliable ingestion, historical modeling, analytical warehousing, database systems, and explainable financial metrics.

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PostgreSQL-15+-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/MongoDB-Raw%20Layer-47A248?logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/Hadoop%20%2F%20Hive-Analytics-FFCC00?logo=apachehadoop&logoColor=black" alt="Hadoop and Hive">
  <img src="https://img.shields.io/badge/Docker-Reproducible%20Dev-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/GitHub%20Actions-CI-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions">
</p>

Overview

FlowWatch turns a large historical World Bank financing dataset into a structured analytics platform for answering questions such as:

How much financing has been committed and disbursed over time?

Which countries, projects, or credits account for the largest movements?

How quickly is financing being disbursed?

Which credits show extended periods of stagnation?

How do relational, document, and distributed analytical systems behave on the same workload?

The project is deliberately broader than a visualization dashboard.

It is designed around the complete data lifecycle:

Source API
   ↓
Ingestion
   ↓
Raw Preservation
   ↓
Validation & Transformation
   ↓
Normalized Operational Model
   ↓
Analytical Warehouse
   ↓
Metrics & Query Layer
   ↓
Application API
   ↓
Interactive Dashboard

The emphasis is on data correctness, reproducibility, temporal modeling, database design, query performance, and system-level engineering decisions.

Project Status

Current phase: Planning / bootstrap

FlowWatch is being developed as a staged engineering project through December 2026.

Architecture, product requirements, technical requirements, data modeling, UI/UX, API design, and implementation planning are documented before the full system is built.

This repository will evolve incrementally as each layer is implemented and validated.

Engineering Scope

Area

Scope

Data ingestion

Paginated World Bank API extraction, retries, checkpoints, resumability

Raw data

Immutable JSON archive and MongoDB document representation

Transformation

Type normalization, validation, deduplication, rejected-record handling

Operational database

PostgreSQL, normalized 3NF schema, PK/FK integrity

Temporal model

Historical credit snapshots ordered by reporting period

Analytics warehouse

Fact/dimension model for OLAP workloads

Distributed analytics

HDFS/Hive experiments over large analytical datasets

Metrics

Disbursement ratio, repayment %, cancellation %, velocity, stagnation

Serving layer

Versioned analytics API

Visualization

Interactive country, project, credit, comparison and alert views

Performance

Indexing, EXPLAIN ANALYZE, partitioning experiments, benchmarks

Reliability

Logging, idempotency, automated tests, CI

Reproducibility

Docker-based local environment and documented setup

System Architecture

flowchart LR
    A[World Bank Data API]

    subgraph INGESTION[Ingestion Layer]
        B[Fetcher]
        C[Checkpoint / Retry]
        D[Validation & Transformation]
    end

    subgraph RAW[Raw Layer]
        E[Raw JSON Archive]
        F[(MongoDB)]
    end

    subgraph RELATIONAL[Relational Layer]
        G[(PostgreSQL Operational DB)]
        H[(Analytical Warehouse)]
    end

    subgraph BIGDATA[Distributed Analytics]
        I[(HDFS)]
        J[(Hive)]
    end

    subgraph SERVING[Serving Layer]
        K[Analytics API]
        L[Interactive Dashboard]
    end

    subgraph QUALITY[Engineering]
        M[Tests]
        N[Benchmarks]
        O[CI/CD]
    end

    A --> B
    B --> C
    C --> E
    C --> D
    E --> F
    D --> G
    G --> H
    E --> I
    I --> J
    G --> K
    H --> K
    K --> L

    G --> N
    F --> N
    J --> N

    M --> O

Architectural intent

Each storage technology has a specific responsibility.

PostgreSQL is the canonical structured store for cleaned relational data.

MongoDB preserves a document-oriented representation and supports NoSQL comparison experiments.

HDFS/Hive provide a distributed analytical path for large aggregation workloads.

The warehouse separates analytical query patterns from the normalized operational schema.

The API is the contract between analytics logic and the user interface.

The dashboard never depends directly on database internals.

This prevents the project from becoming a collection of unrelated technologies.

Data Model

The operational model is centered around financing history:

erDiagram
    REGION ||--o{ COUNTRY : contains
    COUNTRY ||--o{ PROJECT : owns
    PROJECT ||--o{ CREDIT : contains
    CREDIT ||--o{ CREDIT_SNAPSHOT : records

    REGION {
        bigint region_id PK
        string name
    }

    COUNTRY {
        bigint country_id PK
        bigint region_id FK
        string name
    }

    PROJECT {
        string project_id PK
        bigint country_id FK
        string name
    }

    CREDIT {
        string credit_number PK
        string project_id FK
        string borrower
        numeric original_commitment
        date approval_date
        string status
    }

    CREDIT_SNAPSHOT {
        bigint snapshot_id PK
        string credit_number FK
        date end_of_period
        numeric disbursed
        numeric undisbursed
        numeric repaid
        numeric cancelled
    }

A snapshot-based model is important because FlowWatch is interested not only in the latest state of a credit, but also in how that state changes through time.

Analytical Model

The warehouse follows a star-schema design:

                   dim_date
                      │
dim_country ─── fact_finance_snapshot ─── dim_project
                      │
                  dim_credit

The fact table stores measurable financing values at a credit/reporting-period grain.

Example analytical operations:

total disbursement by region and year;

cumulative financing by project;

month-over-month disbursement movement;

cancellation rates;

repayment progression;

stagnant-credit identification;

roll-up and drill-down across country/project/credit dimensions.

Core Metrics

Disbursement Ratio

disbursed_amount / original_commitment

Measures how much of the committed amount has been disbursed.

Disbursement Velocity

current_disbursed - previous_disbursed

Measures movement between consecutive reporting snapshots.

Cancellation Percentage

cancelled_amount / original_commitment

Stagnation

A credit is considered stagnant when its disbursed amount remains unchanged across a configured number of consecutive observed reporting periods.

Missing observations are handled separately and are not automatically classified as stagnation.

Reliability Design

A production-quality ingestion pipeline cannot assume that a 1M+ record extraction completes perfectly in one run.

FlowWatch therefore plans for:

explicit HTTP timeouts;

bounded retries with exponential backoff;

page-level checkpoints;

resumable ingestion;

immutable raw payload storage;

idempotent curated loads;

batch writes;

rejected-record quarantine;

ingestion run metadata;

reconciliation between raw and curated layers.

The goal is simple:

A failed run should be recoverable without rebuilding the entire system or silently corrupting the dataset.

Data Quality

Core invariants include:

snapshot.credit_number → existing credit

credit.project_id → existing project

project.country_id → existing country

Additional checks include:

required identifier validation;

native numeric/date conversion;

snapshot uniqueness;

controlled null handling;

malformed-record quarantine;

source-to-destination row-count reconciliation;

aggregate reconciliation on selected measures.

Financial amounts use exact numeric database types rather than floating-point values.

API Design

The application-facing API is planned under:

/api/v1

Representative resources:

GET /api/v1/overview
GET /api/v1/countries
GET /api/v1/countries/{country_id}
GET /api/v1/projects
GET /api/v1/projects/{project_id}
GET /api/v1/credits/{credit_number}
GET /api/v1/credits/{credit_number}/timeline
GET /api/v1/analytics/stagnation
GET /api/v1/analytics/disbursement
GET /api/v1/health

API responsibilities include:

input validation;

filtering;

sorting;

pagination;

stable metric definitions;

bounded analytical queries;

consistent error contracts;

OpenAPI documentation.

The frontend should not send raw SQL or know database implementation details.

Dashboard

The planned product interface is structured around analytical workflows rather than disconnected charts.

Overview

High-level financing KPIs, trends, major countries/projects, and system freshness.

Countries & Regions

Regional comparison, country ranking, aggregate financing movement.

Project Explorer

Search, filter, sort, and inspect development projects.

Project Detail

Commitment and disbursement history with associated credits.

Credit Detail

Temporal snapshot history and derived credit-level metrics.

Compare

Side-by-side comparison of projects or credits.

Stagnation Monitor

Credits with little or no disbursement movement over configured periods.

Data Quality

Ingestion status, rejected records, freshness, reconciliation, and pipeline health.

Performance Engineering

Performance work is measured rather than assumed.

Planned experiments include:

baseline query timing;

EXPLAIN ANALYZE;

foreign-key and date indexes;

composite indexes for temporal access patterns;

materialized analytical views;

table partitioning experiments;

PostgreSQL vs MongoDB access-pattern comparison;

PostgreSQL vs Hive aggregation comparison;

concurrent worker/isolation-level experiments.

Every performance claim should record:

dataset size
query
database configuration
hardware context
execution plan
before timing
after timing

Repository Structure

flowwatch/
├── README.md
├── docs/
│   ├── 00_PROJECT_OVERVIEW.md
│   ├── 01_PRD.md
│   ├── 02_TRD.md
│   ├── 03_UI_UX_SPEC.md
│   ├── 04_SYSTEM_ARCHITECTURE.md
│   ├── 05_DATABASE_DESIGN.md
│   ├── 06_API_SPEC.md
│   ├── 07_IMPLEMENTATION_FLOW.md
│   └── 08_REPOSITORY_STRUCTURE.md
│
├── src/
│   ├── ingestion/
│   ├── transformation/
│   ├── analytics/
│   └── api/
│
├── frontend/
├── sql/
│   ├── operational/
│   ├── warehouse/
│   ├── analytics/
│   └── benchmarks/
│
├── data/
│   ├── raw/
│   ├── staging/
│   └── rejected/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── data/
│
├── docker/
├── scripts/
├── notebooks/
├── .github/
│   └── workflows/
└── docker-compose.yml

Engineering Documentation

The project is specified before implementation so that architectural decisions are explicit and reviewable.

Document

Purpose

docs/00_PROJECT_OVERVIEW.md

Product and system context

docs/01_PRD.md

Product requirements and acceptance criteria

docs/02_TRD.md

Technical requirements and engineering constraints

docs/03_UI_UX_SPEC.md

Screens, navigation and interaction design

docs/04_SYSTEM_ARCHITECTURE.md

Components, boundaries and data flow

docs/05_DATABASE_DESIGN.md

Operational + analytical data models

docs/06_API_SPEC.md

Application API contract

docs/07_IMPLEMENTATION_FLOW.md

Build sequence and validation gates

docs/08_REPOSITORY_STRUCTURE.md

Codebase organization

Development Roadmap

Phase 1 — Foundation

repository setup;

Python environment;

API exploration;

100-record sample extraction;

source-field profiling.

Phase 2 — Ingestion

pagination;

raw persistence;

PostgreSQL loading;

retries and checkpoints;

full historical extraction.

Phase 3 — Relational Modeling

normalized schema;

integrity constraints;

cleaning rules;

snapshot history.

Phase 4 — Analytics Warehouse

star schema;

fact/dimension ETL;

OLAP queries;

indexing and query-plan analysis.

Phase 5 — Analytics Product

metric layer;

API;

dashboard;

filters;

project/credit timelines;

stagnation analysis.

Phase 6 — Multi-model / Distributed Systems

MongoDB representation;

HDFS raw data;

Hive tables;

MapReduce / aggregate experiments;

database comparison.

Phase 7 — Reliability & Performance

tests;

CI;

Docker;

concurrency experiments;

benchmark suite;

optimization.

Phase 8 — Finalization

documentation;

UI polish;

reproducible demo;

final benchmark report;

project presentation.

Definition of Done

FlowWatch is considered complete when the repository can demonstrate that:

ingestion is reproducible and recoverable;

repeated loads do not create uncontrolled duplicates;

source records can be traced into curated data;

relational integrity is enforced;

temporal credit histories can be reconstructed;

dashboard totals reconcile with analytical queries;

metric definitions are documented and implemented consistently;

representative queries have measured performance;

automated tests execute in CI;

the system can be launched from documented commands;

architecture documentation matches the implemented system.

What This Project Demonstrates

FlowWatch is intended to demonstrate engineering depth across:

Data Engineering
API ingestion · ETL · data validation · temporal modeling · warehousing

Database Systems
PostgreSQL · normalization · indexing · OLAP · isolation · performance analysis

Distributed Data Systems
MongoDB · HDFS · Hive · comparative workload analysis

Backend Engineering
typed service boundaries · API contracts · query design · validation

Platform Engineering
Docker · CI · automated testing · reproducible environments

Product Engineering
PRD · TRD · UI/UX planning · architecture · implementation sequencing

Design Principles

Correctness before scale.

Raw data must remain traceable.

Every technology must have a justified responsibility.

Metrics require explicit definitions.

Performance claims require measurements.

The UI consumes contracts, not database internals.

Documentation must evolve with the implementation.

Complexity is introduced only when it solves a real system problem.

Data Source

FlowWatch is built around the World Bank Finances One / IDA financing dataset exposed through the World Bank data catalog API.

The project plan targets a historical dataset of approximately 1.59 million records and uses paginated extraction to process it incrementally.

FlowWatch does not modify the upstream data source. Source data is treated as externally owned, read-only input.

License

A license has not yet been selected.

Before public distribution, add an explicit repository license such as MIT, Apache-2.0, or another license appropriate to the project and its dependencies.

Author

Sanjay Manickam

Building FlowWatch as a systems-oriented data engineering project with an emphasis on architecture, correctness, observability, temporal analytics, and measurable performance.
