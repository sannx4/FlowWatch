"""Pure, strict scalar converters for source-to-canonical finance data.

No database, network, clock, timezone or locale dependencies.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict

_WB_DATE_PATTERN = re.compile(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})\Z")
_MONTHS = {name.lower(): index for index, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    start=1,
)}
_DECIMAL_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


class TransformationError(ValueError):
    """Source value cannot be represented safely as a canonical value."""


class RegionValues(TypedDict):
    region_name: str


class CountryValues(TypedDict):
    country_code: str
    country_name: str


class ProjectValues(TypedDict):
    project_id: str
    project_name: str | None


class CreditValues(TypedDict):
    credit_number: str
    borrower: str | None
    currency_of_commitment: str | None
    board_approval_date: date | None
    agreement_signing_date: date | None
    effective_date: date | None
    first_repayment_date: date | None
    last_repayment_date: date | None
    closed_date: date | None


class SnapshotValues(TypedDict):
    end_of_period: date
    credit_status: str | None
    service_charge_rate: Decimal | None
    original_principal_amount_usd: Decimal | None
    cancelled_amount_usd: Decimal | None
    undisbursed_amount_usd: Decimal | None
    disbursed_amount_usd: Decimal | None
    repaid_to_ida_usd: Decimal | None
    due_to_ida_usd: Decimal | None
    exchange_adjustment_usd: Decimal | None
    borrowers_obligation_usd: Decimal | None
    sold_third_party_usd: Decimal | None
    repaid_third_party_usd: Decimal | None
    due_third_party_usd: Decimal | None
    credits_held_usd: Decimal | None
    last_disbursement_date: date | None


class CanonicalValues(TypedDict):
    region: RegionValues
    country: CountryValues
    project: ProjectValues
    credit: CreditValues
    snapshot: SnapshotValues


def optional_text(value: Any, *, field: str) -> str | None:
    """Map None/blank strings to null; otherwise require an actual string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TransformationError(f"{field}: expected text, got {type(value).__name__}")
    cleaned = value.strip()
    return cleaned or None


def required_text(value: Any, *, field: str) -> str:
    cleaned = optional_text(value, field=field)
    if cleaned is None:
        raise TransformationError(f"{field}: required nonempty text is missing")
    return cleaned


def optional_date(value: Any, *, field: str) -> date | None:
    """Accept the World Bank DD-Mon-YYYY format or strict ISO calendar dates."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value
    elif isinstance(value, str):
        raw = value.strip()
        match = _WB_DATE_PATTERN.fullmatch(raw)
        if match is not None:
            day_text, month_text, year_text = match.groups()
            month = _MONTHS.get(month_text.lower())
            if month is None:
                raise TransformationError(f"{field}: unknown World Bank month {month_text!r}")
            try:
                return date(int(year_text), month, int(day_text))
            except ValueError as exc:
                raise TransformationError(f"{field}: invalid World Bank date {raw!r}") from exc
        if len(raw) == 10 and raw[4:5] == "-" and raw[7:8] == "-":
            try:
                return date.fromisoformat(raw)
            except ValueError as exc:
                raise TransformationError(f"{field}: invalid ISO date {raw!r}") from exc
        if "T" not in raw:
            raise TransformationError(f"{field}: unsupported date format {raw!r}")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise TransformationError(f"{field}: invalid ISO date/time {raw!r}") from exc
    else:
        raise TransformationError(f"{field}: unsupported date type {type(value).__name__}")

    if parsed.tzinfo is not None and parsed.utcoffset() != UTC.utcoffset(None):
        raise TransformationError(f"{field}: expected UTC timestamp, not a local offset")
    if parsed.time().replace(tzinfo=None) != datetime.min.time():
        raise TransformationError(f"{field}: timestamp must represent UTC midnight")
    return parsed.date()


def required_date(value: Any, *, field: str) -> date:
    result = optional_date(value, field=field)
    if result is None:
        raise TransformationError(f"{field}: reporting date is required")
    return result


def optional_decimal(value: Any, *, field: str) -> Decimal | None:
    """Parse base-10 values without binary-float conversion or quantization."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, (bool, float)):
        raise TransformationError(
            f"{field}: binary floats and booleans are forbidden; "
            "parse JSON financial numbers with parse_float=Decimal"
        )
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not _DECIMAL_PATTERN.fullmatch(raw):
            raise TransformationError(f"{field}: invalid base-10 number {raw!r}")
        try:
            result = Decimal(raw)
        except InvalidOperation as exc:
            raise TransformationError(f"{field}: invalid decimal {raw!r}") from exc
    else:
        raise TransformationError(f"{field}: unsupported numeric type {type(value).__name__}")
    if not result.is_finite():
        raise TransformationError(f"{field}: NaN or infinity is forbidden")
    return result
