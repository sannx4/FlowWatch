from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from src.ingestion.checksum import (
    sha256_bytes,
)
from src.validation.models import (
    RejectionReasonCode,
    ValidationContext,
)
from src.validation.service import (
    SourceRecordValidationService,
)

ROOT = (
    Path(__file__).resolve()
    .parents[1]
)


FIXTURE_DIR = (
    ROOT
    / "tests"
    / "fixtures"
    / "validation"
)


def load_fixture(
    filename: str,
) -> dict[str, Any]:
    with (
        FIXTURE_DIR
        / filename
    ).open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(
            handle
        )


def main() -> None:
    valid = load_fixture(
        "valid_worldbank_record.json"
    )

    malformed_date = load_fixture(
        "invalid_date_worldbank_record.json"
    )

    malformed_numeric = load_fixture(
        "invalid_numeric_worldbank_record.json"
    )

    records = [
        valid,
        malformed_date,
        malformed_numeric,
    ]

    fixture_page_bytes = json.dumps(
        records,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    context = ValidationContext(
        run_id=UUID(
            "12121212-1212-1212-1212-121212121212"
        ),
        page_number=1,
        page_offset=0,
        source_checksum=(
            sha256_bytes(
                fixture_page_bytes
            )
        ),
    )

    service = (
        SourceRecordValidationService()
    )

    result = service.validate_page(
        records,
        context=context,
    )

    print()
    print(
        "DAY 12 VALIDATION PROOF"
    )
    print(
        "total_records:",
        result.total_count,
    )
    print(
        "accepted_records:",
        result.accepted_count,
    )
    print(
        "rejected_records:",
        result.rejected_count,
    )

    assert (
        result.total_count
        == 3
    )

    assert (
        result.accepted_count
        == 1
    )

    assert (
        result.rejected_count
        == 2
    )

    rejection_codes = {
        issue.reason_code
        for rejected_record
        in result.rejected
        for issue
        in rejected_record.reasons
    }

    assert (
        RejectionReasonCode.INVALID_DATE
        in rejection_codes
    )

    assert (
        RejectionReasonCode.INVALID_NUMERIC
        in rejection_codes
    )

    print()
    print(
        "MALFORMED DATE"
    )
    print(
        "input:",
        malformed_date[
            "end_of_period"
        ],
    )
    print(
        "result: QUARANTINED"
    )
    print(
        "reason:",
        RejectionReasonCode.INVALID_DATE.value,
    )

    print()
    print(
        "MALFORMED NUMERIC"
    )
    print(
        "input:",
        malformed_numeric[
            "disbursed_amount_us_"
        ],
    )
    print(
        "result: QUARANTINED"
    )
    print(
        "reason:",
        (
            RejectionReasonCode
            .INVALID_NUMERIC
            .value
        ),
    )

    print()
    print(
        "VALID RECORD"
    )
    print(
        "credit_number:",
        result.accepted[
            0
        ].record.credit_number,
    )
    print(
        "end_of_period:",
        result.accepted[
            0
        ].record.end_of_period,
    )
    print(
        "result: ACCEPTED"
    )

    print()
    print(
        "RUN CONTINUED AFTER BAD RECORDS: YES"
    )

    print()
    print(
        "DAY 12 PROOF PASSED"
    )


if __name__ == "__main__":
    main()