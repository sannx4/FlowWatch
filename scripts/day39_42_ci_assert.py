"""CI fixture gate for immutable Parquet verification; no database writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPORT = Path("reports/day39-42-research-gate.json")
EXPECTED_CI_ID = "00000000-0000-4000-8000-000000000034"


def assert_fixture(report: dict[str, Any], *, expected_reused: bool) -> None:
    assert report["status"] == "PASS_DAY1_BOUNDED_RESEARCH_EXPORT"
    assert report["provenance"]["database"] == "flowwatch_historical_gate"
    assert report["provenance"]["run_id"] == EXPECTED_CI_ID
    assert report["provenance"]["canonical_snapshot_rows"] == 3
    assert report["provenance"]["warehouse_fact_rows"] == 3
    assert report["provenance"]["warehouse_metric_rows"] == 3
    assert report["research_audit"]["observations"] == 3
    assert report["research_audit"]["per_credit"][0]["missing_months_between_endpoints"] == 1
    assert report["research_audit"]["forecasting_readiness"] == "NOT_ESTABLISHED"
    assert report["artifact"]["row_count"] == 3
    assert report["artifact"]["reused"] is expected_reused
    assert report["artifact"]["status"] == (
        "PASS_EXISTING_IMMUTABLE_PARQUET" if expected_reused
        else "PASS_NEW_IMMUTABLE_PARQUET"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-reused", choices=("true", "false"), required=True)
    args = parser.parse_args()
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert_fixture(report, expected_reused=args.expected_reused == "true")
    print("PASS_DAY39_42_SYNTHETIC_CI_FIXTURE")


if __name__ == "__main__":
    main()
