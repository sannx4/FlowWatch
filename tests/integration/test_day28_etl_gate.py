"""Live isolation regression for Day28, run only after the gate on CI services."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from scripts.day28_etl_gate import (
    MONGO_DB,
    PG_DB,
    REPORT,
    create_gate_engine,
    mongo_for_gate,
    verify_gate_database,
)

pytestmark = pytest.mark.skipif(
    os.getenv("FLOWWATCH_RUN_INTEGRATION") != "1",
    reason="Requires ephemeral services and explicit opt-in",
)


def test_integrated_gate_wrote_exact_reconciled_evidence() -> None:
    assert REPORT.exists(), "Run python -m scripts.day28_etl_gate before integration tests"
    import json
    report = json.loads(Path(REPORT).read_text(encoding="utf-8"))
    assert report["status"] == "PASS_DAY26_27_28_LOCAL_ETL_GATE"
    assert report["postgres_database"] == PG_DB
    assert report["mongo_database"] == MONGO_DB
    assert report["source_api_contacted"] is False
    assert report["fault_injection_detection"] is True
    mongo = mongo_for_gate()
    engine = create_gate_engine()
    try:
        with engine.connect() as con:
            verify_gate_database(con)
            run_id = report["run_id"]
            rows = con.execute(text("""
                SELECT attempt_no, fetched, raw_stored, accepted, rejected,
                       inserted, unchanged, status
                FROM public.etl_attempts WHERE run_id=:run_id
                ORDER BY attempt_no
            """), {"run_id": run_id}).all()
            n = report["source_observations"]
            assert [tuple(row) for row in rows] == [
                (1, n, n, n - 1, 1, n - 1, 0, "PASS"),
                (2, n, n, n, 0, 1, n - 1, "PASS"),
                (3, n, n, n, 0, 0, n, "PASS"),
            ]
            assert con.execute(text("""
                SELECT count(*) FROM public.etl_record_decisions
                WHERE run_id=:run_id
            """), {"run_id": run_id}).scalar_one() == n * 3
            assert con.execute(text("""
                SELECT count(*) FROM public.source_quarantine
                WHERE source_run_id=:run_id AND status='RESOLVED' AND retry_count=1
            """), {"run_id": run_id}).scalar_one() == 1
        assert mongo[MONGO_DB]["raw_records"].count_documents({"run_id": run_id}) == n
        assert mongo[MONGO_DB]["raw_pages"].count_documents({"run_id": run_id}) == report["source_pages"]
    finally:
        engine.dispose()
        mongo.close()
