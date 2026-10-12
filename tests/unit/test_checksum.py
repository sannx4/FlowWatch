import pytest

from src.ingestion.checksum import (
    checksum_matches,
    normalize_sha256,
    payload_changed,
    sha256_bytes,
)


def test_sha256_matches_known_vector() -> None:
    checksum = sha256_bytes(
        b"hello"
    )

    assert checksum == (
        "2cf24dba5fb0a30e"
        "26e83b2ac5b9e29e"
        "1b161e5c1fa7425e"
        "73043362938b9824"
    )


def test_identical_payload_has_same_checksum() -> None:
    payload = (
        b'{"count":1,"data":[{"id":1}]}'
    )

    first = sha256_bytes(
        payload
    )

    second = sha256_bytes(
        payload
    )

    assert first == second


def test_changed_payload_has_different_checksum() -> None:
    original = (
        b'{"count":1,"data":[{"id":1}]}'
    )

    changed = (
        b'{"count":1,"data":[{"id":2}]}'
    )

    assert (
        sha256_bytes(
            original
        )
        != sha256_bytes(
            changed
        )
    )


def test_checksum_matches_detects_payload_identity() -> None:
    payload = (
        b'{"count":1,"data":[{"id":1}]}'
    )

    checksum = sha256_bytes(
        payload
    )

    assert checksum_matches(
        payload,
        checksum,
    )

    assert not checksum_matches(
        payload + b" ",
        checksum,
    )


def test_payload_changed_detects_one_byte_change() -> None:
    original = b"flowwatch-page"
    checksum = sha256_bytes(
        original
    )

    assert not payload_changed(
        original,
        checksum,
    )

    assert payload_changed(
        original + b"!",
        checksum,
    )


def test_normalize_sha256_rejects_invalid_digest() -> None:
    with pytest.raises(
        ValueError,
        match="64 hexadecimal",
    ):
        normalize_sha256(
            "not-a-sha256"
        )


def test_sha256_rejects_non_bytes() -> None:
    with pytest.raises(
        TypeError,
        match="payload must be bytes",
    ):
        sha256_bytes(  # type: ignore[arg-type]
            "not-bytes"
        )