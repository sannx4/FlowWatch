
"""Run the Day-20 quality pipeline on real World Bank pages.

Read-only inspection: does not write to PostgreSQL or MongoDB.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from src.ingestion.worldbank_client import (
    WorldBankClient,
    WorldBankClientConfig,
)
from src.quality.temporal import TemporalIdentityScanner
from src.quality.validator import QualityValidationService
from src.validation.models import ValidationContext

PAGE_SIZE = 100
OFFSETS = (0, 100, 500, 700, 2000, 5000)

OUTPUT = Path(
    "reports/day20-live-quality-validation.json"
)


def main() -> None:
    """Validate non-adjacent source pages using one temporal scanner."""

    config = WorldBankClientConfig(max_retries=1)

    inspection_run_id = uuid4()

    quality_service = QualityValidationService(
        temporal_scanner=TemporalIdentityScanner(),
    )

    pages: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    warned: list[dict[str, object]] = []

    warning_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()

    inspected_count = 0
    accepted_count = 0
    total_count: int | None = None

    with WorldBankClient(config=config) as client:
        for offset in OFFSETS:
            if total_count is not None and offset >= total_count:
                print(f"Skipping offset {offset}: beyond source total")
                continue

            print(
                f"Validating World Bank page: "
                f"top={PAGE_SIZE}, skip={offset}"
            )

            response = client.fetch(
                top=PAGE_SIZE,
                skip=offset,
            )

            raw_records = response.payload["data"]

            if not isinstance(raw_records, list):
                raise TypeError(
                    "Expected World Bank 'data' to be a list"
                )

            if len(raw_records) != response.record_count:
                raise ValueError(
                    f"Record count mismatch at offset {offset}"
                )

            if total_count is None:
                total_count = response.total_count
            elif total_count != response.total_count:
                raise ValueError(
                    "World Bank record count changed during inspection."
                )

            page_sha256 = hashlib.sha256(
                response.raw_bytes
            ).hexdigest()

            context = ValidationContext(
                run_id=inspection_run_id,
                page_number=(offset // PAGE_SIZE) + 1,
                page_offset=offset,
                source_checksum=page_sha256,
            )

            result = quality_service.validate_page(
                raw_records,
                context=context,
            )

            inspected_count += result.total_count
            accepted_count += result.accepted_count

            pages.append(
                {
                    "offset": offset,
                    "source_request_id": response.request_id,
                    "source_url": response.url,
                    "page_sha256": page_sha256,
                    "records": result.total_count,
                    "accepted": result.accepted_count,
                    "rejected": result.rejected_count,
                    "records_with_warnings": result.warning_count,
                }
            )

            for item in result.rejected:
                rejected.append(
                    item.model_dump(mode="json")
                )

                for rule_id in item.rule_ids:
                    rejection_counts[rule_id.value] += 1

            for item in result.warnings:
                warned.append(
                    item.model_dump(mode="json")
                )

                for warning in item.warnings:
                    warning_counts[warning.rule_id.value] += 1

    report = {
        "inspected_at_utc": datetime.now(UTC).isoformat(),
        "inspection_run_id": str(inspection_run_id),
        "inspection_run_id_is_not_a_persisted_ingestion_run": True,
        "dataset_id": config.dataset_id,
        "resource_id": config.resource_id,
        "source_reported_total_count": total_count,
        "requested_offsets": list(OFFSETS),
        "page_size": PAGE_SIZE,
        "inspected_records": inspected_count,
        "accepted_records": accepted_count,
        "rejected_records": len(rejected),
        "records_with_warnings": len(warned),
        "warning_conditions": sum(warning_counts.values()),
        "warning_rule_counts": dict(sorted(warning_counts.items())),
        "rejection_rule_counts": dict(sorted(rejection_counts.items())),
        "pages": pages,
        "rejections_with_raw_lineage": rejected,
        "warnings_with_raw_lineage": warned,
        "limitations": [
            "Only six non-adjacent pages were inspected, not the full dataset.",
            "Independent live requests are not an atomic upstream snapshot.",
            "The scanner detects duplicates only within this inspection run.",
            "Warnings are diagnostic and do not establish accounting errors.",
        ],
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"Records inspected: {inspected_count}")
    print(f"Accepted: {accepted_count}")
    print(f"Rejected: {len(rejected)}")
    print(f"Records with warnings: {len(warned)}")
    print(
        f"Warning conditions: "
        f"{sum(warning_counts.values())}"
    )
    print(
        f"Warning rule counts: "
        f"{dict(sorted(warning_counts.items()))}"
    )
    print(
        f"Rejection rule counts: "
        f"{dict(sorted(rejection_counts.items()))}"
    )

    for item in warned:
        print(
            "  Warning record: "
            f"{item['credit_number']} / {item['end_of_period']} "
            f"at page offset {item['page_offset']}"
        )

    print(f"Evidence saved: {OUTPUT}")


if __name__ == "__main__":
    main()
