from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from src.validation.source_record import (
    WorldBankSourceRecord,
)


class RejectionReasonCode(StrEnum):
    INVALID_RECORD_TYPE = "invalid_record_type"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_IDENTIFIER = "invalid_identifier"
    INVALID_DATE = "invalid_date"
    INVALID_NUMERIC = "invalid_numeric"
    INVALID_INTEGER = "invalid_integer"
    INVALID_SOURCE_VALUE = "invalid_source_value"


class ValidationContext(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        strict=True,
    )

    run_id: UUID

    page_number: int = Field(
        ge=1,
    )

    page_offset: int = Field(
        ge=0,
    )

    source_checksum: str

    @field_validator(
        "source_checksum",
        mode="before",
    )
    @classmethod
    def validate_checksum(
        cls,
        value: Any,
    ) -> str:
        # Keep ValueError intentionally here.
        #
        # In a Pydantic field validator, ValueError is converted into a
        # ValidationError. That gives callers one consistent validation
        # failure path instead of allowing an uncaught TypeError to escape.
        if not isinstance(
            value,
            str,
        ):
            raise ValueError(  # noqa: TRY004
                "source_checksum must be a string"
            )

        normalized = (
            value.strip().lower()
        )

        if (
            len(
                normalized
            )
            != 64
        ):
            raise ValueError(
                "source_checksum must contain "
                "64 hexadecimal characters"
            )

        if any(
            character
            not in "0123456789abcdef"
            for character in normalized
        ):
            raise ValueError(
                "source_checksum must contain "
                "only hexadecimal characters"
            )

        return normalized


class RejectionIssue(BaseModel):
    model_config = ConfigDict(
        frozen=True,
    )

    reason_code: RejectionReasonCode

    field_path: str

    message: str

    offending_value: Any = None


class RejectedRecordEnvelope(BaseModel):
    """
    Non-persistent Day-12 quarantine envelope.

    Persistence/remediation is deliberately left for the later
    quarantine-storage phase.
    """

    model_config = ConfigDict(
        frozen=True,
    )

    run_id: UUID

    page_number: int = Field(
        ge=1,
    )

    page_offset: int = Field(
        ge=0,
    )

    record_index: int = Field(
        ge=0,
    )

    source_record_offset: int = Field(
        ge=0,
    )

    source_checksum: str

    raw_record: Any

    reasons: tuple[
        RejectionIssue,
        ...,
    ] = Field(
        min_length=1,
    )

    rejected_at: datetime


class ValidatedSourceRecordEnvelope(BaseModel):
    model_config = ConfigDict(
        frozen=True,
    )

    run_id: UUID

    page_number: int = Field(
        ge=1,
    )

    page_offset: int = Field(
        ge=0,
    )

    record_index: int = Field(
        ge=0,
    )

    source_record_offset: int = Field(
        ge=0,
    )

    source_checksum: str

    record: WorldBankSourceRecord


class PageValidationResult(BaseModel):
    model_config = ConfigDict(
        frozen=True,
    )

    accepted: tuple[
        ValidatedSourceRecordEnvelope,
        ...,
    ]

    rejected: tuple[
        RejectedRecordEnvelope,
        ...,
    ]

    @property
    def accepted_count(
        self,
    ) -> int:
        return len(
            self.accepted
        )

    @property
    def rejected_count(
        self,
    ) -> int:
        return len(
            self.rejected
        )

    @property
    def total_count(
        self,
    ) -> int:
        return (
            self.accepted_count
            + self.rejected_count
        )