from __future__ import annotations

import hashlib

SOURCE_KEY_VERSION = "v1"


def _sha256_text(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


def build_page_source_key(
    *,
    dataset_id: str,
    resource_id: str,
    page_offset: int,
    source_checksum: str,
) -> str:
    """
    Build a deterministic identity for one source page.

    The key intentionally excludes run_id.

    Therefore the same logical source page content fetched in
    different executions produces the same source identity.
    """

    if not dataset_id:
        raise ValueError(
            "dataset_id cannot be empty."
        )

    if not resource_id:
        raise ValueError(
            "resource_id cannot be empty."
        )

    if page_offset < 0:
        raise ValueError(
            "page_offset cannot be negative."
        )

    if len(
        source_checksum
    ) != 64:
        raise ValueError(
            "source_checksum must be "
            "a SHA-256 hex digest."
        )

    identity = "|".join(
        (
            SOURCE_KEY_VERSION,
            "page",
            dataset_id,
            resource_id,
            str(
                page_offset
            ),
            source_checksum,
        )
    )

    return (
        "page:"
        + _sha256_text(
            identity
        )
    )


def build_record_source_key(
    *,
    dataset_id: str,
    resource_id: str,
    page_source_key: str,
    record_index: int,
    record_checksum: str,
) -> str:
    """
    Build a deterministic identity for one source record.

    The record is anchored to the deterministic page identity,
    record position, and checksum of the exact source record.
    """

    if not dataset_id:
        raise ValueError(
            "dataset_id cannot be empty."
        )

    if not resource_id:
        raise ValueError(
            "resource_id cannot be empty."
        )

    if not page_source_key:
        raise ValueError(
            "page_source_key cannot be empty."
        )

    if record_index < 0:
        raise ValueError(
            "record_index cannot be negative."
        )

    if len(
        record_checksum
    ) != 64:
        raise ValueError(
            "record_checksum must be "
            "a SHA-256 hex digest."
        )

    identity = "|".join(
        (
            SOURCE_KEY_VERSION,
            "record",
            dataset_id,
            resource_id,
            page_source_key,
            str(
                record_index
            ),
            record_checksum,
        )
    )

    return (
        "record:"
        + _sha256_text(
            identity
        )
    )