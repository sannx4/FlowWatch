from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pymongo import MongoClient

DEFAULT_MONGODB_HOST = (
    "127.0.0.1"
)

DEFAULT_MONGODB_PORT = (
    27018
)

DEFAULT_MONGODB_DATABASE = (
    "flowwatch"
)

DEFAULT_AUTH_SOURCE = (
    "admin"
)


@dataclass(
    frozen=True
)
class MongoConnectionConfig:
    uri: str
    database_name: str

    username: str | None
    password: str | None

    auth_source: str = (
        DEFAULT_AUTH_SOURCE
    )


def _read_dotenv(
    path: Path = Path(
        ".env"
    ),
) -> dict[str, str]:
    """
    Read simple KEY=VALUE entries from the local .env file.

    Process environment variables always take precedence later.
    """

    if not path.exists():
        return {}

    values: dict[
        str,
        str,
    ] = {}

    for raw_line in (
        path.read_text(
            encoding="utf-8"
        ).splitlines()
    ):
        line = raw_line.strip()

        if (
            not line
            or line.startswith(
                "#"
            )
            or "=" not in line
        ):
            continue

        key, value = line.split(
            "=",
            1,
        )

        key = key.strip()

        value = (
            value.strip()
            .strip('"')
            .strip("'")
        )

        values[
            key
        ] = value

    return values


def load_mongodb_config() -> (
    MongoConnectionConfig
):
    """
    Load MongoDB configuration.

    Priority:

    1. process environment
    2. local .env
    3. safe development defaults

    Credentials are passed separately to PyMongo rather than being
    interpolated into a URI, avoiding URL-encoding problems.
    """

    dotenv = (
        _read_dotenv()
    )

    def value(
        name: str,
        default: str | None = None,
    ) -> str | None:
        return (
            os.getenv(
                name
            )
            or dotenv.get(
                name
            )
            or default
        )

    explicit_uri = value(
        "FLOWWATCH_MONGODB_URI"
    )

    database_name = value(
        "FLOWWATCH_MONGODB_DATABASE"
    )

    if database_name is None:
        database_name = value(
            "MONGO_INITDB_DATABASE",
            DEFAULT_MONGODB_DATABASE,
        )

    if database_name is None:
        database_name = (
            DEFAULT_MONGODB_DATABASE
        )

    if explicit_uri:
        return MongoConnectionConfig(
            uri=explicit_uri,
            database_name=(
                database_name
            ),
            username=None,
            password=None,
        )

    port_text = value(
        "MONGO_PORT",
        str(
            DEFAULT_MONGODB_PORT
        ),
    )

    if port_text is None:
        port = (
            DEFAULT_MONGODB_PORT
        )
    else:
        port = int(
            port_text
        )

    username = value(
        "MONGO_INITDB_ROOT_USERNAME"
    )

    password = value(
        "MONGO_INITDB_ROOT_PASSWORD"
    )

    if (
        username is None
    ) != (
        password is None
    ):
        raise RuntimeError(
            "MongoDB username and password "
            "must either both be configured "
            "or both be absent."
        )

    uri = (
        f"mongodb://"
        f"{DEFAULT_MONGODB_HOST}:"
        f"{port}"
    )

    return MongoConnectionConfig(
        uri=uri,
        database_name=(
            database_name
        ),
        username=username,
        password=password,
    )


def create_mongodb_client(
    config: MongoConnectionConfig,
) -> MongoClient[
    dict[str, Any]
]:
    """
    Build an authenticated PyMongo client.

    Username/password are supplied separately so special characters
    do not need manual URI escaping.
    """

    options: dict[
        str,
        Any,
    ] = {
        "serverSelectionTimeoutMS": (
            5000
        ),
        "tz_aware": True,
    }

    if (
        config.username
        is not None
    ):
        options[
            "username"
        ] = config.username

        options[
            "password"
        ] = config.password

        options[
            "authSource"
        ] = config.auth_source

    return MongoClient(
        config.uri,
        **options,
    )