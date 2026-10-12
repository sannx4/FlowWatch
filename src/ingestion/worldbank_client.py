from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Self

import requests

from src.observability.logging import (
    get_logger,
    log_event,
    set_correlation_ids,
)

DEFAULT_WORLD_BANK_URL = (
    "https://datacatalogapi.worldbank.org/"
    "dexapps/fone/api/apiservice"
)

DEFAULT_DATASET_ID = "DS00976"
DEFAULT_RESOURCE_ID = "RS00906"

DEFAULT_USER_AGENT = (
    "FlowWatch/0.1 "
    "(https://github.com/sannx4/FlowWatch)"
)


@dataclass(frozen=True)
class WorldBankClientConfig:
    """Configuration for World Bank HTTP requests."""

    base_url: str = DEFAULT_WORLD_BANK_URL

    dataset_id: str = DEFAULT_DATASET_ID
    resource_id: str = DEFAULT_RESOURCE_ID

    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0

    # Number of retries AFTER the initial request.
    #
    # max_retries=3 means:
    #
    # attempt 1
    # retry 1
    # retry 2
    # retry 3
    #
    # Maximum total attempts = 4.
    max_retries: int = 3

    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0

    user_agent: str = DEFAULT_USER_AGENT

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError(
                "base_url cannot be empty."
            )

        if not self.dataset_id:
            raise ValueError(
                "dataset_id cannot be empty."
            )

        if not self.resource_id:
            raise ValueError(
                "resource_id cannot be empty."
            )

        if not self.user_agent:
            raise ValueError(
                "user_agent cannot be empty."
            )

        if (
            self.connect_timeout_seconds
            <= 0
        ):
            raise ValueError(
                "connect_timeout_seconds must be "
                "greater than zero."
            )

        if (
            self.read_timeout_seconds
            <= 0
        ):
            raise ValueError(
                "read_timeout_seconds must be "
                "greater than zero."
            )

        if self.max_retries < 0:
            raise ValueError(
                "max_retries cannot be negative."
            )

        if (
            self.backoff_base_seconds
            < 0
        ):
            raise ValueError(
                "backoff_base_seconds cannot be "
                "negative."
            )

        if (
            self.backoff_max_seconds
            < 0
        ):
            raise ValueError(
                "backoff_max_seconds cannot be "
                "negative."
            )

        if (
            self.backoff_max_seconds
            < self.backoff_base_seconds
        ):
            raise ValueError(
                "backoff_max_seconds must be "
                "greater than or equal to "
                "backoff_base_seconds."
            )


@dataclass(frozen=True)
class WorldBankResponse:
    """Validated response returned by the World Bank client."""

    payload: dict[str, Any]
    raw_bytes: bytes

    status_code: int

    request_id: str
    url: str

    attempts: int
    duration_ms: float

    top: int
    skip: int

    total_count: int
    record_count: int


class WorldBankClientError(
    RuntimeError
):
    """Structured failure produced by the World Bank client."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        request_id: str,
        attempts: int,
        max_attempts: int,
        retryable: bool,
        url: str,
        status_code: int | None = None,
        cause_type: str | None = None,
    ) -> None:
        super().__init__(
            message
        )

        self.error_type = (
            error_type
        )

        self.request_id = (
            request_id
        )

        self.attempts = (
            attempts
        )

        self.max_attempts = (
            max_attempts
        )

        self.retryable = (
            retryable
        )

        self.url = url

        self.status_code = (
            status_code
        )

        self.cause_type = (
            cause_type
        )

    def metadata(
        self,
    ) -> dict[str, Any]:
        """Return machine-readable failure metadata."""

        return {
            "error_type": (
                self.error_type
            ),
            "request_id": (
                self.request_id
            ),
            "attempts": (
                self.attempts
            ),
            "max_attempts": (
                self.max_attempts
            ),
            "retryable": (
                self.retryable
            ),
            "url": (
                self.url
            ),
            "status_code": (
                self.status_code
            ),
            "cause_type": (
                self.cause_type
            ),
        }

    def __str__(
        self,
    ) -> str:
        status = (
            f", status_code="
            f"{self.status_code}"
            if (
                self.status_code
                is not None
            )
            else ""
        )

        return (
            f"{super().__str__()} "
            f"[error_type="
            f"{self.error_type}, "
            f"attempts="
            f"{self.attempts}/"
            f"{self.max_attempts}"
            f"{status}, "
            f"request_id="
            f"{self.request_id}]"
        )


class WorldBankClient:
    """Reusable bounded World Bank source HTTP client."""

    RETRYABLE_STATUS_CODES: ClassVar[
        frozenset[int]
    ] = frozenset(
        {
            429,
            500,
            502,
            503,
            504,
        }
    )

    def __init__(
        self,
        config: (
            WorldBankClientConfig
            | None
        ) = None,
        *,
        session: (
            requests.Session
            | None
        ) = None,
        sleep: Callable[
            [float],
            None,
        ] = time.sleep,
    ) -> None:
        self.config = (
            config
            if config is not None
            else (
                WorldBankClientConfig()
            )
        )

        self._owns_session = (
            session is None
        )

        self._session = (
            session
            if session is not None
            else requests.Session()
        )

        self._sleep = sleep

        self._logger = (
            get_logger(
                "ingestion."
                "worldbank-client"
            )
        )

    def __enter__(
        self,
    ) -> Self:
        """Enter the client context."""

        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Close owned resources when leaving the context."""

        self.close()

    def close(
        self,
    ) -> None:
        """Close the internally owned HTTP session."""

        if self._owns_session:
            self._session.close()

    def fetch(
        self,
        *,
        top: int = 100,
        skip: int = 0,
    ) -> WorldBankResponse:
        """Fetch and validate one World Bank API response."""

        if top <= 0:
            raise ValueError(
                "top must be greater "
                "than zero."
            )

        if skip < 0:
            raise ValueError(
                "skip cannot be negative."
            )

        request_id = str(
            uuid.uuid4()
        )

        set_correlation_ids(
            request_id=request_id
        )

        params: dict[
            str,
            str | int,
        ] = {
            "datasetId": (
                self.config.dataset_id
            ),
            "resourceId": (
                self.config.resource_id
            ),
            "top": top,
            "skip": skip,
            "type": "json",
        }

        headers: dict[
            str,
            str,
        ] = {
            "Accept": (
                "application/json"
            ),
            "User-Agent": (
                self.config.user_agent
            ),
        }

        timeout = (
            self.config
            .connect_timeout_seconds,
            self.config
            .read_timeout_seconds,
        )

        max_attempts = (
            self.config.max_retries
            + 1
        )

        started_at = (
            time.perf_counter()
        )

        for attempt in range(
            1,
            max_attempts + 1,
        ):
            try:
                response = (
                    self._session.get(
                        self.config.base_url,
                        params=params,
                        headers=headers,
                        timeout=timeout,
                    )
                )

            except (
                requests.exceptions.Timeout
            ) as exc:
                if (
                    attempt
                    >= max_attempts
                ):
                    self._raise_failure(
                        message=(
                            "World Bank request "
                            "exhausted the timeout "
                            "retry budget."
                        ),
                        error_type="timeout",
                        request_id=(
                            request_id
                        ),
                        attempts=attempt,
                        max_attempts=(
                            max_attempts
                        ),
                        retryable=True,
                        status_code=None,
                        cause_type=(
                            type(
                                exc
                            ).__name__
                        ),
                        started_at=(
                            started_at
                        ),
                        top=top,
                        skip=skip,
                    )

                self._retry(
                    request_id=(
                        request_id
                    ),
                    attempt=attempt,
                    max_attempts=(
                        max_attempts
                    ),
                    error_type=(
                        "timeout"
                    ),
                    status_code=None,
                    top=top,
                    skip=skip,
                )

                continue

            except (
                requests.exceptions
                .ConnectionError
            ) as exc:
                if (
                    attempt
                    >= max_attempts
                ):
                    self._raise_failure(
                        message=(
                            "World Bank request "
                            "exhausted the "
                            "connection retry "
                            "budget."
                        ),
                        error_type=(
                            "connection_error"
                        ),
                        request_id=(
                            request_id
                        ),
                        attempts=attempt,
                        max_attempts=(
                            max_attempts
                        ),
                        retryable=True,
                        status_code=None,
                        cause_type=(
                            type(
                                exc
                            ).__name__
                        ),
                        started_at=(
                            started_at
                        ),
                        top=top,
                        skip=skip,
                    )

                self._retry(
                    request_id=(
                        request_id
                    ),
                    attempt=attempt,
                    max_attempts=(
                        max_attempts
                    ),
                    error_type=(
                        "connection_error"
                    ),
                    status_code=None,
                    top=top,
                    skip=skip,
                )

                continue

            except (
                requests.exceptions
                .RequestException
            ) as exc:
                self._raise_failure(
                    message=(
                        "World Bank request "
                        "failed with a "
                        "non-retryable "
                        "transport error."
                    ),
                    error_type=(
                        "request_error"
                    ),
                    request_id=(
                        request_id
                    ),
                    attempts=attempt,
                    max_attempts=(
                        max_attempts
                    ),
                    retryable=False,
                    status_code=None,
                    cause_type=(
                        type(
                            exc
                        ).__name__
                    ),
                    started_at=(
                        started_at
                    ),
                    top=top,
                    skip=skip,
                )

            status_code = (
                response.status_code
            )

            if (
                status_code
                in self
                .RETRYABLE_STATUS_CODES
            ):
                if (
                    attempt
                    >= max_attempts
                ):
                    self._raise_failure(
                        message=(
                            "World Bank request "
                            "exhausted the HTTP "
                            "retry budget."
                        ),
                        error_type=(
                            "retryable_http_status"
                        ),
                        request_id=(
                            request_id
                        ),
                        attempts=attempt,
                        max_attempts=(
                            max_attempts
                        ),
                        retryable=True,
                        status_code=(
                            status_code
                        ),
                        cause_type=None,
                        started_at=(
                            started_at
                        ),
                        top=top,
                        skip=skip,
                    )

                self._retry(
                    request_id=(
                        request_id
                    ),
                    attempt=attempt,
                    max_attempts=(
                        max_attempts
                    ),
                    error_type=(
                        "retryable_http_status"
                    ),
                    status_code=(
                        status_code
                    ),
                    top=top,
                    skip=skip,
                )

                continue

            if not (
                200
                <= status_code
                < 300
            ):
                self._raise_failure(
                    message=(
                        "World Bank request "
                        "returned a "
                        "non-success HTTP "
                        "status."
                    ),
                    error_type=(
                        "http_status"
                    ),
                    request_id=(
                        request_id
                    ),
                    attempts=attempt,
                    max_attempts=(
                        max_attempts
                    ),
                    retryable=False,
                    status_code=(
                        status_code
                    ),
                    cause_type=None,
                    started_at=(
                        started_at
                    ),
                    top=top,
                    skip=skip,
                )

            raw_bytes = (
                response.content
            )

            try:
                payload = (
                    response.json()
                )

            except ValueError as exc:
                self._raise_failure(
                    message=(
                        "World Bank response "
                        "was not valid JSON."
                    ),
                    error_type=(
                        "invalid_json"
                    ),
                    request_id=(
                        request_id
                    ),
                    attempts=attempt,
                    max_attempts=(
                        max_attempts
                    ),
                    retryable=False,
                    status_code=(
                        status_code
                    ),
                    cause_type=(
                        type(
                            exc
                        ).__name__
                    ),
                    started_at=(
                        started_at
                    ),
                    top=top,
                    skip=skip,
                )

            validation_error = (
                self._validate_payload(
                    payload
                )
            )

            if (
                validation_error
                is not None
            ):
                self._raise_failure(
                    message=(
                        validation_error
                    ),
                    error_type=(
                        "invalid_payload"
                    ),
                    request_id=(
                        request_id
                    ),
                    attempts=attempt,
                    max_attempts=(
                        max_attempts
                    ),
                    retryable=False,
                    status_code=(
                        status_code
                    ),
                    cause_type=None,
                    started_at=(
                        started_at
                    ),
                    top=top,
                    skip=skip,
                )

            total_count = (
                payload["count"]
            )

            records = (
                payload["data"]
            )

            duration_ms = (
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000
            )

            response_url = (
                response.url
                or self.config.base_url
            )

            log_event(
                self._logger,
                (
                    "worldbank_request_"
                    "succeeded"
                ),
                status="success",
                request_id=(
                    request_id
                ),
                duration_ms=(
                    duration_ms
                ),
                attempt=attempt,
                max_attempts=(
                    max_attempts
                ),
                status_code=(
                    status_code
                ),
                top=top,
                skip=skip,
                record_count=len(
                    records
                ),
                total_count=(
                    total_count
                ),
                url=(
                    response_url
                ),
            )

            return WorldBankResponse(
                payload=payload,
                raw_bytes=raw_bytes,
                status_code=(
                    status_code
                ),
                request_id=(
                    request_id
                ),
                url=response_url,
                attempts=attempt,
                duration_ms=(
                    duration_ms
                ),
                top=top,
                skip=skip,
                total_count=(
                    total_count
                ),
                record_count=len(
                    records
                ),
            )

        raise AssertionError(
            "World Bank retry loop "
            "exited without returning "
            "or raising."
        )

    def _retry(
        self,
        *,
        request_id: str,
        attempt: int,
        max_attempts: int,
        error_type: str,
        status_code: (
            int
            | None
        ),
        top: int,
        skip: int,
    ) -> None:
        """Log and wait before the next bounded retry."""

        backoff_seconds = (
            self._backoff_seconds(
                attempt
            )
        )

        log_event(
            self._logger,
            (
                "worldbank_request_retry"
            ),
            status="retry",
            request_id=(
                request_id
            ),
            attempt=attempt,
            max_attempts=(
                max_attempts
            ),
            error_type=(
                error_type
            ),
            status_code=(
                status_code
            ),
            backoff_seconds=(
                backoff_seconds
            ),
            top=top,
            skip=skip,
            url=(
                self.config.base_url
            ),
        )

        self._sleep(
            backoff_seconds
        )

    def _backoff_seconds(
        self,
        attempt: int,
    ) -> float:
        """Calculate bounded exponential-backoff delay."""

        delay = (
            self.config
            .backoff_base_seconds
            * (
                2
                ** (
                    attempt
                    - 1
                )
            )
        )

        return min(
            delay,
            self.config
            .backoff_max_seconds,
        )

    def _raise_failure(
        self,
        *,
        message: str,
        error_type: str,
        request_id: str,
        attempts: int,
        max_attempts: int,
        retryable: bool,
        status_code: (
            int
            | None
        ),
        cause_type: (
            str
            | None
        ),
        started_at: float,
        top: int,
        skip: int,
    ) -> None:
        """Log structured failure metadata and raise."""

        duration_ms = (
            (
                time.perf_counter()
                - started_at
            )
            * 1000
        )

        log_event(
            self._logger,
            (
                "worldbank_request_failed"
            ),
            status="failure",
            request_id=(
                request_id
            ),
            duration_ms=(
                duration_ms
            ),
            error_type=(
                error_type
            ),
            attempts=attempts,
            max_attempts=(
                max_attempts
            ),
            retryable=(
                retryable
            ),
            status_code=(
                status_code
            ),
            cause_type=(
                cause_type
            ),
            top=top,
            skip=skip,
            url=(
                self.config.base_url
            ),
        )

        raise WorldBankClientError(
            message,
            error_type=(
                error_type
            ),
            request_id=(
                request_id
            ),
            attempts=attempts,
            max_attempts=(
                max_attempts
            ),
            retryable=(
                retryable
            ),
            url=(
                self.config.base_url
            ),
            status_code=(
                status_code
            ),
            cause_type=(
                cause_type
            ),
        )

    @staticmethod
    def _validate_payload(
        payload: Any,
    ) -> str | None:
        """Validate the minimum World Bank response envelope."""

        if not isinstance(
            payload,
            dict,
        ):
            return (
                "World Bank response JSON "
                "must be an object."
            )

        if (
            "count"
            not in payload
        ):
            return (
                "World Bank response is "
                "missing 'count'."
            )

        if (
            "data"
            not in payload
        ):
            return (
                "World Bank response is "
                "missing 'data'."
            )

        total_count = (
            payload["count"]
        )

        records = (
            payload["data"]
        )

        if (
            isinstance(
                total_count,
                bool,
            )
            or not isinstance(
                total_count,
                int,
            )
        ):
            return (
                "World Bank response "
                "'count' must be an "
                "integer."
            )

        if total_count < 0:
            return (
                "World Bank response "
                "'count' cannot be "
                "negative."
            )

        if not isinstance(
            records,
            list,
        ):
            return (
                "World Bank response "
                "'data' must be a list."
            )

        if total_count < len(
            records
        ):
            return (
                "World Bank response "
                "'count' cannot be "
                "smaller than the "
                "returned record count."
            )

        return None