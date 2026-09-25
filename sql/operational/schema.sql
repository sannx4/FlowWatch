-- FlowWatch
-- Day 4: Initial operational schema design
--
-- Design-stage DDL.
-- Day 5 will convert this into production migrations
-- and finalize constraints, FK behavior, and indexes.

CREATE TABLE regions (
    region_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_name TEXT NOT NULL UNIQUE
);


CREATE TABLE countries (
    country_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    country_code TEXT NOT NULL UNIQUE,
    country_name TEXT NOT NULL,
    region_id BIGINT REFERENCES regions(region_id)
);


CREATE TABLE projects (
    project_pk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Natural World Bank project identifier
    project_id TEXT NOT NULL UNIQUE,

    project_name TEXT,
    country_id BIGINT REFERENCES countries(country_id)
);


CREATE TABLE credits (
    credit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Natural World Bank credit/grant identifier
    credit_number TEXT NOT NULL UNIQUE,

    project_pk BIGINT REFERENCES projects(project_pk),

    borrower TEXT,
    currency_of_commitment TEXT,

    board_approval_date DATE,
    agreement_signing_date DATE,
    effective_date DATE,
    first_repayment_date DATE,
    last_repayment_date DATE,
    closed_date DATE
);


CREATE TABLE credit_snapshots (
    credit_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    credit_id BIGINT NOT NULL
        REFERENCES credits(credit_id),

    -- Source reporting / as-of date
    end_of_period DATE NOT NULL,

    credit_status TEXT,
    service_charge_rate NUMERIC,

    original_principal_amount_usd NUMERIC(20, 2),
    cancelled_amount_usd NUMERIC(20, 2),
    undisbursed_amount_usd NUMERIC(20, 2),
    disbursed_amount_usd NUMERIC(20, 2),

    repaid_to_ida_usd NUMERIC(20, 2),
    due_to_ida_usd NUMERIC(20, 2),

    exchange_adjustment_usd NUMERIC(20, 2),
    borrowers_obligation_usd NUMERIC(20, 2),

    sold_third_party_usd NUMERIC(20, 2),
    repaid_third_party_usd NUMERIC(20, 2),
    due_third_party_usd NUMERIC(20, 2),

    credits_held_usd NUMERIC(20, 2),

    last_disbursement_date DATE,

    -- Reserved lineage / audit metadata
    ingestion_run_id UUID,
    source_checksum CHAR(64),
    source_record_key TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_credit_snapshot_period
        UNIQUE (credit_id, end_of_period)
);


CREATE INDEX idx_credit_snapshots_credit_period
    ON credit_snapshots (credit_id, end_of_period DESC);

CREATE INDEX idx_projects_country
    ON projects (country_id);

CREATE INDEX idx_credits_project
    ON credits (project_pk);