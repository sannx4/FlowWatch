"""Offline tests for the localhost-only Day 2 API acceptance probe."""
from __future__ import annotations

import io
import sys
from typing import Self
from urllib.error import HTTPError

import pytest

from scripts import day2_live_smoke as smoke


class FakeResponse:
    status = 200

    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return self.data


def test_rejects_external_destinations(monkeypatch: pytest.MonkeyPatch) -> None:
    for base in ("https://example.com", "http://example.com", "http://127.0.0.1:8000@external.example"):
        monkeypatch.setattr(sys, "argv", ["smoke", "--base-url", base])
        with pytest.raises(SystemExit) as exc:
            smoke.main()
        assert exc.value.code == 2


def test_get_and_authorization_header(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str | None]] = []

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        assert timeout == 15
        seen.append((request.get_method(), request.get_header("Authorization")))  # type: ignore[attr-defined]
        return FakeResponse(b'{"status":"alive"}')

    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)
    assert smoke.call("http://127.0.0.1:8000", "/api/v1/health/live", token="not-a-real-token") == {"status": "alive"}
    assert seen == [("GET", "Bearer not-a-real-token")]


def test_denial_response_never_echoes_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        raise HTTPError("http://127.0.0.1:8000", 403, "Forbidden",
                        {}, io.BytesIO(b'{"secret":"do-not-log-this"}'))

    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)
    with pytest.raises(AssertionError) as exc:
        smoke.call("http://127.0.0.1:8000", "/api/v1/operations/warehouse", expected=401)
    assert "secret" not in str(exc.value)
    assert "403" in str(exc.value)


def test_expected_unauthorized_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        raise HTTPError("http://127.0.0.1:8000", 401, "Unauthorized", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)
    assert smoke.call("http://127.0.0.1:8000", "/api/v1/portfolio/summary", expected=401) == {}
