"""Day-22 source-byte recovery and exact financial decimal regression tests."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from src.transformation.rehydration import (
    SourceRehydrationError,
    recover_exact_source_record,
)


@pytest.fixture
def source_page() -> bytes:
    return (
        b'{"data":[{"region":"South Asia","country_code":"IN",'
        b'"country":"India","project_id":"P123456",'
        b'"credit_number":"IDA12345","end_of_period":"30-Jun-2025",'
        b'"original_principal_amount_us_":0.10000000000000001, '
        b'"disbursed_amount_us_":1.000000000000000001}]}'
    )


def _recover(raw: bytes, *, index: int = 0) -> dict[str, object]:
    document = json.loads(raw)
    records = document.get("data", [])
    record = (
        records[index]
        if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(records)
        else {}
    )
    return recover_exact_source_record(
        raw,
        source_checksum=hashlib.sha256(raw).hexdigest(),
        record_index=index,
        stored_payload=record,
    )


def test_exact_decimal_recovered_and_stored_float_unchanged(
    source_page: bytes,
) -> None:
    decoded = json.loads(source_page)["data"][0]
    assert isinstance(decoded["original_principal_amount_us_"], float)
    recovered = _recover(source_page)
    assert recovered["original_principal_amount_us_"] == Decimal(
        "0.10000000000000001"
    )
    assert recovered["disbursed_amount_us_"] == Decimal(
        "1.000000000000000001"
    )
    assert decoded["original_principal_amount_us_"] == 0.1


def test_exact_payload_integrates_with_day22_pure_transform(source_page: bytes) -> None:
    from src.transformation.pure import transform_canonical_record

    result = transform_canonical_record(_recover(source_page))
    assert result["snapshot"]["original_principal_amount_usd"] == Decimal(
        "0.10000000000000001"
    )


def test_recovery_is_repeatable(source_page: bytes) -> None:
    assert _recover(source_page) == _recover(source_page)


def test_checksum_tampering_fails(source_page: bytes) -> None:
    with pytest.raises(SourceRehydrationError, match="SHA-256"):
        recover_exact_source_record(
            source_page + b" ",
            source_checksum=hashlib.sha256(source_page).hexdigest(),
            record_index=0,
            stored_payload=json.loads(source_page)["data"][0],
        )


def test_record_tampering_fails(source_page: bytes) -> None:
    with pytest.raises(SourceRehydrationError, match="differs"):
        recover_exact_source_record(
            source_page,
            source_checksum=hashlib.sha256(source_page).hexdigest(),
            record_index=0,
            stored_payload={"credit_number": "WRONG"},
        )


@pytest.mark.parametrize("index", [-1, 1, 500, True])
def test_out_of_range_or_invalid_record_index_fails(
    source_page: bytes,
    index: int,
) -> None:
    with pytest.raises(SourceRehydrationError):
        _recover(source_page, index=index)


def test_source_page_data_contract_fails() -> None:
    with pytest.raises(SourceRehydrationError, match="data"):
        _recover(b'{"records":[]}')


def test_nonfinite_json_is_rejected() -> None:
    with pytest.raises(SourceRehydrationError, match="numeric constant"):
        _recover(b'{"data":[{"value":NaN}]}')
