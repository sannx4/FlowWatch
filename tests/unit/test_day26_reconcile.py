"""Deterministic Day26 partition proof and injected-loss tests (no DB required)."""
from __future__ import annotations

import pytest

from src.quality.reconcile import ReconciliationError, require_partition, unique_keys


@pytest.mark.parametrize("outcomes", [
    {"a": "INSERTED", "b": "REJECTED", "c": "UNCHANGED"},
    {"a": "UPDATED", "b": "IGNORED", "c": "INSERTED"},
    {"a": "UNCHANGED", "b": "UNCHANGED", "c": "UNCHANGED"},
])
def test_exact_three_way_partition(outcomes: dict[str, str]) -> None:
    got = require_partition(["a", "b", "c"], ["c", "a", "b"], outcomes)
    assert got["fetched"] == 3
    assert got["raw_stored"] == 3
    assert got["accepted"] + got["rejected"] == 3
    assert got["accepted"] == sum(got[name] for name in
                                  ("inserted", "updated", "unchanged", "ignored"))


def test_duplicate_source_key_rejected() -> None:
    with pytest.raises(ReconciliationError, match="duplicate"):
        require_partition(["a", "a"], ["a"], {"a": "INSERTED"})


def test_duplicate_raw_key_rejected() -> None:
    with pytest.raises(ReconciliationError, match="duplicate"):
        require_partition(["a"], ["a", "a"], {"a": "INSERTED"})


def test_missing_raw_key_fails_even_when_decisions_count_matches() -> None:
    with pytest.raises(ReconciliationError, match="raw/source mismatch"):
        require_partition(["a", "b"], ["a", "x"], {"a": "INSERTED", "b": "INSERTED"})


def test_missing_decision_fails_closed() -> None:
    with pytest.raises(ReconciliationError, match="unexplained loss"):
        require_partition(["a", "b"], ["a", "b"], {"a": "INSERTED"})


def test_unexpected_decision_rejected() -> None:
    with pytest.raises(ReconciliationError, match="extra decisions"):
        require_partition(["a"], ["a"], {"a": "INSERTED", "x": "UNCHANGED"})


def test_illegal_outcome_rejected() -> None:
    with pytest.raises(ReconciliationError, match="unsupported"):
        require_partition(["a"], ["a"], {"a": "SILENT_DROP"})


def test_empty_run_cannot_pass() -> None:
    with pytest.raises(ReconciliationError, match="zero source"):
        require_partition([], [], {})


def test_invalid_key_cannot_pass() -> None:
    with pytest.raises(ReconciliationError, match="invalid"):
        unique_keys(["a", ""], "test")


def test_mixed_accepted_and_rejected() -> None:
    got = require_partition(["a", "b", "c"], ["a", "b", "c"],
                            {"a": "INSERTED", "b": "REJECTED", "c": "IGNORED"})
    assert (got["accepted"], got["rejected"]) == (2, 1)
    assert got["inserted"] == 1 and got["ignored"] == 1
