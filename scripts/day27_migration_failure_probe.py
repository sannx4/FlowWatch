"""Prove that a deliberately broken Alembic revision fails and rolls back.

Use ONLY against flowwatch_day28_gate on ephemeral CI services. The original
migration files are copied to a temporary directory before injecting a bad
revision; the repository's Alembic history is never altered.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import URL, create_engine, text

EXPECTED_DB = "flowwatch_day28_gate"
HEAD = "d26e00260001"
BAD = "d27bad260001"


def main() -> int:
    if os.getenv("POSTGRES_DB") != EXPECTED_DB:
        raise RuntimeError("REFUSING: migration probe requires flowwatch_day28_gate")
    if os.getenv("POSTGRES_HOST", "127.0.0.1") not in ("127.0.0.1", "localhost"):
        raise RuntimeError("REFUSING: migration failure probe requires localhost")
    root = Path.cwd()
    source = root / "alembic"
    ini = root / "alembic.ini"
    if not source.is_dir() or not ini.is_file():
        raise RuntimeError("Run from the FlowWatch repository root")
    engine = create_engine(URL.create(
        "postgresql+psycopg", username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")), database=EXPECTED_DB,
    ))
    try:
        with engine.connect() as con:
            if con.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("Migration failure probe requires successful Day26 HEAD")
        with tempfile.TemporaryDirectory(prefix="fw_migration_fault_") as tmp:
            dest = Path(tmp) / "alembic"
            shutil.copytree(source, dest)
            file = dest / "versions" / "d27bad260001_deliberately_broken.py"
            file.write_text('''"""Intentionally broken CI-only migration. NEVER MERGE."""
from alembic import op
revision = "d27bad260001"
down_revision = "d26e00260001"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE TABLE public.day27_atomicity_probe(id integer)")
    op.execute("SELECT * FROM public.day27_table_that_does_not_exist")

def downgrade():
    op.execute("DROP TABLE IF EXISTS public.day27_atomicity_probe")
''', encoding="utf-8")
            settings = ini.read_text(encoding="utf-8")
            settings, n = re.subn(
                r"(?m)^script_location\s*=.*$",
                "script_location = " + str(dest).replace("\\", "/"), settings,
            )
            if n != 1:
                raise RuntimeError("Could not locate Alembic script_location")
            tmpini = Path(tmp) / "alembic.ini"
            tmpini.write_text(settings, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "alembic", "-c", str(tmpini), "upgrade", BAD],
                cwd=root, env=os.environ.copy(), capture_output=True, text=True,
                timeout=90, check=False,
            )
            if proc.returncode == 0:
                raise AssertionError("Deliberately broken migration unexpectedly succeeded")
        with engine.connect() as con:
            still = con.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            marker = con.execute(text("SELECT to_regclass('public.day27_atomicity_probe')")).scalar_one()
            if still != HEAD or marker is not None:
                raise AssertionError(f"Bad migration not fully rolled back: head={still}, marker={marker}")
        print("PASS: broken revision blocked; migration transaction rolled back; original head intact")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
