"""Read-only Mongo hot-raw inventory, index-plan audit, and source inspection."""

from __future__ import annotations

import argparse
import json
from typing import Any

from pymongo import DESCENDING
from pymongo.errors import PyMongoError

from src.ingestion.mongo_raw_audit import (
    compare_raw_runs,
    profile_raw_run,
)
from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)


def _find_query_plan(
    collection: Any,
    query: dict[str, Any],
) -> str:
    """Summarize execution-plan stages (IXSCAN/COLLSCAN/etc.)."""
    try:
        explanation = (
            collection.find(query)
            .limit(1)
            .explain()
        )
    except PyMongoError as exc:
        return (
            f"UNAVAILABLE: {type(exc).__name__}: {exc}"
        )

    stages: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            stage = value.get("stage")

            if isinstance(stage, str):
                stages.add(stage)

            for child in value.values():
                visit(child)

        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(
        explanation.get(
            "queryPlanner",
            {},
        ).get(
            "winningPlan",
            {},
        )
    )

    return (
        ",".join(sorted(stages))
        or "UNRECOGNIZED_PLAN"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--run-id",
        help="Stored run to profile; default latest",
    )

    parser.add_argument(
        "--compare-run",
        help="Second comparable stored run for source drift",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
    )

    args = parser.parse_args()

    if args.limit < 1 or args.limit > 10000:
        parser.error(
            "--limit must be 1..10000"
        )

    config = load_mongodb_config()
    client = create_mongodb_client(config)

    try:
        client.admin.command("ping")

        database = client[
            config.database_name
        ]

        names = sorted(
            database.list_collection_names()
        )

        inventory: list[
            dict[str, Any]
        ] = []

        ttl_indexes: list[str] = []

        for name in names:
            coll = database[name]
            indexes = []

            for index in coll.list_indexes():
                info = {
                    "name": str(index["name"]),
                    "key": list(
                        index["key"].items()
                    ),
                    "unique": bool(
                        index.get("unique", False)
                    ),
                    "expireAfterSeconds": index.get(
                        "expireAfterSeconds"
                    ),
                }

                indexes.append(info)

                if "expireAfterSeconds" in index:
                    ttl_indexes.append(
                        f"{name}.{index['name']}"
                    )

            inventory.append(
                {
                    "collection": name,
                    "document_count": (
                        coll.count_documents({})
                    ),
                    "indexes": indexes,
                }
            )

        raw_records = database[
            "raw_records"
        ]

        latest = raw_records.find_one(
            {},
            projection={
                "run_id": 1,
            },
            sort=[
                (
                    "retrieved_at",
                    DESCENDING,
                ),
                (
                    "_id",
                    DESCENDING,
                ),
            ],
        )

        selected_run = args.run_id or (
            str(latest["run_id"])
            if latest is not None
            else None
        )

        if selected_run is None:
            raise RuntimeError(
                "No stored raw_records found"
            )

        documents = list(
            raw_records.find(
                {
                    "run_id": selected_run,
                }
            )
            .sort(
                [
                    ("page_number", 1),
                    ("record_index", 1),
                ]
            )
            .limit(args.limit)
        )

        if not documents:
            raise RuntimeError(
                "Specified run has no stored raw records"
            )

        profile = profile_raw_run(
            documents
        )

        sample = documents[0]

        record_query = {
            "run_id": selected_run,
            "source_record_key": sample[
                "source_record_key"
            ],
        }

        plans = {
            "raw_record_lineage_lookup": (
                _find_query_plan(
                    raw_records,
                    record_query,
                )
            )
        }

        raw_pages = database[
            "raw_pages"
        ]

        first_page = raw_pages.find_one(
            {
                "run_id": selected_run,
            }
        )

        if first_page is not None:
            plans["raw_page_lookup"] = (
                _find_query_plan(
                    raw_pages,
                    {
                        "run_id": selected_run,
                        "page_source_key": (
                            first_page["page_source_key"]
                        ),
                    },
                )
            )

        status = "SINGLE_RUN_PROFILE_ONLY"
        drift = None

        if args.compare_run:
            comparison = list(
                raw_records.find(
                    {
                        "run_id": args.compare_run,
                    }
                )
                .sort(
                    [
                        ("page_number", 1),
                        ("record_index", 1),
                    ]
                )
                .limit(args.limit)
            )

            drift = compare_raw_runs(
                documents,
                comparison,
            )

            status = "COMPARISON_COMPLETE"

        report = {
            "read_only": True,
            "status": status,
            "profile": profile,
            "source_drift_comparison": drift,
            "collections": inventory,
            "query_plan_stages": plans,
            "ttl_indexes": ttl_indexes,
            "retention_note": (
                "Any TTL index on raw collections is a "
                "retention risk. Do not drop indexes until "
                "their measured workloads and dependencies "
                "have been reviewed."
            ),
        }

        print(
            json.dumps(
                report,
                indent=2,
                default=str,
            )
        )

        return 0

    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())