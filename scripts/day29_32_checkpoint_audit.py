"""Read-only independent PG/Mongo backfill audit, including source variation."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from scripts.day29_32_historical_backfill import _mongo_client, _pg_engine
from src.ingestion.historical_backfill import MONGO_DATABASE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=UUID)
    parser.add_argument("--report", type=Path, default=Path("reports/historical-backfill-audit.json"))
    args = parser.parse_args()
    pg = _pg_engine()
    mongo = _mongo_client()
    try:
        with pg.connect() as con:
            run = con.execute(text("""
                SELECT run_id, dataset_id, resource_id, page_size, max_pages,
                       observed_total, status
                FROM public.historical_backfill_runs WHERE run_id=:rid
            """), {"rid": args.run_id}).mappings().one()
            pages = con.execute(text("""
                SELECT page_number, page_offset, record_count, total_count,
                       source_checksum
                FROM public.historical_backfill_pages
                WHERE run_id=:rid ORDER BY page_number
            """), {"rid": args.run_id}).mappings().all()
        db = mongo[MONGO_DATABASE]
        docs = list(db["raw_pages"].find(
            {"run_id": str(args.run_id)},
            {"page_number": 1, "page_offset": 1, "record_count": 1,
             "source_checksum": 1, "_id": 0},
        ))
        pg_idx = {int(x["page_number"]): x for x in pages}
        mongo_idx = {int(x["page_number"]): x for x in docs}
        if set(pg_idx) != set(mongo_idx):
            raise AssertionError("PostgreSQL and MongoDB have different page identities")
        for number, row in pg_idx.items():
            m = mongo_idx[number]
            for a, b in (("page_offset", "page_offset"), ("record_count", "record_count"),
                         ("source_checksum", "source_checksum")):
                if row[a] != m[b]:
                    raise AssertionError(f"Page {number} source identity mismatch: {a}")
        counts: Counter[str] = Counter()
        nonnull: Counter[str] = Counter()
        credits: set[str] = set()
        periods: Counter[str] = Counter()
        mongo_count = 0
        for record in db["raw_records"].find(
            {"run_id": str(args.run_id)}, {"payload": 1, "_id": 0}
        ):
            mongo_count += 1
            payload = record["payload"]
            if not isinstance(payload, dict):
                raise TypeError("Non-object raw record")
            for key, value in payload.items():
                counts[key] += 1
                if value is not None and value != "":
                    nonnull[key] += 1
            if payload.get("credit_number"):
                credits.add(str(payload["credit_number"]))
            if payload.get("end_of_period"):
                periods[str(payload["end_of_period"])] += 1
        expected_records = sum(int(x["record_count"]) for x in pages)
        if int(mongo_count) != expected_records:
            raise AssertionError("Raw record count does not equal checkpoint sums")
        result = {
            "status": "PASS_RAW_SOURCE_AUDIT", "run_id": str(args.run_id),
            "run_status": run["status"], "pages": len(pages),
            "records": mongo_count, "reported_total": run["observed_total"],
            "distinct_credit_numbers": len(credits),
            "distinct_reporting_dates": len(periods),
            "min_reporting_date_text": min(periods) if periods else None,
            "max_reporting_date_text": max(periods) if periods else None,
            "nonnull_field_rates": {k: round(nonnull[k] / mongo_count, 6) for k in sorted(counts)},
            "field_presence_rates": {k: round(counts[k] / mongo_count, 6) for k in sorted(counts)},
            "note": "Raw-only dataset profile. No canonical, warehouse, label, or statistical independence claims.",
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    finally:
        mongo.close()
        pg.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
