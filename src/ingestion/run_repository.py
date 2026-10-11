from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.db.ingestion_models import IngestionRun


class IngestionRunNotFoundError(LookupError):
    """Raised when an ingestion run does not exist."""


class IngestionRunRepository:
    """Persistence boundary for ingestion-run metadata."""

    def __init__(
        self,
        session: Session,
    ) -> None:
        self._session = session

    def add(
        self,
        run: IngestionRun,
    ) -> IngestionRun:
        self._session.add(
            run
        )

        self._session.flush()

        return run

    def get(
        self,
        run_id: uuid.UUID,
    ) -> IngestionRun | None:
        return self._session.get(
            IngestionRun,
            run_id,
        )

    def get_required(
        self,
        run_id: uuid.UUID,
    ) -> IngestionRun:
        run = self.get(
            run_id
        )

        if run is None:
            raise IngestionRunNotFoundError(
                f"Ingestion run does not exist: "
                f"{run_id}"
            )

        return run

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def refresh(
        self,
        run: IngestionRun,
    ) -> None:
        self._session.refresh(
            run
        )