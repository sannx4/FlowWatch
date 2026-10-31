"""Generate an Alembic revision linked to the current repo head, without DB writes.

Run after merging Day24: python -m scripts.day25_install_migration
The revision is based on sql/operational/day25_quarantine.sql.
"""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "d25cafe01250"
SOURCE = Path("sql/operational/day25_quarantine.sql")
TARGET = Path(f"alembic/versions/{REVISION}_source_quarantine.py")


def main() -> int:
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    if not head:
        raise RuntimeError("No unique Alembic head: resolve migrations first")
    if head == REVISION:
        print(f"Day25 migration already registered: {TARGET}")
        return 0
    if TARGET.exists():
        raise RuntimeError("Migration exists but is not the current head; inspect first")
    sql = SOURCE.read_text(encoding="utf-8")
    sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    statements = [s for s in statements if s not in ("BEGIN", "COMMIT")]
    if not statements or "source_quarantine" not in sql:
        raise RuntimeError("Migration SQL has unexpected contents")
    module = (
        '"""Day25 durable raw-source quarantine.\n\nRevision ID: ' + REVISION + '\nRevises: ' + head + '\n"""\n'
        'from __future__ import annotations\n\n'
        'from collections.abc import Sequence\n\nfrom alembic import op\n\n'
        f'revision: str = {REVISION!r}\n'
        f'down_revision: str | None = {head!r}\n'
        'branch_labels: str | Sequence[str] | None = None\n'
        'depends_on: str | Sequence[str] | None = None\n\n'
        'def upgrade() -> None:\n'
        + "".join(f"    op.execute({statement!r})\n" for statement in statements)
        + '\ndef downgrade() -> None:\n'
        + '    op.execute("DROP TABLE public.source_quarantine")\n'
    )
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(module, encoding="utf-8")
    print(f"Generated {TARGET} based on Alembic head {head}")
    print("Review before applying on any database. This command made no DB changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
