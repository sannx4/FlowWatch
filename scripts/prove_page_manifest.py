from __future__ import annotations

import subprocess
from os import getenv
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import (
    URL,
    create_engine,
    delete,
)
from sqlalchemy.orm import Session

from src.db.ingestion_models import (
    IngestionRun,
)
from src.db.raw_manifest_models import (
    RawPageManifest,
)
from src.ingestion.checksum import (
    sha256_bytes,
)
from src.ingestion.manifest_repository import (
    RawPageManifestRepository,
)
from src.ingestion.manifest_service import (
    RawPageManifestService,
)
from src.ingestion.paginator import (
    PageRequestMetadata,
    WorldBankPage,
)
from src.ingestion.run_repository import (
    IngestionRunRepository,
)
from src.ingestion.run_service import (
    IngestionRunService,
)
from src.ingestion.worldbank_client import (
    WorldBankClient,
    WorldBankClientConfig,
    WorldBankResponse,
)
from src.observability.logging import (
    configure_logging,
)

WORLD_BANK_BASE_URL = (
    "https://datacatalogapi.worldbank.org/"
    "dexapps/fone/api/apiservice"
)

DATASET_ID = "DS00976"
RESOURCE_ID = "RS00906"


def database_url() -> URL:
    return URL.create(
        drivername=(
            "postgresql+psycopg"
        ),
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


def client_config() -> WorldBankClientConfig:
    return WorldBankClientConfig(
        base_url=WORLD_BANK_BASE_URL,
        dataset_id=DATASET_ID,
        resource_id=RESOURCE_ID,
        connect_timeout_seconds=10.0,
        read_timeout_seconds=30.0,
        max_retries=2,
        backoff_base_seconds=0.5,
        backoff_max_seconds=2.0,
        user_agent=(
            "FlowWatch/Day11 "
            "page-manifest-proof"
        ),
    )


def page_from_response(
    response: WorldBankResponse,
) -> WorldBankPage:
    records = tuple(
        response.payload[
            "data"
        ]
    )

    request = PageRequestMetadata(
        request_id=(
            response.request_id
        ),
        status_code=(
            response.status_code
        ),
        attempts=response.attempts,
        duration_ms=(
            response.duration_ms
        ),
        url=response.url,
        requested_top=response.top,
        requested_skip=response.skip,
    )

    return WorldBankPage(
        page_number=1,
        offset=response.skip,
        record_count=(
            response.record_count
        ),
        total_count=(
            response.total_count
        ),
        records=records,
        raw_bytes=response.raw_bytes,
        request=request,
    )


def main() -> None:
    load_dotenv()
    configure_logging()

    engine = create_engine(
        database_url()
    )

    run_ids: list[UUID] = []

    try:
        # ------------------------------------------------------
        # Fetch exactly the same World Bank page twice.
        # ------------------------------------------------------
        with WorldBankClient(
            client_config()
        ) as client:
            first_response = client.fetch(
                top=5,
                skip=0,
            )

            second_response = client.fetch(
                top=5,
                skip=0,
            )

        if (
            first_response.payload
            != second_response.payload
        ):
            raise AssertionError(
                "The source content changed between "
                "the two live downloads. "
                "Run the proof again when the source "
                "is stable."
            )

        first_page = page_from_response(
            first_response
        )

        second_page = page_from_response(
            second_response
        )

        # ------------------------------------------------------
        # Persist each download in a separate ingestion run.
        # ------------------------------------------------------
        with Session(
            engine
        ) as session:
            run_repository = (
                IngestionRunRepository(
                    session
                )
            )

            manifest_repository = (
                RawPageManifestRepository(
                    session
                )
            )

            run_service = (
                IngestionRunService(
                    run_repository
                )
            )

            manifest_service = (
                RawPageManifestService(
                    manifest_repository,
                    run_repository,
                )
            )

            first_run = (
                run_service.start_run(
                    source_dataset_id=(
                        DATASET_ID
                    ),
                    source_resource_id=(
                        RESOURCE_ID
                    ),
                    page_size=5,
                    code_version=(
                        code_version()
                    ),
                )
            )

            run_ids.append(
                first_run.run_id
            )

            first_manifest = (
                manifest_service.record_page(
                    first_run.run_id,
                    first_page,
                )
            )

            second_run = (
                run_service.start_run(
                    source_dataset_id=(
                        DATASET_ID
                    ),
                    source_resource_id=(
                        RESOURCE_ID
                    ),
                    page_size=5,
                    code_version=(
                        code_version()
                    ),
                )
            )

            run_ids.append(
                second_run.run_id
            )

            second_manifest = (
                manifest_service.record_page(
                    second_run.run_id,
                    second_page,
                )
            )

            print()
            print(
                "IDENTICAL RE-DOWNLOAD PROOF"
            )
            print(
                "first_manifest_id:",
                first_manifest.manifest_id,
            )
            print(
                "second_manifest_id:",
                second_manifest.manifest_id,
            )
            print(
                "first_checksum:",
                first_manifest.sha256,
            )
            print(
                "second_checksum:",
                second_manifest.sha256,
            )

            assert (
                first_manifest.sha256
                == second_manifest.sha256
            )

            print(
                "same_checksum: YES"
            )

            # --------------------------------------------------
            # Deliberately modify the exact raw payload.
            # --------------------------------------------------
            changed_payload = (
                first_page.raw_bytes
                + b"!"
            )

            changed_checksum = (
                sha256_bytes(
                    changed_payload
                )
            )

            assert (
                changed_checksum
                != first_manifest.sha256
            )

            assert not (
                manifest_service
                .payload_matches(
                    first_manifest.manifest_id,
                    changed_payload,
                )
            )

            print()
            print(
                "CHANGED PAYLOAD PROOF"
            )
            print(
                "original_checksum:",
                first_manifest.sha256,
            )
            print(
                "changed_checksum:",
                changed_checksum,
            )
            print(
                "change_detected: YES"
            )

            persisted = (
                manifest_repository
                .get_by_run_page(
                    first_run.run_id,
                    1,
                )
            )

            assert persisted is not None

            assert (
                persisted.sha256
                == first_manifest.sha256
            )

            print()
            print(
                "DATABASE MANIFEST PROOF"
            )
            print(
                "queryable_manifest: YES"
            )
            print(
                "run_id:",
                persisted.run_id,
            )
            print(
                "page_number:",
                persisted.page_number,
            )
            print(
                "offset:",
                persisted.offset,
            )
            print(
                "record_count:",
                persisted.record_count,
            )
            print(
                "payload_size_bytes:",
                persisted.payload_size_bytes,
            )

            print()
            print(
                "DAY 11 PROOF PASSED"
            )

    finally:
        with Session(
            engine
        ) as session:
            if run_ids:
                session.execute(
                    delete(
                        RawPageManifest
                    ).where(
                        RawPageManifest.run_id.in_(
                            run_ids
                        )
                    )
                )

                session.execute(
                    delete(
                        IngestionRun
                    ).where(
                        IngestionRun.run_id.in_(
                            run_ids
                        )
                    )
                )

                session.commit()

        engine.dispose()


if __name__ == "__main__":
    main()