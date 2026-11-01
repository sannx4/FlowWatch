"""Local pilot identity, Argon2 credentials, short-lived signed access tokens.

This is a self-hosted pilot identity provider, *not* a complete OIDC server.
Production identity federation is a separate integration milestone.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, status

ROLES = {"analyst", "operator", "administrator"}
AUDIENCE = "flowwatch-analyst-api"
ISSUER = "flowwatch-local-pilot"
TTL_MINUTES = 30
HASHER = PasswordHasher()
_LOCK = threading.Lock()
_FAILURES: dict[str, list[float]] = {}


def load_users(path: Path) -> dict[str, dict[str, str]]:
    users: dict[str, dict[str, str]] = {}
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, list):
        raise TypeError("Local users file must contain an array")
    for item in content:
        if not isinstance(item, dict):
            raise TypeError("Each user must be an object")
        name = item.get("username")
        role = item.get("role")
        hashed = item.get("password_hash")
        if (not isinstance(name, str) or not 1 <= len(name) <= 80 or
                role not in ROLES or not isinstance(hashed, str) or
                not hashed.startswith("$argon2") or name in users):
            raise ValueError("Invalid or duplicate local user entry")
        users[name] = {"role": role, "password_hash": hashed}
    if not users:
        raise ValueError("Configure at least one local user")
    return users


def _rate_guard(key: str) -> None:
    now = time.monotonic()
    with _LOCK:
        failures = [x for x in _FAILURES.get(key, []) if now - x < 60]
        _FAILURES[key] = failures
        if len(failures) >= 5:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts")


def _record_failure(key: str) -> None:
    with _LOCK:
        _FAILURES.setdefault(key, []).append(time.monotonic())


def authenticate(users: dict[str, dict[str, str]], username: str, password: str, client_ip: str) -> dict[str, str]:
    key = f"{client_ip}:{username[:80]}"
    _rate_guard(key)
    user = users.get(username)
    try:
        valid = bool(user) and HASHER.verify(user["password_hash"], password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid:
        _record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    with _LOCK:
        _FAILURES.pop(key, None)
    return {"username": username, "role": user["role"]}


def issue_token(principal: dict[str, str], secret: str) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": principal["username"], "role": principal["role"],
        "iss": ISSUER, "aud": AUDIENCE,
        "iat": now, "nbf": now, "exp": now + timedelta(minutes=TTL_MINUTES),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def verify_token(token: str, secret: str, users: dict[str, dict[str, str]]) -> dict[str, str]:
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], audience=AUDIENCE,
                            issuer=ISSUER, options={"require": ["exp", "iat", "sub", "iss", "aud"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    name, role = claims.get("sub"), claims.get("role")
    if not isinstance(name, str) or name not in users or users[name]["role"] != role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer authorized")
    return {"username": name, "role": role}
