"""Tests for the daily-pipeline rejection path.

Nikki needs a way to permanently reject a daily-idea topic — both
*before* the polling-drafter has approved it and *after* (if she changed
her mind, or a status was mis-flipped to "complete" then changed back).
Setting an explicit reject-type ClickUp status (Rejected / Cancelled /
Archived / etc.) must mark the local state as rejected and keep it out
of both pending_approvals and pending_drafts forever after.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.daily import (
    DailyState,
    is_task_rejected,
    list_states,
    mark_approved,
    mark_emitted,
    mark_rejected,
    pending_approvals,
    pending_drafts,
    save_state,
)


# ---------------------------------------------------------------------------
# is_task_rejected — what counts as rejected
# ---------------------------------------------------------------------------


def test_is_task_rejected_recognises_cancelled_type():
    """ClickUp's built-in 'cancelled' status type is authoritative."""
    resp = {"id": "x", "status": {"status": "Cancelled", "type": "cancelled"}}
    rejected, name = is_task_rejected(resp)
    assert rejected is True
    assert name == "Cancelled"


def test_is_task_rejected_recognises_custom_status_named_rejected():
    """A custom status whose name is 'Rejected' must count, even with type=custom."""
    resp = {"id": "x", "status": {"status": "Rejected", "type": "custom"}}
    rejected, name = is_task_rejected(resp)
    assert rejected is True
    assert name == "Rejected"


def test_is_task_rejected_recognises_archived_and_declined():
    for name in ("Archived", "Declined", "Not Approved", "Skipped"):
        resp = {"id": "x", "status": {"status": name, "type": "custom"}}
        rejected, _ = is_task_rejected(resp)
        assert rejected is True, f"{name!r} should be treated as rejected"


def test_is_task_rejected_handles_bare_string_status():
    rejected, name = is_task_rejected({"status": "rejected"})
    assert rejected is True
    assert name == "rejected"


def test_is_task_rejected_treats_on_hold_as_pending_not_rejected():
    """'on hold' is a pause, not a rejection — Nikki can come back to it later."""
    resp = {"id": "x", "status": {"status": "on hold", "type": "open"}}
    rejected, _ = is_task_rejected(resp)
    assert rejected is False


def test_is_task_rejected_ignores_approved_status():
    resp = {"id": "x", "status": {"status": "complete", "type": "done"}}
    rejected, _ = is_task_rejected(resp)
    assert rejected is False


def test_is_task_rejected_returns_false_on_garbage_input():
    assert is_task_rejected(None) == (False, None)
    assert is_task_rejected("just a string") == (False, None)
    assert is_task_rejected({}) == (False, None)


# ---------------------------------------------------------------------------
# DailyState.is_rejected and mark_rejected
# ---------------------------------------------------------------------------


def _state(date: str = "2026-05-28") -> DailyState:
    return DailyState(
        date=date,
        proposal={"focus_keyword": "fk", "working_title": "T"},
    )


def test_is_rejected_property_false_by_default():
    s = _state()
    assert s.is_rejected is False
    assert s.rejected_at is None
    assert s.rejected_status_name is None


def test_mark_rejected_sets_rejected_fields():
    s = _state()
    mark_rejected(s, status_name="Rejected")
    assert s.is_rejected is True
    assert s.rejected_at is not None
    assert s.rejected_status_name == "Rejected"


def test_state_can_be_approved_then_rejected_audit_trail_preserved():
    """If Nikki approved by accident then explicitly rejected, both timestamps survive on disk."""
    s = _state()
    mark_emitted(s, task_id="abc")
    mark_approved(s, status_name="complete")
    mark_rejected(s, status_name="Rejected")
    assert s.is_emitted is True
    assert s.is_approved is True
    assert s.is_rejected is True
    assert s.approved_at is not None
    assert s.rejected_at is not None


# ---------------------------------------------------------------------------
# pending iterators must exclude rejected states
# ---------------------------------------------------------------------------


def test_pending_approvals_excludes_rejected(tmp_path: Path):
    keep = _state("2026-05-26")
    mark_emitted(keep, task_id="A")
    drop = _state("2026-05-27")
    mark_emitted(drop, task_id="B")
    mark_rejected(drop, status_name="Rejected")
    save_state(keep, tmp_path)
    save_state(drop, tmp_path)

    pending = pending_approvals(tmp_path)
    dates = [s.date for s in pending]
    assert dates == ["2026-05-26"], (
        "Rejected states must never appear in pending_approvals — they are terminal"
    )


def test_pending_drafts_excludes_rejected_even_after_approval(tmp_path: Path):
    """The core fix: a task approved-then-rejected must NOT be drafted."""
    will_draft = _state("2026-05-26")
    mark_emitted(will_draft, task_id="A")
    mark_approved(will_draft, status_name="complete")

    approved_then_rejected = _state("2026-05-27")
    mark_emitted(approved_then_rejected, task_id="B")
    mark_approved(approved_then_rejected, status_name="complete")
    mark_rejected(approved_then_rejected, status_name="Rejected")

    save_state(will_draft, tmp_path)
    save_state(approved_then_rejected, tmp_path)

    drafts = pending_drafts(tmp_path)
    dates = [s.date for s in drafts]
    assert dates == ["2026-05-26"], (
        "A state that was approved then rejected must NOT be drafted — "
        "rejection takes precedence over the prior approval"
    )


# ---------------------------------------------------------------------------
# Backward compatibility: pre-rejection state files on disk must still load
# ---------------------------------------------------------------------------


def test_legacy_state_file_without_rejected_fields_loads_cleanly(tmp_path: Path):
    """State files saved before this patch lack rejected_at / rejected_status_name."""
    legacy = {
        "date": "2026-05-26",
        "proposal": {"focus_keyword": "k", "working_title": "T"},
        "clickup_task_id": "abc",
        "clickup_emitted_at": "2026-05-26T07:00:00+00:00",
        "approved_at": None,
        "approved_status_name": None,
        "wp_post_id": None,
        "wp_edit_url": None,
        "drafted_at": None,
        "notes": [],
    }
    (tmp_path / "2026-05-26.json").write_text(json.dumps(legacy), encoding="utf-8")
    states = list_states(tmp_path)
    assert len(states) == 1
    assert states[0].is_rejected is False
    assert states[0].rejected_at is None
