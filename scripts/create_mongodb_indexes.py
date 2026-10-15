from __future__ import annotations

from src.ingestion.mongodb_connection import (
    create_mongodb_client,
    load_mongodb_config,
)
from src.ingestion.mongodb_indexes import (
    ensure_raw_indexes,
)


def main() -> None:
    """
    Create FlowWatch Day-15 MongoDB collections
    and raw-lineage indexes.
    """

    mongo_config = (
        load_mongodb_config()
    )

    client = (
        create_mongodb_client(
            mongo_config
        )
    )

    database = client[
        mongo_config.database_name
    ]

    try:
        client.admin.command(
            "ping"
        )

        created = (
            ensure_raw_indexes(
                database
            )
        )

        print(
            "MongoDB raw-lineage "
            "collections/indexes ready."
        )

        print(
            "database="
            f"{mongo_config.database_name}"
        )

        for (
            collection_name,
            index_names,
        ) in created.items():
            print(
                f"{collection_name}: "
                f"{', '.join(index_names)}"
            )

    finally:
        client.close()


if __name__ == "__main__":
    main()