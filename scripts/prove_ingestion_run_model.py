from __future__ import annotations

import subprocess
from os import getenv
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, delete
from sqlalchemy.orm import Session

from src.db.ingestion_models import (
    IngestionRun,
    IngestionRunStatus,
)
from src.ingestion.run_repository import (
    IngestionRunRepository,
)
from src.ingestion.run_service import (
    IngestionRunService,
)
from src.observability.logging import (
    configure_logging,
)


def database_url() -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=getenv(
            "POSTGRES_USER",
            "flowwatch_owner",
        ),
        password=getenv(
            "POSTGRES_PASSWORD",
            "replace-with-local-secret",
        ),
        host=getenv(
            "POSTGRES_HOST",
            "localhost",
        ),
        port=int(
            getenv(
                "POSTGRES_PORT",
                "5434",
            )
        ),
        database=getenv(
            "POSTGRES_DB",
            "flowwatch",
        ),
    )


def code_version() -> str:
    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "--short=12",
            "HEAD",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()


def main() -> None:
    load_dotenv()
    configure_logging()

    engine = create_engine(
        database_url()
    )

    failed_run_id: UUID | None = None
    resumed_run_id: UUID | None = None

    try:
        # ---------------------------------------------------------
        # Session A:
        # Create a run, record two completed pages, then fail it.
        # ---------------------------------------------------------
        with Session(engine) as session:
            repository = IngestionRunRepository(
                session
            )

            service = IngestionRunService(
                repository
            )

            run = service.start_run(
                source_dataset_id="DS00976",
                source_resource_id="RS00906",
                page_size=100,
                code_version=code_version(),
            )

            service.record_page(
                run.run_id,
                row_count=100,
            )

            service.record_page(
                run.run_id,
                row_count=100,
            )

            failed = service.fail_run(
                run.run_id,
                reason=(
                    "Day 10 simulated "
                    "upstream failure"
                ),
            )

            failed_run_id = failed.run_id

            print()
            print(
                "FAILED RUN CREATED"
            )
            print(
                "run_id:",
                failed.run_id,
            )
            print(
                "status:",
                failed.status,
            )
            print(
                "pages:",
                failed.pages,
            )
            print(
                "rows:",
                failed.rows,
            )
            print(
                "failure_reason:",
                failed.failure_reason,
            )

        # ---------------------------------------------------------
        # Session B:
        # New DB session proves the failed run is persisted and
        # queryable independently of the original ORM session.
        # ---------------------------------------------------------
        with Session(engine) as session:
            repository = IngestionRunRepository(
                session
            )

            service = IngestionRunService(
                repository
            )

            persisted_failed = service.get_run(
                failed_run_id
            )

            assert (
                persisted_failed.status
                == IngestionRunStatus.FAILED.value
            )

            assert persisted_failed.pages == 2
            assert persisted_failed.rows == 200

            assert (
                persisted_failed.failure_reason
                == (
                    "Day 10 simulated "
                    "upstream failure"
                )
            )

            print()
            print(
                "FAILED RUN QUERY PROOF"
            )
            print(
                "queryable_in_new_session: YES"
            )
            print(
                "run_id:",
                persisted_failed.run_id,
            )
            print(
                "status:",
                persisted_failed.status,
            )
            print(
                "pages:",
                persisted_failed.pages,
            )
            print(
                "rows:",
                persisted_failed.rows,
            )

            resumed = service.resume_failed_run(
                failed_run_id,
                code_version=code_version(),
            )

            resumed_run_id = resumed.run_id

            assert (
                resumed.resumed_from_run_id
                == failed_run_id
            )

            assert resumed.resume_from_page == 3
            assert (
                resumed.resume_from_offset
                == 200
            )

            assert (
                resumed.status
                == IngestionRunStatus.RUNNING.value
            )

            print()
            print(
                "RESUME LINEAGE PROOF"
            )
            print(
                "new_run_id:",
                resumed.run_id,
            )
            print(
                "resumed_from_run_id:",
                resumed.resumed_from_run_id,
            )
            print(
                "resume_from_page:",
                resumed.resume_from_page,
            )
            print(
                "resume_from_offset:",
                resumed.resume_from_offset,
            )

            print()
            print(
                "DAY 10 PROOF PASSED"
            )

    finally:
        # Remove only rows created by this proof.
        # Child run must be removed before parent run because
        # resumed_from_run_id uses ON DELETE RESTRICT.
        with Session(engine) as session:
            if resumed_run_id is not None:
                session.execute(
                    delete(IngestionRun).where(
                        IngestionRun.run_id
                        == resumed_run_id
                    )
                )

            if failed_run_id is not None:
                session.execute(
                    delete(IngestionRun).where(
                        IngestionRun.run_id
                        == failed_run_id
                    )
                )

            session.commit()

        engine.dispose()


if __name__ == "__main__":
    main()