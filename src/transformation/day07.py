from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

SOURCE_DATE_FORMAT = "%d-%b-%Y"

REQUIRED_SOURCE_FIELDS = (
    "region",
    "country",
    "country_code",
    "project_id",
    "credit_number",
    "end_of_period",
)


def parse_source_date(value: Any) -> date | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return datetime.strptime(
        str(value),
        SOURCE_DATE_FORMAT,
    ).date()


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def validate_required_fields(
    record: Mapping[str, Any],
) -> None:
    missing = [
        field
        for field in REQUIRED_SOURCE_FIELDS
        if record.get(field) in (None, "")
    ]

    if missing:
        raise ValueError(
            f"Missing required source fields: {', '.join(missing)}"
        )


def canonical_record_bytes(
    record: Mapping[str, Any],
) -> bytes:
    return json.dumps(
        record,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def record_checksum(
    record: Mapping[str, Any],
) -> str:
    return hashlib.sha256(
        canonical_record_bytes(record)
    ).hexdigest()


def source_record_key(
    record: Mapping[str, Any],
) -> str:
    validate_required_fields(record)

    return (
        f"{record['credit_number']}"
        f"|{record['end_of_period']}"
    )


def transform_record(
    record: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    validate_required_fields(record)

    return {
        "region": {
            "region_name": record["region"],
        },
        "country": {
            "country_code": record["country_code"],
            "country_name": record["country"],
        },
        "project": {
            "project_id": record["project_id"],
            "project_name": record.get("project_name"),
        },
        "credit": {
            "credit_number": record["credit_number"],
            "borrower": record.get("borrower"),
            "currency_of_commitment": record.get(
                "currency_of_commitment"
            ),
            "board_approval_date": parse_source_date(
                record.get("board_approval_date")
            ),
            "agreement_signing_date": parse_source_date(
                record.get("agreement_signing_date")
            ),
            "effective_date": parse_source_date(
                record.get("effective_date_most_recent")
            ),
            "first_repayment_date": parse_source_date(
                record.get("first_repayment_date")
            ),
            "last_repayment_date": parse_source_date(
                record.get("last_repayment_date")
            ),
            "closed_date": parse_source_date(
                record.get("closed_date_most_recent")
            ),
        },
        "snapshot": {
            "end_of_period": parse_source_date(
                record["end_of_period"]
            ),
            "credit_status": record.get("credit_status"),
            "service_charge_rate": decimal_or_none(
                record.get("service_charge_rate")
            ),
            "original_principal_amount_usd": decimal_or_none(
                record.get("original_principal_amount_us_")
            ),
            "cancelled_amount_usd": decimal_or_none(
                record.get("cancelled_amount_us_")
            ),
            "undisbursed_amount_usd": decimal_or_none(
                record.get("undisbursed_amount_us_")
            ),
            "disbursed_amount_usd": decimal_or_none(
                record.get("disbursed_amount_us_")
            ),
            "repaid_to_ida_usd": decimal_or_none(
                record.get("repaid_to_ida_us_")
            ),
            "due_to_ida_usd": decimal_or_none(
                record.get("due_to_ida_us_")
            ),
            "exchange_adjustment_usd": decimal_or_none(
                record.get("exchange_adjustment_us_")
            ),
            "borrowers_obligation_usd": decimal_or_none(
                record.get("borrowers_obligation_us_")
            ),
            "sold_third_party_usd": decimal_or_none(
                record.get("sold_3rd_party_us_")
            ),
            "repaid_third_party_usd": decimal_or_none(
                record.get("repaid_3rd_party_us_")
            ),
            "due_third_party_usd": decimal_or_none(
                record.get("due_3rd_party_us_")
            ),
            "credits_held_usd": decimal_or_none(
                record.get("credits_held_us_")
            ),
            "last_disbursement_date": parse_source_date(
                record.get("last_disbursement_date")
            ),
        },
    }