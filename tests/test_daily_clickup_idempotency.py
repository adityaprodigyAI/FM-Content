"""Tests for tools.daily.should_skip_for_clickup_dup.

Verifies the dual-mode cutover safety check that queries ClickUp for an
existing daily-idea task before the /loop emits a new one. Without this
check, a /schedule cloud routine + a /loop local routine firing on the
same day would produce duplicate ClickUp tasks (the cloud has no access
to the local state file).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tools.daily import should_skip_for_clickup_dup


def test_skip_when_clickup_task_exists_for_today() -> None:
    """A task tagged fm-content-daily with today's date prefix triggers skip."""
    fake_search = MagicMock(return_value={
        "tasks": [
            {
                "id": "abc123",
                "name": "[2026-05-12] AI consulting ROI for mid-market",
                "tags": [{"name": "fm-content-daily"}],
            },
        ],
    })
    skip, task_id = should_skip_for_clickup_dup(
        today="2026-05-12", clickup_search_fn=fake_search,
    )
    assert skip is True
    assert task_id == "abc123"


def test_no_skip_when_no_tasks_returned() -> None:
    """Empty tasks list means no duplicate — proceed with emit."""
    fake_search = MagicMock(return_value={"tasks": []})
    skip, task_id = should_skip_for_clickup_dup(
        today="2026-05-12", clickup_search_fn=fake_search,
    )
    assert skip is False
    assert task_id is None


def test_no_skip_when_clickup_task_for_different_day() -> None:
    """A task from yesterday should not block today's emit."""
    fake_search = MagicMock(return_value={
        "tasks": [
            {
                "id": "abc123",
                "name": "[2026-05-11] Yesterday's idea",
                "tags": [{"name": "fm-content-daily"}],
            },
        ],
    })
    skip, task_id = should_skip_for_clickup_dup(
        today="2026-05-12", clickup_search_fn=fake_search,
    )
    assert skip is False
    assert task_id is None


def test_no_skip_when_task_lacks_required_tag() -> None:
    """Task with today's prefix but wrong tag is not a daily-idea dup."""
    fake_search = MagicMock(return_value={
        "tasks": [
            {
                "id": "abc999",
                "name": "[2026-05-12] Some other workstream task",
                "tags": [{"name": "marketing-ops"}],
            },
        ],
    })
    skip, task_id = should_skip_for_clickup_dup(
        today="2026-05-12", clickup_search_fn=fake_search,
    )
    assert skip is False
    assert task_id is None


def test_passes_correct_query_args_to_clickup() -> None:
    """The helper queries the Content Projects list with the daily tag."""
    fake_search = MagicMock(return_value={"tasks": []})
    should_skip_for_clickup_dup(today="2026-05-12", clickup_search_fn=fake_search)
    fake_search.assert_called_once_with(
        list_id="901326229295",
        tags=["fm-content-daily"],
        order_by="created",
        reverse=True,
        limit=5,
    )
