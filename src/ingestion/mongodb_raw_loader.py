from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pymongo.database import Database

from src.ingestion.mongodb_indexes import (
    RAW_PAGES_COLLECTION,
    RAW_RECORDS_COLLECTION,
)
from src.ingestion.raw_envelope import (
    RawPageEnvelope,
    RawRecordEnvelope,
)


@dataclass(
    frozen=True
)
class RawWriteResult:
    """
    Result of one idempotent raw-page persistence operation.
    """

    page_inserted: bool

    records_inserted: int

    records_existing: int

    page_source_key: str

    source_record_keys: tuple[
        str,
        ...
    ]


class MongoRawLoader:
    """
    Idempotent MongoDB raw landing.

    Day-16 deterministic source identities remain stable
    across ingestion runs.

    Idempotency is enforced within one ingestion run by using:

    - run_id + page_source_key
    - run_id + source_record_key

    Therefore:

    same run + same source object
        -> existing document

    different run + same source object
        -> separate run-specific raw observation
    """

    def __init__(
        self,
        database: Database[
            dict[str, Any]
        ],
    ) -> None:
        self._database = (
            database
        )

        self._pages = database[
            RAW_PAGES_COLLECTION
        ]

        self._records = database[
            RAW_RECORDS_COLLECTION
        ]

    def persist_page(
        self,
        *,
        page: RawPageEnvelope,
        records: list[
            RawRecordEnvelope
        ],
    ) -> RawWriteResult:
        """
        Persist one raw page and its source records.

        Existing identities inside the same ingestion run
        are left unchanged using $setOnInsert.

        This preserves the first raw evidence stored for a
        particular source object/run pair.
        """

        self._validate_records(
            page=page,
            records=records,
        )

        page_document = (
            page.to_mongo_document()
        )

        page_result = (
            self._pages.update_one(
                {
                    "run_id": str(
                        page.run_id
                    ),
                    "page_source_key": (
                        page.page_source_key
                    ),
                },
                {
                    "$setOnInsert": (
                        page_document
                    )
                },
                upsert=True,
            )
        )

        page_inserted = (
            page_result.upserted_id
            is not None
        )

        records_inserted = 0
        records_existing = 0

        source_record_keys: list[
            str
        ] = []

        for record in records:
            source_record_keys.append(
                record.source_record_key
            )

            record_document = (
                record.to_mongo_document()
            )

            result = (
                self._records.update_one(
                    {
                        "run_id": str(
                            record.run_id
                        ),
                        "source_record_key": (
                            record.source_record_key
                        ),
                    },
                    {
                        "$setOnInsert": (
                            record_document
                        )
                    },
                    upsert=True,
                )
            )

            if (
                result.upserted_id
                is not None
            ):
                records_inserted += 1
            else:
                records_existing += 1

        return RawWriteResult(
            page_inserted=(
                page_inserted
            ),
            records_inserted=(
                records_inserted
            ),
            records_existing=(
                records_existing
            ),
            page_source_key=(
                page.page_source_key
            ),
            source_record_keys=tuple(
                source_record_keys
            ),
        )

    @staticmethod
    def _validate_records(
        *,
        page: RawPageEnvelope,
        records: list[
            RawRecordEnvelope
        ],
    ) -> None:
        """
        Reject an internally inconsistent page/record batch
        before any MongoDB write occurs.
        """

        if (
            len(
                records
            )
            != page.record_count
        ):
            raise ValueError(
                "Raw record count does not "
                "match page.record_count."
            )

        seen_keys: set[
            str
        ] = set()

        seen_indexes: set[
            int
        ] = set()

        for record in records:
            if (
                record.run_id
                != page.run_id
            ):
                raise ValueError(
                    "Raw record run_id does "
                    "not match page run_id."
                )

            if (
                record.dataset_id
                != page.dataset_id
            ):
                raise ValueError(
                    "Raw record dataset_id "
                    "does not match page."
                )

            if (
                record.resource_id
                != page.resource_id
            ):
                raise ValueError(
                    "Raw record resource_id "
                    "does not match page."
                )

            if (
                record.page_number
                != page.page_number
            ):
                raise ValueError(
                    "Raw record page_number "
                    "does not match page."
                )

            if (
                record.page_offset
                != page.page_offset
            ):
                raise ValueError(
                    "Raw record page_offset "
                    "does not match page."
                )

            if (
                record.source_checksum
                != page.source_checksum
            ):
                raise ValueError(
                    "Raw record source_checksum "
                    "does not match page."
                )

            if (
                record.page_source_key
                != page.page_source_key
            ):
                raise ValueError(
                    "Raw record page_source_key "
                    "does not match page."
                )

            if (
                record.record_index
                in seen_indexes
            ):
                raise ValueError(
                    "Duplicate record_index "
                    "inside raw page batch."
                )

            seen_indexes.add(
                record.record_index
            )

            if (
                record.source_record_key
                in seen_keys
            ):
                raise ValueError(
                    "Duplicate source_record_key "
                    "inside raw page batch."
                )

            seen_keys.add(
                record.source_record_key
            )