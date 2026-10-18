
"""Detect duplicate credit-period identities across source pages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.quality.rules import QualityRuleId
from src.quality.validator import (
    QualityPageValidationResult,
    QualityRejectedRecordEnvelope,
)
from src.validation.models import (
    RejectionIssue,
    RejectionReasonCode,
    ValidatedSourceRecordEnvelope,
)


@dataclass(frozen=True)
class SeenIdentity:
    """First observation of a credit-period identity."""

    fingerprint: str
    run_id: UUID
    page_number: int
    page_offset: int
    record_index: int
    source_checksum: str


def _fingerprint(record: Mapping[str, Any]) -> str:
    """Hash canonical JSON for source-content comparison."""

    encoded = json.dumps(
        dict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


class TemporalIdentityScanner:
    """
    Track credit-period identities across non-adjacent pages.

    Create one scanner per ingestion run.

    First observation wins within this scan. Repeated identities
    are rejected with explicit quality-rule IDs and lineage.

    This is an in-memory quality gate, not historical versioning.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], SeenIdentity] = {}
        self._run_id: UUID | None = None

    def check_page(
        self,
        page: QualityPageValidationResult,
        *,
        raw_records: Sequence[Any],
    ) -> QualityPageValidationResult:
        """Return a new page result with duplicate identities rejected."""

        accepted: list[ValidatedSourceRecordEnvelope] = []
        rejected = list(page.rejected)

        for envelope in page.accepted:
            if self._run_id is None:
                self._run_id = envelope.run_id
            elif self._run_id != envelope.run_id:
                raise ValueError(
                    "Use a new TemporalIdentityScanner for each run."
                )

            index = envelope.record_index

            if index >= len(raw_records):
                raise ValueError(
                    "Validated record index exceeds source page length."
                )

            raw_record = raw_records[index]

            if not isinstance(raw_record, Mapping):
               raise TypeError(
                   "Accepted source record must be a mapping."
               )

            credit_number = envelope.record.credit_number
            reporting_period = envelope.record.end_of_period.isoformat()

            key = (credit_number, reporting_period)
            fingerprint = _fingerprint(raw_record)

            previous = self._seen.get(key)

            if previous is None:
                self._seen[key] = SeenIdentity(
                    fingerprint=fingerprint,
                    run_id=envelope.run_id,
                    page_number=envelope.page_number,
                    page_offset=envelope.page_offset,
                    record_index=envelope.record_index,
                    source_checksum=envelope.source_checksum,
                )
                accepted.append(envelope)
                continue

            conflicting = previous.fingerprint != fingerprint

            rule_id = (
                QualityRuleId.CONFLICTING_CREDIT_PERIOD
                if conflicting
                else QualityRuleId.DUPLICATE_CREDIT_PERIOD
            )

            issue = RejectionIssue(
                reason_code=RejectionReasonCode.INVALID_SOURCE_VALUE,
                field_path="credit_number,end_of_period",
                message=(
                    "Conflicting source content for credit-period identity."
                    if conflicting
                    else "Repeated credit-period identity with identical content."
                ),
                offending_value={
                    "credit_number": credit_number,
                    "end_of_period": reporting_period,
                    "first_observation": {
                        "run_id": str(previous.run_id),
                        "page_number": previous.page_number,
                        "page_offset": previous.page_offset,
                        "record_index": previous.record_index,
                        "source_checksum": previous.source_checksum,
                        "record_sha256": previous.fingerprint,
                    },
                    "current_record_sha256": fingerprint,
                },
            )

            rejected.append(
                QualityRejectedRecordEnvelope(
                    run_id=envelope.run_id,
                    page_number=envelope.page_number,
                    page_offset=envelope.page_offset,
                    record_index=envelope.record_index,
                    source_record_offset=envelope.source_record_offset,
                    source_checksum=envelope.source_checksum,
                    raw_record=dict(raw_record),
                    reasons=(issue,),
                    rule_ids=(rule_id,),
                    rejected_at=datetime.now(UTC),
                )
            )

        return QualityPageValidationResult(
            accepted=tuple(accepted),
            rejected=tuple(rejected),
        )
