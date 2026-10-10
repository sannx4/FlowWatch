import json

from src.observability.logging import (
    clear_correlation_ids,
    configure_logging,
    get_logger,
    log_event,
    set_correlation_ids,
)


def test_json_log_contains_correlation_fields(capsys) -> None:
    configure_logging()

    set_correlation_ids(
        run_id="run-test-123",
        request_id="request-test-456",
    )

    logger = get_logger("unit-test")

    log_event(
        logger,
        "test_event",
        status="success",
        duration_ms=12.5,
        rows=7,
    )

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert payload["message"] == "test_event"
    assert payload["component"] == "unit-test"
    assert payload["run_id"] == "run-test-123"
    assert payload["request_id"] == "request-test-456"
    assert payload["status"] == "success"
    assert payload["duration_ms"] == 12.5
    assert payload["rows"] == 7

    clear_correlation_ids()