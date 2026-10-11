from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.paginator import (
    PaginationConfig,
    PaginationContractError,
    WorldBankPaginator,
)
from src.ingestion.worldbank_client import (
    WorldBankResponse,
)


class FakeWorldBankClient:
    """Deterministic client used to test pagination logic."""

    def __init__(
        self,
        responses: list[WorldBankResponse],
    ) -> None:
        self._responses = iter(
            responses
        )

        self.calls: list[
            tuple[int, int]
        ] = []

    def fetch(
        self,
        *,
        top: int = 100,
        skip: int = 0,
    ) -> WorldBankResponse:
        self.calls.append(
            (
                top,
                skip,
            )
        )

        return next(
            self._responses
        )


def make_response(
    *,
    top: int,
    skip: int,
    total_count: int,
    records: list[Any],
    request_id: str,
    attempts: int = 1,
    status_code: int = 200,
) -> WorldBankResponse:
    payload = {
        "count": total_count,
        "data": records,
    }

    return WorldBankResponse(
        payload=payload,
        raw_bytes=b"test-page",
        status_code=status_code,
        request_id=request_id,
        url=(
            "https://example.test/"
            "worldbank"
        ),
        attempts=attempts,
        duration_ms=10.0,
        top=top,
        skip=skip,
        total_count=total_count,
        record_count=len(records),
    )


def record_identity(
    record: dict[str, str],
) -> str:
    return (
        f"{record['credit_number']}|"
        f"{record['end_of_period']}"
    )


def test_two_sequential_pages_have_expected_offsets_and_no_overlap(
) -> None:
    first_records = [
        {
            "credit_number": "IDA00010",
            "end_of_period": "30-Jun-2022",
        },
        {
            "credit_number": "IDA00010",
            "end_of_period": "31-May-2022",
        },
    ]

    second_records = [
        {
            "credit_number": "IDA00010",
            "end_of_period": "30-Apr-2022",
        },
        {
            "credit_number": "IDA00010",
            "end_of_period": "31-Mar-2022",
        },
    ]

    client = FakeWorldBankClient(
        [
            make_response(
                top=2,
                skip=0,
                total_count=4,
                records=first_records,
                request_id="request-1",
            ),
            make_response(
                top=2,
                skip=2,
                total_count=4,
                records=second_records,
                request_id="request-2",
            ),
        ]
    )

    paginator = WorldBankPaginator(
        client,
        PaginationConfig(
            page_size=2,
        ),
    )

    pages = list(
        paginator
    )

    assert client.calls == [
        (2, 0),
        (2, 2),
    ]

    assert len(pages) == 2

    assert pages[0].page_number == 1
    assert pages[0].offset == 0
    assert pages[0].record_count == 2

    assert pages[1].page_number == 2
    assert pages[1].offset == 2
    assert pages[1].record_count == 2

    first_ids = {
        record_identity(record)
        for record in pages[0].records
    }

    second_ids = {
        record_identity(record)
        for record in pages[1].records
    }

    assert first_ids.isdisjoint(
        second_ids
    )


def test_page_exposes_request_metadata() -> None:
    client = FakeWorldBankClient(
        [
            make_response(
                top=2,
                skip=0,
                total_count=2,
                records=[
                    {
                        "credit_number": "IDA00010",
                    },
                    {
                        "credit_number": "IDA00020",
                    },
                ],
                request_id="request-123",
                attempts=2,
            )
        ]
    )

    page = next(
        iter(
            WorldBankPaginator(
                client,
                PaginationConfig(
                    page_size=2,
                ),
            )
        )
    )

    assert (
        page.request.request_id
        == "request-123"
    )

    assert (
        page.request.status_code
        == 200
    )

    assert (
        page.request.attempts
        == 2
    )

    assert (
        page.request.requested_top
        == 2
    )

    assert (
        page.request.requested_skip
        == 0
    )

    assert page.total_count == 2


def test_partial_final_page_stops_iteration() -> None:
    client = FakeWorldBankClient(
        [
            make_response(
                top=2,
                skip=0,
                total_count=3,
                records=[
                    {"id": 1},
                    {"id": 2},
                ],
                request_id="request-1",
            ),
            make_response(
                top=2,
                skip=2,
                total_count=3,
                records=[
                    {"id": 3},
                ],
                request_id="request-2",
            ),
        ]
    )

    pages = list(
        WorldBankPaginator(
            client,
            PaginationConfig(
                page_size=2,
            ),
        )
    )

    assert len(pages) == 2

    assert client.calls == [
        (2, 0),
        (2, 2),
    ]

    assert (
        pages[1].record_count
        == 1
    )


def test_empty_dataset_yields_no_pages() -> None:
    client = FakeWorldBankClient(
        [
            make_response(
                top=100,
                skip=0,
                total_count=0,
                records=[],
                request_id="request-empty",
            )
        ]
    )

    pages = list(
        WorldBankPaginator(
            client
        )
    )

    assert pages == []

    assert client.calls == [
        (100, 0),
    ]


def test_max_pages_stops_before_next_request() -> None:
    client = FakeWorldBankClient(
        [
            make_response(
                top=2,
                skip=0,
                total_count=10,
                records=[
                    {"id": 1},
                    {"id": 2},
                ],
                request_id="request-1",
            )
        ]
    )

    pages = list(
        WorldBankPaginator(
            client,
            PaginationConfig(
                page_size=2,
                max_pages=1,
            ),
        )
    )

    assert len(pages) == 1

    assert client.calls == [
        (2, 0),
    ]


def test_start_skip_is_respected() -> None:
    client = FakeWorldBankClient(
        [
            make_response(
                top=2,
                skip=10,
                total_count=12,
                records=[
                    {"id": 11},
                    {"id": 12},
                ],
                request_id="request-1",
            )
        ]
    )

    pages = list(
        WorldBankPaginator(
            client,
            PaginationConfig(
                page_size=2,
                start_skip=10,
            ),
        )
    )

    assert len(pages) == 1

    assert pages[0].offset == 10

    assert client.calls == [
        (2, 10),
    ]


def test_empty_page_before_reported_end_fails_closed(
) -> None:
    client = FakeWorldBankClient(
        [
            make_response(
                top=2,
                skip=0,
                total_count=10,
                records=[],
                request_id="request-1",
            )
        ]
    )

    paginator = WorldBankPaginator(
        client,
        PaginationConfig(
            page_size=2,
        ),
    )

    with pytest.raises(
        PaginationContractError,
        match="empty page",
    ):
        list(paginator)


def test_response_skip_must_match_requested_offset(
) -> None:
    client = FakeWorldBankClient(
        [
            make_response(
                top=2,
                skip=1,
                total_count=4,
                records=[
                    {"id": 1},
                    {"id": 2},
                ],
                request_id="request-1",
            )
        ]
    )

    paginator = WorldBankPaginator(
        client,
        PaginationConfig(
            page_size=2,
        ),
    )

    with pytest.raises(
        PaginationContractError,
        match="skip",
    ):
        list(paginator)


def test_response_top_must_match_page_size() -> None:
    client = FakeWorldBankClient(
        [
            make_response(
                top=3,
                skip=0,
                total_count=3,
                records=[
                    {"id": 1},
                    {"id": 2},
                    {"id": 3},
                ],
                request_id="request-1",
            )
        ]
    )

    paginator = WorldBankPaginator(
        client,
        PaginationConfig(
            page_size=2,
        ),
    )

    with pytest.raises(
        PaginationContractError,
        match="top",
    ):
        list(paginator)


@pytest.mark.parametrize(
    "page_size",
    [
        0,
        -1,
    ],
)
def test_invalid_page_size_is_rejected(
    page_size: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="page_size",
    ):
        PaginationConfig(
            page_size=page_size
        )


def test_negative_start_skip_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="start_skip",
    ):
        PaginationConfig(
            start_skip=-1
        )


@pytest.mark.parametrize(
    "max_pages",
    [
        0,
        -1,
    ],
)
def test_invalid_max_pages_is_rejected(
    max_pages: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="max_pages",
    ):
        PaginationConfig(
            max_pages=max_pages
        )