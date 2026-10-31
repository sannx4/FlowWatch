"""Day33 deterministic partition and date-profile contracts (no DB needed)."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from scripts.day33_update_ci_head import patch_ci_workflow
from src.warehouse.historical_contracts import (
    HistoricalCanonicalIntegrityError,
    assert_identity_partition,
    profile_canonical_keys,
)


def test_exact_partition_and_balance() -> None:
    result = assert_identity_partition(
        ["a", "b", "c"], ["c", "a", "b"],
        {"a": "INSERTED", "b": "UNCHANGED", "c": "REJECTED"},
    )
    assert result == {
        "fetched": 3, "accepted": 2, "rejected": 1,
        "inserted": 1, "updated": 0, "unchanged": 1, "ignored": 0,
    }


@pytest.mark.parametrize(
    "source,raw,decisions",
    [
        ([], [], {}),
        (["a", "a"], ["a"], {"a": "INSERTED"}),
        (["a", "b"], ["a"], {"a": "INSERTED", "b": "REJECTED"}),
        (["a"], ["a", "a"], {"a": "INSERTED"}),
        (["a"], ["a"], {}),
        (["a"], ["a"], {"a": "UNKNOWN"}),
    ],
)
def test_fail_closed_source_identity_partition(
    source: list[str], raw: list[str], decisions: dict[str, str],
) -> None:
    with pytest.raises(HistoricalCanonicalIntegrityError):
        assert_identity_partition(source, raw, decisions)


def test_real_date_order_not_lexicographic_order() -> None:
    result = profile_canonical_keys([
        ("IDA00001", date(2024, 12, 31)),
        ("IDA00001", date(2023, 1, 31)),
        ("IDA00001", date(2023, 1, 31)),
        ("IDA00002", date(2024, 6, 30)),
    ])
    assert result == {
        "observations": 4,
        "unique_temporal_keys": 3,
        "duplicate_temporal_observations": 1,
        "earliest_date": "2023-01-31",
        "latest_date": "2024-12-31",
        "unique_credits": 2,
    }


def test_empty_profile() -> None:
    result = profile_canonical_keys([])
    assert result["observations"] == 0
    assert result["earliest_date"] is None


@pytest.mark.parametrize("bad", [("", date(2024, 1, 1)),
                                  ("C1", datetime(2024, 1, 1))])
def test_invalid_temporal_key_rejected(bad: tuple[str, date]) -> None:
    with pytest.raises(HistoricalCanonicalIntegrityError):
        profile_canonical_keys([bad])


def test_ci_patch_changes_only_head() -> None:
    source = (
        "jobs:\n"
        "      - name: Apply all schema migrations\n"
        "        run: |\n"
        "          python -m alembic upgrade head\n"
        "          echo \"revision = 'd29b00000001'\"\n"
        "      - name: Next step\n"
        "        run: echo d26e00260001\n"
    )
    patched = patch_ci_workflow(source)
    assert "revision = 'd33c00000001'" in patched
    assert "echo d26e00260001" in patched
    assert patch_ci_workflow(patched) == patched


def test_ci_patch_refuses_missing_marker() -> None:
    with pytest.raises(ValueError):
        patch_ci_workflow("some unrelated workflow")
