from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

DEFAULT_PARSER_VERSION = (
    "worldbank-source-v1"
)

_SHA256_PATTERN = (
    r"^[0-9a-f]{64}$"
)


def _as_utc(
    value: datetime,
    *,
    field_name: str,
) -> datetime:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{field_name} must be "
            "timezone-aware"
        )

    return value.astimezone(
        UTC
    )


class MongoDocumentModel(
    BaseModel
):
    """
    Base model for FlowWatch MongoDB documents.

    MongoDB stores run UUIDs as strings so client UUID
    representation settings cannot silently alter lineage keys.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    def to_mongo_document(
        self,
    ) -> dict[str, Any]:
        document = self.model_dump(
            mode="python"
        )

        run_id = document.get(
            "run_id"
        )

        if isinstance(
            run_id,
            UUID,
        ):
            document[
                "run_id"
            ] = str(
                run_id
            )

        return document

    @classmethod
    def from_mongo_document(
        cls,
        document: Mapping[
            str,
            Any,
        ],
    ) -> Self:
        clean_document = dict(
            document
        )

        clean_document.pop(
            "_id",
            None,
        )

        return cls.model_validate(
            clean_document
        )


class RawEnvelopeBase(
    MongoDocumentModel
):
    """
    Metadata shared by raw page and raw-record envelopes.

    The payload is not transformed by this layer.
    """

    envelope_version: int = Field(
        default=1,
        ge=1,
    )

    run_id: UUID

    dataset_id: str = Field(
        min_length=1
    )

    resource_id: str = Field(
        min_length=1
    )

    parser_version: str = Field(
        default=DEFAULT_PARSER_VERSION,
        min_length=1,
    )

    retrieved_at: datetime

    page_number: int = Field(
        ge=1
    )

    page_offset: int = Field(
        ge=0
    )

    source_checksum: str = Field(
        pattern=_SHA256_PATTERN
    )

    @field_validator(
        "retrieved_at"
    )
    @classmethod
    def validate_retrieved_at(
        cls,
        value: datetime,
    ) -> datetime:
        return _as_utc(
            value,
            field_name=(
                "retrieved_at"
            ),
        )


class RawPageEnvelope(
    RawEnvelopeBase
):
    """
    Exact raw-page lineage envelope.

    `raw_bytes` preserves the exact HTTP response bytes used
    to calculate the page checksum.

    `payload` preserves the decoded JSON object without
    business transformation.
    """

    record_count: int = Field(
        ge=0
    )

    total_count: int = Field(
        ge=0
    )

    raw_bytes: bytes

    payload: Any

    def reconstruct_payload(
        self,
    ) -> Any:
        return deepcopy(
            self.payload
        )

    def reconstruct_raw_bytes(
        self,
    ) -> bytes:
        return bytes(
            self.raw_bytes
        )


class RawRecordEnvelope(
    RawEnvelopeBase
):
    """
    One source record with raw payload and lineage metadata.

    credit_number and end_of_period are query projections only.
    The original source object remains unchanged in `payload`.
    """

    record_index: int = Field(
        ge=0
    )

    source_record_offset: int = Field(
        ge=0
    )

    credit_number: str | None = None

    end_of_period: str | None = None

    payload: Any

    @model_validator(
        mode="after"
    )
    def validate_source_offset(
        self,
    ) -> Self:
        expected_offset = (
            self.page_offset
            + self.record_index
        )

        if (
            self.source_record_offset
            != expected_offset
        ):
            raise ValueError(
                "source_record_offset must "
                "equal page_offset + "
                "record_index"
            )

        return self

    @classmethod
    def from_source_payload(
        cls,
        *,
        run_id: UUID,
        dataset_id: str,
        resource_id: str,
        retrieved_at: datetime,
        page_number: int,
        page_offset: int,
        record_index: int,
        source_checksum: str,
        payload: Any,
        parser_version: str = (
            DEFAULT_PARSER_VERSION
        ),
    ) -> Self:
        credit_number: (
            str
            | None
        ) = None

        end_of_period: (
            str
            | None
        ) = None

        if isinstance(
            payload,
            Mapping,
        ):
            raw_credit_number = (
                payload.get(
                    "credit_number"
                )
            )

            raw_end_of_period = (
                payload.get(
                    "end_of_period"
                )
            )

            if isinstance(
                raw_credit_number,
                str,
            ):
                credit_number = (
                    raw_credit_number
                )

            if isinstance(
                raw_end_of_period,
                str,
            ):
                end_of_period = (
                    raw_end_of_period
                )

        return cls(
            run_id=run_id,
            dataset_id=dataset_id,
            resource_id=resource_id,
            parser_version=(
                parser_version
            ),
            retrieved_at=(
                retrieved_at
            ),
            page_number=(
                page_number
            ),
            page_offset=(
                page_offset
            ),
            source_checksum=(
                source_checksum
            ),
            record_index=(
                record_index
            ),
            source_record_offset=(
                page_offset
                + record_index
            ),
            credit_number=(
                credit_number
            ),
            end_of_period=(
                end_of_period
            ),
            payload=payload,
        )

    def reconstruct_payload(
        self,
    ) -> Any:
        return deepcopy(
            self.payload
        )


class RawIngestionRunReference(
    MongoDocumentModel
):
    """
    MongoDB reference to the authoritative ingestion-run identity.

    PostgreSQL remains authoritative for the run lifecycle.
    This Mongo document provides raw-lineage lookup context.
    """

    envelope_version: int = Field(
        default=1,
        ge=1,
    )

    run_id: UUID

    dataset_id: str = Field(
        min_length=1
    )

    resource_id: str = Field(
        min_length=1
    )

    started_at: datetime

    referenced_at: datetime

    status: str = Field(
        min_length=1
    )

    code_version: (
        str
        | None
    ) = None

    @field_validator(
        "started_at",
        "referenced_at",
    )
    @classmethod
    def validate_datetime(
        cls,
        value: datetime,
        info: Any,
    ) -> datetime:
        return _as_utc(
            value,
            field_name=(
                info.field_name
            ),
        )