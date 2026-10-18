"""Read-only profile of monetary values and dates in World Bank pages."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.ingestion.worldbank_client import (
    WorldBankClient,
    WorldBankClientConfig,
)
from src.validation.source_record import (
    DATE_FIELDS,
    DECIMAL_FIELDS,
    WorldBankSourceRecord,
)

OFFSETS = (0, 100, 500, 700, 2000, 5000)
PAGE_SIZE = 100
REPORT_PATH = Path("reports/day20-financial-date-profile.json")
MAX_EXAMPLES = 10

# Hypotheses to examine, NOT automatic rejection conditions.
DATE_PAIRS = {
    "approval_after_signing": (
        "board_approval_date",
        "agreement_signing_date",
    ),
    "first_repayment_after_last_repayment": (
        "first_repayment_date",
        "last_repayment_date",
    ),
    "effective_after_closing": (
        "effective_date_most_recent",
        "closed_date_most_recent",
    ),
}


def _reference(
    raw: dict[str, Any], *, offset: int, index: int, checksum: str
) -> dict[str, Any]:
    return {
        "credit_number": raw.get("credit_number"),
        "end_of_period": raw.get("end_of_period"),
        "page_offset": offset,
        "record_index": index,
        "page_sha256": checksum,
    }


def main() -> None:
    """Fetch bounded samples, profile candidates, and write evidence."""
    config = WorldBankClientConfig(max_retries=1)
    amount_stats: dict[str, dict[str, Any]] = {
        field: {
            "present": 0,
            "null": 0,
            "negative": 0,
            "zero": 0,
            "positive": 0,
            "negative_examples": [],
        }
        for field in sorted(DECIMAL_FIELDS)
    }
    minimum: dict[str, Decimal] = {}
    maximum: dict[str, Decimal] = {}
    date_null: dict[str, int] = dict.fromkeys(sorted(DATE_FIELDS), 0)
    date_checks: dict[str, dict[str, Any]] = {
        label: {"comparable": 0, "reversed": 0, "examples": []}
        for label in DATE_PAIRS
    }
    cross_checks: dict[str, dict[str, Any]] = {
        "disbursed_greater_than_original": {
            "comparable": 0,
            "observed": 0,
            "examples": [],
        },
        "sum_disbursed_undisbursed_cancelled_differs_from_original": {
            "comparable": 0,
            "observed": 0,
            "examples": [],
        },
    }
    pages: list[dict[str, Any]] = []
    parse_failures: list[dict[str, Any]] = []
    records_seen = 0
    parsed_count = 0
    total_count: int | None = None

    with WorldBankClient(config=config) as client:
        for offset in OFFSETS:
            if total_count is not None and offset >= total_count:
                print(f"Skipping offset {offset}: outside dataset")
                continue

            print(f"Fetching page top={PAGE_SIZE}, skip={offset}", flush=True)
            response = client.fetch(top=PAGE_SIZE, skip=offset)
            rows = response.payload["data"]
            if not isinstance(rows, list):
                raise TypeError("World Bank response data must be a list")
            if response.record_count != len(rows):
                raise ValueError("Source response record_count mismatch")
            if total_count is None:
                total_count = response.total_count
            elif total_count != response.total_count:
                raise ValueError("Source total count changed during inspection")

            page_checksum = hashlib.sha256(response.raw_bytes).hexdigest()
            pages.append(
                {
                    "offset": offset,
                    "count": len(rows),
                    "request_id": response.request_id,
                    "page_sha256": page_checksum,
                }
            )
            records_seen += len(rows)

            for index, raw in enumerate(rows):
                if not isinstance(raw, dict):
                    parse_failures.append(
                        {
                            "page_offset": offset,
                            "record_index": index,
                            "page_sha256": page_checksum,
                            "reason": "not_a_json_object",
                        }
                    )
                    continue
                ref = _reference(
                    raw, offset=offset, index=index, checksum=page_checksum
                )
                try:
                    record = WorldBankSourceRecord.model_validate(raw)
                except ValidationError as exc:
                    parse_failures.append(
                        {
                            **ref,
                            "fields": [
                                ".".join(map(str, item["loc"]))
                                for item in exc.errors(include_url=False)
                            ],
                        }
                    )
                    continue

                parsed_count += 1
                for field in sorted(DECIMAL_FIELDS):
                    amount: Decimal | None = getattr(record, field)
                    stats = amount_stats[field]
                    if amount is None:
                        stats["null"] += 1
                        continue
                    stats["present"] += 1
                    if field not in minimum or amount < minimum[field]:
                        minimum[field] = amount
                    if field not in maximum or amount > maximum[field]:
                        maximum[field] = amount
                    if amount < 0:
                        stats["negative"] += 1
                        if len(stats["negative_examples"]) < MAX_EXAMPLES:
                            stats["negative_examples"].append(
                                {**ref, "value": str(amount)}
                            )
                    elif amount == 0:
                        stats["zero"] += 1
                    else:
                        stats["positive"] += 1

                original = record.original_principal_amount_us_
                disbursed = record.disbursed_amount_us_
                undisbursed = record.undisbursed_amount_us_
                cancelled = record.cancelled_amount_us_
                if original is not None and disbursed is not None:
                    check = cross_checks["disbursed_greater_than_original"]
                    check["comparable"] += 1
                    if disbursed > original:
                        check["observed"] += 1
                        if len(check["examples"]) < MAX_EXAMPLES:
                            check["examples"].append(
                                {**ref, "original": str(original),
                                 "disbursed": str(disbursed)}
                            )
                if all(
                    number is not None
                    for number in (original, disbursed, undisbursed, cancelled)
                ):
                    assert original is not None
                    assert disbursed is not None
                    assert undisbursed is not None
                    assert cancelled is not None
                    difference = disbursed + undisbursed + cancelled - original
                    check = cross_checks[
                        "sum_disbursed_undisbursed_cancelled_differs_from_original"
                    ]
                    check["comparable"] += 1
                    if abs(difference) > Decimal("1.00"):
                        check["observed"] += 1
                        if len(check["examples"]) < MAX_EXAMPLES:
                            check["examples"].append(
                                {**ref, "difference_usd": str(difference)}
                            )

                for field in DATE_FIELDS:
                    if getattr(record, field) is None:
                        date_null[field] += 1

                for label, (earlier_field, later_field) in DATE_PAIRS.items():
                    earlier = getattr(record, earlier_field)
                    later = getattr(record, later_field)
                    if earlier is None or later is None:
                        continue
                    checks = date_checks[label]
                    checks["comparable"] += 1
                    if earlier > later:
                        checks["reversed"] += 1
                        if len(checks["examples"]) < MAX_EXAMPLES:
                            checks["examples"].append(
                                {
                                    **ref,
                                    earlier_field: earlier.isoformat(),
                                    later_field: later.isoformat(),
                                }
                            )

    for field, stats in amount_stats.items():
        stats["min"] = str(minimum[field]) if field in minimum else None
        stats["max"] = str(maximum[field]) if field in maximum else None

    report = {
        "profiled_at_utc": datetime.now(UTC).isoformat(),
        "dataset_id": config.dataset_id,
        "resource_id": config.resource_id,
        "source_reported_total_count": total_count,
        "source_pages": pages,
        "source_records_inspected": records_seen,
        "records_parsed": parsed_count,
        "parse_failures": parse_failures,
        "amount_fields": amount_stats,
        "null_date_counts": date_null,
        "date_relation_diagnostics": date_checks,
        "cross_field_diagnostics": cross_checks,
        "policy": "Observations only. No new rejection rules enforced.",
        "limitations": [
            "Non-adjacent pages are not a representative random sample.",
            "Date-order diagnostics are not established business constraints.",
            "Currency and financial-adjustment semantics need source review.",
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Source records inspected: {records_seen}")
    print(f"Successfully parsed: {parsed_count}")
    print(f"Source parsing failures: {len(parse_failures)}")
    for field, stats in amount_stats.items():
        print(
            f"{field}: negative={stats['negative']} "
            f"min={stats['min']} max={stats['max']}"
        )
    for label, stats in date_checks.items():
        print(
            f"{label}: reversed={stats['reversed']} "
            f"out of {stats['comparable']} comparable"
        )
    for label, stats in cross_checks.items():
        print(
            f"{label}: observed={stats['observed']} "
            f"out of {stats['comparable']} comparable"
        )
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
