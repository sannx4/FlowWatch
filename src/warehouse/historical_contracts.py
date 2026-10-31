"""Pure, fail-closed historical-canonical source and decision accounting contracts."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


class HistoricalCanonicalIntegrityError(RuntimeError):
    """Source completeness, identity, or publication balance is violated."""


@dataclass(frozen=True)
class SourceObservation:
    source_record_key: str
    source_checksum: str
    page_number: int
    page_offset: int
    record_index: int
    payload: dict[str, Any]


def assert_identity_partition(
    source: Iterable[str], raw: Iterable[str], decisions: Mapping[str, str],
) -> dict[str, int]:
    """Independent source/raw/decision sets must cover exactly the same identities."""
    expected = list(source)
    observed = list(raw)
    if not expected or len(expected) != len(set(expected)):
        raise HistoricalCanonicalIntegrityError("Source identities are empty or duplicated")
    if len(observed) != len(set(observed)) or set(expected) != set(observed):
        raise HistoricalCanonicalIntegrityError("Mongo source identities are missing or duplicated")
    if set(decisions) != set(expected):
        raise HistoricalCanonicalIntegrityError("Canonical decisions do not partition source identities")
    valid = {"INSERTED", "UNCHANGED", "REJECTED", "IGNORED", "UPDATED"}
    if not set(decisions.values()) <= valid:
        raise HistoricalCanonicalIntegrityError("Unknown historical canonical outcome")
    counts = Counter(decisions.values())
    return {
        "fetched": len(expected),
        "accepted": sum(counts[k] for k in valid if k != "REJECTED"),
        "rejected": counts["REJECTED"],
        "inserted": counts["INSERTED"],
        "updated": counts["UPDATED"],
        "unchanged": counts["UNCHANGED"],
        "ignored": counts["IGNORED"],
    }


def profile_canonical_keys(
    keys: Iterable[tuple[str, date]],
) -> dict[str, Any]:
    """Parse and measure true temporal identities, not lexicographic dates."""
    sequence = list(keys)
    for credit, period in sequence:
        if not isinstance(credit, str) or not credit or not isinstance(period, date):
            raise HistoricalCanonicalIntegrityError("Invalid credit/period identity")
        if isinstance(period, datetime):
            raise HistoricalCanonicalIntegrityError("Period must be a date, not datetime")
    if not sequence:
        return {"observations": 0, "unique_temporal_keys": 0,
                "duplicate_temporal_observations": 0, "earliest_date": None,
                "latest_date": None, "unique_credits": 0}
    periods = [period for _, period in sequence]
    return {
        "observations": len(sequence),
        "unique_temporal_keys": len(set(sequence)),
        "duplicate_temporal_observations": len(sequence) - len(set(sequence)),
        "earliest_date": min(periods).isoformat(),
        "latest_date": max(periods).isoformat(),
        "unique_credits": len({credit for credit, _ in sequence}),
    }
