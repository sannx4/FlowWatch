from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
import requests

from src.ingestion.worldbank_client import (
    WorldBankClient,
    WorldBankClientConfig,
    WorldBankClientError,
)


def test_malformed_json_fails_closed_without_retry() -> None:
    session = Mock(
        spec=requests.Session
    )

    response = Mock(
        spec=requests.Response
    )

    response.status_code = 200

    response.url = (
        "https://datacatalogapi.worldbank.org/"
        "dexapps/fone/api/apiservice"
    )

    response.content = (
        b'{"count":'
    )

    response.json.side_effect = (
        json.JSONDecodeError(
            "Expecting value",
            '{"count":',
            9,
        )
    )

    session.get.return_value = (
        response
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
        == "invalid_json"
    )

    assert error.attempts == 1

    assert (
        session.get.call_count
        == 1
    )

    assert sleep_calls == []