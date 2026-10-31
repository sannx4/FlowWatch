"""Pure, deterministic page planning and source-drift guards for the backfill."""
from __future__ import annotations

from dataclasses import dataclass


class HistoricalSourceDrift(RuntimeError):
    """Upstream pagination metadata changed during a bounded extraction."""


@dataclass(frozen=True, slots=True)
class PageSpec:
    number: int
    offset: int
    expected_count: int


def plan_pages(total_count: int, page_size: int, max_pages: int) -> tuple[PageSpec, ...]:
    """max_pages=0 means the complete reported dataset; otherwise a bounded sample."""
    if total_count <= 0:
        raise ValueError("Refusing empty or invalid upstream dataset")
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be in [1, 1000]")
    if max_pages < 0:
        raise ValueError("max_pages cannot be negative")
    count = (total_count + page_size - 1) // page_size
    if max_pages:
        count = min(count, max_pages)
    return tuple(
        PageSpec(i + 1, i * page_size, min(page_size, total_count - i * page_size))
        for i in range(count)
    )


def assert_page_contract(
    *, spec: PageSpec, reported_total: int, expected_total: int,
    returned_count: int, top: int, skip: int, page_size: int,
) -> None:
    if reported_total != expected_total:
        raise HistoricalSourceDrift(
            f"Source total changed from {expected_total} to {reported_total}; "
            "stop and create a new run rather than mixing source versions"
        )
    if top != page_size or skip != spec.offset:
        raise HistoricalSourceDrift("Source request coordinates changed")
    if returned_count != spec.expected_count:
        raise HistoricalSourceDrift(
            f"Short/long page at offset={spec.offset}: "
            f"expected={spec.expected_count} actual={returned_count}"
        )


def is_full_capture(total_count: int, pages: tuple[PageSpec, ...]) -> bool:
    return bool(pages) and pages[-1].offset + pages[-1].expected_count == total_count
