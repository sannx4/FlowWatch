from logging.config import fileConfig
import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL

from src.db.base import Base

# Import models so SQLAlchemy registers all tables
# in Base.metadata before Alembic autogeneration runs.
import src.db.models  # noqa: F401


# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------
# Alembic configuration
# ---------------------------------------------------------

config = context.config


if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ---------------------------------------------------------
# Build PostgreSQL connection URL from .env
# ---------------------------------------------------------

def build_database_url() -> str:
    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5434")),
        database=os.environ["POSTGRES_DB"],
    )

    return url.render_as_string(hide_password=False)


database_url = build_database_url()

# Alembic Config uses interpolation, so % characters must
# be escaped if one happens to exist inside the password.
config.set_main_option(
    "sqlalchemy.url",
    database_url.replace("%", "%%"),
)


# ---------------------------------------------------------
# SQLAlchemy metadata used by Alembic autogenerate
# ---------------------------------------------------------

target_metadata = Base.metadata


# ---------------------------------------------------------
# Offline migrations
# ---------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations without opening a DB connection."""

    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------
# Online migrations
# ---------------------------------------------------------

def run_migrations_online() -> None:
    """Run migrations using a real database connection."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------
# Execute appropriate migration mode
# ---------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()