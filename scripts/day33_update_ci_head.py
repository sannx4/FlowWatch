"""Update the single `upgrade head` assertion without changing Day26 rollback checks."""
from __future__ import annotations

from pathlib import Path

PATH = Path(".github/workflows/etl-days26-28.yml")
MARKER = "- name: Apply all schema migrations"
OLD = "d29b00000001"
NEW = "d33c00000001"


def patch_ci_workflow(source: str) -> str:
    if source.count(MARKER) != 1:
        raise ValueError("Expected exactly one migration-check step")
    prefix, remainder = source.split(MARKER, 1)
    boundary = remainder.find("\n      - name:")
    if boundary == -1:
        raise ValueError("Cannot locate migration-check step boundary")
    step, suffix = remainder[:boundary], remainder[boundary:]
    if f"= '{NEW}'" in step:
        return source
    if "python -m alembic upgrade head" not in step or step.count(f"= '{OLD}'") != 1:
        raise ValueError("Unexpected migration step; refusing blind CI edit")
    step = step.replace(f"= '{OLD}'", f"= '{NEW}'", 1)
    return prefix + MARKER + step + suffix


def main() -> int:
    original = PATH.read_text(encoding="utf-8")
    updated = patch_ci_workflow(original)
    if updated != original:
        PATH.write_text(updated, encoding="utf-8", newline="\n")
    print(f"CI HEAD now targets {NEW}; explicit Day26 rollback checks preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
