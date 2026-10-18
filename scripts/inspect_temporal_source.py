
"""Inspect real non-adjacent World Bank pages without changing databases."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.ingestion.worldbank_client import (
    WorldBankClient,
    WorldBankClientConfig,
)

PAGE_SIZE = 100

OFFSETS = (0, 100, 500, 700, 2000, 5000)

REPORT_PATH = Path(
    "reports/day20-temporal-source-inspection.json"
)

CHANGEABLE_CANDIDATES = (
    "credit_status",
    "borrower",
    "project_id",
    "country_code",
    "region",
    "currency_of_commitment",
)


def _value(value: Any) -> str:
    """Normalize a source value used for comparison."""

    if isinstance(value, str):
        return value.strip()

    return ""


def _record_hash(record: dict[str, Any]) -> str:
    """Calculate a deterministic checksum for one source record."""

    canonical = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def main() -> None:
    """Inspect source pages and generate temporal evidence."""

    identities: dict[
        tuple[str, str],
        list[dict[str, Any]],
    ] = defaultdict(list)

    attributes: dict[
        str,
        dict[str, set[str]],
    ] = defaultdict(
        lambda: defaultdict(set)
    )

    periods_by_credit: dict[
        str,
        set[str],
    ] = defaultdict(set)

    pages: list[dict[str, Any]] = []

    missing_identities: list[
        dict[str, Any]
    ] = []

    malformed_records: list[
        dict[str, Any]
    ] = []

    total_records = 0
    total_count: int | None = None

    config = WorldBankClientConfig(
        connect_timeout_seconds=5,
        read_timeout_seconds=30,
        max_retries=1,
    )

    with WorldBankClient(config=config) as client:

        for offset in OFFSETS:

            if (
                total_count is not None
                and offset >= total_count
            ):
                print(
                    f"Skipping offset {offset}: "
                    "beyond dataset end"
                )
                continue

            print(
                "Fetching World Bank page: "
                f"top={PAGE_SIZE}, skip={offset}"
            )

            response = client.fetch(
                top=PAGE_SIZE,
                skip=offset,
            )

            raw_records = response.payload["data"]

            if response.record_count != len(raw_records):
                raise ValueError(
                    f"Record count mismatch at offset {offset}"
                )

            if total_count is None:
                total_count = response.total_count

            elif response.total_count != total_count:
                raise ValueError(
                    "The source record count changed "
                    "between requests; rerun the inspection "
                    "for a consistent sample."
                )

            page_checksum = hashlib.sha256(
                response.raw_bytes
            ).hexdigest()

            pages.append(
                {
                    "offset": offset,
                    "requested_top": PAGE_SIZE,
                    "record_count": response.record_count,
                    "request_id": response.request_id,
                    "page_sha256": page_checksum,
                    "source_url": response.url,
                }
            )

            total_records += response.record_count

            for index, raw_record in enumerate(
                raw_records
            ):

                lineage = {
                    "page_offset": offset,
                    "record_index": index,
                    "page_sha256": page_checksum,
                    "request_id": response.request_id,
                }

                if not isinstance(
                    raw_record,
                    dict,
                ):
                    malformed_records.append(
                        lineage
                    )
                    continue

                credit = _value(
                    raw_record.get(
                        "credit_number"
                    )
                )

                period = _value(
                    raw_record.get(
                        "end_of_period"
                    )
                )

                if not credit or not period:
                    missing_identities.append(
                        lineage
                    )
                    continue

                periods_by_credit[
                    credit
                ].add(period)

                identities[
                    (credit, period)
                ].append(
                    {
                        **lineage,
                        "record_sha256": _record_hash(
                            raw_record
                        ),
                    }
                )

                for field in CHANGEABLE_CANDIDATES:

                    value = _value(
                        raw_record.get(field)
                    )

                    if value:
                        attributes[
                            credit
                        ][field].add(value)

    duplicate_identities = [
        {
            "credit_number": credit,
            "end_of_period": period,
            "occurrences": references,
            "conflicting_payloads": (
                len(
                    {
                        item["record_sha256"]
                        for item in references
                    }
                )
                > 1
            ),
        }
        for (credit, period), references in sorted(
            identities.items()
        )
        if len(references) > 1
    ]

    field_variation = {
        field: [
            {
                "credit_number": credit,
                "observed_values": sorted(
                    fields[field]
                ),
            }
            for credit, fields in sorted(
                attributes.items()
            )
            if len(fields[field]) > 1
        ]
        for field in CHANGEABLE_CANDIDATES
    }

    report = {
        "inspected_at_utc": datetime.now(
            UTC
        ).isoformat(),
        "dataset_id": config.dataset_id,
        "resource_id": config.resource_id,
        "source_reported_total_count": total_count,
        "sampling_policy": (
            "Explicit non-adjacent top/skip API "
            "requests; not a full scan"
        ),
        "page_size": PAGE_SIZE,
        "pages": pages,
        "inspected_records": total_records,
        "distinct_credits": len(
            periods_by_credit
        ),
        "distinct_credit_periods": len(
            identities
        ),
        "credits_with_multiple_periods": sum(
            len(periods) > 1
            for periods in periods_by_credit.values()
        ),
        "duplicate_credit_period_identities": (
            duplicate_identities
        ),
        "conflicting_credit_period_identities": sum(
            item["conflicting_payloads"]
            for item in duplicate_identities
        ),
        "missing_identity_lineage": (
            missing_identities
        ),
        "malformed_record_lineage": (
            malformed_records
        ),
        "field_variation": field_variation,
        "limitations": [
            "Sampled pages do not establish uniqueness across the full dataset.",
            "Requests are not guaranteed to be a consistent upstream snapshot.",
            "Field changes are descriptive observations, not validation failures.",
        ],
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    print(
        f"Inspected records: {total_records}"
    )

    print(
        f"Distinct credits: {len(periods_by_credit)}"
    )

    print(
        "Distinct credit-period identities: "
        f"{len(identities)}"
    )

    print(
        "Repeated credit-period identities: "
        f"{len(duplicate_identities)}"
    )

    print(
        "Conflicting repeated identities: "
        f"{report['conflicting_credit_period_identities']}"
    )

    for field, examples in field_variation.items():

        print(
            f"Credits with variation in {field}: "
            f"{len(examples)}"
        )

        for example in examples[:3]:

            print(
                f"  {example['credit_number']}: "
                f"{example['observed_values']}"
            )

    print(
        f"Evidence saved: {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()
