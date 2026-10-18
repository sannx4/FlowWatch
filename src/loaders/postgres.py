
"""Transactional PostgreSQL canonical batch loader.

Day 19: canonical constraints and transactional loaders.

The existing Day-16 single-record loader owns the entity
upsert logic. This module owns the batch transaction boundary.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.engine import Engine

from src.ingestion.postgres_curated_loader import (
    CuratedLoadResult,
    load_curated_record,
)
from src.ingestion.raw_envelope import RawRecordEnvelope


def load_curated_batch(
    engine: Engine,
    envelopes: Iterable[RawRecordEnvelope],
) -> list[CuratedLoadResult]:
    """Atomically load a batch of raw-record envelopes.

    The entire batch uses one PostgreSQL transaction.

    On success:
        Every record is committed together.

    On failure:
        Every database change made by this batch is rolled
        back, including entity inserts and conflict updates.

    An iterator failure, transformation exception, SQL error,
    or integrity violation is propagated to the caller.

    This function does not contact MongoDB or the source API.

    The caller must supply a SQLAlchemy Engine, not a
    preexisting Connection with an unrelated transaction.
    """
    results: list[CuratedLoadResult] = []

    with engine.begin() as connection:
        for envelope in envelopes:
            result = load_curated_record(
                connection,
                envelope,
            )

            results.append(result)

    return results
