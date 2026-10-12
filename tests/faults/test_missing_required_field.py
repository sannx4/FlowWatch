from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.validation.models import (
    RejectedRecordEnvelope,
    RejectionReasonCode,
    ValidationContext,
)
from src.validation.service import (
    SourceRecordValidationService,
)
from tests.faults.helpers import (
    TEST_RUN_ID,
)

FIXTURE_PATH = (
    Path(__file__).resolve()
    .parents[1]
    / "fixtures"
    / "validation"
    / "valid_worldbank_record.json"
)


def load_valid_record() -> dict[str, Any]:
    with FIXTURE_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(
            handle
        )


def test_missing_required_field_is_quarantined_while_page_continues() -> None:
    valid_record = (
        load_valid_record()
    )

    invalid_record = (
        load_valid_record()
    )

    del invalid_record[
        "credit_number"
    ]

    context = ValidationContext(
        run_id=TEST_RUN_ID,
        page_number=1,
        page_offset=0,
        source_checksum=(
            "a" * 64
        ),
    )

    service = (
        SourceRecordValidationService()
    )

    result = service.validate_page(
        [
            valid_record,
            invalid_record,
        ],
        context=context,
    )

    assert result.total_count == 2

    assert (
        result.accepted_count
        == 1
    )

    assert (
        result.rejected_count
        == 1
    )

    rejected = result.rejected[
        0
    ]

    assert isinstance(
        rejected,
        RejectedRecordEnvelope,
    )

    assert any(
        issue.reason_code
        == (
            RejectionReasonCode
            .MISSING_REQUIRED_FIELD
        )
        and issue.field_path
        == "credit_number"
        for issue
        in rejected.reasons
    )

    assert (
        result.accepted[
            0
        ].record.credit_number
        == "IDA00010"
    )