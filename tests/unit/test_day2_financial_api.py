"""Offline identity, warehouse query, and API contracts without DB access."""
from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.day2 import queries
from src.api.day2.app import create_app
from src.api.day2.config import Settings
from src.api.day2.security import authenticate, issue_token, load_users, verify_token


@pytest.fixture
def identity(tmp_path):
    path = tmp_path / "users.json"
    path.write_text(json.dumps([{
        "username": "analyst", "role": "analyst", "password_hash": PasswordHasher().hash("correct-horse-battery")
    }]), encoding="utf-8")
    settings = Settings(database="flowwatch_historical_gate", db_user="flowwatch_api_reader",
                        db_password="not-used", db_host="127.0.0.1", db_port=5434,
                        jwt_secret="s" * 64, users_file=path, ui_origin="http://localhost:5173")
    return settings


def test_identity_isolated_database(identity):
    assert identity.database_url().database == "flowwatch_historical_gate"
    with pytest.raises(ValueError):
        replace(identity, database="flowwatch").database_url()
    with pytest.raises(ValueError):
        replace(identity, db_user="flowwatch_owner").database_url()


def test_local_auth_and_signed_jwt(identity):
    users = load_users(identity.users_file)
    principal = authenticate(users, "analyst", "correct-horse-battery", "test-ip")
    token = issue_token(principal, identity.jwt_secret)
    assert verify_token(token, identity.jwt_secret, users) == principal
    with pytest.raises(HTTPException) as exc:
        verify_token(token, "z" * 64, users)
    assert exc.value.status_code == 401
    decoded = jwt.decode(token, identity.jwt_secret, algorithms=["HS256"],
                         audience="flowwatch-analyst-api", issuer="flowwatch-local-pilot")
    assert decoded["role"] == "analyst"


def test_revoked_user_rejected(identity):
    token = issue_token({"username": "analyst", "role": "analyst"}, identity.jwt_secret)
    with pytest.raises(HTTPException) as exc:
        verify_token(token, identity.jwt_secret, {})
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        verify_token(token, identity.jwt_secret, {"analyst": {"role": "operator"}})
    assert exc.value.status_code == 401


def test_login_rejects_wrong_password(identity):
    with pytest.raises(HTTPException) as exc:
        authenticate(load_users(identity.users_file), "analyst", "wrong", "unit-test-bad-password")
    assert exc.value.status_code == 401


def test_lossless_decimal_serialization():
    assert queries.json_safe({"x": Decimal("12345678901234567890.12")}) == {
        "x": "12345678901234567890.12"
    }


def test_fact_query_is_latest_per_credit_not_all_time():
    assert "DISTINCT ON (credit_id)" in queries.L
    assert "ORDER BY credit_id, end_of_period DESC" in queries.L


def test_api_health_and_auth_guards_without_database(identity):
    class NeverUseEngine:
        def dispose(self):
            pass
    app = create_app(identity, engine=NeverUseEngine())
    with TestClient(app) as client:
        health = client.get("/api/v1/health/live")
        assert health.status_code == 200
        assert health.json() == {"status": "alive"}
        assert client.get("/api/v1/portfolio/summary").status_code == 401
        res = client.post("/api/v1/auth/token", json={
            "username": "analyst", "password": "correct-horse-battery"
        })
        assert res.status_code == 200
        assert res.json()["token_type"] == "bearer"
        token = res.json()["access_token"]
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["role"] == "analyst"
        assert client.get("/api/v1/operations/warehouse", headers={"Authorization": f"Bearer {token}"}).status_code == 403
        assert client.get("/api/v1/countries?limit=101").status_code == 401


def test_no_dynamic_sql_table_identifiers():
    # Query strings are constants. User filters are bound via SQLAlchemy text().
    from inspect import getsource
    source = getsource(queries)
    assert "FROM fw_analytics.fct_credit_period" in source
    assert "LIMIT :limit" in source
    assert "ILIKE '%'||:q||'%'" in source
    assert "ORDER BY" in source


def test_no_password_or_token_in_reported_query_values(identity):
    assert "not-used" not in str(identity.database_url())
