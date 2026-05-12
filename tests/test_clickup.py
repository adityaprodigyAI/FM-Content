"""Tests for tools/clickup.py.

Verifies the slate-emit payload shapes and the approval-parsing logic.
No network calls.
"""

from __future__ import annotations

import json

from tools.clickup import (
    DONE_STATUS_TYPES,
    build_edit_url_reply,
    build_parent_task_payload,
    build_status_comment,
    build_subtask_payloads,
    filter_proposals_by_approval,
    parse_approved_subtasks,
)
from tools.identities import (
    CONTENT_PROJECTS_LIST_ID,
    NIKKI_CLICKUP_USER_ID,
)
from tools.slate import Slate, SlateProposal


def _proposal(focus_keyword: str, *, title: str | None = None) -> SlateProposal:
    return SlateProposal(
        focus_keyword=focus_keyword,
        working_title=title or focus_keyword.title(),
        one_line_angle="angle",
        outline_bullets=["a", "b", "c"],
        slug=focus_keyword.replace(" ", "-"),
        audience="done-for-you",
        category_id=27,
        intent="informational",
        target_date="2026-05-12",
        discovery_source="gsc_striking_distance",
        discovery_id=f"gsc:{focus_keyword}",
        discovery_evidence={"keyword": focus_keyword},
    )


def _slate(*focus_keywords: str) -> Slate:
    proposals = [_proposal(fk) for fk in focus_keywords]
    return Slate(
        week="2026-W22",
        proposals=proposals,
        discovery_summary={
            "by_source": {"gsc_striking_distance": len(proposals)},
            "total_emitted": len(proposals),
        },
    )


# ---------- build_parent_task_payload ----------


def test_parent_task_payload_targets_content_projects_list():
    slate = _slate("a", "b")
    p = build_parent_task_payload(slate)
    assert p.list_id == CONTENT_PROJECTS_LIST_ID
    assert "2026-W22" in p.name
    assert NIKKI_CLICKUP_USER_ID in p.assignees


def test_parent_task_description_includes_source_summary():
    slate = _slate("a", "b")
    p = build_parent_task_payload(slate)
    assert "gsc_striking_distance" in p.description


# ---------- build_subtask_payloads ----------


def test_subtask_payloads_have_one_per_proposal():
    slate = _slate("a", "b", "c")
    subs = build_subtask_payloads(slate, parent_task_id="parent123")
    assert len(subs) == 3
    assert all(s.parent_task_id == "parent123" for s in subs)


def test_subtask_custom_id_is_focus_keyword():
    slate = _slate("ai consulting cost")
    subs = build_subtask_payloads(slate, parent_task_id="p")
    assert subs[0].custom_id == "ai consulting cost"


def test_subtask_description_includes_outline_and_evidence():
    slate = _slate("ai consulting cost")
    subs = build_subtask_payloads(slate, parent_task_id="p")
    desc = subs[0].description
    assert "ai consulting cost" in desc
    assert "discovery_evidence" in desc


# ---------- parse_approved_subtasks ----------


def test_parse_approves_done_status_type():
    response = {
        "subtasks": [
            {"name": "title 1", "custom_id": "focus-1",
             "status": {"type": "done", "status": "complete"}},
            {"name": "title 2", "custom_id": "focus-2",
             "status": {"type": "open", "status": "to do"}},
        ]
    }
    approved = parse_approved_subtasks(response)
    assert approved == ["focus-1"]


def test_parse_approves_closed_status_type():
    response = {
        "subtasks": [
            {"name": "title 1", "custom_id": "focus-a",
             "status": {"type": "closed", "status": "closed"}},
        ]
    }
    approved = parse_approved_subtasks(response)
    assert approved == ["focus-a"]


def test_parse_falls_back_to_name_when_no_custom_id():
    response = {
        "subtasks": [
            {"name": "Working Title One",
             "status": {"type": "done", "status": "complete"}},
        ]
    }
    approved = parse_approved_subtasks(response)
    assert approved == ["Working Title One"]


def test_parse_handles_mcp_text_wrapper():
    response = [{"type": "text", "text": json.dumps({
        "subtasks": [
            {"name": "x", "custom_id": "focus-x",
             "status": {"type": "done", "status": "complete"}},
        ]
    })}]
    approved = parse_approved_subtasks(response)
    assert approved == ["focus-x"]


def test_parse_returns_empty_on_garbage():
    assert parse_approved_subtasks(None) == []
    assert parse_approved_subtasks("nonsense") == []
    assert parse_approved_subtasks({"no_subtasks_key": "yep"}) == []


def test_done_status_types_constant():
    assert "done" in DONE_STATUS_TYPES
    assert "closed" in DONE_STATUS_TYPES
    assert "open" not in DONE_STATUS_TYPES


def test_parse_approves_bare_string_status():
    """The MCP returns subtasks with `status` as a string (not a dict) when
    called with subtasks=true. Match by name allowlist."""
    response = {
        "subtasks": [
            {"name": "title 1", "custom_id": "focus-1", "status": "published"},
            {"name": "title 2", "custom_id": "focus-2", "status": "idea"},
            {"name": "title 3", "custom_id": "focus-3", "status": "Closed"},
        ]
    }
    approved = parse_approved_subtasks(response)
    assert "focus-1" in approved
    assert "focus-3" in approved
    assert "focus-2" not in approved


def test_parse_handles_status_object_with_published_name():
    """Rich object form with `.type` not 'done'/'closed' but `.status` = 'published'."""
    response = {
        "subtasks": [
            {"name": "x", "custom_id": "focus-x",
             "status": {"id": "abc", "status": "published",
                        "type": "closed", "color": "#008844"}},
        ]
    }
    approved = parse_approved_subtasks(response)
    assert approved == ["focus-x"]


# ---------- filter_proposals_by_approval ----------


def test_filter_proposals_returns_approved_subset():
    slate = _slate("focus-a", "focus-b", "focus-c")
    approved = filter_proposals_by_approval(slate, ["focus-a", "focus-c"])
    assert [p.focus_keyword for p in approved] == ["focus-a", "focus-c"]


def test_filter_proposals_caps_at_max_approvals():
    slate = _slate(*[f"focus-{i}" for i in range(10)])
    approved = filter_proposals_by_approval(
        slate,
        [f"focus-{i}" for i in range(10)],
        max_approvals=7,
    )
    assert len(approved) == 7


def test_filter_proposals_matches_by_working_title_too():
    slate = _slate("focus a")
    slate.proposals[0].__dict__  # ensure construction OK
    proposals = filter_proposals_by_approval(slate, ["Focus A"])
    assert len(proposals) == 1


# ---------- build_edit_url_reply ----------


def test_edit_url_reply_lists_each_url():
    text = build_edit_url_reply(
        "2026-W22",
        {"a": "https://x/a", "b": "https://x/b"},
        rank_math_set_count=2,
    )
    assert "https://x/a" in text
    assert "https://x/b" in text
    assert "Rank Math meta set on 2 of 2" in text


# ---------- build_status_comment ----------


def test_status_comment_links_parent_task():
    slate = _slate("a")
    comment = build_status_comment(slate, "TASK123")
    assert "TASK123" in comment
    assert "2026-W22" in comment


# ---------- direct REST wrappers (cron/routine mode) ----------

from unittest.mock import patch  # noqa: E402  — local-only fixtures
from urllib.error import HTTPError  # noqa: E402

from tools.clickup import (  # noqa: E402
    CLICKUP_API_BASE,
    CLICKUP_API_TOKEN_ENV,
    _to_epoch_ms,
    add_tag_to_task,
    create_task,
    create_task_comment,
    get_task,
)


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *a: object) -> None:
        return None


def _captured_request_kwargs(req_obj) -> dict:
    return {
        "url": req_obj.full_url,
        "method": req_obj.get_method(),
        "headers": dict(req_obj.headers),
        "data": req_obj.data,
    }


def test_create_task_builds_correct_request(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        captured.update(_captured_request_kwargs(req))
        return _FakeResponse(b'{"id":"abc123","name":"hello"}')

    monkeypatch.setenv(CLICKUP_API_TOKEN_ENV, "pk_test_token")
    with patch("tools.clickup.urlopen", fake_urlopen):
        resp = create_task(
            "901326229295",
            name="[2026-05-12] hello",
            markdown_description="## body",
            assignees=[26221739],
            due_date="2026-05-12",
            tags=["fm-content-daily"],
        )

    assert resp == {"id": "abc123", "name": "hello"}
    assert captured["url"] == f"{CLICKUP_API_BASE}/list/901326229295/task"
    assert captured["method"] == "POST"
    assert captured["headers"]["Authorization"] == "pk_test_token"
    assert captured["headers"]["Content-type"] == "application/json"
    body = json.loads(captured["data"])
    assert body["name"] == "[2026-05-12] hello"
    assert body["markdown_description"] == "## body"
    assert body["assignees"] == [26221739]
    assert body["tags"] == ["fm-content-daily"]
    assert body["due_date_time"] is True
    assert isinstance(body["due_date"], int)
    assert body["due_date"] == _to_epoch_ms("2026-05-12")


def test_get_task_with_subtasks_query_param(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        captured.update(_captured_request_kwargs(req))
        return _FakeResponse(b'{"id":"86xx","status":{"status":"open","type":"open"}}')

    monkeypatch.setenv(CLICKUP_API_TOKEN_ENV, "pk_test")
    with patch("tools.clickup.urlopen", fake_urlopen):
        resp = get_task("86xx", include_subtasks=True)

    assert resp["id"] == "86xx"
    assert captured["url"] == f"{CLICKUP_API_BASE}/task/86xx?include_subtasks=true"
    assert captured["method"] == "GET"


def test_create_task_comment_payload(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        captured.update(_captured_request_kwargs(req))
        return _FakeResponse(b'{"id":"cm_1","hist_id":"h","date":"1"}')

    monkeypatch.setenv(CLICKUP_API_TOKEN_ENV, "pk_test")
    with patch("tools.clickup.urlopen", fake_urlopen):
        resp = create_task_comment("86ah3ywyh", comment_text="hello world")

    assert resp["id"] == "cm_1"
    assert captured["url"].endswith("/task/86ah3ywyh/comment")
    assert captured["method"] == "POST"
    body = json.loads(captured["data"])
    assert body["comment_text"] == "hello world"
    assert body["notify_all"] is False


def test_add_tag_to_task_no_body(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        captured.update(_captured_request_kwargs(req))
        return _FakeResponse(b"")  # ClickUp returns 200 with empty body

    monkeypatch.setenv(CLICKUP_API_TOKEN_ENV, "pk_test")
    with patch("tools.clickup.urlopen", fake_urlopen):
        resp = add_tag_to_task("86xx", "fm-content-daily")

    assert resp == {}
    assert captured["url"].endswith("/task/86xx/tag/fm-content-daily")
    assert captured["method"] == "POST"


def test_token_arg_overrides_env(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        captured.update(_captured_request_kwargs(req))
        return _FakeResponse(b'{}')

    monkeypatch.setenv(CLICKUP_API_TOKEN_ENV, "pk_env")
    with patch("tools.clickup.urlopen", fake_urlopen):
        get_task("86xx", api_token="pk_arg_override")

    assert captured["headers"]["Authorization"] == "pk_arg_override"


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv(CLICKUP_API_TOKEN_ENV, raising=False)
    try:
        get_task("86xx")
    except RuntimeError as e:
        assert CLICKUP_API_TOKEN_ENV in str(e)
    else:
        raise AssertionError("expected RuntimeError on missing token")


def test_http_error_surfaces_body(monkeypatch):
    err = HTTPError(
        url=f"{CLICKUP_API_BASE}/task/86xx",
        code=401,
        msg="Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    # Make .read() return error body
    err.read = lambda: b'{"err":"OAUTH_019","ECODE":"OAUTH_019"}'  # type: ignore[assignment]

    def fake_urlopen(req, timeout):  # noqa: ARG001
        raise err

    monkeypatch.setenv(CLICKUP_API_TOKEN_ENV, "pk_bad")
    with patch("tools.clickup.urlopen", fake_urlopen):
        try:
            get_task("86xx")
        except RuntimeError as e:
            msg = str(e)
            assert "401" in msg
            assert "OAUTH_019" in msg
        else:
            raise AssertionError("expected RuntimeError")


def test_to_epoch_ms_accepts_yyyy_mm_dd():
    ms = _to_epoch_ms("2026-05-12")
    assert isinstance(ms, int)
    # Sanity: 2026-05-12 23:59:59 UTC is in 2026
    assert ms > _to_epoch_ms("2026-01-01")
    assert ms < _to_epoch_ms("2027-01-01")


def test_to_epoch_ms_rejects_bad_string():
    try:
        _to_epoch_ms("not-a-date")
    except ValueError as e:
        assert "YYYY-MM-DD" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_to_epoch_ms_passthrough_int():
    assert _to_epoch_ms(1234567890123) == 1234567890123
