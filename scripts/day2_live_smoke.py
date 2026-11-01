"""Credential-safe Day 2 local API acceptance smoke test (GET only except login).

No database writes, no credential logging, no external destinations.
Run only after local FastAPI is up and day2_local authentication was initialized.
"""
from __future__ import annotations

import argparse
import getpass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


def call(base_url: str, path: str, *, token: str | None = None,
         payload: dict[str, str] | None = None, expected: int = 200) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base_url + path, data=body, headers=headers,
                      method="POST" if body is not None else "GET")
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            data = response.read()
    except HTTPError as exc:
        status = exc.code
        data = exc.read()
    except URLError as exc:
        raise RuntimeError("Local FastAPI unavailable; start Uvicorn on localhost") from exc
    if status != expected:
        # Deliberately do not print server response bodies or authentication headers.
        raise AssertionError(f"{path}: expected HTTP {expected}, got HTTP {status}")
    if expected != 200:
        return {}
    result = json.loads(data)
    if not isinstance(result, dict):
        raise TypeError(f"{path}: expected JSON object")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="analyst")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        parser.error("Only localhost HTTP origin URLs are accepted")
    base_url = args.base_url.rstrip("/")

    live = call(base_url, "/api/v1/health/live")
    assert live.get("status") == "alive", "API live health mismatch"
    call(base_url, "/api/v1/portfolio/summary", expected=401)
    password = getpass.getpass("Local analyst password (hidden): ")
    try:
        signed = call(base_url, "/api/v1/auth/token",
                      payload={"username": args.username, "password": password})
    finally:
        password = ""
    token = signed.get("access_token")
    assert isinstance(token, str) and token, "Login response has no token"

    user = call(base_url, "/api/v1/auth/me", token=token)
    assert user.get("username") == args.username, "Session identity mismatch"
    assert user.get("role") == "analyst", "This smoke requires an analyst account"
    call(base_url, "/api/v1/operations/warehouse", token=token, expected=403)
    call(base_url, "/api/v1/credits?limit=101", token=token, expected=422)
    ready = call(base_url, "/api/v1/health/ready", token=token)
    assert ready.get("status") == "ready", "Warehouse readiness failed"

    summary = call(base_url, "/api/v1/portfolio/summary", token=token)
    count = int(summary.get("credits", 0))
    assert summary.get("grain") == "latest_observation_per_credit" and count > 0
    countries = call(base_url, "/api/v1/countries?limit=100", token=token)
    projects = call(base_url, "/api/v1/projects?limit=100", token=token)
    credits = call(base_url, "/api/v1/credits?limit=100", token=token)
    watchlist = call(base_url, "/api/v1/risk/watchlist?limit=100", token=token)
    for name, value in (("countries", countries), ("projects", projects),
                        ("credits", credits), ("watchlist", watchlist)):
        assert isinstance(value.get("items"), list), f"{name}: items missing"
    assert countries["items"] and projects["items"] and credits["items"]
    assert len(credits["items"]) <= 100

    credit_id = int(credits["items"][0]["credit_id"])
    history = call(base_url, f"/api/v1/credits/{credit_id}/timeline?limit=250", token=token)
    observations = history.get("items")
    assert isinstance(observations, list) and observations, "Missing credit history"
    latest = observations[0]
    period = quote(str(latest["end_of_period"]), safe="")
    lineage = call(base_url, f"/api/v1/credits/{credit_id}/lineage?period={period}", token=token)
    source = lineage.get("item")
    assert isinstance(source, dict), "Missing source locator"
    assert source.get("credit_snapshot_id") is not None, "Missing canonical snapshot ID"
    assert source.get("ingestion_run_id") and source.get("source_record_key") and source.get("source_checksum"), "Incomplete source lineage"

    print("PASS_DAY2_LOCAL_API_ACCEPTANCE")
    print("Validated: unauthenticated rejection, analyst JWT, denied operator access, bounds validation,")
    print("warehouse readiness, portfolio, countries, projects, credits, watchlist, history, source lineage")
    print(f"Portfolio credits: {count}; selected credit history observations: {len(observations)}")
    print("No passwords, JWTs, or source identifiers were logged.")


if __name__ == "__main__":
    main()
