from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text


def build_engine():
    return create_engine(
        URL.create(
            drivername="postgresql+psycopg",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.getenv(
                "POSTGRES_HOST",
                "localhost",
            ),
            port=int(
                os.getenv(
                    "POSTGRES_PORT",
                    "5434",
                )
            ),
            database=os.environ["POSTGRES_DB"],
        )
    )


def main() -> None:
    load_dotenv()

    engine = build_engine()

    query = text(
        """
        SELECT
            c.credit_number,
            cs.end_of_period AS forecast_origin,

            (
                cs.end_of_period
                + INTERVAL '3 months'
            )::date AS target_3m,

            (
                cs.end_of_period
                + INTERVAL '6 months'
            )::date AS target_6m,

            (
                cs.end_of_period
                + INTERVAL '12 months'
            )::date AS target_12m

        FROM credit_snapshots cs

        JOIN credits c
          ON c.credit_id = cs.credit_id

        ORDER BY cs.end_of_period

        LIMIT 5
        """
    )

    try:
        with engine.connect() as connection:
            rows = connection.execute(
                query
            ).mappings().all()

        if not rows:
            raise RuntimeError(
                "No credit snapshots found in PostgreSQL."
            )

        print()
        print("DAY 7 TEMPORAL PROOF")
        print("--------------------")

        for row in rows:
            print()

            print(
                f"credit="
                f"{row['credit_number']}"
            )

            print(
                f"forecast_origin="
                f"{row['forecast_origin']}"
            )

            print(
                f"target_3m="
                f"{row['target_3m']}"
            )

            print(
                f"target_6m="
                f"{row['target_6m']}"
            )

            print(
                f"target_12m="
                f"{row['target_12m']}"
            )

        print()
        print(
            "forecast origin available: YES"
        )

        print(
            "3-month target constructible: YES"
        )

        print(
            "6-month target constructible: YES"
        )

        print(
            "12-month target constructible: YES"
        )

        print()
        print(
            "NOTE: these are candidate horizon target dates."
        )

        print(
            "Exact maturity and label-availability semantics "
            "will be formalized later."
        )

        print()
        print("TEMPORAL PROOF: SUCCESS")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()