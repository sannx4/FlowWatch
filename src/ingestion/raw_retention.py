"""Day 18: fail-closed retention policy for MongoDB hot-raw data.

There is intentionally no deletion function in this module. A future
Day-94 implementation must independently validate an HDFS archive
before defining an authorized cleanup operation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID


class RawRetentionDenied(RuntimeError):
    """The run is not authorized for deletion from MongoDB."""


@dataclass(frozen=True)
class RawRetentionDecision:
    run_id: str
    allowed: bool
    reason_code: str
    reason: str


def assess_raw_retention(
    run_id: UUID | str,
    *,
    archive_manifest: Mapping[str, Any] | None = None,
) -> RawRetentionDecision:
    """Refuse every deletion until a trusted archive verifier exists.

    A dictionary, local JSON file, or boolean archive flag must never
    be accepted as independently verified proof of durable storage.
    """
    canonical_run_id = str(UUID(str(run_id)))

    if archive_manifest is None:
        return RawRetentionDecision(
            run_id=canonical_run_id,
            allowed=False,
            reason_code="ARCHIVE_MANIFEST_MISSING",
            reason=(
                "No durable archive manifest exists. MongoDB raw data "
                "must be retained until independently verified archival "
                "is implemented on Day 94."
            ),
        )

    return RawRetentionDecision(
        run_id=canonical_run_id,
        allowed=False,
        reason_code="ARCHIVE_NOT_INDEPENDENTLY_VERIFIED",
        reason=(
            "An untrusted manifest or archive_verified flag is not proof "
            "of durability. Day 94 must verify coverage, object existence "
            "and checksums against the archive before authorizing deletion."
        ),
    )


def require_raw_deletion_authorization(
    run_id: UUID | str,
    *,
    archive_manifest: Mapping[str, Any] | None = None,
) -> None:
    """Raise unconditionally for Day-18 requests to purge raw data."""
    decision = assess_raw_retention(
        run_id,
        archive_manifest=archive_manifest,
    )
    raise RawRetentionDenied(
        f"{decision.reason_code}: {decision.reason}"
    )