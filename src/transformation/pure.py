"""Pure World Bank IDA source -> canonical table-values mapping (Day 22).

Compatibility target: the five dictionaries returned by Day-7 transform_record.
No persistence, API calls, timestamps, or mutation of caller input.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from src.transformation.types import (
    CanonicalValues,
    CountryValues,
    CreditValues,
    ProjectValues,
    RegionValues,
    SnapshotValues,
    optional_date,
    optional_decimal,
    optional_text,
    required_date,
    required_text,
)

# Source keys intentionally match the existing Day-7 mapping, including
# truncation in the World Bank API's published monetary field names.
MONEY_FIELDS: dict[str, str] = {
    "service_charge_rate": "service_charge_rate",
    "original_principal_amount_usd": "original_principal_amount_us_",
    "cancelled_amount_usd": "cancelled_amount_us_",
    "undisbursed_amount_usd": "undisbursed_amount_us_",
    "disbursed_amount_usd": "disbursed_amount_us_",
    "repaid_to_ida_usd": "repaid_to_ida_us_",
    "due_to_ida_usd": "due_to_ida_us_",
    "exchange_adjustment_usd": "exchange_adjustment_us_",
    "borrowers_obligation_usd": "borrowers_obligation_us_",
    "sold_third_party_usd": "sold_3rd_party_us_",
    "repaid_third_party_usd": "repaid_3rd_party_us_",
    "due_third_party_usd": "due_3rd_party_us_",
    "credits_held_usd": "credits_held_us_",
}


def transform_region(record: Mapping[str, Any]) -> RegionValues:
    return {"region_name": required_text(record.get("region"), field="region")}


def transform_country(record: Mapping[str, Any]) -> CountryValues:
    return {
        "country_code": required_text(record.get("country_code"), field="country_code"),
        "country_name": required_text(record.get("country"), field="country"),
    }


def transform_project(record: Mapping[str, Any]) -> ProjectValues:
    return {
        "project_id": required_text(record.get("project_id"), field="project_id"),
        "project_name": optional_text(record.get("project_name"), field="project_name"),
    }


def transform_credit(record: Mapping[str, Any]) -> CreditValues:
    return {
        "credit_number": required_text(record.get("credit_number"), field="credit_number"),
        "borrower": optional_text(record.get("borrower"), field="borrower"),
        "currency_of_commitment": optional_text(
            record.get("currency_of_commitment"), field="currency_of_commitment"
        ),
        "board_approval_date": optional_date(
            record.get("board_approval_date"), field="board_approval_date"
        ),
        "agreement_signing_date": optional_date(
            record.get("agreement_signing_date"), field="agreement_signing_date"
        ),
        "effective_date": optional_date(
            record.get("effective_date_most_recent"), field="effective_date_most_recent"
        ),
        "first_repayment_date": optional_date(
            record.get("first_repayment_date"), field="first_repayment_date"
        ),
        "last_repayment_date": optional_date(
            record.get("last_repayment_date"), field="last_repayment_date"
        ),
        "closed_date": optional_date(
            record.get("closed_date_most_recent"), field="closed_date_most_recent"
        ),
    }


def transform_snapshot(record: Mapping[str, Any]) -> SnapshotValues:
    money = {
        canonical: optional_decimal(record.get(source), field=source)
        for canonical, source in MONEY_FIELDS.items()
    }
    return {
        "end_of_period": required_date(record.get("end_of_period"), field="end_of_period"),
        "credit_status": optional_text(record.get("credit_status"), field="credit_status"),
        "service_charge_rate": money["service_charge_rate"],
        "original_principal_amount_usd": money["original_principal_amount_usd"],
        "cancelled_amount_usd": money["cancelled_amount_usd"],
        "undisbursed_amount_usd": money["undisbursed_amount_usd"],
        "disbursed_amount_usd": money["disbursed_amount_usd"],
        "repaid_to_ida_usd": money["repaid_to_ida_usd"],
        "due_to_ida_usd": money["due_to_ida_usd"],
        "exchange_adjustment_usd": money["exchange_adjustment_usd"],
        "borrowers_obligation_usd": money["borrowers_obligation_usd"],
        "sold_third_party_usd": money["sold_third_party_usd"],
        "repaid_third_party_usd": money["repaid_third_party_usd"],
        "due_third_party_usd": money["due_third_party_usd"],
        "credits_held_usd": money["credits_held_usd"],
        "last_disbursement_date": optional_date(
            record.get("last_disbursement_date"), field="last_disbursement_date"
        ),
    }


def transform_canonical_record(record: Mapping[str, Any]) -> CanonicalValues:
    """Return newly allocated, typed canonical dictionaries for one raw record."""
    return {
        "region": transform_region(record),
        "country": transform_country(record),
        "project": transform_project(record),
        "credit": transform_credit(record),
        "snapshot": transform_snapshot(record),
    }


def _encode_canonical(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported canonical fingerprint value: {type(value).__name__}")


def canonical_fingerprint(record: Mapping[str, Any]) -> str:
    """Deterministic SHA-256 of the canonical fields, independent of dict ordering."""
    canonical = transform_canonical_record(record)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_encode_canonical,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
