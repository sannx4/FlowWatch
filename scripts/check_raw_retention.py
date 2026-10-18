"""Demonstrate Day-18 fail-closed raw retention; no database writes."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.ingestion.raw_retention import assess_raw_retention


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        help=(
            "Untrusted example manifest "
            "(never authorizes deletion)"
        ),
    )

    args = parser.parse_args()

    manifest = None

    if args.manifest is not None:
        manifest = json.loads(
            args.manifest.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(manifest, dict):
            parser.error(
                "Manifest must be a JSON object"
            )

    result = assess_raw_retention(
        args.run_id,
        archive_manifest=manifest,
    )

    print(
        json.dumps(
            asdict(result),
            indent=2,
        )
    )

    # Exit zero because denying deletion is the expected
    # Day-18 result. The allowed field is authoritative.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())