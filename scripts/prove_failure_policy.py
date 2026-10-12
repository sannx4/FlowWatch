from __future__ import annotations

import pytest


def print_policy() -> None:
    print()
    print("DAY 13 FAILURE POLICY")
    print()

    print(
        "connection reset       "
        "-> RETRY -> FAIL CLOSED"
    )

    print(
        "malformed JSON         "
        "-> FAIL CLOSED"
    )

    print(
        "missing required field "
        "-> QUARANTINE"
    )

    print(
        "duplicate page         "
        "-> REJECT / FAIL CLOSED"
    )

    print(
        "partial write          "
        "-> ROLLBACK -> FAIL CLOSED"
    )

    print()


def main() -> None:
    print_policy()

    exit_code = pytest.main(
        [
            "tests/faults",
            "-q",
        ]
    )

    if (
        exit_code
        != pytest.ExitCode.OK
    ):
        raise SystemExit(
            int(
                exit_code
            )
        )

    print()
    print(
        "CONNECTION RESET POLICY: PASS"
    )

    print(
        "MALFORMED JSON POLICY: PASS"
    )

    print(
        "MISSING FIELD POLICY: PASS"
    )

    print(
        "DUPLICATE PAGE POLICY: PASS"
    )

    print(
        "PARTIAL WRITE POLICY: PASS"
    )

    print()
    print(
        "DAY 13 PROOF PASSED"
    )


if __name__ == "__main__":
    main()