"""Read-only parity report: legacy Day-7 vs new Day-22 canonical dictionaries.

Only reads an existing local raw fixture; does not connect to external services.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.transformation.day07 import transform_record as legacy_transform
from src.transformation.pure import transform_canonical_record


def _json_value(value: Any) -> str:
    if isinstance(value, (date, Decimal)):
        return str(value)
    return repr(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/raw/world_bank_sample.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/day22-transformation-parity.json"))
    args = parser.parse_args()
    payload = json.loads(args.source.read_text(encoding="utf-8"), parse_float=Decimal)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise TypeError("Expected World Bank payload with a 'data' record list")

    mismatches: list[dict[str, Any]] = []
    matched = 0
    for index, source_record in enumerate(payload["data"]):
        try:
            old = legacy_transform(source_record)
            new = transform_canonical_record(source_record)
            if old == new:
                matched += 1
                continue
            different = []
            for entity in ("region", "country", "project", "credit", "snapshot"):
                all_fields = set(old[entity]) | set(new[entity])
                for field in sorted(all_fields):
                    if old[entity].get(field) != new[entity].get(field):
                        different.append({
                            "field": f"{entity}.{field}",
                            "day07": _json_value(old[entity].get(field)),
                            "day22": _json_value(new[entity].get(field)),
                        })
            mismatches.append({"source_row_index": index, "differences": different[:20]})
        except (ValueError, TypeError, KeyError) as exc:
            mismatches.append({
                "source_row_index": index,
                "error": f"{type(exc).__name__}: {exc}",
            })

    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "source_path": str(args.source),
        "source_records": len(payload["data"]),
        "matched_records": matched,
        "mismatched_records": len(mismatches),
        "gate": "PASS" if not mismatches else "FAIL_REVIEW_REQUIRED",
        "sample_differences": mismatches[:25],
        "source_api_contacted": False,
        "postgresql_modified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Day-22 parity: {report['gate']}; matched={matched}; mismatched={len(mismatches)}")
    print(f"Evidence: {args.output}")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
