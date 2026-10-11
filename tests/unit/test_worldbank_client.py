from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest
import requests

from src.ingestion.worldbank_client import (
    DEFAULT_USER_AGENT,
    WorldBankClient,
    WorldBankClientConfig,
    WorldBankClientError,
)


def make_response(
    status_code: int,
    payload: object | None = None,
    *,
    raw_bytes: bytes | None = None,
) -> requests.Response:
    response = requests.Response()

    response.status_code = (
        status_code
    )

    response.url = (
        "https://example.test/worldbank"
    )

    if raw_bytes is not None:
        response._content = raw_bytes

    elif payload is not None:
        response._content = json.dumps(
            payload
        ).encode("utf-8")

    else:
        response._content = b""

    response.encoding = "utf-8"

    response.headers[
        "Content-Type"
    ] = "application/json"

    return response


def valid_payload() -> dict[str, object]:
    return {
        "count": 2,
        "data": [
            {
                "credit_number": "IDA00010",
            },
            {
                "credit_number": "IDA00020",
            },
        ],
    }


def test_successful_request_is_validated() -> None:
    session = Mock(
        spec=requests.Session
    )

    response = make_response(
        200,
        valid_payload(),
    )

    session.get.return_value = (
        response
    )

    client = WorldBankClient(
        session=session
    )

    result = client.fetch(
        top=2,
        skip=0,
    )

    assert result.status_code == 200
    assert result.attempts == 1
    assert result.total_count == 2
    assert result.record_count == 2

    assert (
        result.payload["data"][0][
            "credit_number"
        ]
        == "IDA00010"
    )


def test_request_uses_user_agent_and_timeouts() -> None:
    session = Mock(
        spec=requests.Session
    )

    session.get.return_value = (
        make_response(
            200,
            valid_payload(),
        )
    )

    config = WorldBankClientConfig(
        connect_timeout_seconds=1.5,
        read_timeout_seconds=4.0,
        max_retries=0,
    )

    client = WorldBankClient(
        config,
        session=session,
    )

    client.fetch(
        top=2,
        skip=10,
    )

    call = session.get.call_args

    assert call.kwargs["timeout"] == (
        1.5,
        4.0,
    )

    assert (
        call.kwargs["headers"][
            "User-Agent"
        ]
        == DEFAULT_USER_AGENT
    )

    assert (
        call.kwargs["headers"]["Accept"]
        == "application/json"
    )

    assert call.kwargs["params"] == {
        "datasetId": "DS00976",
        "resourceId": "RS00906",
        "top": 2,
        "skip": 10,
        "type": "json",
    }


def test_timeout_stops_after_retry_budget() -> None:
    session = Mock(
        spec=requests.Session
    )

    session.get.side_effect = (
        requests.exceptions.Timeout(
            "simulated timeout"
        )
    )

    sleep_calls: list[float] = []

    config = WorldBankClientConfig(
        max_retries=2,
        backoff_base_seconds=0.25,
        backoff_max_seconds=2.0,
    )

    client = WorldBankClient(
        config,
        session=session,
        sleep=sleep_calls.append,
    )

    with patch(
        "src.ingestion."
        "worldbank_client.log_event"
    ) as mocked_log_event, pytest.raises(
        WorldBankClientError
    ) as exc_info:
        client.fetch()

    error = exc_info.value

    # 1 initial attempt + 2 retries.
    assert session.get.call_count == 3

    assert error.error_type == "timeout"
    assert error.retryable is True
    assert error.attempts == 3
    assert error.max_attempts == 3
    assert error.status_code is None

    # Sleep only occurs BETWEEN attempts.
    assert sleep_calls == [
        0.25,
        0.5,
    ]

    metadata = error.metadata()

    assert metadata[
        "error_type"
    ] == "timeout"

    assert metadata[
        "attempts"
    ] == 3

    assert metadata[
        "max_attempts"
    ] == 3

    failure_calls = [
        call
        for call
        in mocked_log_event.call_args_list
        if call.args[1]
        == "worldbank_request_failed"
    ]

    assert len(failure_calls) == 1

    failure = failure_calls[0]

    assert (
        failure.kwargs["error_type"]
        == "timeout"
    )

    assert (
        failure.kwargs["attempts"]
        == 3
    )

    assert (
        failure.kwargs["max_attempts"]
        == 3
    )

    assert (
        failure.kwargs["retryable"]
        is True
    )


def test_5xx_stops_after_retry_budget() -> None:
    session = Mock(
        spec=requests.Session
    )

    session.get.side_effect = [
        make_response(
            503,
            {
                "message": (
                    "temporarily unavailable"
                )
            },
        ),
        make_response(
            503,
            {
                "message": (
                    "temporarily unavailable"
                )
            },
        ),
        make_response(
            503,
            {
                "message": (
                    "temporarily unavailable"
                )
            },
        ),
    ]

    sleep_calls: list[float] = []

    config = WorldBankClientConfig(
        max_retries=2,
        backoff_base_seconds=0.5,
        backoff_max_seconds=5.0,
    )

    client = WorldBankClient(
        config,
        session=session,
        sleep=sleep_calls.append,
    )

    with pytest.raises(
        WorldBankClientError
    ) as exc_info:
        client.fetch()

    error = exc_info.value

    assert session.get.call_count == 3

    assert (
        error.error_type
        == "retryable_http_status"
    )

    assert error.status_code == 503
    assert error.retryable is True

    assert error.attempts == 3
    assert error.max_attempts == 3

    assert sleep_calls == [
        0.5,
        1.0,
    ]


def test_retry_can_recover_to_success() -> None:
    session = Mock(
        spec=requests.Session
    )

    session.get.side_effect = [
        make_response(
            503,
            {
                "message": (
                    "temporary failure"
                )
            },
        ),
        make_response(
            200,
            valid_payload(),
        ),
    ]

    sleep_calls: list[float] = []

    config = WorldBankClientConfig(
        max_retries=3,
        backoff_base_seconds=0.5,
    )

    client = WorldBankClient(
        config,
        session=session,
        sleep=sleep_calls.append,
    )

    result = client.fetch(
        top=2,
    )

    assert session.get.call_count == 2

    assert result.status_code == 200
    assert result.attempts == 2

    assert sleep_calls == [
        0.5,
    ]


def test_404_fails_without_retry() -> None:
    session = Mock(
        spec=requests.Session
    )

    session.get.return_value = (
        make_response(
            404,
            {
                "message": (
                    "not found"
                )
            },
        )
    )

    sleep_calls: list[float] = []

    client = WorldBankClient(
        WorldBankClientConfig(
            max_retries=5,
        ),
        session=session,
        sleep=sleep_calls.append,
    )

    with pytest.raises(
        WorldBankClientError
    ) as exc_info:
        client.fetch()

    error = exc_info.value

    assert session.get.call_count == 1

    assert (
        error.error_type
        == "http_status"
    )

    assert error.status_code == 404
    assert error.retryable is False

    assert sleep_calls == []


def test_malformed_json_fails_closed() -> None:
    session = Mock(
        spec=requests.Session
    )

    session.get.return_value = (
        make_response(
            200,
            raw_bytes=b"{not-json",
        )
    )

    client = WorldBankClient(
        session=session
    )

    with pytest.raises(
        WorldBankClientError
    ) as exc_info:
        client.fetch()

    error = exc_info.value

    assert (
        error.error_type
        == "invalid_json"
    )

    assert error.retryable is False
    assert session.get.call_count == 1


def test_invalid_payload_shape_fails_closed() -> None:
    session = Mock(
        spec=requests.Session
    )

    session.get.return_value = (
        make_response(
            200,
            {
                "count": 1,
                "records": [],
            },
        )
    )

    client = WorldBankClient(
        session=session
    )

    with pytest.raises(
        WorldBankClientError
    ) as exc_info:
        client.fetch()

    error = exc_info.value

    assert (
        error.error_type
        == "invalid_payload"
    )

    assert error.retryable is False
    assert session.get.call_count == 1


def test_raw_response_bytes_are_preserved() -> None:
    session = Mock(
        spec=requests.Session
    )

    raw_bytes = (
        b'{"count":1,"data":'
        b'[{"credit_number":"IDA00010"}]}'
    )

    session.get.return_value = (
        make_response(
            200,
            raw_bytes=raw_bytes,
        )
    )

    client = WorldBankClient(
        session=session
    )

    result = client.fetch(
        top=1
    )

    assert (
        result.raw_bytes
        == raw_bytes
    )


@pytest.mark.parametrize(
    (
        "top",
        "skip",
    ),
    [
        (0, 0),
        (-1, 0),
    ],
)
def test_invalid_top_is_rejected(
    top: int,
    skip: int,
) -> None:
    client = WorldBankClient(
        session=Mock(
            spec=requests.Session
        )
    )

    with pytest.raises(
        ValueError,
        match="top",
    ):
        client.fetch(
            top=top,
            skip=skip,
        )


def test_negative_skip_is_rejected() -> None:
    client = WorldBankClient(
        session=Mock(
            spec=requests.Session
        )
    )

    with pytest.raises(
        ValueError,
        match="skip",
    ):
        client.fetch(
            top=100,
            skip=-1,
        )