"""Rehydrate one exact JSON source record from checksum-verified raw page bytes.

Pure function: never mutates a MongoDB document, contacts a service, or changes
existing raw envelope checksums/lineage. MongoDB access belongs to its caller.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any


class SourceRehydrationError(ValueError):
    """A source page or stored record fails its integrity contract."""


def _reject_nonfinite(value: str) -> None:
    raise SourceRehydrationError(f"Invalid JSON numeric constant: {value}")


def _source_record(
    raw_bytes: bytes,
    *,
    record_index: int,
    exact_decimal: bool,
) -> dict[str, Any]:
    try:
        if exact_decimal:
            page = json.loads(
                raw_bytes,
                parse_float=Decimal,
                parse_constant=_reject_nonfinite,
            )
        else:
            page = json.loads(raw_bytes, parse_constant=_reject_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SourceRehydrationError("Raw source page is not valid JSON") from exc

    if not isinstance(page, dict) or not isinstance(page.get("data"), list):
        raise SourceRehydrationError("Source page must contain a 'data' list")
    records = page["data"]
    if record_index < 0 or record_index >= len(records):
        raise SourceRehydrationError("Source record index is outside the page")
    item = records[record_index]
    if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
        raise SourceRehydrationError("Source record must be a JSON object")
    return item


def recover_exact_source_record(
    raw_bytes: bytes,
    *,
    source_checksum: str,
    record_index: int,
    stored_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Restore original base-10 numeric literals, checking checksum and identity.

    The existing envelope remains untouched. Its `payload` is used to verify
    that the source record selected by `record_index` is the same observation.
    """
    if not isinstance(raw_bytes, bytes):
        raise SourceRehydrationError("Raw page bytes are missing")
    actual_checksum = hashlib.sha256(raw_bytes).hexdigest()
    if actual_checksum != source_checksum:
        raise SourceRehydrationError("Raw page SHA-256 mismatch")
    if not isinstance(record_index, int) or isinstance(record_index, bool):
        raise SourceRehydrationError("Record index must be an integer")

    # Parse once with standard JSON float conversion to verify the MongoDB
    # record is identical to the observation at this position in the page.
    normal = _source_record(raw_bytes, record_index=record_index, exact_decimal=False)
    if normal != stored_payload:
        raise SourceRehydrationError(
            "Stored raw record differs from the JSON page at its record index"
        )
    return _source_record(raw_bytes, record_index=record_index, exact_decimal=True)
