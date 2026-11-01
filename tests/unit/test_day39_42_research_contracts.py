"""Pure tests for causal-safe structural research evidence."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.warehouse.research_contracts import (
    FINANCIAL_COLUMNS,
    ResearchContractError,
    coverage_audit,
)


def row(month: int, credit: str = "A", *, year: int = 2024) -> dict[str, object]:
    from calendar import monthrange
    record: dict[str, object] = {
        "credit_number": credit,
        "end_of_period": date(year, month, monthrange(year, month)[1]),
        "country_code": "IN",
        "project_id": "P1",
    }
    record.update(dict.fromkeys(FINANCIAL_COLUMNS, Decimal("1.20")))
    return record


def test_horizon_counts_including_feature_history() -> None:
    samples = [row(m, year=y) for y in (2023, 2024) for m in range(1, 13)]
    report = coverage_audit(samples)
    assert report["horizon_structure"]["3"] == {
        "contiguous_future_windows": 21, "feature_mature_12m_windows": 10,
    }
    assert report["horizon_structure"]["6"]["feature_mature_12m_windows"] == 7
    assert report["horizon_structure"]["12"]["feature_mature_12m_windows"] == 1
    assert report["forecasting_readiness"] == "NOT_ESTABLISHED"


def test_missing_month_blocks_three_month_window() -> None:
    samples = [row(m) for m in (1, 2, 4, 5, 6)]
    report = coverage_audit(samples)
    assert report["per_credit"][0]["missing_months_between_endpoints"] == 1
    assert report["horizon_structure"]["3"]["contiguous_future_windows"] == 0


def test_null_and_negative_are_reported_not_imputed() -> None:
    value = row(1)
    value["disbursed_amount_usd"] = None
    value["undisbursed_amount_usd"] = Decimal("-10.00")
    report = coverage_audit([value])
    assert report["null_counts"]["disbursed_amount_usd"] == 1
    assert report["negative_value_counts_review_only"]["undisbursed_amount_usd"] == 1


def test_duplicate_credit_date_rejected() -> None:
    with pytest.raises(ResearchContractError, match="Duplicate"):
        coverage_audit([row(1), row(1)])


def test_multiple_dates_in_same_month_rejected() -> None:
    later = row(1)
    later["end_of_period"] = date(2024, 1, 15)
    with pytest.raises(ResearchContractError, match="Multiple snapshots"):
        coverage_audit([row(1), later])


def test_float_financial_values_rejected() -> None:
    value = row(1)
    value["disbursed_amount_usd"] = 1.5
    with pytest.raises(ResearchContractError, match="exact Decimal"):
        coverage_audit([value])


def test_no_observations_rejected() -> None:
    with pytest.raises(ResearchContractError, match="empty"):
        coverage_audit([])


def test_12_month_history_requires_all_prior_months() -> None:
    samples = [row(m, year=y) for y in (2023, 2024) for m in range(1, 13)]
    samples = [r for r in samples if r["end_of_period"] != date(2023, 7, 31)]
    report = coverage_audit(samples)
    assert report["horizon_structure"]["12"]["feature_mature_12m_windows"] == 0
