from __future__ import annotations

from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.observability.logging import (
    get_logger,
    log_event,
    set_correlation_ids,
)
from src.validation.models import (
    PageValidationResult,
    RejectedRecordEnvelope,
    RejectionIssue,
    RejectionReasonCode,
    ValidatedSourceRecordEnvelope,
    ValidationContext,
)
from src.validation.source_record import (
    DATE_FIELDS,
    DECIMAL_FIELDS,
    IDENTIFIER_FIELDS,
    INTEGER_FIELDS,
    WorldBankSourceRecord,
)

logger = get_logger(
    "validation.source-record"
)


def utc_now() -> datetime:
    return datetime.now(
        UTC
    )


ValidationOutcome = (
    ValidatedSourceRecordEnvelope
    | RejectedRecordEnvelope
)


class SourceRecordValidationService:
    """
    Parse source records without performing business transformation.

    Invalid source records become rejected-record envelopes rather
    than raising out of the page-validation loop.
    """

    def __init__(
        self,
        *,
        clock: Callable[
            [],
            datetime,
        ] = utc_now,
    ) -> None:
        self._clock = clock

    def validate_record(
        self,
        raw_record: Any,
        *,
        context: ValidationContext,
        record_index: int,
    ) -> ValidationOutcome:
        if record_index < 0:
            raise ValueError(
                "record_index cannot be negative"
            )

        source_record_offset = (
            context.page_offset
            + record_index
        )

        if not isinstance(
            raw_record,
            Mapping,
        ):
            return (
                RejectedRecordEnvelope(
                    run_id=context.run_id,
                    page_number=(
                        context.page_number
                    ),
                    page_offset=(
                        context.page_offset
                    ),
                    record_index=record_index,
                    source_record_offset=(
                        source_record_offset
                    ),
                    source_checksum=(
                        context.source_checksum
                    ),
                    raw_record=raw_record,
                    reasons=(
                        RejectionIssue(
                            reason_code=(
                                RejectionReasonCode
                                .INVALID_RECORD_TYPE
                            ),
                            field_path="$",
                            message=(
                                "source record must "
                                "be a JSON object"
                            ),
                            offending_value=(
                                raw_record
                            ),
                        ),
                    ),
                    rejected_at=(
                        self._clock()
                    ),
                )
            )

        source_record = dict(
            raw_record
        )

        try:
            parsed = (
                WorldBankSourceRecord
                .model_validate(
                    source_record
                )
            )

        except ValidationError as exc:
            reasons = tuple(
                self._map_validation_error(
                    error
                )
                for error in exc.errors(
                    include_url=False
                )
            )

            return (
                RejectedRecordEnvelope(
                    run_id=context.run_id,
                    page_number=(
                        context.page_number
                    ),
                    page_offset=(
                        context.page_offset
                    ),
                    record_index=record_index,
                    source_record_offset=(
                        source_record_offset
                    ),
                    source_checksum=(
                        context.source_checksum
                    ),
                    raw_record=(
                        source_record
                    ),
                    reasons=reasons,
                    rejected_at=(
                        self._clock()
                    ),
                )
            )

        return (
            ValidatedSourceRecordEnvelope(
                run_id=context.run_id,
                page_number=(
                    context.page_number
                ),
                page_offset=(
                    context.page_offset
                ),
                record_index=record_index,
                source_record_offset=(
                    source_record_offset
                ),
                source_checksum=(
                    context.source_checksum
                ),
                record=parsed,
            )
        )

    def validate_page(
        self,
        records: Sequence[Any],
        *,
        context: ValidationContext,
    ) -> PageValidationResult:
        accepted: list[
            ValidatedSourceRecordEnvelope
        ] = []

        rejected: list[
            RejectedRecordEnvelope
        ] = []

        for (
            record_index,
            raw_record,
        ) in enumerate(
            records
        ):
            result = self.validate_record(
                raw_record,
                context=context,
                record_index=record_index,
            )

            if isinstance(
                result,
                RejectedRecordEnvelope,
            ):
                rejected.append(
                    result
                )

            else:
                accepted.append(
                    result
                )

        validation_result = (
            PageValidationResult(
                accepted=tuple(
                    accepted
                ),
                rejected=tuple(
                    rejected
                ),
            )
        )

        set_correlation_ids(
            run_id=str(
                context.run_id
            )
        )

        log_event(
            logger,
            "source_page_validated",
            component=(
                "validation.source-record"
            ),
            status="completed",
            page_number=(
                context.page_number
            ),
            page_offset=(
                context.page_offset
            ),
            source_checksum=(
                context.source_checksum
            ),
            accepted_count=(
                validation_result
                .accepted_count
            ),
            rejected_count=(
                validation_result
                .rejected_count
            ),
            total_count=(
                validation_result
                .total_count
            ),
        )

        return validation_result

    @staticmethod
    def _map_validation_error(
        error: dict[str, Any],
    ) -> RejectionIssue:
        location = error.get(
            "loc",
            (),
        )

        field_name = (
            str(
                location[0]
            )
            if location
            else ""
        )

        field_path = (
            ".".join(
                str(
                    part
                )
                for part in location
            )
            if location
            else "$"
        )

        error_type = str(
            error.get(
                "type",
                "",
            )
        )

        if error_type == "missing":
            reason_code = (
                RejectionReasonCode
                .MISSING_REQUIRED_FIELD
            )

        elif field_name in DATE_FIELDS:
            reason_code = (
                RejectionReasonCode
                .INVALID_DATE
            )

        elif (
            field_name
            in DECIMAL_FIELDS
        ):
            reason_code = (
                RejectionReasonCode
                .INVALID_NUMERIC
            )

        elif (
            field_name
            in INTEGER_FIELDS
        ):
            reason_code = (
                RejectionReasonCode
                .INVALID_INTEGER
            )

        elif (
            field_name
            in IDENTIFIER_FIELDS
        ):
            reason_code = (
                RejectionReasonCode
                .INVALID_IDENTIFIER
            )

        else:
            reason_code = (
                RejectionReasonCode
                .INVALID_SOURCE_VALUE
            )

        return RejectionIssue(
            reason_code=reason_code,
            field_path=field_path,
            message=str(
                error.get(
                    "msg",
                    "invalid source value",
                )
            ),
            offending_value=(
                error.get(
                    "input"
                )
            ),
        )