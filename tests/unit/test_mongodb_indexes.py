from __future__ import annotations

from pymongo import IndexModel

from src.ingestion.mongodb_indexes import (
    INGESTION_RUN_ID_INDEX,
    INGESTION_RUN_INDEXES,
    INGESTION_RUNS_COLLECTION,
    RAW_COLLECTIONS,
    RAW_PAGE_INDEXES,
    RAW_PAGES_COLLECTION,
    RAW_RECORD_INDEXES,
    RAW_RECORD_SOURCE_IDENTITY_INDEX,
    RAW_RECORDS_COLLECTION,
)


def index_documents(
    indexes: tuple[
        IndexModel,
        ...,
    ],
) -> dict[
    str,
    dict,
]:
    documents = {}

    for index in indexes:
        document = (
            index.document
        )

        documents[
            document["name"]
        ] = document

    return documents


def test_day15_collection_contract() -> None:
    assert set(
        RAW_COLLECTIONS
    ) == {
        RAW_PAGES_COLLECTION,
        RAW_RECORDS_COLLECTION,
        INGESTION_RUNS_COLLECTION,
    }


def test_raw_record_source_identity_index_contract() -> None:
    indexes = index_documents(
        RAW_RECORD_INDEXES
    )

    source_index = indexes[
        RAW_RECORD_SOURCE_IDENTITY_INDEX
    ]

    assert list(
        source_index[
            "key"
        ].items()
    ) == [
        (
            "dataset_id",
            1,
        ),
        (
            "resource_id",
            1,
        ),
        (
            "credit_number",
            1,
        ),
        (
            "end_of_period",
            1,
        ),
    ]


def test_ingestion_run_id_is_unique() -> None:
    indexes = index_documents(
        INGESTION_RUN_INDEXES
    )

    run_index = indexes[
        INGESTION_RUN_ID_INDEX
    ]

    assert (
        run_index[
            "unique"
        ]
        is True
    )


def test_raw_page_indexes_are_named() -> None:
    indexes = index_documents(
        RAW_PAGE_INDEXES
    )

    assert len(
        indexes
    ) == len(
        RAW_PAGE_INDEXES
    )

    assert all(
        name
        for name in indexes
    )