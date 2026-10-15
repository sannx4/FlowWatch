from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from src.db.models import (
    Country,
    Credit,
    CreditSnapshot,
    Project,
    Region,
)
from src.ingestion.raw_envelope import (
    RawRecordEnvelope,
)
from src.transformation.day07 import (
    transform_record,
)


@dataclass(
    frozen=True
)
class CuratedLoadResult:
    """
    PostgreSQL identifiers produced by loading one
    validated raw-record envelope.
    """

    region_id: int

    country_id: int

    project_pk: int

    credit_id: int

    credit_snapshot_id: int

    ingestion_run_id: str

    source_checksum: str

    source_record_key: str


def _upsert_returning_id(
    connection: Connection,
    *,
    table: Any,
    values: dict[
        str,
        Any,
    ],
    conflict_columns: tuple[
        str,
        ...
    ],
    id_column_name: str,
) -> int:
    """
    PostgreSQL upsert helper.

    The business identity columns determine conflict
    resolution while all non-key supplied values are
    refreshed from EXCLUDED.
    """

    statement = insert(
        table
    ).values(
        **values
    )

    update_values = {
        column_name: getattr(
            statement.excluded,
            column_name,
        )
        for column_name
        in values
        if column_name
        not in conflict_columns
    }

    id_column = table.c[
        id_column_name
    ]

    conflict_elements = [
        table.c[
            column_name
        ]
        for column_name
        in conflict_columns
    ]

    if update_values:
        upsert = (
            statement.on_conflict_do_update(
                index_elements=(
                    conflict_elements
                ),
                set_=update_values,
            )
            .returning(
                id_column
            )
        )

        return int(
            connection.execute(
                upsert
            ).scalar_one()
        )

    insert_only = (
        statement.on_conflict_do_nothing(
            index_elements=(
                conflict_elements
            )
        )
        .returning(
            id_column
        )
    )

    inserted_id = (
        connection.execute(
            insert_only
        ).scalar_one_or_none()
    )

    if inserted_id is not None:
        return int(
            inserted_id
        )

    conditions = [
        table.c[
            column_name
        ]
        == values[
            column_name
        ]
        for column_name
        in conflict_columns
    ]

    existing_id = (
        connection.execute(
            select(
                id_column
            ).where(
                *conditions
            )
        ).scalar_one()
    )

    return int(
        existing_id
    )


def load_curated_record(
    connection: Connection,
    envelope: RawRecordEnvelope,
) -> CuratedLoadResult:
    """
    Transform and upsert one raw World Bank record.

    The business payload is transformed using the existing
    Day-7 canonical transformation.

    Lineage values are NOT recomputed from transformed data.

    They are propagated directly from RawRecordEnvelope:

        run_id
            -> credit_snapshots.ingestion_run_id

        source_checksum
            -> credit_snapshots.source_checksum

        source_record_key
            -> credit_snapshots.source_record_key
    """

    if not isinstance(
    envelope.payload,
    dict,
    ):
     raise TypeError(
        "RawRecordEnvelope payload must "
        "be a source-record mapping."
    )

    transformed = (
        transform_record(
            envelope.payload
        )
    )

    region_values = dict(
        transformed[
            "region"
        ]
    )

    region_id = (
        _upsert_returning_id(
            connection,
            table=(
                Region.__table__
            ),
            values=(
                region_values
            ),
            conflict_columns=(
                "region_name",
            ),
            id_column_name=(
                "region_id"
            ),
        )
    )

    country_values = {
        **transformed[
            "country"
        ],
        "region_id": (
            region_id
        ),
    }

    country_id = (
        _upsert_returning_id(
            connection,
            table=(
                Country.__table__
            ),
            values=(
                country_values
            ),
            conflict_columns=(
                "country_code",
            ),
            id_column_name=(
                "country_id"
            ),
        )
    )

    project_values = {
        **transformed[
            "project"
        ],
        "country_id": (
            country_id
        ),
    }

    project_pk = (
        _upsert_returning_id(
            connection,
            table=(
                Project.__table__
            ),
            values=(
                project_values
            ),
            conflict_columns=(
                "project_id",
            ),
            id_column_name=(
                "project_pk"
            ),
        )
    )

    credit_values = {
        **transformed[
            "credit"
        ],
        "project_pk": (
            project_pk
        ),
    }

    credit_id = (
        _upsert_returning_id(
            connection,
            table=(
                Credit.__table__
            ),
            values=(
                credit_values
            ),
            conflict_columns=(
                "credit_number",
            ),
            id_column_name=(
                "credit_id"
            ),
        )
    )

    snapshot_values = {
        **transformed[
            "snapshot"
        ],
        "credit_id": (
            credit_id
        ),

        # Day-16 authoritative lineage.
        "ingestion_run_id": (
            envelope.run_id
        ),
        "source_checksum": (
            envelope.source_checksum
        ),
        "source_record_key": (
            envelope.source_record_key
        ),
    }

    credit_snapshot_id = (
        _upsert_returning_id(
            connection,
            table=(
                CreditSnapshot.__table__
            ),
            values=(
                snapshot_values
            ),
            conflict_columns=(
                "credit_id",
                "end_of_period",
            ),
            id_column_name=(
                "credit_snapshot_id"
            ),
        )
    )

    return CuratedLoadResult(
        region_id=(
            region_id
        ),
        country_id=(
            country_id
        ),
        project_pk=(
            project_pk
        ),
        credit_id=(
            credit_id
        ),
        credit_snapshot_id=(
            credit_snapshot_id
        ),
        ingestion_run_id=str(
            envelope.run_id
        ),
        source_checksum=(
            envelope.source_checksum
        ),
        source_record_key=(
            envelope.source_record_key
        ),
    )