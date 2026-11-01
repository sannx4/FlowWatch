"""Check the synthetic CI fixture's month adjacency and exact NUMERIC change."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from scripts.day34_38_dbt_gate import _connection_settings, connect_isolated


def main() -> None:
    host, port, password = _connection_settings()
    engine = connect_isolated(host, port, password)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT end_of_period, is_consecutive_month,
                       change_in_reported_disbursed_usd
                FROM fw_analytics.mart_credit_period_metrics
                ORDER BY end_of_period
            """)).all()
            assert len(rows) == 3, "CI source fixture should have three rows"
            assert [r[1] for r in rows] == [False, True, False]
            assert rows[0][2] is None
            assert rows[1][2] == Decimal("150.00")
            assert rows[2][2] is None
        print("PASS_SYNTHETIC_DBT_MONTH_GAP_AND_NUMERIC_CONTRACT")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
