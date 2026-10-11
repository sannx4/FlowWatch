from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from bson.binary import Binary
from dotenv import load_dotenv
from pymongo import MongoClient
from sqlalchemy import URL, create_engine, text

from src.observability.logging import (
    configure_logging,
    get_logger,
    log_event,
    set_correlation_ids,
)
from src.transformation.day07 import (
    record_checksum,
    source_record_key,
    transform_record,
)


def build_postgres_engine():
    """Create the PostgreSQL SQLAlchemy engine."""

    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5434")),
        database=os.environ["POSTGRES_DB"],
    )

    return create_engine(url)


def build_mongo_client() -> MongoClient:
    """Create an authenticated MongoDB client."""

    return MongoClient(
        host=os.getenv("MONGO_HOST", "localhost"),
        port=int(os.getenv("MONGO_PORT", "27018")),
        username=os.environ["MONGO_INITDB_ROOT_USERNAME"],
        password=os.environ["MONGO_INITDB_ROOT_PASSWORD"],
        authSource="admin",
        serverSelectionTimeoutMS=5000,
    )


REGION_SQL = text(
    """
    INSERT INTO regions (
        region_name
    )
    VALUES (
        :region_name
    )
    ON CONFLICT (region_name)
    DO UPDATE SET
        region_name = EXCLUDED.region_name
    RETURNING region_id
    """
)


COUNTRY_SQL = text(
    """
    INSERT INTO countries (
        country_code,
        country_name,
        region_id
    )
    VALUES (
        :country_code,
        :country_name,
        :region_id
    )
    ON CONFLICT (country_code)
    DO UPDATE SET
        country_name = EXCLUDED.country_name,
        region_id = EXCLUDED.region_id
    RETURNING country_id
    """
)


PROJECT_SQL = text(
    """
    INSERT INTO projects (
        project_id,
        project_name,
        country_id
    )
    VALUES (
        :project_id,
        :project_name,
        :country_id
    )
    ON CONFLICT (project_id)
    DO UPDATE SET
        project_name = EXCLUDED.project_name,
        country_id = EXCLUDED.country_id
    RETURNING project_pk
    """
)


CREDIT_SQL = text(
    """
    INSERT INTO credits (
        credit_number,
        project_pk,
        borrower,
        currency_of_commitment,
        board_approval_date,
        agreement_signing_date,
        effective_date,
        first_repayment_date,
        last_repayment_date,
        closed_date
    )
    VALUES (
        :credit_number,
        :project_pk,
        :borrower,
        :currency_of_commitment,
        :board_approval_date,
        :agreement_signing_date,
        :effective_date,
        :first_repayment_date,
        :last_repayment_date,
        :closed_date
    )
    ON CONFLICT (credit_number)
    DO UPDATE SET
        project_pk = EXCLUDED.project_pk,
        borrower = EXCLUDED.borrower,
        currency_of_commitment = EXCLUDED.currency_of_commitment,
        board_approval_date = EXCLUDED.board_approval_date,
        agreement_signing_date = EXCLUDED.agreement_signing_date,
        effective_date = EXCLUDED.effective_date,
        first_repayment_date = EXCLUDED.first_repayment_date,
        last_repayment_date = EXCLUDED.last_repayment_date,
        closed_date = EXCLUDED.closed_date
    RETURNING credit_id
    """
)


SNAPSHOT_SQL = text(
    """
    INSERT INTO credit_snapshots (
        credit_id,
        end_of_period,
        credit_status,
        service_charge_rate,
        original_principal_amount_usd,
        cancelled_amount_usd,
        undisbursed_amount_usd,
        disbursed_amount_usd,
        repaid_to_ida_usd,
        due_to_ida_usd,
        exchange_adjustment_usd,
        borrowers_obligation_usd,
        sold_third_party_usd,
        repaid_third_party_usd,
        due_third_party_usd,
        credits_held_usd,
        last_disbursement_date,
        ingestion_run_id,
        source_checksum,
        source_record_key
    )
    VALUES (
        :credit_id,
        :end_of_period,
        :credit_status,
        :service_charge_rate,
        :original_principal_amount_usd,
        :cancelled_amount_usd,
        :undisbursed_amount_usd,
        :disbursed_amount_usd,
        :repaid_to_ida_usd,
        :due_to_ida_usd,
        :exchange_adjustment_usd,
        :borrowers_obligation_usd,
        :sold_third_party_usd,
        :repaid_third_party_usd,
        :due_third_party_usd,
        :credits_held_usd,
        :last_disbursement_date,
        :ingestion_run_id,
        :source_checksum,
        :source_record_key
    )
    ON CONFLICT (credit_id, end_of_period)
    DO UPDATE SET
        credit_status = EXCLUDED.credit_status,
        service_charge_rate = EXCLUDED.service_charge_rate,
        original_principal_amount_usd =
            EXCLUDED.original_principal_amount_usd,
        cancelled_amount_usd =
            EXCLUDED.cancelled_amount_usd,
        undisbursed_amount_usd =
            EXCLUDED.undisbursed_amount_usd,
        disbursed_amount_usd =
            EXCLUDED.disbursed_amount_usd,
        repaid_to_ida_usd =
            EXCLUDED.repaid_to_ida_usd,
        due_to_ida_usd =
            EXCLUDED.due_to_ida_usd,
        exchange_adjustment_usd =
            EXCLUDED.exchange_adjustment_usd,
        borrowers_obligation_usd =
            EXCLUDED.borrowers_obligation_usd,
        sold_third_party_usd =
            EXCLUDED.sold_third_party_usd,
        repaid_third_party_usd =
            EXCLUDED.repaid_third_party_usd,
        due_third_party_usd =
            EXCLUDED.due_third_party_usd,
        credits_held_usd =
            EXCLUDED.credits_held_usd,
        last_disbursement_date =
            EXCLUDED.last_disbursement_date,
        ingestion_run_id =
            EXCLUDED.ingestion_run_id,
        source_checksum =
            EXCLUDED.source_checksum,
        source_record_key =
            EXCLUDED.source_record_key
    """
)


def load_postgres_record(
    connection,
    raw_record,
    run_id: uuid.UUID,
) -> None:
    """Transform one source record and upsert it into PostgreSQL."""

    transformed = transform_record(raw_record)

    region_id = connection.execute(
        REGION_SQL,
        transformed["region"],
    ).scalar_one()

    country_id = connection.execute(
        COUNTRY_SQL,
        {
            **transformed["country"],
            "region_id": region_id,
        },
    ).scalar_one()

    project_pk = connection.execute(
        PROJECT_SQL,
        {
            **transformed["project"],
            "country_id": country_id,
        },
    ).scalar_one()

    credit_id = connection.execute(
        CREDIT_SQL,
        {
            **transformed["credit"],
            "project_pk": project_pk,
        },
    ).scalar_one()

    connection.execute(
        SNAPSHOT_SQL,
        {
            **transformed["snapshot"],
            "credit_id": credit_id,
            "ingestion_run_id": run_id,
            "source_checksum": record_checksum(raw_record),
            "source_record_key": source_record_key(raw_record),
        },
    )


def main() -> None:
    """Execute the Day-7 real-data vertical slice."""

    parser = argparse.ArgumentParser(
        description=(
            "Load the real World Bank sample into MongoDB "
            "and PostgreSQL."
        )
    )

    parser.add_argument(
        "--sample",
        default="data/raw/world_bank_sample.json",
        help="Path to the real World Bank JSON response.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of real source records to process.",
    )

    args = parser.parse_args()

    if args.limit <= 0:
        raise ValueError("--limit must be greater than zero.")

    load_dotenv()

    sample_path = Path(args.sample)

    if not sample_path.exists():
        raise FileNotFoundError(
            f"Source sample not found: {sample_path}"
        )

    raw_bytes = sample_path.read_bytes()

    source_file_checksum = hashlib.sha256(
        raw_bytes
    ).hexdigest()

    source_payload = json.loads(
        raw_bytes.decode("utf-8")
    )

    records = source_payload.get("data")

    if not isinstance(records, list):
        raise TypeError(
            "Expected source payload to contain a 'data' list."
        )

    if len(records) < args.limit:
        raise ValueError(
            f"Need at least {args.limit} records; "
            f"source contains {len(records)}."
        )

    selected_records = records[: args.limit]

    # Deterministic Day-7 run ID:
    # same source bytes + same limit => same run identity.
    run_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        (
            "flowwatch-day07:"
            f"{source_file_checksum}:"
            f"{args.limit}"
        ),
    )

    configure_logging()

    set_correlation_ids(
        run_id=str(run_id)
    )

    logger = get_logger(
        "day07.vertical-slice"
    )

    started_at = time.perf_counter()

    mongo = build_mongo_client()
    postgres = build_postgres_engine()

    try:
        #
        # 1. Verify MongoDB connectivity.
        #
        mongo.admin.command("ping")

        mongo_database = mongo[
            os.environ["MONGO_INITDB_DATABASE"]
        ]

        raw_payloads = mongo_database[
            "day07_raw_payloads"
        ]

        raw_records = mongo_database[
            "day07_raw_records"
        ]

        #
        # 2. Preserve the exact freshly fetched response bytes.
        #
        raw_payloads.replace_one(
            {
                "_id": source_file_checksum,
            },
            {
                "_id": source_file_checksum,
                "run_id": str(run_id),
                "source_file": sample_path.name,
                "source_file_checksum": (
                    source_file_checksum
                ),
                "api_total_count": source_payload.get(
                    "count"
                ),
                "selected_record_count": args.limit,
                "raw_bytes": Binary(raw_bytes),
            },
            upsert=True,
        )

        #
        # 3. Preserve all selected source records in MongoDB
        #    before transformation.
        #
        for index, record in enumerate(
            selected_records
        ):
            key = source_record_key(record)
            checksum = record_checksum(record)

            raw_records.replace_one(
                {
                    "_id": f"{run_id}:{key}",
                },
                {
                    "_id": f"{run_id}:{key}",
                    "run_id": str(run_id),
                    "source_index": index,
                    "source_record_key": key,
                    "source_checksum": checksum,
                    "source_file_checksum": (
                        source_file_checksum
                    ),
                    "payload": record,
                },
                upsert=True,
            )

        #
        # 4. Transform and load PostgreSQL.
        #
        #    All 100 canonical writes happen in one
        #    PostgreSQL transaction.
        #
        with postgres.begin() as connection:
            for record in selected_records:
                load_postgres_record(
                    connection,
                    record,
                    run_id,
                )

        duration_ms = (
            time.perf_counter() - started_at
        ) * 1000

        #
        # 5. Emit Day-6 structured logging format.
        #
        log_event(
            logger,
            "day07_vertical_slice_complete",
            status="success",
            duration_ms=duration_ms,
            records=len(selected_records),
        )

        #
        # 6. Print human-readable proof.
        #
        print()
        print("DAY 7 LOAD COMPLETE")
        print("-------------------")
        print(f"run_id={run_id}")
        print(
            f"source_file_sha256="
            f"{source_file_checksum}"
        )
        print(
            "api_total_count="
            f"{source_payload.get('count')}"
        )
        print(
            f"records_selected="
            f"{len(selected_records)}"
        )

        #
        # 7. PostgreSQL row-count evidence.
        #
        with postgres.connect() as connection:
            for table in (
                "regions",
                "countries",
                "projects",
                "credits",
                "credit_snapshots",
            ):
                count = connection.execute(
                    text(
                        f"SELECT COUNT(*) "
                        f"FROM {table}"
                    )
                ).scalar_one()

                print(
                    f"{table}={count}"
                )

        #
        # 8. MongoDB evidence.
        #
        mongo_record_count = (
            raw_records.count_documents(
                {
                    "run_id": str(run_id),
                }
            )
        )

        mongo_payload_count = (
            raw_payloads.count_documents(
                {
                    "_id": source_file_checksum,
                }
            )
        )

        print(
            f"mongo_raw_records="
            f"{mongo_record_count}"
        )

        print(
            f"mongo_raw_payloads="
            f"{mongo_payload_count}"
        )

        print()
        print("DAY 7 VERTICAL SLICE: SUCCESS")

    except Exception:
        duration_ms = (
            time.perf_counter() - started_at
        ) * 1000

        log_event(
            logger,
            "day07_vertical_slice_failed",
            status="failure",
            duration_ms=duration_ms,
        )

        raise

    finally:
        mongo.close()
        postgres.dispose()


if __name__ == "__main__":
    main()