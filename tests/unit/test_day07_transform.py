from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from src.transformation.day07 import (
    parse_source_date,
    record_checksum,
    source_record_key,
    transform_record,
)

REAL_SOURCE_RECORD = {
    "agreement_signing_date": "12-May-1961",
    "board_approval_date": "11-May-1961",
    "borrower": "MINISTERIO DE HACIENDA Y CREDITO PUBLICO",
    "borrowers_obligation_us_": 0,
    "cancelled_amount_us_": 572026.03,
    "closed_date_most_recent": "31-Jul-1967",
    "country": "Honduras",
    "country_code": "HN",
    "credit_number": "IDA00010",
    "credit_status": "Fully Repaid",
    "credits_held_us_": 0,
    "currency_of_commitment": "USD",
    "disbursed_amount_us_": 8427973.97,
    "due_3rd_party_us_": 0,
    "due_to_ida_us_": 0,
    "effective_date_most_recent": "29-Jun-1961",
    "end_of_period": "30-Jun-2022",
    "exchange_adjustment_us_": "0",
    "first_repayment_date": "01-Sep-1971",
    "last_disbursement_date": None,
    "last_repayment_date": "01-Mar-2011",
    "original_principal_amount_us_": 9000000,
    "project_id": "P007335",
    "project_name": "WESTERN HIGHWAY",
    "region": "LATIN AMERICA AND CARIBBEAN",
    "repaid_3rd_party_us_": 0,
    "repaid_to_ida_us_": 8427973.97,
    "service_charge_rate": 0.75,
    "sold_3rd_party_us_": 0,
    "undisbursed_amount_us_": 0,
}


def test_parse_source_date() -> None:
    assert parse_source_date(
        "30-Jun-2022"
    ) == date(2022, 6, 30)


def test_parse_null_source_date() -> None:
    assert parse_source_date(None) is None


def test_source_record_key() -> None:
    assert source_record_key(
        REAL_SOURCE_RECORD
    ) == "IDA00010|30-Jun-2022"


def test_checksum_is_deterministic() -> None:
    first = record_checksum(
        REAL_SOURCE_RECORD
    )

    second = record_checksum(
        deepcopy(REAL_SOURCE_RECORD)
    )

    assert first == second
    assert len(first) == 64


def test_transform_preserves_identity() -> None:
    transformed = transform_record(
        REAL_SOURCE_RECORD
    )

    assert (
        transformed["region"]["region_name"]
        == "LATIN AMERICA AND CARIBBEAN"
    )

    assert (
        transformed["country"]["country_code"]
        == "HN"
    )

    assert (
        transformed["country"]["country_name"]
        == "Honduras"
    )

    assert (
        transformed["project"]["project_id"]
        == "P007335"
    )

    assert (
        transformed["credit"]["credit_number"]
        == "IDA00010"
    )

    assert (
        transformed["snapshot"]["end_of_period"]
        == date(2022, 6, 30)
    )


def test_transform_uses_decimal_for_money() -> None:
    transformed = transform_record(
        REAL_SOURCE_RECORD
    )

    assert (
        transformed["snapshot"][
            "original_principal_amount_usd"
        ]
        == Decimal(9000000)
    )

    assert (
        transformed["snapshot"][
            "service_charge_rate"
        ]
        == Decimal("0.75")
    )


def test_transform_does_not_mutate_raw_record() -> None:
    original = deepcopy(
        REAL_SOURCE_RECORD
    )

    transform_record(
        REAL_SOURCE_RECORD
    )

    assert REAL_SOURCE_RECORD == original


def test_required_identity_field_is_rejected() -> None:
    record = deepcopy(
        REAL_SOURCE_RECORD
    )

    record["credit_number"] = None

    with pytest.raises(
        ValueError,
        match="credit_number",
    ):
        transform_record(record)