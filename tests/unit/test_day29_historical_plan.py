from __future__ import annotations

import pytest

from src.ingestion.historical_plan import (
    HistoricalSourceDrift,
    PageSpec,
    assert_page_contract,
    is_full_capture,
    plan_pages,
)


def test_ten_hundred_rows_three_pages() -> None:
    pages = plan_pages(1001, 1000, 0)
    assert pages == (PageSpec(1, 0, 1000), PageSpec(2, 1000, 1))
    assert is_full_capture(1001, pages)


def test_bounded_vs_full_report() -> None:
    pages = plan_pages(2500, 1000, 2)
    assert [p.offset for p in pages] == [0, 1000]
    assert not is_full_capture(2500, pages)
    assert is_full_capture(2500, plan_pages(2500, 1000, 0))


@pytest.mark.parametrize("total,size,max_pages", [(0, 1000, 3), (-1, 1000, 3), (1, 0, 3), (1, 1001, 0), (1, 10, -1)])
def test_invalid_plan_fails_closed(total: int, size: int, max_pages: int) -> None:
    with pytest.raises(ValueError):
        plan_pages(total, size, max_pages)


def test_accept_correct_page_boundary() -> None:
    assert_page_contract(
        spec=PageSpec(3, 2000, 17), reported_total=2017,
        expected_total=2017, returned_count=17,
        top=1000, skip=2000, page_size=1000,
    )


@pytest.mark.parametrize("changes", [
    {"reported_total": 2018}, {"returned_count": 16},
    {"top": 100}, {"skip": 2010},
])
def test_source_drift_rejected(changes: dict[str, int]) -> None:
    kwargs = {
        "spec": PageSpec(3, 2000, 17),
        "reported_total": 2017,
        "expected_total": 2017,
        "returned_count": 17,
        "top": 1000,
        "skip": 2000,
        "page_size": 1000,
    }
    kwargs.update(changes)
    with pytest.raises(HistoricalSourceDrift):
        assert_page_contract(**kwargs)


def test_exact_multiple_no_extra_empty_page() -> None:
    assert plan_pages(2000, 1000, 0)[-1].offset == 1000
    assert len(plan_pages(2000, 1000, 0)) == 2


def test_ci_head_patch_changes_only_first_assertion() -> None:
    from scripts.day29_32_update_ci_head import patch_ci_workflow

    original = ("- name: Apply all schema migrations\n"
                "        run: |\n"
                "          python -m alembic upgrade head\n"
                "          test \"$value\" = 'd26e00260001'\n"
                "      - name: Downgrade and repeat upgrade\n"
                "          test \"$value\" = 'd26e00260001'\n")
    changed = patch_ci_workflow(original)
    assert changed.count("= 'd26e00260001'") == 1
    assert changed.count("= 'd29b00000001'") == 1
    assert patch_ci_workflow(changed) == changed
