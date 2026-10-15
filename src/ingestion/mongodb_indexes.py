from __future__ import annotations

from typing import Any, Final

from pymongo import (
    ASCENDING,
    IndexModel,
)

RAW_PAGES_COLLECTION: Final[
    str
] = "raw_pages"

RAW_RECORDS_COLLECTION: Final[
    str
] = "raw_records"

INGESTION_RUNS_COLLECTION: Final[
    str
] = "ingestion_runs"


RAW_PAGE_RUN_INDEX: Final[
    str
] = "ix_raw_pages_run_page"

RAW_PAGE_SOURCE_INDEX: Final[
    str
] = "ix_raw_pages_source_page"

RAW_PAGE_CHECKSUM_INDEX: Final[
    str
] = "ix_raw_pages_checksum"

RAW_PAGE_SOURCE_KEY_INDEX: Final[
    str
] = "ux_raw_pages_run_source_key"


RAW_RECORD_RUN_INDEX: Final[
    str
] = "ix_raw_records_run_position"

RAW_RECORD_SOURCE_IDENTITY_INDEX: Final[
    str
] = "ix_raw_records_source_identity"

RAW_RECORD_CREDIT_PERIOD_INDEX: Final[
    str
] = "ix_raw_records_credit_period"

RAW_RECORD_SOURCE_KEY_INDEX: Final[
    str
] = "ux_raw_records_run_source_key"


INGESTION_RUN_ID_INDEX: Final[
    str
] = "ux_ingestion_runs_run_id"

INGESTION_RUN_SOURCE_INDEX: Final[
    str
] = "ix_ingestion_runs_source_started"


RAW_COLLECTIONS: Final[
    tuple[str, ...]
] = (
    RAW_PAGES_COLLECTION,
    RAW_RECORDS_COLLECTION,
    INGESTION_RUNS_COLLECTION,
)


RAW_PAGE_INDEXES: Final[
    tuple[IndexModel, ...]
] = (
    IndexModel(
        [
            (
                "run_id",
                ASCENDING,
            ),
            (
                "page_number",
                ASCENDING,
            ),
        ],
        name=(
            RAW_PAGE_RUN_INDEX
        ),
    ),
    IndexModel(
        [
            (
                "dataset_id",
                ASCENDING,
            ),
            (
                "resource_id",
                ASCENDING,
            ),
            (
                "page_number",
                ASCENDING,
            ),
        ],
        name=(
            RAW_PAGE_SOURCE_INDEX
        ),
    ),
    IndexModel(
        [
            (
                "source_checksum",
                ASCENDING,
            ),
        ],
        name=(
            RAW_PAGE_CHECKSUM_INDEX
        ),
    ),
    IndexModel(
        [
            (
                "run_id",
                ASCENDING,
            ),
            (
                "page_source_key",
                ASCENDING,
            ),
        ],
        name=(
            RAW_PAGE_SOURCE_KEY_INDEX
        ),
        unique=True,
        partialFilterExpression={
            "run_id": {
                "$type": "string"
            },
            "page_source_key": {
                "$type": "string"
            },
        },
    ),
)


RAW_RECORD_INDEXES: Final[
    tuple[IndexModel, ...]
] = (
    IndexModel(
        [
            (
                "run_id",
                ASCENDING,
            ),
            (
                "page_number",
                ASCENDING,
            ),
            (
                "record_index",
                ASCENDING,
            ),
        ],
        name=(
            RAW_RECORD_RUN_INDEX
        ),
    ),
    IndexModel(
        [
            (
                "dataset_id",
                ASCENDING,
            ),
            (
                "resource_id",
                ASCENDING,
            ),
            (
                "credit_number",
                ASCENDING,
            ),
            (
                "end_of_period",
                ASCENDING,
            ),
        ],
        name=(
            RAW_RECORD_SOURCE_IDENTITY_INDEX
        ),
    ),
    IndexModel(
        [
            (
                "credit_number",
                ASCENDING,
            ),
            (
                "end_of_period",
                ASCENDING,
            ),
        ],
        name=(
            RAW_RECORD_CREDIT_PERIOD_INDEX
        ),
    ),
    IndexModel(
        [
            (
                "run_id",
                ASCENDING,
            ),
            (
                "source_record_key",
                ASCENDING,
            ),
        ],
        name=(
            RAW_RECORD_SOURCE_KEY_INDEX
        ),
        unique=True,
        partialFilterExpression={
            "run_id": {
                "$type": "string"
            },
            "source_record_key": {
                "$type": "string"
            },
        },
    ),
)


INGESTION_RUN_INDEXES: Final[
    tuple[IndexModel, ...]
] = (
    IndexModel(
        [
            (
                "run_id",
                ASCENDING,
            ),
        ],
        name=(
            INGESTION_RUN_ID_INDEX
        ),
        unique=True,
    ),
    IndexModel(
        [
            (
                "dataset_id",
                ASCENDING,
            ),
            (
                "resource_id",
                ASCENDING,
            ),
            (
                "started_at",
                ASCENDING,
            ),
        ],
        name=(
            INGESTION_RUN_SOURCE_INDEX
        ),
    ),
)


def ensure_raw_collections(
    database: Any,
) -> None:
    """
    Create raw-lineage collections when absent.

    This does not insert source data.
    """

    existing = set(
        database.list_collection_names()
    )

    for collection_name in (
        RAW_COLLECTIONS
    ):
        if (
            collection_name
            not in existing
        ):
            database.create_collection(
                collection_name
            )


def ensure_raw_indexes(
    database: Any,
) -> dict[
    str,
    list[str],
]:
    """
    Create all raw-lineage indexes required by
    Day 15 and Day 16.

    Day 15:
    - run lookup
    - source lookup
    - checksum lookup
    - credit/reporting-period lookup

    Day 16:
    - unique run + deterministic page identity
    - unique run + deterministic record identity

    The deterministic source keys themselves remain stable
    across runs.

    run_id is included in the unique index so the same source
    object may be observed by multiple ingestion runs while a
    retry inside the same run remains idempotent.

    Partial unique indexes allow legacy Day-15 documents
    without Day-16 keys to coexist.
    """

    ensure_raw_collections(
        database
    )

    created: dict[
        str,
        list[str],
    ] = {}

    created[
        RAW_PAGES_COLLECTION
    ] = database[
        RAW_PAGES_COLLECTION
    ].create_indexes(
        list(
            RAW_PAGE_INDEXES
        )
    )

    created[
        RAW_RECORDS_COLLECTION
    ] = database[
        RAW_RECORDS_COLLECTION
    ].create_indexes(
        list(
            RAW_RECORD_INDEXES
        )
    )

    created[
        INGESTION_RUNS_COLLECTION
    ] = database[
        INGESTION_RUNS_COLLECTION
    ].create_indexes(
        list(
            INGESTION_RUN_INDEXES
        )
    )

    return created