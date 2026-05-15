"""Regression: list_states must ignore archive-style filenames.

Bug history: 2026-05-13 the polling-drafter /loop fired and pending_approvals
returned the OLD test seed from `2026-05-12.test-archive-pre-e2e.json` —
because list_states' glob `*.json` matched the archived file. The state's
`date` field was still `2026-05-12` and its `clickup_task_id` (86ahe10xa)
pointed at the original test seed's ClickUp task, which was still in
status=published. Had the workflow proceeded, the polling-drafter would
have generated 2500-word prose and pushed a duplicate WP draft.

The fix: list_states only loads filenames matching strict YYYY-MM-DD.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.daily import DailyState, list_states


def _write_state(tmp: Path, name: str, *, task_id: str | None) -> None:
    state = {
        "date": "2026-05-12",
        "proposal": {
            "focus_keyword": "x",
            "working_title": "x",
            "one_line_angle": "x",
            "outline_bullets": [],
            "slug": "x",
            "audience": "done-for-you",
            "category_id": 29,
            "intent": "informational",
            "target_date": "2026-05-12",
            "discovery_source": "test",
            "discovery_id": "test",
            "discovery_evidence": {},
            "cannibalization_severity": "clear",
            "cannibalization_rationale": "",
            "matched_post_url": None,
            "score": 0.0,
        },
        "clickup_task_id": task_id,
        "clickup_emitted_at": "2026-05-12T00:00:00+00:00" if task_id else None,
        "approved_at": None,
        "approved_status_name": None,
        "wp_post_id": None,
        "wp_edit_url": None,
        "drafted_at": None,
        "notes": [],
    }
    (tmp / name).write_text(json.dumps(state), encoding="utf-8")


def test_list_states_includes_strict_date_filenames(tmp_path: Path) -> None:
    _write_state(tmp_path, "2026-05-12.json", task_id="LIVE_TASK")
    states = list_states(tmp_path)
    assert len(states) == 1
    assert states[0].clickup_task_id == "LIVE_TASK"


def test_list_states_ignores_archive_suffix(tmp_path: Path) -> None:
    _write_state(tmp_path, "2026-05-12.json", task_id="LIVE_TASK")
    _write_state(tmp_path, "2026-05-12.test-archive.json", task_id="ARCHIVED_TASK")
    _write_state(tmp_path, "2026-05-09.test-archive-pre-e2e.json", task_id="OLDER_ARCHIVED")
    states = list_states(tmp_path)
    assert len(states) == 1
    assert states[0].clickup_task_id == "LIVE_TASK"
    archived_ids = {s.clickup_task_id for s in states}
    assert "ARCHIVED_TASK" not in archived_ids
    assert "OLDER_ARCHIVED" not in archived_ids


def test_list_states_ignores_other_non_date_filenames(tmp_path: Path) -> None:
    _write_state(tmp_path, "2026-05-12.json", task_id="LIVE_TASK")
    _write_state(tmp_path, "backup.json", task_id="BACKUP")
    _write_state(tmp_path, "scratch-state.json", task_id="SCRATCH")
    _write_state(tmp_path, "2026-05-12.bak.json", task_id="BAK")
    states = list_states(tmp_path)
    assert len(states) == 1
    assert states[0].clickup_task_id == "LIVE_TASK"


def test_list_states_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert list_states(tmp_path) == []
