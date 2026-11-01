"""Pure historical coverage and maturity diagnostics, with no forecasting claims."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

HORIZONS = (3, 6, 12)
FINANCIAL_COLUMNS = (
    "service_charge_rate",
    "original_principal_amount_usd", "cancelled_amount_usd",
    "undisbursed_amount_usd", "disbursed_amount_usd",
    "repaid_to_ida_usd", "due_to_ida_usd",
    "exchange_adjustment_usd", "borrowers_obligation_usd",
    "sold_third_party_usd", "repaid_third_party_usd",
    "due_third_party_usd", "credits_held_usd",
)


class ResearchContractError(RuntimeError):
    """Research evidence cannot be safely interpreted or published."""


def month_id(value: date) -> int:
    if not isinstance(value, date):
        raise ResearchContractError("Reporting periods must be dates")
    return value.year * 12 + value.month


def coverage_audit(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Count observed sequence structure; no target labels and no imputations.

    For an anchor t, an h-month structural label window requires each month
    t+1,...,t+h to exist. The 12-month feature-mature variant additionally
    requires months t-11,...,t. Neither condition proves target validity.
    """
    data = list(rows)
    if not data:
        raise ResearchContractError("Research dataset is empty")
    columns = FINANCIAL_COLUMNS
    by_credit: dict[str, set[int]] = defaultdict(set)
    periods_by_credit: dict[str, list[date]] = defaultdict(list)
    null_counts: dict[str, int] = {name: 0 for name in columns}
    negative_counts: dict[str, int] = {name: 0 for name in columns}
    countries: set[str] = set()
    projects: set[str] = set()
    positions: set[tuple[str, date]] = set()
    months_not_eom = 0
    from calendar import monthrange

    for row in data:
        credit = row.get("credit_number")
        period = row.get("end_of_period")
        if not isinstance(credit, str) or not credit or not isinstance(period, date):
            raise ResearchContractError("Invalid credit/date identity")
        if (credit, period) in positions:
            raise ResearchContractError("Duplicate credit/reporting-date identity")
        positions.add((credit, period))
        mi = month_id(period)
        if mi in by_credit[credit]:
            raise ResearchContractError("Multiple snapshots for one credit/month; month sequence ambiguous")
        by_credit[credit].add(mi)
        periods_by_credit[credit].append(period)
        if period.day != monthrange(period.year, period.month)[1]:
            months_not_eom += 1
        country = row.get("country_code")
        project = row.get("project_id")
        if not country or not project:
            raise ResearchContractError("Country or project identity missing")
        countries.add(str(country))
        projects.add(str(project))
        for name in columns:
            value = row.get(name)
            if value is None:
                null_counts[name] += 1
            elif not isinstance(value, Decimal):
                raise ResearchContractError(f"{name} is not an exact Decimal")
            elif not value.is_finite():
                raise ResearchContractError(f"{name} is nonfinite")
            elif value < 0:
                negative_counts[name] += 1

    profile: list[dict[str, Any]] = []
    horizon_totals: dict[str, dict[str, int]] = {
        str(h): {"contiguous_future_windows": 0, "feature_mature_12m_windows": 0}
        for h in HORIZONS
    }
    for credit in sorted(by_credit):
        months = sorted(by_credit[credit])
        available = set(months)
        longest = run = 0
        gap_months = 0
        for i, mi in enumerate(months):
            if i and mi == months[i - 1] + 1:
                run += 1
            else:
                run = 1
            longest = max(longest, run)
            if i:
                gap_months += mi - months[i - 1] - 1
        counts: dict[str, dict[str, int]] = {}
        for horizon in HORIZONS:
            candidate = sum(
                all(mi + offset in available for offset in range(1, horizon + 1))
                for mi in months
            )
            feature_mature = sum(
                all(mi - offset in available for offset in range(12))
                and all(mi + offset in available for offset in range(1, horizon + 1))
                for mi in months
            )
            horizon_totals[str(horizon)]["contiguous_future_windows"] += candidate
            horizon_totals[str(horizon)]["feature_mature_12m_windows"] += feature_mature
            counts[str(horizon)] = {
                "contiguous_future_windows": candidate,
                "feature_mature_12m_windows": feature_mature,
            }
        dates = sorted(periods_by_credit[credit])
        profile.append({
            "credit_number": credit,
            "observation_count": len(months),
            "first_observation": dates[0].isoformat(),
            "last_observation": dates[-1].isoformat(),
            "span_months_inclusive": months[-1] - months[0] + 1,
            "missing_months_between_endpoints": gap_months,
            "longest_contiguous_month_run": longest,
            "horizon_structure": counts,
        })

    all_dates = [p for periods in periods_by_credit.values() for p in periods]
    return {
        "status": "PASS_DESCRIPTIVE_COVERAGE_AUDIT",
        "observations": len(data),
        "unique_credits": len(by_credit),
        "unique_projects": len(projects),
        "unique_countries": len(countries),
        "earliest_date": min(all_dates).isoformat(),
        "latest_date": max(all_dates).isoformat(),
        "non_month_end_dates": months_not_eom,
        "missing_last_disbursement_dates": sum(
            row.get("last_disbursement_date") is None for row in data
        ),
        "missing_credit_status": sum(row.get("credit_status") is None for row in data),
        "null_counts": null_counts,
        "negative_value_counts_review_only": negative_counts,
        "horizon_structure": horizon_totals,
        "per_credit": profile,
        "forecasting_readiness": "NOT_ESTABLISHED",
        "interpretation": (
            "3/6/12-month counts are structurally contiguous windows only, not verified "
            "labels, independent samples, or time-split/model-ready training examples. "
            "A 12-month pre-anchor history is a feature-maturity proxy only."
        ),
    }
