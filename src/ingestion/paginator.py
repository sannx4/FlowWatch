from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from src.ingestion.worldbank_client import WorldBankResponse


class WorldBankPageFetcher(Protocol):
    """Minimum client contract required by the paginator."""

    def fetch(
        self,
        *,
        top: int = 100,
        skip: int = 0,
    ) -> WorldBankResponse:
        """Fetch one World Bank source page."""
        ...


class PaginationContractError(RuntimeError):
    """Raised when page metadata violates the pagination contract."""


@dataclass(frozen=True, slots=True)
class PaginationConfig:
    """Configuration controlling deterministic top/skip pagination."""

    page_size: int = 100
    start_skip: int = 0
    max_pages: int | None = None

    def __post_init__(self) -> None:
        if self.page_size <= 0:
            raise ValueError(
                "page_size must be greater than zero."
            )

        if self.start_skip < 0:
            raise ValueError(
                "start_skip cannot be negative."
            )

        if (
            self.max_pages is not None
            and self.max_pages <= 0
        ):
            raise ValueError(
                "max_pages must be greater than zero "
                "when provided."
            )


@dataclass(frozen=True, slots=True)
class PageRequestMetadata:
    """Request-level metadata inherited from WorldBankClient."""

    request_id: str

    status_code: int

    attempts: int
    duration_ms: float

    url: str

    requested_top: int
    requested_skip: int


@dataclass(frozen=True, slots=True)
class WorldBankPage:
    """One validated page produced by the paginator."""

    page_number: int
    offset: int

    record_count: int
    total_count: int

    records: tuple[Any, ...]

    raw_bytes: bytes

    request: PageRequestMetadata


class WorldBankPaginator:
    """Iterate over World Bank data using deterministic top/skip pages."""

    def __init__(
        self,
        client: WorldBankPageFetcher,
        config: PaginationConfig | None = None,
    ) -> None:
        self.client = client

        self.config = (
            config
            if config is not None
            else PaginationConfig()
        )

    def __iter__(self) -> Iterator[WorldBankPage]:
        """Yield validated pages until the source is exhausted."""

        page_number = 1
        offset = self.config.start_skip
        pages_yielded = 0

        while True:
            if (
                self.config.max_pages is not None
                and pages_yielded
                >= self.config.max_pages
            ):
                return

            response = self.client.fetch(
                top=self.config.page_size,
                skip=offset,
            )

            self._validate_response(
                response,
                expected_top=self.config.page_size,
                expected_skip=offset,
            )

            if response.record_count == 0:
                if offset < response.total_count:
                    raise PaginationContractError(
                        "World Bank returned an empty page "
                        "before the reported dataset end: "
                        f"offset={offset}, "
                        f"total_count={response.total_count}."
                    )

                return

            records = tuple(
                response.payload["data"]
            )

            page = WorldBankPage(
                page_number=page_number,
                offset=offset,
                record_count=response.record_count,
                total_count=response.total_count,
                records=records,
                raw_bytes=response.raw_bytes,
                request=PageRequestMetadata(
                    request_id=response.request_id,
                    status_code=response.status_code,
                    attempts=response.attempts,
                    duration_ms=response.duration_ms,
                    url=response.url,
                    requested_top=response.top,
                    requested_skip=response.skip,
                ),
            )

            yield page

            pages_yielded += 1

            # A short page means the source has reached
            # the end of the available result set.
            if (
                response.record_count
                < self.config.page_size
            ):
                return

            next_offset = (
                offset
                + self.config.page_size
            )

            # Avoid an unnecessary empty request when the
            # current page reaches the reported source end.
            if (
                next_offset
                >= response.total_count
            ):
                return

            offset = next_offset
            page_number += 1

    @staticmethod
    def _validate_response(
        response: WorldBankResponse,
        *,
        expected_top: int,
        expected_skip: int,
    ) -> None:
        """Validate client metadata against the paginator request."""

        if response.top != expected_top:
            raise PaginationContractError(
                "Client response top does not match "
                "the paginator request: "
                f"expected={expected_top}, "
                f"actual={response.top}."
            )

        if response.skip != expected_skip:
            raise PaginationContractError(
                "Client response skip does not match "
                "the paginator offset: "
                f"expected={expected_skip}, "
                f"actual={response.skip}."
            )

        records = response.payload.get(
            "data"
        )

        if not isinstance(
            records,
            list,
        ):
            raise PaginationContractError(
                "Client response payload does not "
                "contain a list-valued 'data' field."
            )

        if (
            response.record_count
            != len(records)
        ):
            raise PaginationContractError(
                "Client response record_count does not "
                "match the number of payload records."
            )

        if (
            response.record_count
            > expected_top
        ):
            raise PaginationContractError(
                "Source returned more records than the "
                "requested page size: "
                f"requested={expected_top}, "
                f"returned={response.record_count}."
            )

        if response.total_count < 0:
            raise PaginationContractError(
                "Source total_count cannot be negative."
            )

        if response.record_count < 0:
            raise PaginationContractError(
                "Source record_count cannot be negative."
            )

        if (
            response.record_count > 0
            and (
                expected_skip
                + response.record_count
                > response.total_count
            )
        ):
            raise PaginationContractError(
                "Page extends beyond the source's "
                "reported total_count."
            )