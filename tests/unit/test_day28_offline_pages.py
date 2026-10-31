"""Offline data-origin guarantees for the Day28 page-window planner."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.day28_etl_gate import load_source_pages, manifest_identity


def _fixture(tmp_path: Path, n: int = 12) -> Path:
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"data": [{"credit_number": f"C-{i}"}
                                       for i in range(n)]}), encoding="utf-8")
    return path


def test_windowed_fixture_reuses_original_bytes(tmp_path: Path) -> None:
    source = _fixture(tmp_path)
    pages, mode = load_source_pages(source_file=source, pages_dir=None, windows=3)
    assert mode == "logical_windows_of_single_stored_page"
    assert len(pages) == 3
    assert sum(len(p.records) for p in pages) == 12
    assert all(p.raw_bytes == source.read_bytes() for p in pages)
    assert len({r.key for p in pages for r in p.records}) == 12
    assert {r.record_index for p in pages for r in p.records} == set(range(12))


def test_manifest_run_identity_deterministic(tmp_path: Path) -> None:
    source = _fixture(tmp_path)
    a, _ = load_source_pages(source_file=source, pages_dir=None, windows=3)
    b, _ = load_source_pages(source_file=source, pages_dir=None, windows=3)
    assert manifest_identity(a) == manifest_identity(b)


def test_source_mutation_changes_run_id(tmp_path: Path) -> None:
    source = _fixture(tmp_path)
    before, _ = load_source_pages(source_file=source, pages_dir=None, windows=3)
    source.write_text(source.read_text(encoding="utf-8") + " ", encoding="utf-8")
    after, _ = load_source_pages(source_file=source, pages_dir=None, windows=3)
    assert manifest_identity(before) != manifest_identity(after)


def test_requires_enough_observations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fewer observations"):
        load_source_pages(source_file=_fixture(tmp_path, 2), pages_dir=None, windows=3)


def test_real_page_directory(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for i in range(3):
        (pages_dir / f"page_{i:02}.json").write_text(
            json.dumps({"data": [{"credit_number": f"C-{i}"}]}), encoding="utf-8"
        )
    pages, mode = load_source_pages(source_file=None, pages_dir=pages_dir, windows=3)
    assert mode == "independent_stored_pages"
    assert sum(len(p.records) for p in pages) == 3
    assert all(p.records[0].record_index == 0 for p in pages)


def test_missing_true_pages_fails(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    with pytest.raises(ValueError, match="Require"):
        load_source_pages(source_file=None, pages_dir=pages_dir, windows=10)


def test_invalid_page_shape_fails(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text('{"not_data": []}', encoding="utf-8")
    with pytest.raises(TypeError, match="data list"):
        load_source_pages(source_file=source, pages_dir=None, windows=2)
