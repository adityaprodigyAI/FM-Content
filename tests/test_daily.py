"""Tests for tools/daily.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools.daily import (
    DailyState,
    candidate_to_proposal_dict,
    is_task_approved,
    list_states,
    load_state,
    mark_approved,
    mark_drafted,
    mark_emitted,
    pending_approvals,
    pending_drafts,
    pick_top_candidate,
    save_state,
)
from tools.discover import Candidate


# ---------- pick_top_candidate ----------


def _cand(focus_keyword: str, *, source: str = "gsc_striking_distance",
          score: float = 5.0) -> Candidate:
    return Candidate(
        focus_keyword=focus_keyword,
        suggested_title_seed=focus_keyword.title(),
        audience="done-for-you",  # type: ignore[arg-type]
        category_id=27,
        intent="informational",  # type: ignore[arg-type]
        score=score,
        rationale="test",
        discovery_source=source,  # type: ignore[arg-type]
        discovery_id=f"{source}:{focus_keyword}",
        discovery_evidence={"keyword": focus_keyword},
    )


def test_pick_top_candidate_returns_none_on_empty():
    assert pick_top_candidate([]) is None


def test_pick_top_candidate_applies_source_weights():
    cands = [
        _cand("low gsc", source="gsc_striking_distance", score=3.0),  # 3.0 * 1.4 = 4.2
        _cand("high aeo", source="searchable_prompt", score=4.0),     # 4.0 * 1.0 = 4.0
    ]
    pick = pick_top_candidate(cands)
    assert pick is not None
    assert pick.focus_keyword == "low gsc"


# ---------- candidate_to_proposal_dict ----------


def test_candidate_to_proposal_dict_shape():
    cand = _cand("ai workflow")
    proposal = candidate_to_proposal_dict(
        cand,
        title="AI Workflow Automation: A Proven 2026 Guide",
        angle="The operator's view.",
        outline=["a", "b", "c"],
        target_date="2026-05-09",
    )
    assert proposal["focus_keyword"] == "ai workflow"
    assert proposal["working_title"] == "AI Workflow Automation: A Proven 2026 Guide"
    assert proposal["slug"] == "ai-workflow"
    assert proposal["target_date"] == "2026-05-09"
    assert proposal["discovery_source"] == "gsc_striking_distance"


# ---------- save / load round-trip ----------


def _make_state(date_str: str = "2026-05-09") -> DailyState:
    cand = _cand("ai shopping")
    return DailyState(
        date=date_str,
        proposal=candidate_to_proposal_dict(
            cand, title="AI Shopping: 2026 Guide",
            angle="x", outline=["1", "2", "3"],
            target_date=date_str,
        ),
    )


def test_save_load_roundtrip(tmp_path: Path):
    s = _make_state("2026-05-09")
    save_state(s, dir_=tmp_path)
    loaded = load_state("2026-05-09", dir_=tmp_path)
    assert loaded is not None
    assert loaded.date == "2026-05-09"
    assert loaded.proposal["focus_keyword"] == "ai shopping"


def test_load_state_returns_none_when_missing(tmp_path: Path):
    assert load_state("2026-01-01", dir_=tmp_path) is None


# ---------- state-machine markers ----------


def test_mark_emitted_sets_clickup_id_and_timestamp():
    s = _make_state()
    mark_emitted(s, task_id="86abc123")
    assert s.is_emitted
    assert s.clickup_task_id == "86abc123"
    assert s.clickup_emitted_at is not None


def test_mark_approved_sets_timestamp_and_status_name():
    s = _make_state()
    mark_emitted(s, task_id="86abc")
    mark_approved(s, status_name="published")
    assert s.is_approved
    assert s.approved_status_name == "published"
    assert s.approved_at is not None


def test_mark_drafted_sets_post_id_and_edit_url():
    s = _make_state()
    mark_emitted(s, task_id="86abc")
    mark_approved(s)
    mark_drafted(s, post_id=12345,
                 edit_url="https://firstmovers.ai/wp-admin/post.php?post=12345&action=edit")
    assert s.is_drafted
    assert s.wp_post_id == 12345
    assert s.wp_edit_url is not None


# ---------- pending lists ----------


def test_pending_approvals_returns_only_emitted_unapproved(tmp_path: Path):
    a = _make_state("2026-05-09"); mark_emitted(a, task_id="86a")
    b = _make_state("2026-05-10"); mark_emitted(b, task_id="86b"); mark_approved(b)
    c = _make_state("2026-05-11")  # not yet emitted
    save_state(a, dir_=tmp_path)
    save_state(b, dir_=tmp_path)
    save_state(c, dir_=tmp_path)
    pending = pending_approvals(dir_=tmp_path)
    assert [s.date for s in pending] == ["2026-05-09"]


def test_pending_drafts_returns_only_approved_undrafted(tmp_path: Path):
    a = _make_state("2026-05-09"); mark_emitted(a, task_id="86a")
    b = _make_state("2026-05-10"); mark_emitted(b, task_id="86b"); mark_approved(b)
    c = _make_state("2026-05-11"); mark_emitted(c, task_id="86c")
    mark_approved(c); mark_drafted(c, post_id=999)
    save_state(a, dir_=tmp_path)
    save_state(b, dir_=tmp_path)
    save_state(c, dir_=tmp_path)
    pending = pending_drafts(dir_=tmp_path)
    assert [s.date for s in pending] == ["2026-05-10"]


def test_list_states_returns_in_date_order(tmp_path: Path):
    save_state(_make_state("2026-05-11"), dir_=tmp_path)
    save_state(_make_state("2026-05-09"), dir_=tmp_path)
    save_state(_make_state("2026-05-10"), dir_=tmp_path)
    states = list_states(dir_=tmp_path)
    assert [s.date for s in states] == ["2026-05-09", "2026-05-10", "2026-05-11"]


# ---------- is_task_approved ----------


def test_is_task_approved_with_dict_status_done():
    response = {
        "id": "abc",
        "status": {"id": "x", "status": "complete", "type": "done", "color": "#080"},
    }
    approved, name = is_task_approved(response)
    assert approved
    assert name == "complete"


def test_is_task_approved_with_dict_status_open():
    response = {"status": {"id": "x", "status": "idea", "type": "open"}}
    approved, name = is_task_approved(response)
    assert not approved


def test_is_task_approved_with_bare_string_published():
    response = {"id": "x", "status": "published"}
    approved, name = is_task_approved(response)
    assert approved
    assert name == "published"


def test_is_task_approved_with_bare_string_idea():
    response = {"id": "x", "status": "idea"}
    approved, name = is_task_approved(response)
    assert not approved


def test_is_task_approved_returns_false_on_garbage():
    approved, name = is_task_approved(None)
    assert not approved
    assert name is None
