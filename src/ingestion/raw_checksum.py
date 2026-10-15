from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(
    payload: Any,
) -> bytes:
    """
    Serialize JSON-compatible content deterministically.

    This checksum is for logical raw-record identity.

    Page-level source_checksum still represents the exact HTTP
    response bytes from the source.
    """

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )


def checksum_record(
    payload: Any,
) -> str:
    """
    SHA-256 checksum for one logical source record.
    """

    return hashlib.sha256(
        canonical_json_bytes(
            payload
        )
    ).hexdigest()