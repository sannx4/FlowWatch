from __future__ import annotations

import argparse
from pathlib import Path

from src.ingestion.worldbank_client import (
    WorldBankClient,
    WorldBankClientConfig,
    WorldBankClientError,
)
from src.observability.logging import (
    configure_logging,
)

DEFAULT_OUTPUT = (
    "data/raw/world_bank_sample.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a validated World Bank "
            "credit-data sample."
        )
    )

    parser.add_argument(
        "--top",
        type=int,
        default=100,
        help=(
            "Maximum number of records "
            "to request."
        ),
    )

    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help=(
            "Number of source records "
            "to skip."
        ),
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=(
            "Destination path for the "
            "raw JSON response."
        ),
    )

    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=5.0,
        help=(
            "Connection timeout in seconds."
        ),
    )

    parser.add_argument(
        "--read-timeout",
        type=float,
        default=30.0,
        help=(
            "Read timeout in seconds."
        ),
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help=(
            "Number of retries after the "
            "initial attempt."
        ),
    )

    parser.add_argument(
        "--backoff-base",
        type=float,
        default=0.5,
        help=(
            "Initial exponential-backoff "
            "delay in seconds."
        ),
    )

    parser.add_argument(
        "--backoff-max",
        type=float,
        default=8.0,
        help=(
            "Maximum backoff delay "
            "in seconds."
        ),
    )

    return parser


def main() -> None:
    configure_logging()

    parser = build_parser()
    args = parser.parse_args()

    config = WorldBankClientConfig(
        connect_timeout_seconds=(
            args.connect_timeout
        ),
        read_timeout_seconds=(
            args.read_timeout
        ),
        max_retries=args.max_retries,
        backoff_base_seconds=(
            args.backoff_base
        ),
        backoff_max_seconds=(
            args.backoff_max
        ),
    )

    output_path = Path(
        args.output
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        with WorldBankClient(
            config
        ) as client:
            result = client.fetch(
                top=args.top,
                skip=args.skip,
            )

    except WorldBankClientError as exc:
        print()
        print("WORLD BANK FETCH FAILED")
        print("-----------------------")
        print(str(exc))
        print()
        print(
            "failure_metadata="
            f"{exc.metadata()}"
        )

        raise SystemExit(1) from exc

    output_path.write_bytes(
        result.raw_bytes
    )

    print()
    print("WORLD BANK FETCH COMPLETE")
    print("-------------------------")

    print(
        f"request_id="
        f"{result.request_id}"
    )

    print(
        f"status_code="
        f"{result.status_code}"
    )

    print(
        f"attempts="
        f"{result.attempts}"
    )

    print(
        f"duration_ms="
        f"{result.duration_ms:.2f}"
    )

    print(
        f"total_source_records="
        f"{result.total_count}"
    )

    print(
        f"records_fetched="
        f"{result.record_count}"
    )

    print(
        f"top="
        f"{result.top}"
    )

    print(
        f"skip="
        f"{result.skip}"
    )

    print(
        f"output="
        f"{output_path}"
    )


if __name__ == "__main__":
    main()