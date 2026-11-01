"""Create ignored local user JSON and token secret; never prints credentials.

Run from repository root: python -m scripts.day2_init_auth --username analyst
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
from getpass import getpass
from pathlib import Path

from argon2 import PasswordHasher


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="analyst")
    parser.add_argument("--role", choices=("analyst", "operator", "administrator"), default="analyst")
    args = parser.parse_args()
    if not args.username or len(args.username) > 80:
        parser.error("Username must be 1-80 characters")
    folder = Path("day2_local")
    folder.mkdir(exist_ok=True)
    target, env_path = folder / "users.json", folder / ".env"
    if target.exists() or env_path.exists():
        parser.error("Local auth configuration already exists; refusing to overwrite")
    password = getpass("New analyst password (minimum 12 characters): ")
    confirm = getpass("Confirm analyst password: ")
    if len(password) < 12 or password != confirm:
        parser.error("Passwords must match and be at least 12 characters")
    reader_password = getpass("PostgreSQL flowwatch_api_reader password: ")
    if not reader_password or any(ch in reader_password for ch in '\r\n'):
        parser.error("Invalid DB password")
    target.write_text(json.dumps([{"username": args.username, "role": args.role,
        "password_hash": PasswordHasher().hash(password)}], indent=2) + "\n", encoding="utf-8")
    env_path.write_text("FLOWWATCH_TOKEN_SECRET=" + secrets.token_hex(32) + "\n" +
                        "FLOWWATCH_AUTH_USERS_FILE=day2_local/users.json\n" +
                        "FLOWWATCH_API_DB_NAME=flowwatch_historical_gate\n" +
                        "FLOWWATCH_API_DB_USER=flowwatch_api_reader\n" +
                        "FLOWWATCH_API_DB_PASSWORD='" + reader_password.replace("'", "\\'") + "'\n" +
                        "FLOWWATCH_UI_ORIGIN=http://localhost:5173\n", encoding="utf-8")
    if os.name != "nt":
        target.chmod(0o600)
        env_path.chmod(0o600)
    print("PASS_LOCAL_AUTH_BOOTSTRAP: files created under ignored day2_local/; no passwords displayed")


if __name__ == "__main__":
    main()
