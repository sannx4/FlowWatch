"""Day33 isolated historical raw-to-canonical gate; read-only preview by default."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from scripts.day29_32_historical_backfill import _mongo_client, _pg_engine
from src.warehouse.historical_canonical import publish_historical_canonical


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=UUID)
    parser.add_argument("--apply", action="store_true", help="Explicitly authorize canonical DB writes")
    parser.add_argument("--allow-quarantine", action="store_true",
                        help="Permit incomplete accepted population with persisted rejects")
    parser.add_argument("--report", type=Path,
                        default=Path("reports/day33-historical-canonical.json"))
    args = parser.parse_args()
    engine = _pg_engine()
    mongo = _mongo_client()
    try:
        result = publish_historical_canonical(
            engine, mongo, args.run_id, apply=args.apply,
            allow_quarantine=args.allow_quarantine,
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, default=str) + "\n",
                               encoding="utf-8")
        print(json.dumps(result, indent=2, default=str))
        print(f"VERIFIED REPORT: {args.report}")
        return 0
    finally:
        mongo.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
