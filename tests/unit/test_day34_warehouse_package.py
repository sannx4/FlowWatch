"""Static, installation-free regressions for the isolated Day34-38 dbt contract."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.day34_38_dbt_gate import (
    DB_NAME,
    OWNER,
    WAREHOUSE_SCHEMA,
    WarehouseGateError,
)

ROOT = Path(__file__).resolve().parents[2]
DBT = ROOT / "warehouse_dbt"


def test_profile_cannot_target_primary_database() -> None:
    profile = (DBT / "profiles.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s+dbname: flowwatch_historical_gate$", profile, re.MULTILINE)
    assert re.search(r"^\s+schema: fw_analytics$", profile, re.MULTILINE)
    assert re.search(r"^\s+user: flowwatch_owner$", profile, re.MULTILINE)
    assert "env_var('FLOWWATCH_DBT_PASSWORD')" in profile
    assert "password: ci_owner" not in profile
    assert (DB_NAME, OWNER, WAREHOUSE_SCHEMA) == (
        "flowwatch_historical_gate", "flowwatch_owner", "fw_analytics"
    )


def test_dbt_model_graph_and_contracts() -> None:
    project = yaml.safe_load((DBT / "dbt_project.yml").read_text(encoding="utf-8"))
    assert project["name"] == "flowwatch_financial"
    properties = yaml.safe_load((DBT / "models" / "properties.yml").read_text(encoding="utf-8"))
    models = {m["name"] for m in properties["models"]}
    assert {"dim_country", "dim_project", "dim_credit", "fct_credit_period",
            "mart_credit_period_metrics"} <= models
    for name in models:
        assert list((DBT / "models").rglob(name + ".sql")), name
    source = yaml.safe_load((DBT / "models" / "staging" / "sources.yml").read_text(encoding="utf-8"))
    assert source["sources"][0]["database"] == DB_NAME
    assert source["sources"][0]["schema"] == "public"


def test_every_fact_financial_field_preserved() -> None:
    from src.transformation.pure import MONEY_FIELDS

    fact = (DBT / "models" / "marts" / "fct_credit_period.sql").read_text(encoding="utf-8")
    stage = (DBT / "models" / "staging" / "stg_credit_snapshots.sql").read_text(encoding="utf-8")
    parity = (DBT / "tests" / "assert_fact_matches_source.sql").read_text(encoding="utf-8")
    for field in MONEY_FIELDS:
        assert "s." + field in fact
        assert field in stage
        assert "src." + field + " is distinct from fact." + field in parity
    assert "float" not in fact.lower()
    assert "round(" not in fact.lower()
    assert "coalesce(" not in fact.lower()


def test_temporal_metric_contract_is_honest() -> None:
    sql = (DBT / "models" / "reporting" / "mart_credit_period_metrics.sql").read_text(encoding="utf-8")
    assert "lag(" in sql
    assert "is_consecutive_month" in sql
    assert "case when is_consecutive_month" in sql
    assert "is not null" in sql
    assert "cashflow" not in sql.lower()


def test_singular_tests_include_canonical_parity() -> None:
    names = {p.name for p in (DBT / "tests").glob("*.sql")}
    assert {
        "assert_fact_matches_source.sql", "assert_unique_credit_period.sql",
        "assert_reporting_no_nonadjacent_delta.sql", "assert_metric_matches_fact.sql"
    } <= names


@pytest.mark.parametrize("bad_host", ["db.example.com", "postgres", "192.168.1.1"])
def test_external_host_is_rejected(monkeypatch: pytest.MonkeyPatch, bad_host: str) -> None:
    from scripts.day34_38_dbt_gate import _connection_settings

    monkeypatch.setenv("POSTGRES_HOST", bad_host)
    monkeypatch.setenv("FLOWWATCH_DBT_PASSWORD", "test-only-placeholder")
    with pytest.raises(WarehouseGateError, match="REFUSING"):
        _connection_settings()
