
"""Integrated source, temporal, and financial quality validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from src.quality.invariants import (
    QualityWarningEnvelope,
    build_warning_envelope,
)
from src.quality.rules import QualityRuleId, rule_id_for_issue
from src.validation.models import (
    RejectedRecordEnvelope,
    ValidatedSourceRecordEnvelope,
    ValidationContext,
)
from src.validation.service import SourceRecordValidationService

if TYPE_CHECKING:
    from src.quality.temporal import TemporalIdentityScanner


class QualityRejectedRecordEnvelope(RejectedRecordEnvelope):
    """Rejected source record with stable quality-rule IDs."""

    rule_ids: tuple[QualityRuleId, ...] = Field(
        min_length=1,
    )


class QualityPageValidationResult(BaseModel):
    """Accepted, rejected, and warned source records."""

    model_config = ConfigDict(frozen=True)

    accepted: tuple[ValidatedSourceRecordEnvelope, ...]
    rejected: tuple[QualityRejectedRecordEnvelope, ...]
    warnings: tuple[QualityWarningEnvelope, ...] = ()

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def total_count(self) -> int:
        return self.accepted_count + self.rejected_count


class QualityValidationService:
    """
    Combine source validation, temporal uniqueness, and warnings.

    Processing order:
      1. Parse and validate source records.
      2. Apply optional temporal duplicate detection.
      3. Generate non-blocking financial/date warnings.

    Warning records remain accepted.

    A temporal scanner is scoped to one ingestion run.
    """

    def __init__(
        self,
        source_service: SourceRecordValidationService | None = None,
        *,
        temporal_scanner: TemporalIdentityScanner | None = None,
    ) -> None:
        self._source_service = (
            source_service
            if source_service is not None
            else SourceRecordValidationService()
        )

        self._temporal_scanner = temporal_scanner

    def validate_page(
        self,
        records: Sequence[Any],
        *,
        context: ValidationContext,
    ) -> QualityPageValidationResult:
        """Validate a page and preserve all source lineage."""

        source_result = self._source_service.validate_page(
            records,
            context=context,
        )

        quality_rejections: list[
            QualityRejectedRecordEnvelope
        ] = []

        for rejected in source_result.rejected:
            rule_ids = tuple(
                dict.fromkeys(
                    rule_id_for_issue(issue)
                    for issue in rejected.reasons
                )
            )

            quality_rejections.append(
                QualityRejectedRecordEnvelope(
                    run_id=rejected.run_id,
                    page_number=rejected.page_number,
                    page_offset=rejected.page_offset,
                    record_index=rejected.record_index,
                    source_record_offset=(
                        rejected.source_record_offset
                    ),
                    source_checksum=rejected.source_checksum,
                    raw_record=rejected.raw_record,
                    reasons=rejected.reasons,
                    rejected_at=rejected.rejected_at,
                    rule_ids=rule_ids,
                )
            )

        result = QualityPageValidationResult(
            accepted=source_result.accepted,
            rejected=tuple(quality_rejections),
        )

        # Reject repeated credit-period identities before
        # calculating warnings.
        if self._temporal_scanner is not None:
            result = self._temporal_scanner.check_page(
                result,
                raw_records=records,
            )

        warning_envelopes: list[
            QualityWarningEnvelope
        ] = []

        for accepted in result.accepted:
            record_index = accepted.record_index

            if record_index >= len(records):
                raise ValueError(
                    "Accepted record index exceeds page length."
                )

            raw_record = records[record_index]

            if not isinstance(raw_record, Mapping):
                raise TypeError(
                    "Accepted source record must be a mapping."
                )

            warning_envelope = build_warning_envelope(
                accepted,
                raw_record=raw_record,
            )

            if warning_envelope is not None:
                warning_envelopes.append(
                    warning_envelope
                )

        return QualityPageValidationResult(
            accepted=result.accepted,
            rejected=result.rejected,
            warnings=tuple(warning_envelopes),
        )
