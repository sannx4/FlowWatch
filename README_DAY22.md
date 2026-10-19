# FlowWatch Day 22 — Complete Installation & Verification (Windows CMD)

## 0. Git workflow

Only after Day-21 PR is merged:

```bat
git switch main
git pull --ff-only origin main
git switch -c day22-deterministic-transformations
```

## 1. Install this package

Place ZIP in Downloads, open CMD in `E:\flowwatch\FlowWatch` with `.venv` active:

```bat
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%USERPROFILE%\Downloads\FlowWatch_Day22_Full.zip' -DestinationPath '.' -Force"
```

Adds 5 files under `src`, `tests`, `scripts`, `docs` and one research report. It does **not** overwrite `day07.py`, ingestion loader, database credentials or migrations.

## 2. Run fast checks

```bat
python -m py_compile src\transformation\types.py src\transformation\pure.py scripts\day22_parity_audit.py tests\unit\test_day22_pure_transformation.py
python -m ruff check src tests scripts
python -m mypy src\transformation\types.py src\transformation\pure.py
python -m pytest -q tests\unit\test_day22_pure_transformation.py
```

Standalone implementation validation (outside the original repo): 47 new unit cases passed, with the Day-7 parity case skipped because the old module was not mounted. An available 1,000-row World Bank sample was decoded with `parse_float=Decimal`; all 1,000 records transformed without error. These checks do **not** replace your repository's Ruff, mypy, parity, or full-suite checks.

## 3. Compare to historical mapping on real local fixture

```bat
python -m scripts.day22_parity_audit
```

The command **does not** contact the World Bank, MongoDB or PostgreSQL. It compares the existing `day07.transform_record()` result to `pure.transform_canonical_record()` for every entry in `data/raw/world_bank_sample.json`. Returns exit code 1 and shows a mismatch count if it discovers behavior differences. Report: `reports/day22-transformation-parity.json`.

## 4. Full regression gate

```bat
python -m pytest -q
python -m ruff check src tests scripts
git diff --check
git status --short
```

## 5. Load-path integration policy

If and ONLY if parity audit and full regression pass, a **separate reviewed change** can redirect the `load_curated_record` import to the new function:

```
from src.transformation.pure import transform_canonical_record as transform_record
```

Do not blindly replace the loader yet. This package intentionally safeguards Day-21's verified route. In particular, strict rejection of binary floats is a changed contract and must be reconciled with source JSON decoding before activation on new batches.

## 6. Complete milestone evidence

- `src/transformation/types.py`
- `src/transformation/pure.py`
- `tests/unit/test_day22_pure_transformation.py`
- `scripts/day22_parity_audit.py`
- `docs/day22-source-mapping.md`
- `reports/day22-research-integrity.md`
- `reports/day22-transformation-parity.json` (generated locally)

Day-22 readiness requires a passing parity result and tests, not merely the creation of these files.
