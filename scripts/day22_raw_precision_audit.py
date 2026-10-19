"""Read-only MongoDB raw-byte audit for exact Day-22 decimal transformations.

Usage:
    python -m scripts.day22_raw_precision_audit --limit 5
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.raw_replay import select_raw_record_envelopes
from src.transformation.pure import MONEY_FIELDS, transform_canonical_record
from src.transformation.rehydration import recover_exact_source_record

REPORT = Path("reports/day22-raw-precision-audit.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--run-id", type=str)
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be positive")

    client = create_mongodb_client(load_mongodb_config())
    try:
        db = client[load_mongodb_config().database_name]
        if args.run_id:
            run_id = args.run_id
        else:
            from scripts.replay_raw import resolve_latest_run_id

            run_id = resolve_latest_run_id(db)

        envelopes = select_raw_record_envelopes(db, run_id=run_id, limit=args.limit)
        if not envelopes:
            raise LookupError(f"No MongoDB raw records found for {run_id}")

        page_cache: dict[tuple[int, int, str], bytes] = {}
        value_types: Counter[str] = Counter()
        drift_counts: Counter[str] = Counter()
        exact_decimal_values = 0
        for envelope in envelopes:
            key = (
                envelope.page_number,
                envelope.page_offset,
                envelope.source_checksum,
            )
            if key not in page_cache:
                query = {
                    "run_id": str(envelope.run_id),
                    "page_number": envelope.page_number,
                    "page_offset": envelope.page_offset,
                    "source_checksum": envelope.source_checksum,
                }
                page = db["raw_pages"].find_one(query, {"raw_bytes": 1})
                if page is None:
                    raise LookupError(f"Matching raw page is missing for {key}")
                original = page.get("raw_bytes")
                if not isinstance(original, bytes):
                    raise TypeError(f"Original source bytes unavailable for {key}")
                page_cache[key] = original

            exact_payload = recover_exact_source_record(
                page_cache[key],
                source_checksum=envelope.source_checksum,
                record_index=envelope.record_index,
                stored_payload=envelope.payload,
            )
            transform_canonical_record(exact_payload)
            for source_field in MONEY_FIELDS.values():
                prior = envelope.payload.get(source_field)
                exact = exact_payload.get(source_field)
                if prior is not None:
                    value_types[type(prior).__name__] += 1
                if isinstance(exact, Decimal):
                    exact_decimal_values += 1
                    if isinstance(prior, float) and Decimal(str(prior)) != exact:
                        drift_counts[source_field] += 1

    finally:
        client.close()

    report: dict[str, Any] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "run_id": str(run_id),
        "records_checked": len(envelopes),
        "verified_source_pages": len(page_cache),
        "exact_decimal_source_values_recovered": exact_decimal_values,
        "stored_financial_value_types": dict(sorted(value_types.items())),
        "float_round_trip_numeric_differences_by_field": dict(
            sorted(drift_counts.items())
        ),
        "source_api_contacted": False,
        "postgresql_modified": False,
        "mongodb_modified": False,
        "status": "PASS_RAW_CHECKSUM_AND_EXACT_TRANSFORM",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Verified records: {len(envelopes)}")
    print(f"Verified raw pages: {len(page_cache)}")
    print(f"Exact Decimal tokens recovered: {exact_decimal_values}")
    print(f"Stored financial value types: {dict(value_types)}")
    print(f"Float round-trip value differences: {sum(drift_counts.values())}")
    print(f"Evidence: {REPORT}")
    print("Status: PASS (read-only; loader unchanged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
