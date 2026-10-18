from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pymongo import ASCENDING
from pymongo.database import Database
from sqlalchemy.engine import Connection

from src.ingestion.postgres_curated_loader import (
    CuratedLoadResult,
    load_curated_record,
)
from src.ingestion.raw_envelope import (
    RawRecordEnvelope,
)

RAW_RECORDS_COLLECTION = "raw_records"


@dataclass(frozen=True)
class RawReplayResult:
    """
    Result of rebuilding canonical PostgreSQL records
    from MongoDB raw-record envelopes.
    """

    run_id: str
    selected_records: int
    replayed_records: int
    credit_snapshot_ids: tuple[int, ...]
    source_record_keys: tuple[str, ...]


def select_raw_record_envelopes(
    mongo_database: Database[dict[str, Any]],
    *,
    run_id: UUID | str,
    limit: int | None = None,
    source_record_keys: Sequence[str] | None = None,
) -> tuple[RawRecordEnvelope, ...]:
    """
    Read stored raw-record envelopes from MongoDB.

    No source API is contacted.

    Records are returned in deterministic source order:
    page_number -> record_index.
    """

    if limit is not None and limit <= 0:
        raise ValueError(
            "limit must be greater than zero."
        )

    query: dict[str, Any] = {
        "run_id": str(run_id),
    }

    if source_record_keys:
        query["source_record_key"] = {
            "$in": list(source_record_keys),
        }

    collection = mongo_database[
        RAW_RECORDS_COLLECTION
    ]

    cursor = collection.find(
        query
    ).sort(
        [
            ("page_number", ASCENDING),
            ("record_index", ASCENDING),
        ]
    )

    if limit is not None:
        cursor = cursor.limit(
            limit
        )

    envelopes = tuple(
        RawRecordEnvelope.from_mongo_document(
            document
        )
        for document in cursor
    )

    return envelopes


def replay_envelopes(
    connection: Connection,
    envelopes: Sequence[RawRecordEnvelope],
) -> RawReplayResult:
    """
    Rebuild PostgreSQL curated records from already
    materialized MongoDB raw envelopes.

    All transformation and lineage behavior is delegated
    to the existing canonical loader.

    This function performs no network/source acquisition.
    """

    if not envelopes:
        raise ValueError(
            "No raw envelopes were supplied for replay."
        )

    run_ids = {
        str(envelope.run_id)
        for envelope in envelopes
    }

    if len(run_ids) != 1:
        raise ValueError(
            "A replay batch must contain records "
            "from exactly one ingestion run."
        )

    load_results: list[
        CuratedLoadResult
    ] = []

    for envelope in envelopes:
        result = load_curated_record(
            connection,
            envelope,
        )

        load_results.append(
            result
        )

    return RawReplayResult(
        run_id=next(
            iter(run_ids)
        ),
        selected_records=len(
            envelopes
        ),
        replayed_records=len(
            load_results
        ),
        credit_snapshot_ids=tuple(
            result.credit_snapshot_id
            for result in load_results
        ),
        source_record_keys=tuple(
            result.source_record_key
            for result in load_results
        ),
    )


def replay_raw_records(
    mongo_database: Database[dict[str, Any]],
    connection: Connection,
    *,
    run_id: UUID | str,
    limit: int | None = None,
    source_record_keys: Sequence[str] | None = None,
) -> RawReplayResult:
    """
    Select MongoDB raw records and rebuild their
    corresponding canonical PostgreSQL state.
    """

    envelopes = (
        select_raw_record_envelopes(
            mongo_database,
            run_id=run_id,
            limit=limit,
            source_record_keys=(
                source_record_keys
            ),
        )
    )

    if not envelopes:
        raise LookupError(
            "No MongoDB raw records matched "
            f"run_id={run_id}."
        )

    return replay_envelopes(
        connection,
        envelopes,
    )