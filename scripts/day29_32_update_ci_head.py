"""Safely update only the legacy CI assertion following `alembic upgrade head`."""
from __future__ import annotations

from pathlib import Path

PATH = Path(".github/workflows/etl-days26-28.yml")
OLD = "d26e00260001"
NEW = "d29b00000001"
MARKER = "- name: Apply all schema migrations"


def patch_ci_workflow(source: str) -> str:
    if source.count(MARKER) != 1:
        raise ValueError("Expected exactly one migration-check step")
    prefix, remainder = source.split(MARKER, 1)
    boundary = remainder.find("\n      - name:")
    if boundary == -1:
        raise ValueError("Cannot locate the end of the migration-check step")
    section, suffix = remainder[:boundary], remainder[boundary:]
    if f"= '{NEW}'" in section:
        return source  # Safely idempotent.
    if section.count(f"= '{OLD}'") != 1 or "python -m alembic upgrade head" not in section:
        raise ValueError("Unexpected migration-check contents: refusing blind replacement")
    section = section.replace(f"= '{OLD}'", f"= '{NEW}'", 1)
    return prefix + MARKER + section + suffix


def main() -> int:
    original = PATH.read_text(encoding="utf-8")
    changed = patch_ci_workflow(original)
    if changed != original:
        PATH.write_text(changed, encoding="utf-8", newline="\n")
    print("CI HEAD check now targets d29b00000001; explicit d26 checks preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
