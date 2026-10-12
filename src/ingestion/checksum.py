import re
from hashlib import sha256
from hmac import compare_digest

_SHA256_PATTERN = re.compile(
    r"^[0-9a-fA-F]{64}$"
)


def sha256_bytes(
    payload: bytes,
) -> str:
    """Return the SHA-256 digest of exact raw payload bytes."""

    if not isinstance(
        payload,
        bytes,
    ):
        raise TypeError(
            "payload must be bytes"
        )

    return sha256(
        payload
    ).hexdigest()


def normalize_sha256(
    checksum: str,
) -> str:
    """Validate and normalize a SHA-256 hexadecimal digest."""

    if not isinstance(
        checksum,
        str,
    ):
        raise TypeError(
            "checksum must be a string"
        )

    normalized = checksum.strip().lower()

    if not _SHA256_PATTERN.fullmatch(
        normalized
    ):
        raise ValueError(
            "checksum must contain exactly "
            "64 hexadecimal characters"
        )

    return normalized


def checksum_matches(
    payload: bytes,
    expected_checksum: str,
) -> bool:
    """Return whether raw bytes match an expected SHA-256 digest."""

    expected = normalize_sha256(
        expected_checksum
    )

    actual = sha256_bytes(
        payload
    )

    return compare_digest(
        actual,
        expected,
    )


def payload_changed(
    payload: bytes,
    expected_checksum: str,
) -> bool:
    """Return True when payload bytes differ from the manifest."""

    return not checksum_matches(
        payload,
        expected_checksum,
    )