from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Self, TypeGuard
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.ingestion.raw_checksum import (
    checksum_record,
)
from src.ingestion.source_keys import (
    build_page_source_key,
    build_record_source_key,
)

DEFAULT_PARSER_VERSION = (
    "worldbank-source-v1"
)

_SHA256_PATTERN = (
    r"^[0-9a-f]{64}$"
)

_HEX_CHARS = frozenset(
    "0123456789abcdef"
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


def _is_sha256_hex(
    value: Any,
) -> TypeGuard[str]:
    """
    Return True only when value is a lowercase
    64-character SHA-256 hexadecimal digest.

    TypeGuard also tells mypy that a successful
    check guarantees value is str.
    """

    if not isinstance(
        value,
        str,
    ):
        return False

    if len(
        value
    ) != 64:
        return False

    return all(
        character
        in _HEX_CHARS
        for character in value
    )


def _populate_page_source_key(
    value: Mapping[
        str,
        Any,
    ],
) -> dict[str, Any]:
    """
    Generate page_source_key when it is absent.

    Invalid supplied values are not silently corrected.
    They remain available for Pydantic validation.

    This also allows legacy Day-15 documents that did not
    yet contain page_source_key to be reconstructed.
    """

    data = dict(
        value
    )

    if (
        "page_source_key"
        in data
        and data[
            "page_source_key"
        ]
        is not None
    ):
        return data

    dataset_id = data.get(
        "dataset_id"
    )

    resource_id = data.get(
        "resource_id"
    )

    page_offset = data.get(
        "page_offset"
    )

    source_checksum = data.get(
        "source_checksum"
    )

    if (
        isinstance(
            dataset_id,
            str,
        )
        and bool(
            dataset_id
        )
        and isinstance(
            resource_id,
            str,
        )
        and bool(
            resource_id
        )
        and isinstance(
            page_offset,
            int,
        )
        and page_offset >= 0
        and _is_sha256_hex(
            source_checksum
        )
    ):
        data[
            "page_source_key"
        ] = build_page_source_key(
            dataset_id=(
                dataset_id
            ),
            resource_id=(
                resource_id
            ),
            page_offset=(
                page_offset
            ),
            source_checksum=(
                source_checksum
            ),
        )

    return data


class MongoDocumentModel(
    BaseModel
):
    """
    Base model for FlowWatch MongoDB documents.

    MongoDB stores run UUIDs as strings so UUID representation
    settings cannot silently alter lineage identifiers.
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

    The raw payload is never transformed by this layer.

    page_source_key identifies a logical raw page version
    independently of ingestion execution identity.
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

    page_source_key: str = Field(
        default="",
        min_length=1,
    )

    @model_validator(
        mode="before"
    )
    @classmethod
    def populate_page_source_key(
        cls,
        value: Any,
    ) -> Any:
        if not isinstance(
            value,
            Mapping,
        ):
            return value

        return _populate_page_source_key(
            value
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

    @model_validator(
        mode="after"
    )
    def validate_page_source_key(
        self,
    ) -> Self:
        expected_key = (
            build_page_source_key(
                dataset_id=(
                    self.dataset_id
                ),
                resource_id=(
                    self.resource_id
                ),
                page_offset=(
                    self.page_offset
                ),
                source_checksum=(
                    self.source_checksum
                ),
            )
        )

        if (
            self.page_source_key
            != expected_key
        ):
            raise ValueError(
                "page_source_key does not "
                "match the deterministic "
                "source-page identity"
            )

        return self


class RawPageEnvelope(
    RawEnvelopeBase
):
    """
    Exact raw-page lineage envelope.

    raw_bytes preserves the exact HTTP response bytes used
    to calculate source_checksum.

    payload preserves the decoded source JSON without
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
    The original source object remains unchanged in payload.

    record_checksum identifies canonical logical record content.

    source_record_key provides deterministic Day-16 raw-record
    identity for idempotent MongoDB landing.
    """

    record_index: int = Field(
        ge=0
    )

    source_record_offset: int = Field(
        ge=0
    )

    record_checksum: str = Field(
        default="",
        pattern=_SHA256_PATTERN,
    )

    source_record_key: str = Field(
        default="",
        min_length=1,
    )

    credit_number: (
        str
        | None
    ) = None

    end_of_period: (
        str
        | None
    ) = None

    payload: Any

    @model_validator(
        mode="before"
    )
    @classmethod
    def populate_record_identity(
        cls,
        value: Any,
    ) -> Any:
        if not isinstance(
            value,
            Mapping,
        ):
            return value

        data = (
            _populate_page_source_key(
                value
            )
        )

        payload_present = (
            "payload"
            in data
        )

        if (
            (
                "record_checksum"
                not in data
                or data[
                    "record_checksum"
                ]
                is None
            )
            and payload_present
        ):
            data[
                "record_checksum"
            ] = checksum_record(
                data.get(
                    "payload"
                )
            )

        dataset_id = data.get(
            "dataset_id"
        )

        resource_id = data.get(
            "resource_id"
        )

        page_source_key = data.get(
            "page_source_key"
        )

        record_index = data.get(
            "record_index"
        )

        record_checksum = data.get(
            "record_checksum"
        )

        source_record_key_missing = (
            "source_record_key"
            not in data
            or data[
                "source_record_key"
            ]
            is None
        )

        if (
            source_record_key_missing
            and isinstance(
                dataset_id,
                str,
            )
            and bool(
                dataset_id
            )
            and isinstance(
                resource_id,
                str,
            )
            and bool(
                resource_id
            )
            and isinstance(
                page_source_key,
                str,
            )
            and bool(
                page_source_key
            )
            and isinstance(
                record_index,
                int,
            )
            and record_index >= 0
            and _is_sha256_hex(
                record_checksum
            )
        ):
            data[
                "source_record_key"
            ] = build_record_source_key(
                dataset_id=(
                    dataset_id
                ),
                resource_id=(
                    resource_id
                ),
                page_source_key=(
                    page_source_key
                ),
                record_index=(
                    record_index
                ),
                record_checksum=(
                    record_checksum
                ),
            )

        return data

    @model_validator(
        mode="after"
    )
    def validate_record_identity(
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

        expected_checksum = (
            checksum_record(
                self.payload
            )
        )

        if (
            self.record_checksum
            != expected_checksum
        ):
            raise ValueError(
                "record_checksum does not "
                "match the deterministic "
                "source-record payload "
                "checksum"
            )

        expected_source_key = (
            build_record_source_key(
                dataset_id=(
                    self.dataset_id
                ),
                resource_id=(
                    self.resource_id
                ),
                page_source_key=(
                    self.page_source_key
                ),
                record_index=(
                    self.record_index
                ),
                record_checksum=(
                    self.record_checksum
                ),
            )
        )

        if (
            self.source_record_key
            != expected_source_key
        ):
            raise ValueError(
                "source_record_key does not "
                "match the deterministic "
                "source-record identity"
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
        """
        Build an envelope from an unchanged source record.

        Deterministic Day-16 lineage fields are generated by
        Pydantic model validators rather than this factory.

        This keeps malformed source metadata inside Pydantic's
        validation path.
        """

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
            dataset_id=(
                dataset_id
            ),
            resource_id=(
                resource_id
            ),
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

    PostgreSQL remains authoritative for ingestion-run lifecycle.
    This document supplies raw-lineage lookup context.
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