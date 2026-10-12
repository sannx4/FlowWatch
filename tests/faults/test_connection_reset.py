from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from src.ingestion.worldbank_client import (
    WorldBankClient,
    WorldBankClientConfig,
    WorldBankClientError,
)


def test_connection_reset_retries_then_fails_closed() -> None:
    session = Mock(
        spec=requests.Session
    )

    session.get.side_effect = (
        requests.ConnectionError(
            "injected connection reset"
        )
    )

    sleep_calls: list[float] = []

    client = WorldBankClient(
        config=WorldBankClientConfig(
            max_retries=2,
        ),
        session=session,
        sleep=sleep_calls.append,
    )

    with pytest.raises(
        WorldBankClientError
    ) as exc_info:
        client.fetch(
            top=5,
            skip=0,
        )

    error = exc_info.value

    assert (
        error.error_type
        == "connection_error"
    )

    assert error.attempts == 3

    assert error.retryable is True

    assert (
        session.get.call_count
        == 3
    )

    assert sleep_calls == [
        0.5,
        1.0,
    ]