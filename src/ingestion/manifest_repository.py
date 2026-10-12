from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.raw_manifest_models import (
    RawPageManifest,
)


class RawPageManifestNotFoundError(
    LookupError
):
    """Raised when a requested raw-page manifest does not exist."""


class RawPageManifestRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        manifest: RawPageManifest,
    ) -> RawPageManifest:
        self._session.add(
            manifest
        )

        self._session.flush()

        return manifest

    def get(
        self,
        manifest_id: UUID,
    ) -> RawPageManifest | None:
        return self._session.get(
            RawPageManifest,
            manifest_id,
        )

    def get_required(
        self,
        manifest_id: UUID,
    ) -> RawPageManifest:
        manifest = self.get(
            manifest_id
        )

        if manifest is None:
            raise RawPageManifestNotFoundError(
                "Raw page manifest "
                f"{manifest_id} was not found"
            )

        return manifest

    def get_by_run_page(
        self,
        run_id: UUID,
        page_number: int,
    ) -> RawPageManifest | None:
        statement = select(
            RawPageManifest
        ).where(
            RawPageManifest.run_id
            == run_id,
            RawPageManifest.page_number
            == page_number,
        )

        return self._session.scalar(
            statement
        )

    def get_by_run_offset(
        self,
        run_id: UUID,
        offset: int,
    ) -> RawPageManifest | None:
        statement = select(
            RawPageManifest
        ).where(
            RawPageManifest.run_id
            == run_id,
            RawPageManifest.offset
            == offset,
        )

        return self._session.scalar(
            statement
        )

    def list_for_run(
        self,
        run_id: UUID,
    ) -> list[RawPageManifest]:
        statement = (
            select(
                RawPageManifest
            )
            .where(
                RawPageManifest.run_id
                == run_id
            )
            .order_by(
                RawPageManifest.page_number
            )
        )

        return list(
            self._session.scalars(
                statement
            )
        )

    def commit(
        self,
    ) -> None:
        self._session.commit()

    def rollback(
        self,
    ) -> None:
        self._session.rollback()

    def refresh(
        self,
        manifest: RawPageManifest,
    ) -> None:
        self._session.refresh(
            manifest
        )