from __future__ import annotations

import contextvars
import json
import logging
import sys
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import Any

_RUN_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "run_id",
    default=None,
)

_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)


_STANDARD_LOG_FIELDS = set(
    logging.makeLogRecord({}).__dict__
)

_STANDARD_LOG_FIELDS.update(
    {
        "message",
        "asctime",
    }
)


class JsonFormatter(logging.Formatter):
    """Serialize log records as one JSON object per line."""

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(
                UTC
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in (
            "run_id",
            "request_id",
            "component",
            "duration_ms",
            "status",
        ):
            value = getattr(
                record,
                field,
                None,
            )

            if value is not None:
                payload[field] = value

        for (
            key,
            value,
        ) in record.__dict__.items():
            if (
                key
                not in _STANDARD_LOG_FIELDS
                and key
                not in payload
                and value is not None
            ):
                payload[key] = value

        if record.exc_info:
            payload[
                "exception"
            ] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            default=str,
            separators=(
                ",",
                ":",
            ),
        )


class ContextLoggerAdapter(
    logging.LoggerAdapter
):
    """Attach FlowWatch correlation context to every log event."""

    def process(
        self,
        msg: object,
        kwargs: MutableMapping[
            str,
            Any,
        ],
    ) -> tuple[
        object,
        MutableMapping[
            str,
            Any,
        ],
    ]:
        extra = dict(
            kwargs.get(
                "extra"
            )
            or {}
        )

        component = (
            self.logger.name
        )

        if self.extra is not None:
            configured_component = (
                self.extra.get(
                    "component"
                )
            )

            if isinstance(
                configured_component,
                str,
            ):
                component = (
                    configured_component
                )

        extra.setdefault(
            "component",
            component,
        )

        extra.setdefault(
            "run_id",
            _RUN_ID.get(),
        )

        extra.setdefault(
            "request_id",
            _REQUEST_ID.get(),
        )

        kwargs[
            "extra"
        ] = extra

        return (
            msg,
            kwargs,
        )


def configure_logging(
    level: str | int = "INFO",
) -> None:
    """Configure process-wide JSON logging."""

    root_logger = (
        logging.getLogger()
    )

    root_logger.handlers.clear()

    handler = (
        logging.StreamHandler(
            sys.stdout
        )
    )

    handler.setFormatter(
        JsonFormatter()
    )

    root_logger.addHandler(
        handler
    )

    root_logger.setLevel(
        level
    )

    logging.captureWarnings(
        True
    )


def set_correlation_ids(
    *,
    run_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Attach correlation identifiers to the current execution context."""

    _RUN_ID.set(
        run_id
    )

    _REQUEST_ID.set(
        request_id
    )


def clear_correlation_ids() -> None:
    """Clear correlation identifiers from the current context."""

    _RUN_ID.set(
        None
    )

    _REQUEST_ID.set(
        None
    )


def get_logger(
    component: str,
) -> ContextLoggerAdapter:
    """Return a logger carrying a stable component name."""

    logger = logging.getLogger(
        f"flowwatch.{component}"
    )

    return ContextLoggerAdapter(
        logger,
        {
            "component": component,
        },
    )


def log_event(
    logger: ContextLoggerAdapter,
    message: str,
    *,
    status: str,
    duration_ms: float | None = None,
    **fields: Any,
) -> None:
    """Emit one structured FlowWatch event."""

    extra: dict[
        str,
        Any,
    ] = {
        "status": status,
        **fields,
    }

    if duration_ms is not None:
        extra[
            "duration_ms"
        ] = round(
            duration_ms,
            3,
        )

    logger.info(
        message,
        extra=extra,
    )