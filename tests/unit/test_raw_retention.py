from __future__ import annotations

from uuid import uuid4

import pytest

from src.ingestion.raw_retention import (
    RawRetentionDenied,
    assess_raw_retention,
    require_raw_deletion_authorization,
)


def test_missing_manifest_denies_deletion() -> None:
    result = assess_raw_retention(
        uuid4()
    )

    assert result.allowed is False

    assert (
        result.reason_code
        == "ARCHIVE_MANIFEST_MISSING"
    )


def test_claimed_verified_manifest_still_denies_deletion() -> None:
    result = assess_raw_retention(
        uuid4(),
        archive_manifest={
            "archive_verified": True,
        },
    )

    assert result.allowed is False

    assert (
        result.reason_code
        == "ARCHIVE_NOT_INDEPENDENTLY_VERIFIED"
    )


def test_authorization_entrypoint_always_fails_closed() -> None:
    with pytest.raises(
        RawRetentionDenied
    ):
        require_raw_deletion_authorization(
            uuid4()
        )

    with pytest.raises(
        RawRetentionDenied
    ):
        require_raw_deletion_authorization(
            uuid4(),
            archive_manifest={
                "archive_verified": True,
            },
        )


def test_invalid_run_identity_is_rejected() -> None:
    with pytest.raises(
        ValueError
    ):
        assess_raw_retention(
            "not-a-uuid"
        )